#!/usr/bin/env python3
"""
Steuerprogramm für Labornetzteil negative Spannung.
"""

from __future__ import print_function
import spidev
import time
import lgpio
import sys

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask

# --- Globale Konstanten ---
# Parameter der Strommessung (ACHTUNG: Messung muss negativ sein)
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor des Strommessverstärkers
KANAL_STROMMESSUNG = 4      # Kanal für die Strommessung

# DAC-Parameter (Negativ-Seite)
DAC_VREF = -10.75           # Referenzspannung des DAC in Volt.
CS_PIN = 22                 # Chip-Select-Pin für den DAC

# ADC-Parameter
READ_ALL_AVAILABLE = -1

# --- Hardware-Initialisierung ---
spi = spidev.SpiDev()
gpio_handle = None
hat = None

def setup_hardware():
    """Initialisiert SPI, GPIO und MCC 118."""
    global gpio_handle, hat
    try:
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00
        
        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN)
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)

        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        
        print("Hardware erfolgreich initialisiert.")
    except Exception as e:
        print(f"Fehler bei der Hardware-Initialisierung: {e}")
        sys.exit(1)

def spannung_zu_dac_wert_negativ(spannung, v_ref=DAC_VREF):
    """
    Rechnet eine gewünschte negative Spannung in einen 12-Bit DAC-Wert (0-4095) um.
    Spannungsbereich: v_ref (z.B. -10.75V) bis 0V.
    """
    if not (v_ref <= spannung <= 0):
        raise ValueError(f"Spannung muss zwischen {v_ref:.2f} V und 0 V liegen.")

    # Invertierte Skalierung: 0V -> 4095, -10.75V -> 0
    return int(round((spannung / v_ref) * 4095))

def write_dac_minus(value):
    """
    Schreibt einen 12-Bit-Wert (0-4095) an den DAC über SPI (für die Minus-Seite).
    """
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
        
    # Steuerbits für MCP4822: Channel B=1, Gain=1x, Shutdown=Normal
    control = 0b1101000000000000
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def start_live_messung_negativ():
    """
    Konfiguriert den MCC 118 und startet die kontinuierliche Live-Messung für die negative Seite.
    """
    channels = [KANAL_STROMMESSUNG]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    try:
        actual_scan_rate = hat.a_in_scan_actual_rate(num_channels, scan_rate)
        
        print('\nLive-Messung (negative Seite) läuft... (Drücke Strg+C zum Stoppen)\n')
        print(f'{"Scan-Rate":<15} {"Spannung (V)":<20} {"Strom (A)":<20}')
        print('---------------------------------------------------------')
        
        hat.a_in_scan_start(channel_mask, 0, scan_rate, options)
        
        read_and_display_data_negativ(hat, num_channels, actual_scan_rate)
        
    except HatError as err:
        print(f'\nFehler bei der Messung: {err}')
    except KeyboardInterrupt:
        print("\nMessung durch Benutzer unterbrochen.")
    finally:
        if hat and hat.status().running:
            hat.a_in_scan_stop()
            hat.a_in_scan_cleanup()
        print("Rückkehr zum Hauptmenü.")

def read_and_display_data_negativ(hat, num_channels, actual_scan_rate):
    """Liest kontinuierlich Daten vom MCC 118 und zeigt Spannung/Strom an."""
    read_request_size = READ_ALL_AVAILABLE
    timeout = 0.1

    while hat.status().running:
        read_result = hat.a_in_scan_read(read_request_size, timeout)

        if read_result.hardware_overrun or read_result.buffer_overrun:
            print('\n\nÜberlauf erkannt! Messung gestoppt.\n')
            break
            
        samples_read_per_channel = len(read_result.data) // num_channels
        if samples_read_per_channel > 0:
            latest_voltage = read_result.data[-1]
            # Strom auf der negativen Seite ist ebenfalls negativ
            current = -latest_voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)

            print(f'\r{actual_scan_rate:<15.2f} {latest_voltage:<20.5f} {current:<20.5f}', end='', flush=True)
            
        time.sleep(0.1)

def cleanup_hardware():
    """Setzt den DAC auf 0V und gibt alle Hardware-Ressourcen frei."""
    print("\n\nRäume auf und beende das Programm...")
    try:
        print("Setze DAC-Spannung auf 0V...")
        # DAC-Wert 4095 entspricht 0V auf der negativen Seite
        write_dac_minus(4095) 
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
        print("Ressourcen erfolgreich freigegeben.")
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")
    finally:
        print("Programm beendet.")

def main():
    """Hauptfunktion mit interaktivem Menü."""
    setup_hardware()
    
    try:
        while True:
            print("\n--- Hauptmenü ---")
            print(f"1. Spannung einstellen & Live-Messung starten ({DAC_VREF:.2f} V bis 0 V)")
            print("2. Programm beenden")
            choice = input("Bitte wählen Sie eine Option (1-2): ")

            if choice == '1':
                try:
                    spannung_str = input(f"Geben Sie die gewünschte Spannung ein ({DAC_VREF:.2f} V bis 0 V): ")
                    spannung = float(spannung_str)
                    dac_wert = spannung_zu_dac_wert_negativ(spannung)
                    write_dac_minus(dac_wert)
                    print(f"Spannung auf {spannung:.3f} V gesetzt (DAC-Wert: {dac_wert}).")
                    start_live_messung_negativ()
                except ValueError as e:
                    print(f"FEHLER: Ungültige Eingabe. {e}")
                except Exception as e:
                    print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

            elif choice == '2':
                print("Beende Programm auf Wunsch des Benutzers.")
                break
                
            else:
                print("Ungültige Auswahl. Bitte geben Sie 1 oder 2 ein.")
                
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nProgramm durch Strg+C unterbrochen.")
    finally:
        cleanup_hardware()

if __name__ == '__main__':
    main()
