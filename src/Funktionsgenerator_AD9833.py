# -*- coding: utf-8 -*-
"""
Funktionsgenerator für AD9833 DDS (Direct Digital Synthesis)
Optimiert für MCC 118 DAQ HAT auf Raspberry Pi
"""

import sys
import time

# Simulation Mode aktivieren wenn --simulate übergeben wird
SIMULATION_MODE = '--simulate' in sys.argv

# Hardware Imports - nur wenn nicht im Simulation Mode
if not SIMULATION_MODE:
    try:
        import lgpio
        import spidev
    except ImportError as e:
        print(f"Fehler beim Importieren von lgpio oder spidev: {e}")
        print("Wechsle zu Simulation Mode")
        SIMULATION_MODE = True

# AD9833 Konstanten
FREQ0_REG = 0x4000      # Frequenz Register 0
PHASE0_REG = 0xC000     # Phase Register 0
CONTROL_REG = 0x2000    # Kontroll Register
RESET = 0x2100          # Reset Kommando

# Wellenform Konstanten für AD9833
SINE_WAVE = 0x2000      # Sinus: D5=0, D1=0, D3=0
TRIANGLE_WAVE = 0x2002  # Dreieck: D5=0, D1=1, D3=0  
SQUARE_WAVE = 0x2020    # Rechteck: D5=1, D1=0, D3=0

# Frequenz Konstanten
FMCLK = 25000000        # Master Clock Frequenz (25 MHz)
MAX_FREQUENCY = 20000   # Maximale Ausgangsfrequenz (20 kHz)
MIN_FREQUENCY = 0.1     # Minimale Ausgangsfrequenz (0.1 Hz)

# Hardware Konfiguration
SPI_BUS = 0             # SPI Bus Nummer
SPI_DEVICE = 0          # SPI Device Nummer  
SPI_MAX_SPEED = 2000000 # SPI Geschwindigkeit (2 MHz)
FSYNC_PIN = 22          # GPIO Pin für FSYNC Signal

# Globale Variablen für Hardware-Handles
gpio_handle = None
spi = None

def init_AD9833():
    """
    Initialisiert die Hardware-Verbindung zum AD9833
    Konfiguriert GPIO für FSYNC und öffnet SPI-Verbindung
    """
    global gpio_handle, spi
    
    if SIMULATION_MODE:
        print("SIMULATION: Hardware-Initialisierung")
        gpio_handle = "simulation"
        spi = "simulation"
        return True
    
    try:
        # GPIO Chip öffnen
        gpio_handle = lgpio.gpiochip_open(0)
        if gpio_handle < 0:
            print("Fehler: GPIO Chip konnte nicht geöffnet werden")
            return False
        
        # FSYNC Pin als Ausgang konfigurieren
        lgpio.gpio_claim_output(gpio_handle, FSYNC_PIN, lgpio.SET)
        print("GPIO erfolgreich initialisiert")
        
        # SPI öffnen
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_DEVICE)
        spi.max_speed_hz = SPI_MAX_SPEED
        spi.mode = 2  # SPI Mode 2 (CPOL=1, CPHA=0)
        print("SPI erfolgreich initialisiert")
        
        return True
        
    except Exception as e:
        print(f"Fehler bei der Hardware-Initialisierung: {e}")
        return False

def write_to_AD9833(data):
    """
    Sendet 16-Bit Daten an den AD9833 über SPI
    Implementiert das korrekte Timing-Protokoll:
    1. FSYNC auf LOW (Übertragung startet)
    2. 16-Bit Daten senden (High-Byte zuerst)
    3. FSYNC auf HIGH (Übertragung beendet)
    """
    if SIMULATION_MODE:
        print(f"SIMULATION: Schreibe 0x{data:04X} an AD9833")
        return True
    
    if gpio_handle is None or spi is None:
        print("Fehler: GPIO oder SPI nicht initialisiert")
        return False
    
    try:
        # FSYNC auf LOW setzen (Übertragung startet)
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, lgpio.CLEAR)
        
        # 16-Bit Daten in zwei 8-Bit Bytes aufteilen und senden
        high_byte = (data >> 8) & 0xFF
        low_byte = data & 0xFF
        spi.xfer2([high_byte, low_byte])
        
        # FSYNC auf HIGH setzen (Übertragung beendet)
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, lgpio.SET)
        
        return True
        
    except Exception as e:
        print(f"Fehler beim Schreiben an AD9833: {e}")
        return False

def set_ad9833_frequency(freq_hz):
    """
    Stellt die Ausgangsfrequenz des AD9833 ein
    
    KRITISCHE SEQUENZ basierend auf funktionierender Filterkennlinie.ipynb:
    1. Reset
    2. Lower 14 Bits vom Frequenzwort 
    3. Upper 14 Bits vom Frequenzwort
    4. Wellenform aktivieren
    
    Diese exakte Reihenfolge ist ESSENTIELL für korrekte Funktion!
    """
    if not (MIN_FREQUENCY <= freq_hz <= MAX_FREQUENCY):
        print(f"Fehler: Frequenz {freq_hz} Hz außerhalb des gültigen Bereichs ({MIN_FREQUENCY}-{MAX_FREQUENCY} Hz)")
        return False
    
    try:
        # Frequenzwort berechnen (28-Bit)
        freq_word = int((freq_hz * (2**28)) / FMCLK)
        
        # KRITISCHE ÜBERTRAGUNGSSEQUENZ (genau wie in funktionierenden Code!)
        # 1. Reset aktivieren
        if not write_to_AD9833(RESET):
            return False
        
        # 2. Lower 14 Bits schreiben
        if not write_to_AD9833(FREQ0_REG | (freq_word & 0x3FFF)):
            return False
        
        # 3. Upper 14 Bits schreiben  
        if not write_to_AD9833(FREQ0_REG | ((freq_word >> 14) & 0x3FFF)):
            return False
        
        print(f"Frequenz auf {freq_hz} Hz eingestellt (Frequenzwort: 0x{freq_word:08X})")
        return True
        
    except Exception as e:
        print(f"Fehler beim Setzen der Frequenz: {e}")
        return False

