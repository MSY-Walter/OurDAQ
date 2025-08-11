#!/usr/bin/env python3
"""
Netzteil Minus Seite: Strombegrenzung und DAC Steuerung
"""

from __future__ import print_function
import spidev
import time
import lgpio

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, enum_mask_to_string, \
    chan_list_to_mask

READ_ALL_AVAILABLE = -1
CURSOR_BACK_2 = '\x1b[2D'
ERASE_TO_END_OF_LINE = '\x1b[0K'

# Parameter der Strommessung (Negativ)
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor

CS_PIN = 22

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

# lgpio Initialisierung
gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, CS_PIN)
lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def write_dac_minus(value):
    """
    Schreibt einen Wert an den DAC für die Minus-Seite.
    """
    assert 0 <= value <= 4095
    
    # Kontrolle-Bytes für DAC-Kommunikation
    # Bits: 15-12 (Konfig), 11-0 (Daten)
    # Channel B = 1, Gain = 1x (bit 13 = 1), Shutdown = Normal Operation (bit 12 = 1)
    control = 0
    control |= 1 << 15  # DAC B
    control |= 1 << 14  # Unused
    control |= 1 << 13  # Gain Select = 1x
    control |= 1 << 12  # Shutdown = Normal Operation
    
    data = (control | (value & 0xFFF))
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    print(f"Sende SPI (Minus): {data:016b} (0x{high_byte:02X} {low_byte:02X})")
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def strombegrenzung_minus():
    """
    MCC 118: Strommessung über Kanal 4 mit Verstärkerfaktor und Shunt (Negativ)
    Umrechnen von Spannung → Strom: I = U / (Verstärkung * R_shunt)
    """
    channels = [4]  # Kanal 4 für negative Seite
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

        print('\nMCC 118 kontinuierliche Strommessung MINUS (Kanal 4)')
        print('    Scan-Rate (gewünscht): ', scan_rate, 'Hz')
        print('    Scan-Rate (tatsächlich): ', actual_scan_rate, 'Hz')
        print('    Verstärkung: ', VERSTAERKUNG)
        print('    Shunt-Widerstand: ', SHUNT_WIDERSTAND, 'Ohm')

        input('\nDrücke ENTER zum Starten ...')

        hat.a_in_scan_start(channel_mask, samples_per_channel, scan_rate, options)

        print('\nMessung läuft ... (Strg+C zum Beenden)\n')
        print('Samples Read      Scan Count        Spannung (V)      Strom (A)')

        read_and_display_data_minus(hat, num_channels)
        
    except (HatError, ValueError) as err:
        print('\nFehler:', err)
    finally:
        hat.a_in_scan_stop()
        hat.a_in_scan_cleanup()

def read_and_display_data_minus(hat, num_channels):
    """Liest Daten und berechnet negativen Strom aus Spannung"""
    total_samples_read = 0
    read_request_size = READ_ALL_AVAILABLE
    timeout = 5.0

    while True:
        try:
            read_result = hat.a_in_scan_read(read_request_size, timeout)

            if read_result.hardware_overrun:
                print('\n\nHardwareüberlauf erkannt\n')
                break
            elif read_result.buffer_overrun:
                print('\n\nPufferüberlauf erkannt\n')
                break

            samples_read_per_channel = int(len(read_result.data) / num_channels)
            total_samples_read += samples_read_per_channel

            print('\r{:12}      {:12}        '.format(samples_read_per_channel, total_samples_read), end='')

            if samples_read_per_channel > 0:
                index = samples_read_per_channel * num_channels - num_channels

                for i in range(num_channels):
                    voltage = read_result.data[index + i]
                    current = -voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)  # Negativ für Minus-Seite

                    print('{:10.5f} V      {:10.5f} A'.format(voltage, current), end='  ')
                stdout.flush()
                time.sleep(0.1)

        except KeyboardInterrupt:
            break
            
    print('\n')

def main():
    try:
        write_dac_minus(4095)
        strombegrenzung_minus()
    except KeyboardInterrupt:
        print("Programm beendet durch Benutzer.")
    finally:
        # DAC auf Null setzen und Ressourcen freigeben
        write_dac_minus(0)
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
        print("Ressourcen freigegeben.")
        
if __name__ == '__main__':
    main()
