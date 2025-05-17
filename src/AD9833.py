import RPi.GPIO as GPIO
import spidev
import time

# AD9833 Register-Konstanten
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
CONTROL_REG = 0x2000

# Wellenform-Konstanten
SINE_WAVE = 0x2000      # Sinuswelle
TRIANGLE_WAVE = 0x2002  # Dreieckswelle
SQUARE_WAVE = 0x2028    # Rechteckwelle

# SPI Einstellungen
spi_bus = 0
spi_device = 0
spi_frequency = 1000000  # 1 MHz

# FSYNC Pin (Chip Select)
FSYNC = 25  # GPIO-Pin für FSYNC

# Initialisierung
def init_AD9833():
    # GPIO initialisieren
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(FSYNC, GPIO.OUT)
    GPIO.output(FSYNC, GPIO.HIGH)
    
    # SPI initialisieren
    global spi
    spi = spidev.SpiDev()
    spi.open(spi_bus, spi_device)
    spi.max_speed_hz = spi_frequency
    spi.mode = 0b10  # SPI Modus 2
    
    # Reset des AD9833
    write_to_AD9833(0x2100)
    time.sleep(0.1)

# Daten an AD9833 senden
def write_to_AD9833(data):
    GPIO.output(FSYNC, GPIO.LOW)
    spi.xfer2([data >> 8, data & 0xFF])
    GPIO.output(FSYNC, GPIO.HIGH)

# Frequenz einstellen (in Hz)
def set_frequency(freq):
    # Berechne Frequenzregister-Wert
    # AD9833 hat einen 28-Bit Frequenzregister
    # FREQ = (frequency * 2^28) / fMCLK
    fMCLK = 25000000  # 25 MHz Standardtaktfrequenz
    freq_word = int((freq * 2**28) / fMCLK)
    
    # Reset aktivieren
    write_to_AD9833(0x2100)
    
    # Frequenzregister schreiben (in zwei 14-Bit Wörtern)
    write_to_AD9833(FREQ0_REG | (freq_word & 0x3FFF))
    write_to_AD9833(FREQ0_REG | ((freq_word >> 14) & 0x3FFF))

# Wellenform einstellen
def set_waveform(waveform):
    write_to_AD9833(waveform)

# Hauptprogramm
def main():
    try:
        # AD9833 initialisieren
        init_AD9833()
        print("AD9833 initialisiert.")
        
        # 1 kHz Sinuswelle erzeugen
        set_frequency(10000)  # 100 Hz einstellen
        set_waveform(SINE_WAVE)  # Sinuswelle auswählen
        print("100 Hz Sinuswelle wird ausgegeben (nativ ca. ±0.325V).")
        
        # Programm laufen lassen, bis Benutzer abbricht
        print("Drücken Sie STRG+C zum Beenden...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nProgramm beendet.")
    finally:
        # Aufräumen
        GPIO.cleanup()
        spi.close()

if __name__ == "__main__":
    main()