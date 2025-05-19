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

# Wellenform vom Benutzer erfragen
def get_waveform_choice():
    while True:
        print("\nWählen Sie die Wellenform:")
        print("1. Sinuswelle")
        print("2. Dreieckswelle")
        print("3. Rechteckwelle")
        choice = input("Bitte wählen Sie (1-3): ")
        
        if choice == '1':
            return SINE_WAVE, "Sinuswelle"
        elif choice == '2':
            return TRIANGLE_WAVE, "Dreieckswelle"
        elif choice == '3':
            return SQUARE_WAVE, "Rechteckwelle"
        else:
            print("Ungültige Auswahl, bitte versuchen Sie es erneut.")

# Frequenz vom Benutzer erfragen
def get_frequency():
    while True:
        try:
            freq = float(input("\nBitte geben Sie die Frequenz ein (Hz): "))
            if 0 < freq <= 12500000:  # AD9833 maximale Frequenz ist ca. 12.5 MHz
                return freq
            else:
                print("Die Frequenz muss zwischen 0 und 12.500.000 Hz liegen.")
        except ValueError:
            print("Bitte geben Sie eine gültige Zahl ein.")

# Hauptprogramm
def main():
    try:
        # AD9833 initialisieren
        init_AD9833()
        print("AD9833 wurde initialisiert.")
        
        while True:
            # Vom Benutzer Wellenform und Frequenz erhalten
            waveform, waveform_name = get_waveform_choice()
            freq = get_frequency()
            
            # Wellenform und Frequenz einstellen
            set_frequency(freq)
            set_waveform(waveform)
            
            print(f"\nAusgabe: {freq} Hz {waveform_name} (Standard-Spannungspegel ca. 0,65V Spitze-zu-Spitze)")
            print("Drücken Sie Strg+C zum Beenden oder Enter, um die Einstellungen zu ändern.")
            input()  # Warten auf Benutzereingabe
            
    except KeyboardInterrupt:
        print("\nProgramm wurde beendet.")
    finally:
        # Gerät zurücksetzen vor dem Beenden
        write_to_AD9833(0x2100)
        # Ressourcen aufräumen
        GPIO.cleanup()
        spi.close()

if __name__ == "__main__":
    main()