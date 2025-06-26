# -*- coding: utf-8 -*-
import spidev
import time
import lgpio

# Globale Variable für das lgpio-Handle
h_gpio = None
spi = None

try:
    # Öffne den Standard-GPIO-Chip (normalerweise 0) und erhalte ein Handle
    h_gpio = lgpio.gpiochip_open(0)
    
    # SPI-Initialisierung
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1000000
    spi.mode = 0b00

except Exception as e:
    print(f"Hardware-Initialisierungsfehler (lgpio oder spidev): {e}")
    h_gpio = None
    spi = None

CS_PIN = 22

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
    control |= 1 << 15  # Channel B ausgewählt (A=0, B=1)
    control |= 1 << 14
    control |= 0 << 13  # Gain 0=2x
    control |= 1 << 12
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF
    
    print(f"Sende an Kanal B: {data:016b} (0x{high_byte:02X} {low_byte:02X})")
    
    # Stelle sicher, dass die Hardware-Handles gültig sind
    if h_gpio is not None and spi is not None:
        # CS-Pin auf LOW setzen, um die SPI-Kommunikation zu aktivieren
        lgpio.gpio_write(h_gpio, CS_PIN, 0)
        # Sende die Daten
        spi.xfer2([high_byte, low_byte])
        # CS-Pin auf HIGH setzen, um die Kommunikation zu beenden
        lgpio.gpio_write(h_gpio, CS_PIN, 1)
    else:
        print("Hardware-Fehler: lgpio oder spi ist nicht initialisiert.")


def main():
    """ Hauptfunktion des Programms. """
    time.sleep(1)
    # Setzt den Wert für Kanal B
    # write_dac(0) # Auf 0 setzen
    write_dac(4095) # Auf maximalen Wert setzen


if __name__ == '__main__':
    try:
        if h_gpio and spi: # Führe main nur aus, wenn die Initialisierung erfolgreich war
            main()
        else:
            print("Programm wird aufgrund von Initialisierungsfehlern nicht ausgeführt.")
    except KeyboardInterrupt:
        print("\nProgramm durch Benutzer unterbrochen.")
    finally:
        # Aufräumen: Ressourcen sicher freigeben
        print("\nBeende das Programm und gebe Ressourcen frei.")
        if h_gpio is not None:
            # Setze den DAC auf 0V, bevor das Programm endet
            print("Setze DAC (Kanal B) auf 0.")
            write_dac(0)
            # Gebe das GPIO-Handle frei
            lgpio.gpiochip_close(h_gpio)
        if spi:
            spi.close()
        print("Ressourcen freigegeben. Beendet.")