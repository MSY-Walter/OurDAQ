#!/usr/bin/env python3
"""
Netzteil Plus Seite: Strombegrenzung und DAC Steuerung
(Angepasste Version, die eine direkte Spannungseingabe ermöglicht)
"""

from __future__ import print_function
import spidev
import time
import lgpio

from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, enum_mask_to_string, \
    chan_list_to_mask

# --- WICHTIGE HARDWARE-PARAMETER (BITTE ANPASSEN) ---
# Hier die Referenzspannung des DAC-Chips eintragen!
V_REF_SPANNUNG = 2.5  # V
DAC_GAIN = 2.0  # Gemäß der Einstellung in write_dac (0 << 13 bedeutet Gain=2x)
MAX_SPANNUNG = V_REF_SPANNUNG * DAC_GAIN # Maximal einstellbare Spannung

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
    value = int(round(value))
    value = max(0, min(4095, value)) # Sicherstellen, dass der Wert im Bereich liegt
    
    control = 0
    control |= 0 << 15 # Channel A
    control |= 1 << 14 # Buffered output
    control |= 0 << 13 # Gain 0=2x
    control |= 1 << 12 # Activate output
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def spannung_zu_dac_wert(spannung):
    """Rechnet eine gewünschte Spannung in einen 12-Bit DAC-Wert um."""
    if spannung > MAX_SPANNUNG:
        print(f"Warnung: Angeforderte Spannung {spannung:.3f}V ist höher als das Maximum von {MAX_SPANNUNG:.3f}V. Begrenze auf Maximum.")
        spannung = MAX_SPANNUNG
    if spannung < 0:
        spannung = 0
        
    dac_wert = (spannung / MAX_SPANNUNG) * 4095
    return dac_wert

# ... (Die Funktionen strombegrenzung und read_and_display_data bleiben unverändert) ...
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
            last_voltage = read_result.data[-1]
            current = last_voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)
            
            print(f'\r{last_voltage:10.5f} V    {current:10.5f} A', end='')
            stdout.flush()
        
        time.sleep(0.1)


def main():
    """Hauptprogramm: Fragt nach der Spannung und startet die Überwachung."""
    try:
        # Benutzer nach der gewünschten Spannung fragen
        while True:
            try:
                # Hier die Frage auf Deutsch, wie im Originalcode-Stil
                prompt = f"Bitte gewünschte Spannung eingeben (0.0 - {MAX_SPANNUNG:.3f} V), oder 'q' zum Beenden: "
                user_input = input(prompt)
                
                if user_input.lower() == 'q':
                    print("Programm wird beendet.")
                    return

                gewuenschte_spannung = float(user_input)
                if 0.0 <= gewuenschte_spannung <= MAX_SPANNUNG:
                    break  # Gültiger Wert, Schleife verlassen
                else:
                    print(f"Fehler: Der Wert muss zwischen 0.0 und {MAX_SPANNUNG:.3f} liegen.")
            except ValueError:
                print("Fehler: Bitte eine gültige Zahl eingeben (z.B. '3.3').")
        
        # Spannung in DAC-Wert umrechnen
        dac_wert = spannung_zu_dac_wert(gewuenschte_spannung)
        
        # DAC auf den berechneten Wert einstellen
        print(f"\nStelle Spannung auf {gewuenschte_spannung:.3f}V ein (entspricht DAC-Wert ~{dac_wert:.0f})...")
        write_dac(dac_wert)
        
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