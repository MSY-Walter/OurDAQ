#!/usr/bin/env python3
"""
Steuerprogramm für Labornetzteil negative Spannung.
"""

from __future__ import print_function
import spidev
import time
import lgpio

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, enum_mask_to_string, \
    chan_list_to_mask

# --- Globale Konstanten ---
# Parameter der Strommessung
SHUNT_WIDERSTAND = 0.1   # Ohm
VERSTAERKUNG = 69.0      # Verstärkungsfaktor des Strommessverstärkers

# DAC-Parameter
# Dies ist die positive Referenzspannung des DAC.
# Die resultierende Ausgangsspannung ist von -DAC_VREF bis 0 V.
DAC_VREF = 10.75
CS_PIN = 22              # Chip-Select-Pin für den DAC

# ADC-Parameter
READ_ALL_AVAILABLE = -1
CURSOR_BACK_2 = '\x1b[2D'
ERASE_TO_END_OF_LINE = '\x1b[0K'

# --- Hardware-Initialisierung ---
# SPI für DAC
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

# lgpio für Chip Select
gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, CS_PIN)
lgpio.gpio_write(gpio_handle, CS_PIN, 1) # CS Pin initial auf HIGH (inaktiv)


def spannung_zu_dac_wert(spannung, v_ref=DAC_VREF):
    """
    Rechnet eine gewünschte negative Spannung in einen 12-Bit DAC-Wert (0-4095) um.
    Wirft einen ValueError, wenn die Spannung außerhalb des gültigen Bereichs liegt.
    Annahme: Die positive DAC-Spannung wird extern invertiert.
    """
    if not (-v_ref <= spannung <= 0):
        raise ValueError(f"Spannung muss zwischen -{v_ref:.2f} V und 0 V liegen.")
    
    # Wandelt die negative Spannung in einen positiven Wert für den DAC um.
    # z.B. eine Anforderung von -5V benötigt eine DAC-Ausgabe von +5V.
    positive_spannung = abs(spannung)
    return int((positive_spannung / v_ref) * 4095)

def write_dac(value):
    """
    Schreibt einen 12-Bit-Wert (0-4095) an den DAC über SPI.
    """
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    
    # Steuerbits für MCP4921 (Beispielkonfiguration)
    control = 0b0011000000000000  # Vref gepuffert, Gain=1x, Ausgang aktiv
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    # Senden der Daten
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)  # Chip Select aktivieren (LOW)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # Chip Select deaktivieren (HIGH)

def strombegrenzung_messen():
    """
    Konfiguriert den MCC 118 und startet die kontinuierliche Strommessung auf Kanal 5.
    Die Messung läuft, bis der Benutzer Strg+C drückt.
    """
    channels = [5]  # Kanal 5 für Strommessung
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    try:
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        print(f'\nAusgewähltes MCC 118 HAT Gerät bei Adresse {address}')
        actual_scan_rate = hat.a_in_scan_actual_rate(num_channels, scan_rate)

        print('\nKonfiguriere MCC 118 für kontinuierliche Strommessung...')
        print(f'    Kanal:                  {channels[0]}')
        print(f'    Scan-Rate (gewünscht):  {scan_rate:.2f} Hz')
        print(f'    Scan-Rate (tatsächlich): {actual_scan_rate:.2f} Hz')
        print(f'    Verstärkung:            {VERSTAERKUNG}')
        print(f'    Shunt-Widerstand:       {SHUNT_WIDERSTAND} Ohm')

        input('\nDrücke ENTER zum Starten der Messung...')
        
        hat.a_in_scan_start(channel_mask, 0, scan_rate, options)
        print('\nMessung läuft... (Drücke Strg+C zum Stoppen und Zurückkehren zum Menü)\n')
        print('Samples Read    Scan Count       Spannung (V)      Strom (A)')
        print('-----------------------------------------------------------------')
        
        read_and_display_data(hat, num_channels)

    except (HatError, ValueError) as err:
        print(f'\nFehler bei der Initialisierung des MCC 118: {err}')
    except KeyboardInterrupt:
        # Fängt Strg+C ab, um die Messung sauber zu beenden
        print("\nMessung durch Benutzer unterbrochen.")
        if 'hat' in locals():
            hat.a_in_scan_stop()
    finally:
        if 'hat' in locals() and hat.is_scan_running():
            hat.a_in_scan_stop()
        print("Rückkehr zum Hauptmenü.")


def read_and_display_data(hat, num_channels):
    """Liest kontinuierlich Daten vom MCC 118 und zeigt Spannung/Strom an."""
    total_samples_read = 0
    read_request_size = READ_ALL_AVAILABLE
    timeout = 5.0

    while True:
        try:
            read_result = hat.a_in_scan_read(read_request_size, timeout)

            if read_result.hardware_overrun:
                print('\n\nHardwareüberlauf erkannt! Messung gestoppt.\n')
                break
            elif read_result.buffer_overrun:
                print('\n\nPufferüberlauf erkannt! Messung gestoppt.\n')
                break

            samples_read_per_channel = len(read_result.data) // num_channels
            if samples_read_per_channel > 0:
                total_samples_read += samples_read_per_channel
                
                # Nimm den letzten Messwert des Pakets für die Anzeige
                latest_voltage = read_result.data[-1]
                current = latest_voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)

                print(f'\r{samples_read_per_channel:12d}    {total_samples_read:12d}    '
                      f'{latest_voltage:10.5f} V    {current:10.5f} A'
                      f'{ERASE_TO_END_OF_LINE}', end='')
                stdout.flush()
            
            time.sleep(0.1)
        except KeyboardInterrupt:
            raise # Erneut auslösen, um von der äußeren Schleife gefangen zu werden

def cleanup():
    """
    Setzt den DAC auf 0V und gibt alle Hardware-Ressourcen frei.
    """
    print("\n\nRäume auf und beende das Programm...")
    try:
        print("Setze Ausgangsspannung auf 0V...")
        write_dac(0)  # DAC auf 0V -> Ausgang auf 0V
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
        print("Ressourcen erfolgreich freigegeben.")
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")
    finally:
        print("Programm beendet.")


def main():
    """
    Hauptfunktion mit interaktivem Menü.
    """
    try:
        while True:
            print("\n--- Hauptmenü (Negative Spannung) ---")
            print("1. Spannung einstellen")
            print("2. Strommessung starten (Kanal 5)")
            print("3. Programm beenden")
            choice = input("Bitte wählen Sie eine Option (1-3): ")

            if choice == '1':
                try:
                    spannung_str = input(f"Geben Sie die gewünschte Spannung ein (-{DAC_VREF:.2f} V bis 0 V): ")
                    spannung = float(spannung_str)
                    dac_wert = spannung_zu_dac_wert(spannung)
                    write_dac(dac_wert)
                    print(f"Spannung auf {spannung:.3f} V gesetzt (DAC-Wert: {dac_wert}).")
                except ValueError as e:
                    print(f"FEHLER: Ungültige Eingabe. {e}")
                except Exception as e:
                    print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

            elif choice == '2':
                strombegrenzung_messen()

            elif choice == '3':
                print("Beende Programm auf Wunsch des Benutzers.")
                break
            
            else:
                print("Ungültige Auswahl. Bitte geben Sie 1, 2 oder 3 ein.")
            
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nProgramm durch Strg+C unterbrochen.")
    finally:
        cleanup()


if __name__ == '__main__':
    main()