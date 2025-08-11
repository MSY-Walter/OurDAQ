#!/usr/bin/env python3
"""
Diodenkennlinie Messung
"""

from __future__ import print_function
import spidev
import time
import lgpio
import matplotlib.pyplot as plt
from daqhats import mcc118, OptionFlags, HatIDs
from daqhats_utils import select_hat_device

CS_PIN = 22
MAX_DAC_VALUE = 4095
# MAX_SPANNUNG = 10.5  # Veraltet, wird jetzt dynamisch gemessen

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
    """
    DAC-Wert schreiben mit lgpio
    """
    global gpio_handle
    
    assert 0 <= value <= MAX_DAC_VALUE
    
    control = 0
    control |= 0 << 15  # Channel A
    control |= 1 << 14  # Buffered
    control |= 0 << 13  # Gain = 2x (0)
    control |= 1 << 12  # Shutdown normal
    
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    # print(f"Sende SPI: {data:016b} (0x{high_byte:02X} {low_byte:02X})") # Deaktiviert für saubere Ausgabe
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def cleanup_gpio():
    """
    GPIO-Cleanup mit lgpio
    """
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
        print("GPIO-Cleanup abgeschlossen (lgpio)")
    except Exception as e:
        print(f"Cleanup-Fehler: {e}")

def main():
    print("### Diodenkennlinie Messung (lgpio) ###\n")
    
    try:
        # Verbindung zum MCC118 herstellen, bevor Benutzereingaben abgefragt werden
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        print(f"\nMCC 118 Gerät an Adresse {address} verbunden.")

        # NEU: Reale maximale Spannung von Kanal 0 messen
        # Diese Spannung dient als Referenz für die DAC-Berechnungen.
        # Es wird davon ausgegangen, dass hier die maximale Versorgungsspannung des DAC anliegt.
        print("Messe maximale Referenzspannung von Kanal 0...")
        max_referenzspannung = hat.a_in_read(0)
        print(f"-> Gemessene Referenzspannung: {max_referenzspannung:.4f} V\n")

        # Benutzereingaben abfragen
        r_serie = float(input("Wert des Serienwiderstands in Ohm (z.B. 100): "))
        anzahl_punkte = int(input("Anzahl der Spannungspunkte (mind. 15): "))
        
        if anzahl_punkte < 15:
            print("Mindestens 15 Punkte erforderlich – setze auf 15.")
            anzahl_punkte = 15
            
        # GEÄNDERT: Maximale Spannung basierend auf der gemessenen Referenzspannung abfragen
        spannung_max = float(input(f"Maximale Sweep-Spannung in V (max. {max_referenzspannung:.2f} V): "))
        if spannung_max > max_referenzspannung:
            print(f"Eingabe zu hoch. Begrenze auf {max_referenzspannung:.2f} V.")
            spannung_max = max_referenzspannung
        
        # Messdaten-Listen
        eingestellte_spannungen = []
        diodenspannungen = []
        stroeme = []
        
        print("\nMessung läuft...\n")
        
        for i in range(anzahl_punkte):
            # Dies ist die *gewünschte* Spannung am Ausgang des DAC für diesen Schritt
            spannung_dac_soll = i * spannung_max / (anzahl_punkte - 1)
            
            # GEÄNDERT: DAC-Wert basierend auf der real gemessenen Referenzspannung berechnen
            dac_value = int((spannung_dac_soll / max_referenzspannung) * MAX_DAC_VALUE)
            
            write_dac(dac_value)
            time.sleep(5)
            
            # Spannung an Kanal 7 messen (Spannung über der Diode)
            spannung_diode = hat.a_in_read(7)
            
            # Strom berechnen. HINWEIS: Dies verwendet den theoretischen Sollwert (spannung_dac_soll).
            # Für eine höhere Genauigkeit könnte man die tatsächliche Spannung vor dem Widerstand
            # (z.B. an Kanal 0) in jeder Schleife neu messen.
            strom = (spannung_dac_soll - spannung_diode) / r_serie
            
            # Werte speichern
            eingestellte_spannungen.append(spannung_dac_soll)
            diodenspannungen.append(spannung_diode)
            stroeme.append(strom)
            
            print(f"Soll-Spannung: {spannung_dac_soll:.3f} V | "
                  f"Diode: {spannung_diode:.5f} V | "
                  f"Strom: {strom:.6f} A")
        
        write_dac(0)
        
        print("\nMessung abgeschlossen. Erstelle Diagramm...")
        
        plt.figure(figsize=(12, 5))
        
        plt.subplot(1, 2, 1)
        plt.plot(diodenspannungen, stroeme, marker='.')
        plt.xlabel("Spannung über Diode (V)")
        plt.ylabel("Strom durch Diode (A)")
        plt.title("Diodenkennlinie")
        plt.grid(True)
        
        plt.subplot(1, 2, 2)
        plt.plot(eingestellte_spannungen, stroeme, marker='.', color='orange')
        plt.xlabel("Eingestellte Soll-Spannung (V)")
        plt.ylabel("Strom durch Diode (A)")
        plt.title("Soll-Spannung vs. Strom")
        plt.xlim(0, spannung_max)
        plt.grid(True)
        
        plt.tight_layout()
        plt.show()
        
    except KeyboardInterrupt:
        print("\nMessung abgebrochen.")
    except Exception as e:
        print("Fehler:", e)
    finally:
        cleanup_gpio()

if __name__ == "__main__":
    main()