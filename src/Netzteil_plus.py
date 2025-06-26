# -*- coding: utf-8 -*-

from __future__ import print_function
import spidev
import time
import lgpio  # RPi.GPIO durch lgpio ersetzt

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, enum_mask_to_string, \
    chan_list_to_mask

# Globale Variable für das lgpio-Handle
h_gpio = None

try:
    # Öffne den Standard-GPIO-Chip (normalerweise 0) und erhalte ein Handle
    h_gpio = lgpio.gpiochip_open(0)
except Exception as e:
    print(f"lgpio nicht verfügbar: {e}")
    h_gpio = None

READ_ALL_AVAILABLE = -1
CURSOR_BACK_2 = '\x1b[2D'
ERASE_TO_END_OF_LINE = '\x1b[0K'

# Parameter der Strommessung
SHUNT_WIDERSTAND = 0.1  # Ohm
VERSTAERKUNG = 69.0      # Verstärkungsfaktor

CS_PIN = 22

# SPI-Initialisierung (unverändert)
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

# Initialisiere den CS-Pin mit lgpio, falls verfügbar
if h_gpio is not None:
    # Beanspruche den GPIO-Pin als Ausgang
    lgpio.gpio_claim_output(h_gpio, CS_PIN)
    # Setze den CS-Pin initial auf HIGH (inaktiv), 1 ist HIGH
    lgpio.gpio_write(h_gpio, CS_PIN, 1)

def write_dac(value):
    """
    Schreibt einen Wert an den DAC über SPI.
    Der CS-Pin wird manuell mit lgpio gesteuert.
    """
    assert 0 <= value <= 4095

    control = 0
    control |= 0 << 15  # Channel A=0 oder B=1
    control |= 1 << 14
    control |= 0 << 13  # Gain 0=2x
    control |= 1 << 12
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF

    print(f"Sende SPI: {data:016b} (0x{high_byte:02X} {low_byte:02X})")

    if h_gpio is not None:
        # CS-Pin auf LOW setzen, um die SPI-Kommunikation zu aktivieren
        lgpio.gpio_write(h_gpio, CS_PIN, 0)
        # Sende die Daten
        spi.xfer2([high_byte, low_byte])
        # CS-Pin auf HIGH setzen, um die Kommunikation zu beenden
        lgpio.gpio_write(h_gpio, CS_PIN, 1)
    else:
        print("GPIO-Fehler: lgpio-Handle ist nicht initialisiert.")


def strombegrenzung():
    """
    MCC 118: Strommessung über Kanal 5 mit Verstärkerfaktor und Shunt
    Umrechnen von Spannung → Strom: I = U / (Verstärkung * R_shunt)
    (Diese Funktion ist unverändert)
    """
    channels = [5]  # Nur Kanal 5 aktiv
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

        print('\nMCC 118 kontinuierliche Strommessung (Kanal 5)')
        print('    Scan-Rate (gewünscht): ', scan_rate, 'Hz')
        print('    Scan-Rate (tatsächlich): ', actual_scan_rate, 'Hz')
        print('    Verstärkung: ', VERSTAERKUNG)
        print('    Shunt-Widerstand: ', SHUNT_WIDERSTAND, 'Ohm')

        input('\nDrücke ENTER zum Starten ...')

        hat.a_in_scan_start(channel_mask, samples_per_channel, scan_rate, options)

        print('\nMessung läuft ... (Strg+C zum Beenden)\n')
        print('Samples Read     Scan Count      Spannung (V)      Strom (A)')

        read_and_display_data(hat, num_channels, channels)

    except (HatError, ValueError) as err:
        print('\nFehler:', err)


def read_and_display_data(hat, num_channels, channels):
    """
    Liest Daten und berechnet Strom aus Spannung
    (Diese Funktion ist unverändert)
    """
    total_samples_read = 0
    read_request_size = READ_ALL_AVAILABLE
    timeout = 5.0

    try:
        while True:
            read_result = hat.a_in_scan_read(read_request_size, timeout)

            if read_result.hardware_overrun:
                print('\n\nHardwareüberlauf erkannt\n')
                break
            elif read_result.buffer_overrun:
                print('\n\nPufferüberlauf erkannt\n')
                break

            samples_read_per_channel = int(len(read_result.data) / num_channels)
            total_samples_read += samples_read_per_channel

            print('\r{:12}     {:12}      '.format(samples_read_per_channel, total_samples_read), end='')

            if samples_read_per_channel > 0:
                index = samples_read_per_channel * num_channels - num_channels

                for i in range(num_channels):
                    voltage = read_result.data[index + i]
                    current = voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)

                    print('{:10.5f} V      {:10.5f} A'.format(voltage, current), end='  ')

                stdout.flush()
                time.sleep(0.1)
    except KeyboardInterrupt:
        print('\nMessung gestoppt.')
        hat.a_in_scan_stop()
        hat.a_in_scan_cleanup()


def main():
    """ Hauptfunktion des Programms. """
    time.sleep(1)
    write_dac(3000)
    
    # Die auskommentierten Teile bleiben unverändert
    """
    while True:
        strombegrenzung()
        time.sleep(0.5)
    """


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgramm durch Benutzer unterbrochen.")
    finally:
        # Aufräumen: Ressourcen sicher freigeben
        print("\nBeende das Programm und gebe Ressourcen frei.")
        if h_gpio is not None:
            # Setze den DAC auf 0V, bevor das Programm endet
            print("Setze DAC auf 0.")
            write_dac(0)
            # Gebe das GPIO-Handle frei
            lgpio.gpiochip_close(h_gpio)
        if spi:
            spi.close()
        print("Ressourcen freigegeben. Beendet.")