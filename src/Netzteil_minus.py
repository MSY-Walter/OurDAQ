#!/usr/bin/env python3
"""
Steuerprogramm für Labornetzteil – Negative Spannung
- Automatische Kalibrierung (MCC118 Channel 0)
- Lineare Interpolation der Kalibrierpunkte
- Dauerhafte Stromüberwachung (MCC118 Channel 5) in mA
- Lineare Kalibrierkorrektur für MCC-Strommessung (Offset + Gain)
- Überstromschutz: bei > MAX_STROM_MA wird DAC sofort auf 0 gesetzt
"""

import spidev
import time
import lgpio
from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask

# ----------------- Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 27                 # Chip Select Pin
READ_ALL_AVAILABLE = -1

MAX_SPANNUNG_NEGATIV = -10  # minimaler Wert (negativ)
MAX_STROM_MA = 500.0       # Überstromschutz (mA)

# ----------------- Kalibrierdaten (Spannung <-> DAC) -----------------
kalibrier_tabelle = []  # Liste von (spannung_in_v, dac_wert)

# ----------------- Korrektur für MCC Strommessung -----------------
# Anfangswerte (analog zum positiven Beispiel, anpassen falls nötig)
corr_a = -0.279388
corr_b = 1.782842

# ----------------- Hardware initialisieren -----------------
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, CS_PIN)
lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

# ----------------- DAC Funktionen -----------------
def write_dac(value):
    """Schreibt 12-bit Wert 0..4095 an DAC (MCP49xx-kompatibel)."""
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    control = 0b1011000000000000
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte  = data & 0xFF
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

# ----------------- Kalibrierung (Spannungs-Mapping) -----------------
def kalibrieren(sp_step, settle):
    """
    Fährt DAC von 0..4095 mit Schritt sp_step, misst MCC118 Channel 0,
    und füllt kalibrier_tabelle mit (gemessene_spannung_V, dac_wert).
    Nur negative Spannungen werden gespeichert.
    """
    global kalibrier_tabelle
    kalibrier_tabelle.clear()
    print("\nStarte Kalibrierung (Negative Spannung)...")
    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)

    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert)
        time.sleep(settle)
        spannung = hat.a_in_read(0)  # Channel 0 misst Ausgangsspannung
        # Nur negative Spannungen speichern, andere ignorieren
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, dac_wert))
            print(f"  DAC {dac_wert:4d} -> {spannung:8.5f} V")
        else:
            print(f"  DAC {dac_wert:4d} -> {spannung:8.5f} V (nicht negativ, ignoriert)")

    # Sicherstellen, dass DAC 4095 auch dabei ist (falls sp_step nicht genau 1)
    if not any(dac == 4095 for _, dac in kalibrier_tabelle):
        print("Messe maximale DAC Spannung bei 4095...")
        write_dac(4095)
        time.sleep(settle)
        spannung = hat.a_in_read(0)
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, 4095))
            print(f"  DAC 4095 -> {spannung:8.5f} V")
        else:
            print(f"  DAC 4095 -> {spannung:8.5f} V (nicht negativ, ignoriert)")

    write_dac(0)
    kalibrier_tabelle.sort(key=lambda x: x[0])
    print("Kalibrierung (Negative Spannung) abgeschlossen.")
    print(f"Gespeicherte Punkte: {len(kalibrier_tabelle)}")

def spannung_zu_dac_interpoliert(ziel_spannung):
    """Lineare Interpolation zwischen Kalibrierpunkten -> DAC-Wert (int)."""
    if not kalibrier_tabelle:
        raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
    if ziel_spannung > 0:
        raise ValueError("Nur negative Spannungen erlaubt.")
    # Randbehandlung
    if ziel_spannung <= kalibrier_tabelle[0][0]:
        return kalibrier_tabelle[0][1]
    if ziel_spannung >= kalibrier_tabelle[-1][0]:
        return kalibrier_tabelle[-1][1]
    # Suche Intervall
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i+1]
        if u1 <= ziel_spannung <= u2:
            if u2 == u1:
                return d1
            # lineare Interpolation
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return int(round(dac))
    raise ValueError("Interpolation fehlgeschlagen.")

