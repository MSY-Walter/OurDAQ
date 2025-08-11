#!/usr/bin/env python3
"""
Steuerprogramm für Labornetzteil negative Spannung.
"""

from __future__ import print_function
import spidev
import time
import lgpio
import atexit

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask

# --- Globale Konstanten ---
# Parameter der Strommessung
SHUNT_WIDERSTAND = 0.1   # Ohm
VERSTAERKUNG = 69.0      # Verstärkungsfaktor des Strommessverstärkers
MESS_KANAL = 5           # ADC-Kanal für die Strommessung (geändert auf 5)

# DAC-Parameter
DAC_VREF = 10.75         # Referenzspannung des DAC in Volt
CS_PIN = 22              # Chip-Select-Pin für den DAC

# ADC-Parameter
READ_ALL_AVAILABLE = -1
ERASE_TO_END_OF_LINE = '\x1b[0K'

# --- Globale Variablen für die Hardware ---
spi = None
gpio_handle = None
hat = None

def hardware_init():
    """Initialisiert die gesamte Hardware (SPI, GPIO, DAC, ADC)."""
    global spi, gpio_handle, hat
    try:
        # SPI für DAC
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00

        # lgpio für Chip Select
        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN)
        lgpio.gpio_write(gpio_handle, CS_PIN, 1) # CS Pin initial auf HIGH (inaktiv)

        # ADC (MCC 118)
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        print(f'MCC 118 HAT Gerät bei Adresse {address} ausgewählt.')

        # Registriert die Cleanup-Funktion, die bei Programmende ausgeführt wird
        atexit.register(cleanup)
        return True

    except (HatError, lgpio.error, FileNotFoundError) as err:
        print(f"Fehler bei der Hardware-Initialisierung: {err}")
        return False

def cleanup():
    """Setzt DAC auf 0V und gibt alle Hardware-Ressourcen frei."""
    print("\n\nRäume auf und beende das Programm...")
    global hat, spi, gpio_handle
    try:
        if hat and hat.is_scan_running():
            hat.a_in_scan_stop()
        if spi:
            # Sicherheitsabschaltung: DAC auf 0V setzen
            print("Setze DAC-Spannung auf 0V...")
            write_dac(0)
            spi.close()
        if gpio_handle is not None:
            lgpio.gpiochip_close(gpio_handle)
        print("Ressourcen erfolgreich freigegeben.")
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")
    finally:
        print("Programm beendet.")

def spannung_zu_dac_wert(spannung, v_ref=DAC_VREF):
    """Rechnet eine Spannung in einen 12-Bit DAC-Wert um."""
    if not (0 <= spannung <= v_ref):
        raise ValueError(f"Spannung muss zwischen 0 und {v_ref:.2f} V liegen.")
    return int((spannung / v_ref) * 4095)

def write_dac(value):
    """Schreibt einen 12-Bit-Wert an den DAC über SPI."""
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    
    # Steuerbits: Channel A, Buffered, Gain=1x, Shutdown=aktiv
    control = 0b0011000000000000 
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)  # Chip Select aktivieren (LOW)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # Chip Select deaktivieren (HIGH)

def start_monitoring():
    """Startet die kontinuierliche Messung und Anzeige."""
    global hat
    channels = [MESS_KANAL]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    try:
        actual_scan_rate = hat.a_in_scan_actual_rate(num_channels, scan_rate)
        
        print('\n--- Starte Messung ---')
        print(f'    Kanal:                  {MESS_KANAL}')
        print(f'    Scan-Rate (tatsächlich): {actual_scan_rate:.2f} Hz')
        print(f'    Verstärkung:            {VERSTAERKUNG}')
        print(f'    Shunt-Widerstand:       {SHUNT_WIDERSTAND} Ohm\n')
        
        hat.a_in_scan_start(channel_mask, 0, scan_rate, options)
        print('Messung läuft... (Drücke Strg+C zum Beenden)\n')
        print('Spannung (V)      Strom (A)')
        print('-----------------------------------')
        
        total_samples_read = 0
        timeout = 5.0

        while True:
            read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, timeout)

            if read_result.hardware_overrun or read_result.buffer_overrun:
                print('\n\nHardware- oder Pufferüberlauf erkannt! Messung gestoppt.\n')
                break

            if len(read_result.data) > 0:
                # Nimm den letzten Messwert für die Anzeige
                latest_adc_voltage = read_result.data[-1]
                current = latest_adc_voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)

                print(f'\r{latest_adc_voltage:10.5f} V    {current:10.5f} A{ERASE_TO_END_OF_LINE}', end='')
                stdout.flush()
            
            time.sleep(0.1)

    except (HatError, ValueError) as err:
        print(f'\nFehler während der Messung: {err}')
    except KeyboardInterrupt:
        # Fängt Strg+C ab, um die Messung sauber zu beenden
        print("\n\nMessung durch Benutzer unterbrochen.")
    finally:
        if hat and hat.is_scan_running():
            hat.a_in_scan_stop()

def main():
    """Hauptfunktion: Spannung einstellen und Überwachung starten."""
    if not hardware_init():
        return # Beenden, wenn die Hardware nicht initialisiert werden kann

    try:
        # 1. Spannung einstellen
        while True:
            try:
                spannung_str = input(f"Geben Sie die gewünschte Spannung ein (0 - {DAC_VREF:.2f} V) oder 'q' zum Beenden: ")
                if spannung_str.lower() == 'q':
                    return
                spannung = float(spannung_str)
                dac_wert = spannung_zu_dac_wert(spannung)
                write_dac(dac_wert)
                print(f"Spannung auf {spannung:.3f} V gesetzt (DAC-Wert: {dac_wert}).")
                break # Schleife verlassen, wenn die Eingabe gültig war
            except ValueError as e:
                print(f"FEHLER: Ungültige Eingabe. {e}")
        
        # 2. Überwachung starten
        start_monitoring()

    except KeyboardInterrupt:
        # Fängt Strg+C ab, falls es vor dem Start der Messung gedrückt wird
        print("\nProgramm unterbrochen.")

if __name__ == '__main__':
    main()