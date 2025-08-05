#!/usr/bin/env python3
"""
Filterkennlinie Messung Sven
"""

from daqhats import mcc118, OptionFlags
from ctypes import c_uint32
import numpy as np
import matplotlib.pyplot as plt

def round_down_to_10(x):
    return (x // 10) * 10

def round_up_to_10(x):
    return ((x + 9) // 10) * 10

# Benutzerabfrage mit Rundung auf Vielfache von 10
start_freq = int(float(input("Startfrequenz (Hz): ")))
stop_freq = int(float(input("Stoppfrequenz (Hz): ")))

start_freq = round_down_to_10(start_freq)
stop_freq = round_up_to_10(stop_freq)

print(f"Frequenzbereich wird angepasst auf {start_freq} Hz bis {stop_freq} Hz (glatt durch 10 teilbar)")

steps = int(input("Anzahl Zwischenschritte: "))
signal_type = input("Signalart (sinus, rechteck, dreieck): ").strip().lower()
amplitude = float(input("Amplitude (Vpp): "))

# Frequenzliste erzeugen und auf Vielfache von 10 runden
frequencies = np.linspace(start_freq, stop_freq, steps)
frequencies = np.round(frequencies / 10) * 10
frequencies = np.unique(frequencies).astype(int)  # Duplikate entfernen

# MCC 118 Setup
address = 0
hat = mcc118(address)
channels = [6, 7]

# Bitmaske manuell berechnen
channel_mask = 0
for ch in channels:
    channel_mask |= (1 << ch)

sample_rate = 50000.0
samples_per_channel = int(5000)
scan_options = OptionFlags.DEFAULT

print("DEBUG TYPES:")
print(f"channel_mask = {channel_mask} ({type(channel_mask)})")
print(f"sample_rate = {sample_rate} ({type(sample_rate)})")
print(f"samples_per_channel = {samples_per_channel} ({type(samples_per_channel)})")
print(f"scan_options = {scan_options} ({type(scan_options)})")

# Ergebnislisten
phase_results = []
gain_results = []

def get_phase(signal, sr, freq):
    N = len(signal)
    window = np.hanning(N)
    fft = np.fft.fft(signal * window)
    freqs = np.fft.fftfreq(N, 1/sr)
    idx = np.argmin(np.abs(freqs - freq))
    return np.angle(fft[idx]), np.abs(fft[idx])

for freq in frequencies:
    print(f"\n>>> Stelle den Funktionsgenerator auf {freq:.2f} Hz, {amplitude} Vpp, {signal_type}")
    input("Drücke [Enter], wenn bereit zur Messung...")

    # Messung starten
    hat.a_in_scan_start(channel_mask, samples_per_channel, sample_rate, scan_options)
    result = hat.a_in_scan_read_numpy(samples_per_channel, timeout=5.0)
    hat.a_in_scan_stop()
    hat.a_in_scan_cleanup()

    data = result.data
    in_sig = data[::2]   # Kanal 6 = Eingang FG
    out_sig = data[1::2] # Kanal 7 = Filterausgang

    phase_in, amp_in = get_phase(in_sig, sample_rate, freq)
    phase_out, amp_out = get_phase(out_sig, sample_rate, freq)

    phase_diff = np.rad2deg((phase_out - phase_in + np.pi) % (2 * np.pi) - np.pi)
    gain = 20 * np.log10(amp_out / amp_in) if amp_in > 0 else -np.inf

    print(f"  → Phasendifferenz: {phase_diff:.2f}°")
    print(f"  → Verstärkung: {gain:.2f} dB")

    # Effektivwerte berechnen (RMS)
    rms_in = np.sqrt(np.mean(np.square(in_sig)))
    rms_out = np.sqrt(np.mean(np.square(out_sig)))
    print(f"  → Effektivwert Eingang: {rms_in:.4f} V")
    print(f"  → Effektivwert Ausgang: {rms_out:.4f} V")

    phase_results.append(phase_diff)
    gain_results.append(gain)

# Ergebnisse plotten
plt.figure(figsize=(10, 6))

plt.subplot(2, 1, 1)
plt.semilogx(frequencies, gain_results, marker='o')
plt.ylabel("Verstärkung (dB)")
plt.title("Frequenzgang")
plt.grid(True)

plt.subplot(2, 1, 2)
plt.semilogx(frequencies, phase_results, marker='x', color='orange')
plt.xlabel("Frequenz (Hz)")
plt.ylabel("Phasendifferenz (°)")
plt.grid(True)

plt.tight_layout()
plt.show()
