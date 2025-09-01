#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frequenzgang-Messung (MCC118)
Kanal 6 = Eingang (Funktionsgenerator)
Kanal 7 = Ausgang (Filter)
- Gain(dB) aus AC-RMS (DC entfernt)
- Phase via Lock-In (I/Q)
- Korrektur der Kanal-Scan-Verzögerung (Multiplexer Delay)
- Drei Plots: Gain, Phase, Vrms (In/Out)
"""

import numpy as np
import matplotlib.pyplot as plt
from daqhats import mcc118, OptionFlags

# --------- Utilities ---------

def ac_rms(x):
    """AC-RMS nach Entfernen des DC-Anteils; gibt (rms, x_ac) zurück."""
    x_ac = x - np.mean(x)
    return np.sqrt(np.mean(x_ac * x_ac)), x_ac

def lockin_phase_deg(signal_ac, fs, f_hz):
    """
    Phase bei f_hz mittels Lock-In (I/Q).
    Gibt Phase in Grad im Bereich (-180, 180] zurück.
    """
    N = len(signal_ac)
    t = np.arange(N) / fs
    c = np.cos(2*np.pi*f_hz*t)
    s = np.sin(2*np.pi*f_hz*t)
    # Minus beim Sinus entspricht exp(-jωt)
    I = (2.0/N) * np.dot(signal_ac, c)
    Q = (2.0/N) * np.dot(signal_ac, -s)
    phase = np.degrees(np.arctan2(Q, I))
    return (phase + 180.0) % 360.0 - 180.0

def wrap_deg(x):
    """Auf (-180, 180] wickeln."""
    return (x + 180.0) % 360.0 - 180.0

# --------- User Input ---------

start_freq = float(input("Startfrequenz (Hz): "))
stop_freq  = float(input("Stoppfrequenz (Hz): "))
steps      = int(input("Anzahl Zwischenschritte: "))
amplitude  = float(input("Amplitude (Vpp): "))
print(f"Frequenzbereich: {start_freq:.0f} Hz bis {stop_freq:.0f} Hz")

frequencies = np.linspace(start_freq, stop_freq, steps)

# --------- MCC118 Setup ---------

address = 0
hat = mcc118(address)

# ACHTUNG: Reihenfolge definiert Interleaving!
channels = [6, 7]                  # 6 = In, 7 = Out
channel_mask = sum(1 << ch for ch in channels)

fs = 50_000.0                      # Sample-Rate (pro Kanal-Scan)
periods = 10                       # ~10 Perioden je Frequenz
min_samples = 2048                 # Minimum je Kanal für stabile Werte
scan_options = OptionFlags.DEFAULT

# Ermitteln der Positionen von In/Out im Scan-Zyklus (0-basiert)
scan_order = sorted(channels)      # MCC118 scannt aufsteigend
pos = {ch: scan_order.index(ch) for ch in channels}
# Zeitversatz zwischen den beiden Kanälen (in Sekunden):
delta_samples = pos[7] - pos[6]    # >0: Ausgang wird nach Eingang gesampelt
dt = delta_samples / fs            # hier bei [6,7]: dt = 1/fs = 20 µs

# --------- Result-Speicher ---------

gain_db_list   = []
phase_deg_list = []
rms_in_list    = []
rms_out_list   = []

print("\n>>> Messe Frequenzgang...\n")

for f in frequencies:
    input(f"Stelle Funktionsgenerator auf {f:.2f} Hz, {amplitude} Vpp, sinus\nDrücke [Enter] wenn bereit...")

    # genügend Samples: mindestens min_samples, sonst ~periods Perioden
    samples_per_channel = int(max(min_samples, round(fs * periods / f)))

    # Scan
    hat.a_in_scan_start(channel_mask, samples_per_channel, fs, scan_options)
    result = hat.a_in_scan_read_numpy(samples_per_channel, timeout=5.0)
    hat.a_in_scan_stop()
    hat.a_in_scan_cleanup()

    # Interleaved: Kanäle in aufsteigender Reihenfolge -> 6, 7, 6, 7, ...
    data = result.data
    # Index 0 gehört zum kleinsten Kanal in channel_mask
    # Finde Offsets für ch6 & ch7 im Interleave
    offset_ch6 = scan_order.index(6)
    offset_ch7 = scan_order.index(7)

    in_sig  = data[offset_ch6::len(scan_order)]  # Kanal 6
    out_sig = data[offset_ch7::len(scan_order)]  # Kanal 7

    # AC-RMS
    rms_in,  in_ac  = ac_rms(in_sig)
    rms_out, out_ac = ac_rms(out_sig)

    # Gain dB (korrekt aus AC-RMS)
    eps = 1e-15
    gain_db = 20.0 * np.log10((rms_out + eps) / (rms_in + eps))

    # Phase (roh) via Lock-In
    phi_in  = lockin_phase_deg(in_ac,  fs, f)
    phi_out = lockin_phase_deg(out_ac, fs, f)
    phi_raw = wrap_deg(phi_out - phi_in)

    # Korrektur für Kanal-Scan-Verzögerung (Multiplexer Delay)
    # Ausgang wird dt Sekunden NACH Eingang gemessen -> zusätzliche scheinbare "Lag"-Phase:
    # phi_delay = +360° * f * dt (addieren, um die künstliche Verzögerung zu kompensieren)
    phi_delay = 360.0 * f * dt
    phi_corr  = wrap_deg(phi_raw - phi_delay)

    print(f"  → Effektivwert Eingang: {rms_in:.4f} V")
    print(f"  → Effektivwert Ausgang: {rms_out:.4f} V")
    print(f"  → Verstärkung: {gain_db:.2f} dB")
    print(f"  → Phase roh: {phi_raw:.2f}°, Delay-Korrektur: {phi_delay:.2f}°,  Phase korr.: {phi_corr:.2f}°\n")

    gain_db_list.append(gain_db)
    phase_deg_list.append(phi_corr)   # geplottet wird die korrigierte Phase
    rms_in_list.append(rms_in)
    rms_out_list.append(rms_out)

# --------- Plots ---------

plt.figure(figsize=(10, 8))

# 1) Gain (dB)
plt.subplot(3, 1, 1)
plt.semilogx(frequencies, gain_db_list, marker='o')
plt.ylabel("Verstärkung (dB)")
plt.title("Frequenzgang (Kanal 6 → Kanal 7)")
plt.grid(True, which='both', ls='--', alpha=0.5)

# 2) Phase (°), korrigiert
plt.subplot(3, 1, 2)
plt.semilogx(frequencies, phase_deg_list, marker='x')
plt.ylabel("Phasendifferenz (°)")
plt.grid(True, which='both', ls='--', alpha=0.5)

# 3) Vrms In/Out
plt.subplot(3, 1, 3)
plt.semilogx(frequencies, rms_in_list,  marker='o', label="Eingang Vrms (Ch6)")
plt.semilogx(frequencies, rms_out_list, marker='s', label="Ausgang Vrms (Ch7)")
plt.xlabel("Frequenz (Hz)")
plt.ylabel("Effektivwert (V)")
plt.legend()
plt.grid(True, which='both', ls='--', alpha=0.5)

plt.tight_layout()
plt.show()
