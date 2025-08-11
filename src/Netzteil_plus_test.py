#!/usr/bin/env python3
"""
Netzteil Plus Seite: Strombegrenzung und DAC Steuerung
"""

from __future__ import print_function
import spidev
import time
import lgpio

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, enum_mask_to_string, \
    chan_list_to_mask

# --- Globale Parameter und Initialisierung ---
READ_ALL_AVAILABLE = -1

# Parameter der Strommessung
SHUNT_WIDERSTAND = 0.1   # Ohm
VERSTAERKUNG = 69.0      # Verstärkungsfaktor

# GPIO und SPI Konfiguration
CS_PIN = 22
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, CS_PIN)
lgpio.gpio_write(gpio_handle, CS_PIN, 1) # CS Pin standardmäßig hoch (inaktiv)


def write_dac(value):
    """Sendet einen 12-Bit-Wert an den DAC über SPI."""
    assert 0 <= value <= 4095
    
    control = 0
    control |= 0 << 15 # Channel A=0 oder B=1
    control |= 1 << 14
    control |= 0 << 13 # Gain 0=2x
    control |= 1 << 12
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    # print(f"Sende SPI: {data:016b} (0x{high_byte:02X} {low_byte:02X})")
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)


def strombegrenzung():
    """Konfiguriert und startet die kontinuierliche Strommessung mit dem MCC 118."""
    channels = [4]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)

    samples_per_channel = 0
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    try:
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        print('\nAusgewähltes MCC 118 HAT Gerät bei Adresse', address)
        actual_scan_rate = hat.a_in_scan_actual_rate(num_channels, scan_rate)

        print('\nMCC 118 kontinuierliche Strommessung (Kanal 4)')
        print(f'    Scan-Rate (tatsächlich): {actual_scan_rate:.2f} Hz')
        print(f'    Verstärkung: {VERSTAERKUNG}')
        print(f'    Shunt-Widerstand: {SHUNT_WIDERSTAND} Ohm')
        
        input('\nDrücke ENTER zum Starten der Messung...')

        hat.a_in_scan_start(channel_mask, samples_per_channel, scan_rate, options)

        print('\nMessung läuft ... (Strg+C zum Beenden)\n')
        print('Spannung (V)      Strom (A)')
        print('--------------------------------')

        read_and_display_data(hat, num_channels)

    except (HatError, ValueError) as err:
        print(f'\nFehler: {err}')


def read_and_display_data(hat, num_channels):
    """Liest kontinuierlich Daten vom HAT, berechnet den Strom und zeigt ihn an."""
    timeout = 5.0

    while True:
        read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, timeout)

        if read_result.hardware_overrun or read_result.buffer_overrun:
            print('\n\nHardware- oder Pufferüberlauf erkannt. Messung gestoppt.\n')
            break

        samples_read = len(read_result.data)
        if samples_read > 0:
            # Nur den letzten Messwert anzeigen für eine saubere Ausgabe
            last_voltage = read_result.data[-1]
            current = last_voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)
            
            # \r (Carriage Return) bewegt den Cursor an den Zeilenanfang
            print(f'\r{last_voltage:10.5f} V    {current:10.5f} A', end='')
            stdout.flush()
        
        time.sleep(0.1)


def main():
    """Hauptprogramm: Fragt nach dem DAC-Wert und startet die Überwachung."""
    try:
        # Benutzer nach dem gewünschten DAC-Wert fragen
        while True:
            try:
                # Hier die Frage auf Deutsch, wie im Originalcode-Stil
                prompt = "Bitte gewünschten DAC-Wert eingeben (0-4095), oder 'q' zum Beenden: "
                user_input = input(prompt)
                
                if user_input.lower() == 'q':
                    print("Programm wird beendet.")
                    return

                dac_value = int(user_input)
                if 0 <= dac_value <= 4095:
                    break  # Gültiger Wert, Schleife verlassen
                else:
                    print("Fehler: Der Wert muss zwischen 0 und 4095 liegen.")
            except ValueError:
                print("Fehler: Bitte eine gültige Ganzzahl eingeben.")
        
        # DAC auf den vom Benutzer gewählten Wert einstellen
        print(f"\nStelle DAC auf {dac_value} ein...")
        write_dac(dac_value)
        
        # Dauerhafte Strommessung starten
        strombegrenzung()

    except KeyboardInterrupt:
        print("\n\nBenutzerabbruch erkannt. Räume auf...")
    except Exception as e:
        print(f"\nEin unerwarteter Fehler ist aufgetreten: {e}")
    finally:
        # Aufräumarbeiten: DAC auf 0 setzen und Ressourcen freigeben
        print("Setze DAC auf 0 und schließe Ressourcen.")
        write_dac(0)
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
        print("Aufräumen abgeschlossen. Auf Wiedersehen!")


if __name__ == '__main__':
    main()