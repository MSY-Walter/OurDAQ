#!/usr/bin/env python3
"""
Diodenkennlinie Messung
"""

from __future__ import print_function
import spidev
import time
import lgpio
import matplotlib.pyplot as plt
from daqhats import mcc118, HatIDs
from daqhats_utils import select_hat_device

CS_PIN = 22
MAX_DAC_VALUE = 4095

gpio_handle = None

# SPI einrichten
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

# GPIO Setup mit lgpio
gpio_handle = lgpio.gpiochip_open(0)
if gpio_handle < 0:
    raise Exception("Fehler beim Öffnen des GPIO Chips")

ret = lgpio.gpio_claim_output(gpio_handle, CS_PIN, lgpio.SET_PULL_NONE)
if ret < 0:
    raise Exception(f"Fehler beim Konfigurieren von GPIO Pin {CS_PIN}")

lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def write_dac(value):
    """DAC-Wert schreiben"""
    global gpio_handle
    assert 0 <= value <= MAX_DAC_VALUE
    control = 0
    control |= 0 << 15
    control |= 1 << 14
    control |= 0 << 13
    control |= 1 << 12
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def cleanup_gpio():
    """GPIO-Cleanup"""
    global gpio_handle
    try:
        write_dac(0)
    except:
        pass
    try:
        if gpio_handle is not None:
            lgpio.gpio_free(gpio_handle, CS_PIN)
            lgpio.gpiochip_close(gpio_handle)
            gpio_handle = None
        spi.close()
        print("GPIO-Cleanup abgeschlossen")
    except Exception as e:
        print(f"Cleanup-Fehler: {e}")

def main():
    print("### Diodenkennlinie Messung ###\n")
    
    try:
        # MCC118 Verbindung
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        print(f"MCC 118 Gerät an Adresse {address} verbunden.")

        # Kalibrierung maximale DAC-Spannung
        print("Kalibriere maximale DAC-Spannung an Kanal 7...")
        write_dac(MAX_DAC_VALUE)
        time.sleep(0.5)
        gemessene_max_spannung = hat.a_in_read(7)
        write_dac(0)
        print(f"Gemessene maximale Spannung (Referenz): {gemessene_max_spannung:.4f} V")

        r_serie = float(input("Wert des Serienwiderstands in Ohm: "))
        anzahl_punkte = int(input("Anzahl der Spannungspunkte: "))

        spannung_max = float(input(f"Maximale Spannung in V (max {gemessene_max_spannung:.2f} V): "))
        if spannung_max > gemessene_max_spannung:
            print(f"Begrenze auf {gemessene_max_spannung:.2f} V.")
            spannung_max = gemessene_max_spannung

        # DAC-Wert, der genau spannung_max liefert
        dac_max_wert = int(MAX_DAC_VALUE * spannung_max / gemessene_max_spannung)

        # Listen für Messwerte
        eingestellte_spannungen = []
        diodenspannungen = []
        stroeme = []

        print("\nMessung läuft...\n")

        for i in range(anzahl_punkte):
            # DAC linear von 0 bis dac_max_wert verteilen
            dac_value = int(i * dac_max_wert / (anzahl_punkte - 1))
            #print(dac_value)
            write_dac(dac_value)
            #print(dac_value)
            time.sleep(2.0)

            spannung_diode = hat.a_in_read(6)
            spannung_gesamt = hat.a_in_read(7)
            strom = ((spannung_gesamt - spannung_diode) / r_serie) * 1000  # mA

            # Geplante Spannung für Plot (0 bis spannung_max)
            spannung_dac = spannung_max * i / (anzahl_punkte - 1)
            print(spannung_dac)

            eingestellte_spannungen.append(spannung_dac)
            diodenspannungen.append(spannung_diode)
            stroeme.append(strom)

            print(f"Eingestellte Spannung: {spannung_dac:.3f} V | "
                  f"Gemessene Spannung: {spannung_gesamt:.5f} V | "
                  f"Diode: {spannung_diode:.5f} V | Strom: {strom:.3f} mA")

        write_dac(0)

        # Diagramm erstellen
        plt.figure(figsize=(12,5))

        plt.subplot(1,2,1)
        plt.plot(diodenspannungen, stroeme, marker='.')
        plt.xlabel("Spannung über Diode (V)")
        plt.ylabel("Strom durch Diode (mA)")
        plt.title("Diodenkennlinie")
        plt.grid(True)

        plt.subplot(1,2,2)
        plt.plot(eingestellte_spannungen, stroeme, marker='.', color='orange')
        plt.xlabel("Eingestellte Spannung (V)")
        plt.ylabel("Strom durch Diode (mA)")
        plt.title("Eingestellte Spannung vs. Strom")
        plt.xlim(0, spannung_max)
        plt.grid(True)

        plt.tight_layout()
        plt.show()

    except KeyboardInterrupt:
        print("Messung abgebrochen.")
    except Exception as e:
        print("Fehler:", e)
    finally:
        cleanup_gpio()

if __name__ == "__main__":
    main()