def activate_waveform(waveform):
    """
    Aktiviert die gewählte Wellenform
    
    WICHTIG: Dies muss NACH der Frequenzeinstellung erfolgen!
    Die Wellenform-Aktivierung beendet den Reset-Zustand.
    """
    waveform_names = {
        SINE_WAVE: "Sinuswelle",
        TRIANGLE_WAVE: "Dreieckswelle", 
        SQUARE_WAVE: "Rechteckwelle"
    }
    
    try:
        # Wellenform aktivieren (beendet gleichzeitig Reset-Zustand)
        if not write_to_AD9833(waveform):
            return False
        
        waveform_name = waveform_names.get(waveform, f"Unbekannt (0x{waveform:04X})")
        print(f"Wellenform {waveform_name} aktiviert")
        return True
        
    except Exception as e:
        print(f"Fehler beim Aktivieren der Wellenform: {e}")
        return False

def configure_AD9833(freq_hz, waveform):
    """
    Komplette Konfiguration des AD9833 mit korrekter Sequenz
    
    Diese Funktion implementiert die exakte Sequenz aus der
    funktionierenden Filterkennlinie.ipynb
    """
    print(f"Starte AD9833 Konfiguration...")
    print(f"   Zielfrequenz: {freq_hz} Hz")
    
    try:
        # Schritt 1: Frequenz einstellen (beinhaltet Reset und Frequenz-Setup)
        print("   Setze Frequenz...")
        if not set_ad9833_frequency(freq_hz):
            print("   Frequenz-Einstellung fehlgeschlagen")
            return False
        
        # Schritt 2: Wellenform aktivieren (beendet Reset, startet Ausgabe)
        print("   Aktiviere Wellenform...")
        if not activate_waveform(waveform):
            print("   Wellenform-Aktivierung fehlgeschlagen")
            return False
        
        print(f"   AD9833 Konfiguration abgeschlossen")
        return True
        
    except Exception as e:
        print(f"   Fehler bei der Konfiguration: {e}")
        return False

def cleanup_AD9833():
    """Räumt GPIO und SPI Ressourcen auf"""
    global gpio_handle, spi
    
    if SIMULATION_MODE:
        print("SIMULATION: Ressourcen-Cleanup")
        return
    
    try:
        # AD9833 zurücksetzen vor dem Beenden
        if gpio_handle is not None and spi is not None:
            print("Setze AD9833 zurück...")
            write_to_AD9833(RESET)
            time.sleep(0.1)
        
        # GPIO freigeben
        if gpio_handle is not None:
            lgpio.gpio_free(gpio_handle, FSYNC_PIN)
            lgpio.gpiochip_close(gpio_handle)
            gpio_handle = None
            print("GPIO Ressourcen freigegeben")
        
        # SPI schließen
        if spi is not None:
            spi.close()
            spi = None
            print("SPI Schnittstelle geschlossen")
            
    except Exception as e:
        print(f"Warnung: Fehler beim Cleanup: {e}")

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
        except KeyboardInterrupt:
            print("\n\nProgramm durch Benutzer abgebrochen.")
            return None

def main():
    """Hauptfunktion des Funktionsgenerators - einmalige Konfiguration"""
    print("=" * 60)
    print("    AD9833 FUNKTIONSGENERATOR")
    print("=" * 60)
    
    try:
        # Hardware initialisieren
        print("\nInitialisiere Hardware...")
        if not init_AD9833():
            print("Initialisierung fehlgeschlagen. Programm wird beendet.")
            input("Drücken Sie Enter zum Beenden...")
            return
        
        # Wellenform auswählen
        print("\nSchritt 1: Wellenform auswählen")
        waveform_code, waveform_name = get_waveform_choice()
        print(f"Gewählt: {waveform_name}")
        
        # Frequenz eingeben
        print("\nSchritt 2: Frequenz eingeben")
        freq = get_frequency()
        if freq is None:  # Benutzer hat abgebrochen
            print("Frequenzeingabe abgebrochen.")
            input("Drücken Sie Enter zum Beenden...")
            return
        
        print(f"Gewählt: {freq} Hz")
        
        # Konfiguration durchführen
        print(f"\nSchritt 3: AD9833 konfigurieren")
        print(f"   Frequenz: {freq} Hz")
        print(f"   Wellenform: {waveform_name}")
        
        config_success = configure_AD9833(freq, waveform_code)
        
        if config_success:
            print(f"\nFUNKTIONSGENERATOR ERFOLGREICH KONFIGURIERT:")
            print(f"   Frequenz: {freq} Hz")
            print(f"   Wellenform: {waveform_name}")
            print(f"   Signal wird ausgegeben!")
            print(f"\nFür neue Einstellungen starten Sie das Programm erneut.")
        else:
            print("Konfiguration fehlgeschlagen")
            
        # Warten auf Benutzeraktion vor dem Beenden
        print("\n" + "─" * 40)
        input("Drücken Sie Enter zum Beenden...")
                
    except KeyboardInterrupt:
        print("\n\nProgramm durch Benutzer abgebrochen.")
        
    except Exception as e:
        print(f"\nUnerwarteter Fehler: {e}")
        input("Drücken Sie Enter zum Beenden...")
        
    finally:
        # Aufräumen
        print("\nRäume Ressourcen auf...")
        cleanup_AD9833()
        print("Programm beendet.")

if __name__ == "__main__":
    main()