#!/usr/bin/env python3
"""
Funktionsgenerator mit AD9833
"""

import lgpio
import time

# Konfiguration der GPIO-Pins (BCM-Nummerierung)
# FNC/FSYNC-Pin des AD9833
FNC_PIN = 25

# SPI-Konfiguration
SPI_DEVICE = 0  # SPI-Bus 0
SPI_CHANNEL = 0 # Chip Select 0
SPI_SPEED = 1000000  # 1 MHz
SPI_FLAGS = 0

# AD9833 Register und Befehle
CONTROL_REG = 0x2000
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000

# Wellenform-Definitionen
SINE_WAVE = 0x2000
TRIANGLE_WAVE = 0x2002
SQUARE_WAVE = 0x2028

# Taktfrequenz des Oszillators auf dem AD9833-Modul
MASTER_CLOCK_FREQ = 25000000.0  # 25 MHz

def write_data(handle, fnc_handle, data):
    """Sendet ein 16-Bit-Wort an den AD9833."""
    # FSYNC auf LOW setzen, um die Übertragung zu starten
    lgpio.gpio_write(fnc_handle, FNC_PIN, 0)
    time.sleep(0.00001)

    # Daten senden (High-Byte und Low-Byte)
    tx_data = [(data >> 8) & 0xFF, data & 0xFF]
    lgpio.spi_write(handle, tx_data)

    # FSYNC auf HIGH setzen, um die Übertragung zu beenden
    lgpio.gpio_write(fnc_handle, FNC_PIN, 1)
    time.sleep(0.00001)

def set_frequency(handle, fnc_handle, frequency):
    """Berechnet und setzt die Frequenz des AD9833."""
    if frequency > MASTER_CLOCK_FREQ / 2:
        frequency = MASTER_CLOCK_FREQ / 2
    if frequency < 0:
        frequency = 0

    # Frequenzwort berechnen
    freq_word = int(round((frequency * (2**28)) / MASTER_CLOCK_FREQ))

    # Frequenzwort in zwei 14-Bit-Teile aufteilen
    msb = (freq_word >> 14) & 0x3FFF
    lsb = freq_word & 0x3FFF

    # Kontrollregister schreiben (B28 = 1, um Frequenzregister zu aktualisieren)
    write_data(handle, fnc_handle, CONTROL_REG | 0x2000)

    # LSB und MSB des Frequenzregisters schreiben
    write_data(handle, fnc_handle, lsb | FREQ0_REG)
    write_data(handle, fnc_handle, msb | FREQ0_REG)

def set_waveform(handle, fnc_handle, waveform):
    """Setzt die Wellenform des AD9833."""
    write_data(handle, fnc_handle, waveform)

def main():
    """Hauptprogramm zur Abfrage und Konfiguration des AD9833."""
    h = None
    fnc_handle = None
    try:
        # GPIO-Chip für FNC-Pin öffnen
        fnc_handle = lgpio.gpiochip_open(0)
        # FNC-Pin als Ausgang konfigurieren und auf HIGH setzen
        lgpio.gpio_claim_output(fnc_handle, FNC_PIN)
        lgpio.gpio_write(fnc_handle, FNC_PIN, 1)

        # SPI-Gerät öffnen
        h = lgpio.spi_open(SPI_DEVICE, SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)

        # AD9833 initialisieren (Reset)
        write_data(h, fnc_handle, 0x2100)
        time.sleep(0.01)

        while True:
            # Benutzereingabe für die Wellenform
            print("\nBitte wählen Sie eine Wellenform:")
            print("1: Sinuswelle")
            print("2: Dreieckswelle")
            print("3: Rechteckwelle")
            wahl = input("Ihre Wahl (1-3): ")

            waveform = 0
            if wahl == '1':
                waveform = SINE_WAVE
            elif wahl == '2':
                waveform = TRIANGLE_WAVE
            elif wahl == '3':
                waveform = SQUARE_WAVE
            else:
                print("Ungültige Eingabe. Bitte versuchen Sie es erneut.")
                continue

            # Benutzereingabe für die Frequenz
            try:
                frequenz = float(input("Bitte geben Sie die Frequenz in Hz ein: "))
            except ValueError:
                print("Ungültige Frequenzeingabe. Bitte geben Sie eine Zahl ein.")
                continue

            # AD9833 konfigurieren
            set_waveform(h, fnc_handle, waveform)
            set_frequency(h, fnc_handle, frequenz)

            print(f"AD9833 konfiguriert für eine Frequenz von {frequenz} Hz.")

    except (KeyboardInterrupt, SystemExit):
        print("\nProgramm wird beendet.")
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
    finally:
        # Ressourcen freigeben
        if h is not None:
            lgpio.spi_close(h)
        if fnc_handle is not None:
            lgpio.gpiochip_close(fnc_handle)

if __name__ == "__main__":
    main()