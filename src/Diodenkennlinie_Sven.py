from __future__ import print_function
import spidev
import time
import RPi.GPIO as GPIO
import matplotlib.pyplot as plt

from daqhats import mcc118, OptionFlags, HatIDs
from daqhats_utils import select_hat_device

CS_PIN = 22
MAX_DAC_VALUE = 4095
MAX_SPANNUNG = 10.5  # Volt (für DAC-Wert 4095)

# SPI einrichten
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

# GPIO Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)

def write_dac(value):
    assert 0 <= value <= MAX_DAC_VALUE
    control = 0
    control |= 0 << 15  # Channel A
    control |= 1 << 14  # Buffered
    control |= 0 << 13  # Gain = 2x (0)
    control |= 1 << 12  # Shutdown normal
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF

    print(f"Sende SPI: {data:016b} (0x{high_byte:02X} {low_byte:02X})")
    GPIO.output(CS_PIN, GPIO.LOW)
    spi.xfer2([high_byte, low_byte])
    GPIO.output(CS_PIN, GPIO.HIGH)

def main():
    print("### Diodenkennlinie Messung ###\n")

    try:
        r_serie = float(input("Wert des Serienwiderstands in Ohm (z.B. 100): "))
        anzahl_punkte = int(input("Anzahl der Spannungspunkte (mind. 15): "))
        if anzahl_punkte < 15:
            print("Mindestens 15 Punkte erforderlich – setze auf 15.")
            anzahl_punkte = 15

        spannung_max = float(input(f"Maximale Spannung in V (max {MAX_SPANNUNG} V): "))
        if spannung_max > MAX_SPANNUNG:
            print(f"Begrenze auf {MAX_SPANNUNG} V.")
            spannung_max = MAX_SPANNUNG

        # Verbindung zum MCC118
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        print(f"\nMCC 118 Gerät an Adresse {address} verbunden.")

        # Messdaten-Listen
        eingestellte_spannungen = []
        diodenspannungen = []
        stroeme = []

        print("\nMessung läuft...\n")
        for i in range(anzahl_punkte):
            spannung_dac = i * spannung_max / (anzahl_punkte - 1)
            dac_value = int((spannung_dac / MAX_SPANNUNG) * MAX_DAC_VALUE)
            write_dac(dac_value)
            time.sleep(0.05)

            # Spannung an Kanal 7 messen (Diode gegen Masse)
            spannung_diode = hat.a_in_read(7)

            # Strom berechnen
            strom = (spannung_dac - spannung_diode) / r_serie

            # Werte speichern
            eingestellte_spannungen.append(spannung_dac)
            diodenspannungen.append(spannung_diode)
            stroeme.append(strom)

            print(f"Eingestellte Spannung: {spannung_dac:.3f} V | "
                  f"Diode: {spannung_diode:.5f} V | "
                  f"Strom: {strom:.6f} A")

        # DAC wieder auf 0 setzen
        write_dac(0)

        print("\nMessung abgeschlossen. Erstelle Diagramm...")

        # Plotten
        plt.figure(figsize=(12, 5))

        plt.subplot(1, 2, 1)
        plt.plot(diodenspannungen, stroeme, marker='.')
        plt.xlabel("Spannung über Diode (V)")
        plt.ylabel("Strom durch Diode (A)")
        plt.title("Diodenkennlinie")
        plt.grid(True)

        plt.subplot(1, 2, 2)
        plt.plot(eingestellte_spannungen, stroeme, marker='.', color='orange')
        plt.xlabel("Eingestellte Spannung (V)")
        plt.ylabel("Strom durch Diode (A)")
        plt.title("Eingestellte Spannung vs. Strom")
        plt.xlim(0, spannung_max)
        plt.grid(True)

        plt.tight_layout()
        plt.show()

    except KeyboardInterrupt:
        print("\nMessung abgebrochen.")
        write_dac(0)
    except Exception as e:
        print("Fehler:", e)
        write_dac(0)
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()
