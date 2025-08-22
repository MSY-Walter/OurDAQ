#!/usr/bin/env python3
"""
Funktionsgenerator mit AD9833
"""

import lgpio
import time
import math

# Pin-Definitionen basierend auf der GPIO-Nummerierung (BCM)
# Raspberry Pi 5 verwendet SPI0 für diese Pins
SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED = 2000000  # 2 MHz, sicher für den AD9833
FCN_PIN = 25         # Frame Sync Pin, wie gewünscht

# AD9833 Konstanten
# Master Clock Frequenz des Oszillators auf dem AD9833-Modul (meist 25 MHz)
MCLK = 25000000.0

# AD9833 Register und Befehle (16-Bit Kontrollwörter)
# Kontrollregister-Bits
B28_BIT = 1 << 13
RESET_CMD = 1 << 8

# Wellenform-Modi (werden zum Kontrollregister addiert)
SINE_WAVE = 0x2000
TRIANGLE_WAVE = 0x2002
SQUARE_WAVE = 0x2028
SQUARE_DIV2_WAVE = 0x2020 # Rechteck mit 50% Tastverhältnis (F_OUT = F_MCLK/2)

# Frequenz- und Phasenregister-Adressen
FREQ0_REG = 0x4000
FREQ1_REG = 0x8000
PHASE0_REG = 0xC000
PHASE1_REG = 0xE000

class AD9833:
    """
    Eine Klasse zur Ansteuerung des AD9833 DDS Signalgenerators
    über SPI mit der lgpio-Bibliothek auf einem Raspberry Pi.
    """
    def __init__(self, fcn_pin, spi_bus, spi_device, spi_speed, mclk):
        """
        Initialisiert die SPI- und GPIO-Verbindung.
        """
        self.mclk = mclk
        self.fcn_pin = fcn_pin

        # GPIO Chip öffnen (für Pi 5 ist das meist Chip 4, aber 0 ist ein Symlink)
        self.gpio_h = lgpio.gpiochip_open(0)
        
        # SPI-Gerät öffnen
        self.spi_h = lgpio.spi_open(spi_bus, spi_device, spi_speed, 0)

        # FCN-Pin als Ausgang konfigurieren
        lgpio.gpio_claim_output(self.gpio_h, self.fcn_pin)
        lgpio.gpio_write(self.gpio_h, self.fcn_pin, 1) # FCN Pin auf HIGH setzen (inaktiv)

        print("AD9833-Treiber initialisiert.")
        self.reset()

    def write_register(self, data):
        """
        Schreibt einen 16-Bit-Wert in ein Register des AD9833.
        """
        # Daten in zwei Bytes aufteilen (High Byte, Low Byte)
        high_byte = (data >> 8) & 0xFF
        low_byte = data & 0xFF
        tx_data = bytes([high_byte, low_byte])

        # Kommunikationssequenz: FCN LOW -> Daten senden -> FCN HIGH
        lgpio.gpio_write(self.gpio_h, self.fcn_pin, 0)
        time.sleep(1e-6) # Kurze Pause zur Stabilisierung
        lgpio.spi_write(self.spi_h, tx_data)
        time.sleep(1e-6)
        lgpio.gpio_write(self.gpio_h, self.fcn_pin, 1)

    def reset(self):
        """
        Setzt den AD9833 zurück und initialisiert ihn.
        """
        # Reset-Bit setzen, um den internen Zustand zurückzusetzen
        self.write_register(RESET_CMD)
        time.sleep(0.01) # Kurze Wartezeit nach dem Reset
        
        # Setzt die Frequenz auf 0 Hz und wählt Sinuswelle als Standard
        self.set_frequency(0)
        self.set_waveform(SINE_WAVE)

    def set_frequency(self, frequency, register=0):
        """
        Stellt die Ausgangsfrequenz in Hz ein.
        'register' kann 0 (FREQ0) oder 1 (FREQ1) sein.
        """
        if frequency > self.mclk / 2:
            print(f"Warnung: Frequenz {frequency} Hz ist zu hoch. Maximum ist {self.mclk / 2} Hz.")
            frequency = self.mclk / 2
        if frequency < 0:
            frequency = 0
            
        # Berechnet das 28-Bit Frequenz-Wort
        # freq_word = int(round((frequency * (2**28)) / self.mclk))
        freq_word = int(round(frequency * (2**28 / self.mclk)))

        # Teilt das 28-Bit-Wort in zwei 14-Bit-Wörter (MSB und LSB)
        msb = (freq_word >> 14) & 0x3FFF
        lsb = freq_word & 0x3FFF

        # Wählt das Ziel-Register (FREQ0 oder FREQ1)
        reg_addr = FREQ0_REG if register == 0 else FREQ1_REG

        # Schreibt die Werte in die Register
        # Wichtig: B28-Bit setzen, damit beide Bytes (LSB & MSB) auf einmal geladen werden
        control_word = B28_BIT 
        self.write_register(control_word)
        self.write_register(lsb | reg_addr)
        self.write_register(msb | reg_addr)
        
    def set_waveform(self, waveform):
        """
        Wählt die Wellenform aus.
        Benutzt die Konstanten: SINE_WAVE, TRIANGLE_WAVE, SQUARE_WAVE
        """
        self.write_register(waveform)

    def close(self):
        """
        Gibt die GPIO- und SPI-Ressourcen sauber frei.
        """
        print("Ressourcen werden freigegeben.")
        lgpio.spi_close(self.spi_h)
        lgpio.gpiochip_close(self.gpio_h)

# --- Hauptprogramm ---
if __name__ == "__main__":
    
    ad9833 = None # Deklarieren, damit es im finally-Block verfügbar ist
    
    try:
        # Initialisiert den AD9833-Generator
        ad9833 = AD9833(
            fcn_pin=FCN_PIN,
            spi_bus=SPI_BUS,
            spi_device=SPI_DEVICE,
            spi_speed=SPI_SPEED,
            mclk=MCLK
        )
        
        # Stellt eine Testfrequenz ein
        test_frequenz = 1000  # 1 kHz
        print(f"Setze Frequenz auf {test_frequenz} Hz.")
        ad9833.set_frequency(test_frequenz)
        
        print("\nWechsle alle 5 Sekunden die Wellenform. Drücke STRG+C zum Beenden.")
        
        # Endlosschleife zum Wechseln der Wellenformen
        while True:
            print("-> Erzeuge Sinuswelle...")
            ad9833.set_waveform(SINE_WAVE)
            time.sleep(5)
            
            print("-> Erzeuge Dreieckwelle...")
            ad9833.set_waveform(TRIANGLE_WAVE)
            time.sleep(5)
            
            print("-> Erzeuge Rechteckwelle...")
            ad9833.set_waveform(SQUARE_WAVE)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nProgramm durch Benutzer beendet.")
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
    finally:
        if ad9833:
            # Stellt die Frequenz auf 0, bevor das Programm endet
            ad9833.set_frequency(0)
            ad9833.close()