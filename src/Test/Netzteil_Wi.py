#!/usr/bin/env python3
"""
Netzteil Minus Seite: Strombegrenzung und DAC Steuerung
"""

from __future__ import print_function
import spidev
import time
import lgpio
import sys

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask

# --- Globale Konstanten und Variablen ---
READ_ALL_AVAILABLE = -1
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor
CS_PIN = 22
MAX_DAC_VALUE = 4095
DAC_SPAN = -10.75           # Maximale negative Spannung des DACs

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

def cleanup_hardware():
    """Schließt SPI und gibt GPIO-Ressourcen frei."""
    if hat and hat.status().running:
        hat.a_in_scan_stop()
        hat.a_in_scan_cleanup()

    if gpio_handle:
        try:
            write_dac_minus(0) # DAC auf 0V setzen
            time.sleep(0.1)
        except Exception as e:
            print(f"Fehler beim Zurücksetzen des DACs: {e}")
        
        lgpio.gpiochip_close(gpio_handle)
    
    if spi:
        spi.close()
    
    print("Hardware-Ressourcen freigegeben.")

def write_dac_minus(value):
    """
    Schreibt einen DAC-Wert (0-4095) an den MCP4822 über SPI.
    
    :param value: Der 12-Bit-Wert für den DAC-Kanal B (Minus-Seite).
    """
    if not (0 <= value <= MAX_DAC_VALUE):
        raise ValueError(f"DAC-Wert muss zwischen 0 und {MAX_DAC_VALUE} liegen.")
        
    control = 0
    control |= 1 << 15  # Kanal B (Minus)
    control |= 1 << 13  # Verstärkung auf 1x
    control |= 1 << 12  # Normaler Betrieb (kein Shutdown)
    
    data = (control | (value & 0xFFF))
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    # print(f"Sende SPI DAC-Wert {value} für {-10.75 * (1 - value/MAX_DAC_VALUE):.2f} V")
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def set_voltage_minus(voltage):
    """
    Stellt die Spannung auf der Minus-Seite ein.
    
    :param voltage: Die gewünschte Spannung in Volt (-10.75 bis 0).
    """
    if not (DAC_SPAN <= voltage <= 0):
        print(f"Ungültige Spannung: {voltage} V. Der gültige Bereich ist {DAC_SPAN}V bis 0V.")
        return
        
    dac_value = int((1 - (voltage / DAC_SPAN)) * MAX_DAC_VALUE)
    write_dac_minus(dac_value)
    print(f"Spannung auf {voltage:.2f} V eingestellt.")


def continuous_measurement():
    """Führt die kontinuierliche Strommessung und -ausgabe durch."""
    channels = [4]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    try:
        actual_scan_rate = hat.a_in_scan_actual_rate(num_channels, scan_rate)
        
        print('\nStarte Messung...')
        print('    Scan-Rate (tatsächlich): ', actual_scan_rate, 'Hz')
        
        hat.a_in_scan_start(channel_mask, 0, scan_rate, options)
        print('\nMessung läuft ... (Strg+C zum Beenden)\n')
        
        total_samples_read = 0
        read_request_size = READ_ALL_AVAILABLE
        timeout = 5.0
        
        # Header für die Live-Anzeige
        print(f'{"Spannung [V]":<20} {"Strom [A]":<20}', end='')

        while hat.status().running:
            read_result = hat.a_in_scan_read(read_request_size, timeout)
            
            if read_result.hardware_overrun or read_result.buffer_overrun:
                print('\n\nÜberlauf erkannt. Messung stoppt.\n')
                break
                
            samples_read_per_channel = len(read_result.data) // num_channels
            if samples_read_per_channel == 0:
                continue

            total_samples_read += samples_read_per_channel
            index = (samples_read_per_channel * num_channels) - num_channels

            voltage = read_result.data[index]
            current = -voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)
            
            # Ausgabe auf einer Zeile, die ständig aktualisiert wird
            print(f'\r{voltage:<20.5f} {current:<20.5f}', end='', flush=True)

            time.sleep(0.1)

    except (HatError, ValueError) as err:
        print(f'\nFehler: {err}')
    except KeyboardInterrupt:
        print("\nMessung beendet durch Benutzer.")
    finally:
        if hat.status().running:
            hat.a_in_scan_stop()
            hat.a_in_scan_cleanup()


def main():
    """Hauptfunktion des Programms."""
    setup_hardware()
    
    try:
        while True:
            print("\n--- Menü ---")
            print(f"Spannung einstellen: {DAC_SPAN}V bis 0V")
            print("Messung starten: 'm'")
            print("Beenden: 'q'")
            
            user_input = input("Gib deine Wahl ein: ")
            
            if user_input.lower() == 'q':
                break
            elif user_input.lower() == 'm':
                continuous_measurement()
            else:
                try:
                    spannung = float(user_input)
                    set_voltage_minus(spannung)
                except ValueError:
                    print("Ungültige Eingabe. Bitte gib eine Zahl, 'm' oder 'q' ein.")
    except KeyboardInterrupt:
        print("\nProgramm beendet durch Benutzer.")
    finally:
        cleanup_hardware()

if __name__ == '__main__':
    main()
