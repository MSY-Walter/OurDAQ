import gpiod
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
SPI_BUS = 0
SPI_DEVICE = 0
SPI_FREQUENCY = 1000000  # 1 MHz

# FSYNC Pin (Chip Select)
FSYNC_PIN = 25  # GPIO-Pin für FSYNC
CHIP = 'gpiochip4'  # GPIO chip for Raspberry Pi 5 (RP1)

# Frequenz-Konstanten
FMCLK = 25000000  # 25 MHz Standardtaktfrequenz
MAX_FREQUENCY = 20000  # Maximale Ausgangsfrequenz: 20 kHz
MIN_FREQUENCY = 0.1    # Minimale Ausgangsfrequenz: 0.1 Hz

def init_AD9833():
    """Initialisiert GPIO und SPI für AD9833"""
    # GPIO initialisieren
    global chip, fsync_line
    chip = gpiod.Chip(CHIP)
    fsync_line = chip.get_line(FSYNC_PIN)
    fsync_line.request(consumer="ad9833_fsync", type=gpiod.LINE_REQ_DIR_OUT, default_val=1)  # FSYNC high
    
    # SPI initialisieren
    global spi
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_FREQUENCY
    spi.mode = 0b10  # SPI Modus 2
    
    # Reset des AD9833
    write_to_AD9833(0x2100)
    time.sleep(0.1)

def write_to_AD9833(data):
    """Sendet 16-Bit Daten an AD9833"""
    fsync_line.set_value(0)  # FSYNC low
    spi.xfer2([data >> 8, data & 0xFF])
    fsync_line.set_value(1)  # FSYNC high

def set_frequency(freq):
    """Stellt die Ausgangsfrequenz ein (in Hz)"""
    # Berechne Frequenzregister-Wert
    freq_word = int((freq * 2**28) / FMCLK)
    
    # Reset aktivieren
    write_to_AD9833(0x2100)
    
    # Frequenzregister schreiben (in zwei 14-Bit Wörtern)
    write_to_AD9833(FREQ0_REG | (freq_word & 0x3FFF))
    write_to_AD9833(FREQ0_REG | ((freq_word >> 14) & 0x3FFF))

def set_waveform(waveform):
    """Stellt die Wellenform ein"""
    write_to_AD9833(waveform)

def get_waveform_choice():
    """Erfasst Wellenform-Auswahl vom Benutzer"""
    wellenformen = {
        '1': (SINE_WAVE, "Sinuswelle"),
        '2': (TRIANGLE_WAVE, "Dreieckswelle"), 
        '3': (SQUARE_WAVE, "Rechteckwelle")
    }
    
    while True:
        print("\nWählen Sie die Wellenform:")
        print("1. Sinuswelle")
        print("2. Dreieckswelle")
        print("3. Rechteckwelle")
        
        choice = input("Bitte wählen Sie (1-3): ").strip()
        
        if choice in wellenformen:
            return wellenformen[choice]
        else:
            print("Ungültige Auswahl, bitte versuchen Sie es erneut.")

def get_frequency():
    """Erfasst Frequenz vom Benutzer mit Validierung"""
    while True:
        try:
            freq_input = input(f"\nBitte geben Sie die Frequenz ein ({MIN_FREQUENCY} - {MAX_FREQUENCY} Hz): ")
            freq = float(freq_input)
            
            if MIN_FREQUENCY <= freq <= MAX_FREQUENCY:
                return freq
            else:
                print(f"Die Frequenz muss zwischen {MIN_FREQUENCY} und {MAX_FREQUENCY} Hz liegen.")
                
        except ValueError:
            print("Bitte geben Sie eine gültige Zahl ein.")

def cleanup():
    """Räumt Ressourcen auf"""
    try:
        # Gerät zurücksetzen
        write_to_AD9833(0x2100)
    except:
        pass
    finally:
        # Ressourcen freigeben
        if 'fsync_line' in globals():
            fsync_line.release()
        if 'chip' in globals():
            chip.close()
        if 'spi' in globals():
            spi.close()

def main():
    """Hauptprogramm"""
    try:
        # AD9833 initialisieren
        init_AD9833()
        print("AD9833 wurde erfolgreich initialisiert.")
        print(f"Frequenzbereich: {MIN_FREQUENCY} Hz - {MAX_FREQUENCY} Hz")
        
        while True:
            # Benutzerparameter erfassen
            waveform, waveform_name = get_waveform_choice()
            freq = get_frequency()
            
            # Konfiguration anwenden
            set_frequency(freq)
            set_waveform(waveform)
            
            print(f"\nAktive Konfiguration:")
            print(f"  Wellenform: {waveform_name}")
            print(f"  Frequenz: {freq} Hz")
            print("\nDrücken Sie Enter für neue Konfiguration oder Strg+C zum Beenden...")
            
            input()  # Warten auf Benutzereingabe
            
    except KeyboardInterrupt:
        print("\n\nProgramm wird beendet...")
    except Exception as e:
        print(f"\nFehler: {e}")
    finally:
        cleanup()
        print("Ressourcen wurden freigegeben.")

if __name__ == "__main__":
    main()