# ----------------- Stromkorrektur Hilfsfunktionen -----------------
def kalibriere_stromkorrektur(mcc_list_mA, true_list_mA):
    import numpy as np
    mcc = np.array(mcc_list_mA, dtype=float)
    true = np.array(true_list_mA, dtype=float)
    A = np.vstack([np.ones_like(mcc), mcc]).T
    a, b = np.linalg.lstsq(A, true, rcond=None)[0]
    return float(a), float(b)

def apply_strom_korrektur(i_mcc_mA):
    return corr_a + corr_b * i_mcc_mA

# ----------------- Stromüberwachung (kontinuierlich) -----------------
def strom_ueberwachung(max_strom_ma=MAX_STROM_MA):
    channels = [5]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)
    hat.a_in_scan_start(channel_mask, 0, scan_rate, options)

    print("\nStromüberwachung läuft – Strg+C zum Beenden")
    print("Shunt-Spannung (V)   MCC_mA   Korrigiert_mA")

    try:
        while True:
            read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.5)
            if len(read_result.data) >= num_channels:
                shunt_v = read_result.data[-1]
                current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA = apply_strom_korrektur(current_mcc_mA)
                print(f"\r{shunt_v:10.5f} V   {current_mcc_mA:7.2f} mA   {current_true_mA:9.2f} mA", end='')

                if current_true_mA > max_strom_ma:
                    write_dac(0)
                    print(f"\n\n⚠️  ÜBERSTROM: {current_true_mA:.1f} mA > {max_strom_ma:.1f} mA  -- DAC auf 0 gesetzt (Netzteil AUS).")
                    break
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nÜberwachung beendet (Strg+C).")

    finally:
        try:
            hat.a_in_scan_stop()
        except Exception:
            pass

# ----------------- Aufräumen -----------------
def cleanup():
    print("\nAufräumen...")
    try:
        write_dac(0)
    except Exception:
        pass
    try:
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
    except Exception:
        pass
    print("Beendet.")

# ----------------- Hauptprogramm -----------------
def main():
    try:
        # Automatische Kalibrierung am Programmstart
        kalibrieren(sp_step=32, settle=0.05)

        while True:
            print("\n--- Hauptmenü – Negatives Netzteil ---")
            print("1) Spannung einstellen (startet automatische Stromüberwachung)")
            print("2) Stromkorrektur neu berechnen (manuelle Eingabe von Messwerten)")
            print("3) Beenden")
            choice = input("Option: ").strip()

            if choice == "1":
                try:
                    ziel = float(input(f"Gewünschte Spannung ({MAX_SPANNUNG_NEGATIV:.2f} … 0 V): "))
                    if ziel > 0 or ziel < MAX_SPANNUNG_NEGATIV:
                        print(f"Bitte nur negative Spannung im Bereich {MAX_SPANNUNG_NEGATIV:.2f} bis 0 eingeben.")
                        continue
                    dac = spannung_zu_dac_interpoliert(ziel)
                    write_dac(dac)
                    print(f"Spannung eingestellt: {ziel:.3f} V  (DAC={dac})")
                    strom_ueberwachung()
                except Exception as e:
                    print(f"Fehler: {e}")

            elif choice == "2":
                print("Gib paarweise MCC_mA und True_mA ein (z. B.: '6 0.328'), eine Leerzeile beendet.")
                mccs = []
                trues = []
                while True:
                    line = input("mcc_mA true_mA > ").strip()
                    if not line:
                        break
                    try:
                        mcc_val, true_val = map(float, line.split())
                        mccs.append(mcc_val)
                        trues.append(true_val)
                    except Exception:
                        print("Ungültiges Format. Bitte 'mcc true' eingeben.")
                if len(mccs) >= 2:
                    a, b = kalibriere_stromkorrektur(mccs, trues)
                    global corr_a, corr_b
                    corr_a, corr_b = a, b
                    print(f"Neue Korrektur gesetzt: a={corr_a:.6f} mA, b={corr_b:.9f}")
                else:
                    print("Mindestens 2 Punkte erforderlich.")

            elif choice == "3":
                break

            else:
                print("Ungültige Auswahl.")

    except KeyboardInterrupt:
        print("\nProgramm durch Strg+C beendet.")
    finally:
        cleanup()

if __name__ == "__main__":
    main()