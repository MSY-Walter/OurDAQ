#!/usr/bin/env python3
"""
AD9833 Minimaler Test
"""

import lgpio
import spidev
import time

# --- Konfiguration ---
SPI_BUS = 0
SPI_DEVICE = 0
FSYNC_PIN = 25
FMCLK = 25000000.0  # 25 MHz Taktfrequenz
TARGET_FREQ = 10000 # Testfrequenz: 10 kHz

# --- AD9833 Befehle (bereits für 28-Bit Modus korrigiert) ---
RESET_CMD = 0x2100
FREQ0_REG = 0x4000
SINE_WAVE_CMD = 0x2000 # Sinus-Befehl mit B28=1

# --- Globale Handles ---
gpio_handle = None
spi = None

def write_to_AD9833(data):
    """Sendet 16-Bit Daten an den AD9833."""
    try:
        # FSYNC LOW
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 0)
        # Sende High-Byte, dann Low-Byte
        spi.xfer2([(data >> 8) & 0xFF, data & 0xFF])
        # FSYNC HIGH
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 1)
        # Kurze Pause zur Stabilisierung
        time.sleep(0.001)
        return True
    except Exception as e:
        print(f"Fehler beim Schreiben: {e}")
        return False

def main():
    global gpio_handle, spi
    try:
        # --- Initialisierung ---
        print("Initialisiere GPIO und SPI...")
        gpio_handle = lgpio.gpiochip_open(4)
        lgpio.gpio_claim_output(gpio_handle, FSYNC_PIN, 1)
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_DEVICE)
        spi.max_speed_hz = 1000000
        spi.mode = 0b10 # SPI Modus 2
        print("Initialisierung abgeschlossen.")

        # --- AD9833 Konfiguration für 10 kHz Sinus ---
        print(f"Konfiguriere AD9833 für {TARGET_FREQ} Hz...")
        
        # 1. Reset-Befehl senden (setzt B28=1 und RESET=1)
        print(f"Sende RESET Befehl: {RESET_CMD:#06x}")
        write_to_AD9833(RESET_CMD)

        # 2. Frequenzwort berechnen
        freq_word = int(round((TARGET_FREQ * (2**28)) / FMCLK))
        print(f"Berechnetes Frequenzwort: {freq_word} ({freq_word:#010x})")
        
        lsb = freq_word & 0x3FFF
        msb = (freq_word >> 14) & 0x3FFF
        
        # 3. Frequenzwort senden (LSB zuerst, dann MSB)
        print(f"Sende LSB: {(FREQ0_REG | lsb):#06x}")
        write_to_AD9833(FREQ0_REG | lsb)
        
        print(f"Sende MSB: {(FREQ0_REG | msb):#06x}")
        write_to_AD9833(FREQ0_REG | msb)

        # 4. Ausgang aktivieren (RESET=0, aber B28=1 beibehalten)
        print(f"Aktiviere Sinuswelle: {SINE_WAVE_CMD:#06x}")
        write_to_AD9833(SINE_WAVE_CMD)

        print("\nKonfiguration abgeschlossen. 10 kHz Sinussignal sollte ausgegeben werden.")
        print("Drücken Sie Strg+C zum Beenden.")
        
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nProgramm beendet.")
    finally:
        # --- Aufräumen ---
        if spi:
            spi.close()
        if gpio_handle:
            lgpio.gpiochip_close(gpio_handle)
        print("Ressourcen freigegeben.")

if __name__ == "__main__":
    main()