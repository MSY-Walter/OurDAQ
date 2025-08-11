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

def setup_hardware():
    """Initialisiert SPI und GPIO."""
    global gpio_handle
    try:
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00
        
        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN)
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)
        print("Hardware erfolgreich initialisiert.")
    except Exception as e:
        print(f"Fehler bei der Hardware-Initialisierung: {e}")
        sys.exit(1)

def cleanup_hardware():
    """Schließt SPI und gibt GPIO-Ressourcen frei."""
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
    
    print(f"Sende SPI DAC-Wert {value} (Binär: {data:016b}) für {-10.75 * (1 - value/MAX_DAC_VALUE):.2f} V")
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def set_voltage_minus(voltage):
    """
    Stellt die Spannung auf der Minus-Seite ein, indem der DAC-Wert berechnet wird.
    
    :param voltage: Die gewünschte Spannung in Volt (-10.75 bis 0).
    """
    if not (DAC_SPAN <= voltage <= 0):
        print(f"Ungültige Spannung: {voltage} V. Der gültige Bereich ist {DAC_SPAN}V bis 0V.")
        return
        
    # Lineare Skalierung: 0V -> 4095, -10.75V -> 0
    dac_value = int((1 - (voltage / DAC_SPAN)) * MAX_DAC_VALUE)
    write_dac_minus(dac_value)

def strombegrenzung_minus():
    """Führt die kontinuierliche Strommessung durch."""
    channels = [4]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    try:
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        actual_scan_rate = hat.a_in_scan_actual_rate(num_channels, scan_rate)
        
        print('\nMCC 118 Strommessung MINUS (Kanal 4)')
        print('    Scan-Rate (tatsächlich): ', actual_scan_rate, 'Hz')
        
        hat.a_in_scan_start(channel_mask, 0, scan_rate, options)
        print('\nMessung läuft ... (Strg+C zum Beenden)\n')
        print('Samples Read      Scan Count        Spannung (V)      Strom (A)')
        
        read_and_display_data_minus(hat, num_channels)
        
    except (HatError, ValueError) as err:
        print('\nFehler:', err)
    finally:
        if 'hat' in locals() and hat.status().running:
            hat.a_in_scan_stop()
            hat.a_in_scan_cleanup()

def read_and_display_data_minus(hat, num_channels):
    """Liest Daten aus dem MCC 118 und berechnet den Strom."""
    total_samples_read = 0
    timeout = 5.0

    while True:
        try:
            read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, timeout)
            
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
            
            # Ausgabe auf einer Zeile
            print(f'\r{samples_read_per_channel:12}      {total_samples_read:12}        {voltage:10.5f} V      {current:10.5f} A', end='', flush=True)

            time.sleep(0.1)

        except KeyboardInterrupt:
            break
    print('\n')

def main():
    """Hauptfunktion des Programms."""
    setup_hardware()
    
    try:
        while True:
            # Benutzer zur Eingabe der Spannung auffordern
            input_voltage = input(f"Gib die gewünschte Spannung in Volt ein (Bereich {DAC_SPAN}V bis 0V) oder 's' für Strombegrenzung, 'q' zum Beenden: ")
            
            if input_voltage.lower() == 'q':
                break
            elif input_voltage.lower() == 's':
                strombegrenzung_minus()
            else:
                try:
                    spannung = float(input_voltage)
                    set_voltage_minus(spannung)
                except ValueError:
                    print("Ungültige Eingabe. Bitte gib eine Zahl oder 'q'/'s' ein.")
    except KeyboardInterrupt:
        print("\nProgramm beendet durch Benutzer.")
    finally:
        cleanup_hardware()

if __name__ == '__main__':
    main()
