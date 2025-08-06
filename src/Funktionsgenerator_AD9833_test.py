#!/usr/bin/env python3
"""
Funktionsgenerator mit AD9833
"""

import lgpio
import spidev
import time

# AD9833 Register-Konstanten (basierend auf funktionierenden Projektdateien)
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
CONTROL_REG = 0x2000

# Wellenform-Konstanten
SINE_WAVE = 0x2000      # Sinuswelle
TRIANGLE_WAVE = 0x2002  # Dreieckswelle
SQUARE_WAVE = 0x2028    # Rechteckwelle

# Reset-Konstante (kritisch für korrekte Funktion!)
RESET = 0x2100          # Reset-Befehl wie in Filterkennlinie.ipynb

# SPI Einstellungen
SPI_BUS = 0
SPI_DEVICE = 0
SPI_FREQUENCY = 1000000  # 1 MHz

# FSYNC Pin (Chip Select)
FSYNC_PIN = 25  # GPIO-Pin für FSYNC

# PIN24 für Wellenform-Kontrolle
WAVEFORM_CONTROL_PIN = 24  # GPIO-Pin für zusätzliche Wellenform-Kontrolle

# Frequenz-Konstanten
FMCLK = 25000000  # 25 MHz Standardtaktfrequenz
MAX_FREQUENCY = 20000  # Maximale Ausgangsfrequenz: 20 kHz
MIN_FREQUENCY = 0.1    # Minimale Ausgangsfrequenz: 0.1 Hz

# Globale Variablen
gpio_handle = None
spi = None

def init_AD9833():
    """Initialisiert GPIO und SPI für AD9833"""
    global gpio_handle, spi
    
    try:
        print("Öffne GPIO-Chip 4...")
        # lgpio initialisieren - öffnet GPIO-Chip
        gpio_handle = lgpio.gpiochip_open(4)  # gpiochip4 für Raspberry Pi 5
        print("GPIO-Chip 4 geöffnet")

        print(f"Konfiguriere GPIO Pin {FSYNC_PIN} als Ausgang...")
        # FSYNC Pin als Ausgang konfigurieren (initial HIGH)
        lgpio.gpio_claim_output(gpio_handle, FSYNC_PIN, lgpio.SET)  
        print(f"GPIO Pin {FSYNC_PIN} konfiguriert")

        print(f"Konfiguriere GPIO Pin {WAVEFORM_CONTROL_PIN} als Ausgang...")
        # PIN24 für Wellenform-Kontrolle als Ausgang konfigurieren (initial LOW)
        lgpio.gpio_claim_output(gpio_handle, WAVEFORM_CONTROL_PIN, lgpio.CLEAR)  
        print(f"GPIO Pin {WAVEFORM_CONTROL_PIN} für Wellenform-Kontrolle konfiguriert")

        print("Initialisiere SPI...")
        # SPI initialisieren
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_DEVICE)
        spi.max_speed_hz = SPI_FREQUENCY
        spi.mode = 0b10  # SPI Modus 2 (CPOL=1, CPHA=0)
        print(f"SPI Bus {SPI_BUS}.{SPI_DEVICE} geöffnet (Geschwindigkeit: {SPI_FREQUENCY} Hz)")

        print("Führe initiales Reset durch...")
        # Initiales Reset des AD9833
        reset_success = write_to_AD9833(RESET)
        if not reset_success:
            print("Initiales Reset fehlgeschlagen")
            return False
            
        time.sleep(0.1)  # Warten bis Reset abgeschlossen
        print("Initiales Reset abgeschlossen")

        print("AD9833 erfolgreich initialisiert")
        return True
        
    except Exception as e:
        print(f"Fehler bei der Initialisierung: {e}")
        print(f"Details: {type(e).__name__}")
        cleanup_AD9833()
        return False

def set_waveform_control_pin(waveform):
    """
    Steuert PIN24 basierend auf der gewählten Wellenform
    
    Parameter:
    waveform: Wellenform-Konstante (SINE_WAVE, TRIANGLE_WAVE, SQUARE_WAVE)
    
    Logik:
    - Rechteckwelle (SQUARE_WAVE): PIN24 = HIGH
    - Sinus oder Dreieckswelle: PIN24 = LOW
    """
    global gpio_handle
    
    if gpio_handle is None:
        print("GPIO nicht initialisiert")
        return False
    
    try:
        if waveform == SQUARE_WAVE:
            # Rechteckwelle: PIN24 auf HIGH setzen
            lgpio.gpio_write(gpio_handle, WAVEFORM_CONTROL_PIN, lgpio.SET)
            print(f"PIN{WAVEFORM_CONTROL_PIN} auf HIGH gesetzt (Rechteckwelle)")
        else:
            # Sinus oder Dreieckswelle: PIN24 auf LOW setzen
            lgpio.gpio_write(gpio_handle, WAVEFORM_CONTROL_PIN, lgpio.CLEAR)
            print(f"PIN{WAVEFORM_CONTROL_PIN} auf LOW gesetzt (Sinus/Dreieckswelle)")
        
        return True
        
    except Exception as e:
        print(f"Fehler beim Setzen von PIN{WAVEFORM_CONTROL_PIN}: {e}")
        return False

def write_to_AD9833(data):
    """
    Sendet 16-Bit Daten an AD9833
    
    Kritische Timing-Sequenz:
    1. FSYNC auf LOW (Übertragung startet)
    2. 16-Bit Daten senden (High-Byte zuerst)
    3. FSYNC auf HIGH (Übertragung beendet)
    """
    if gpio_handle is None or spi is None:
        print("GPIO oder SPI nicht initialisiert")
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
        print(f"Frequenz {freq_hz} Hz außerhalb des gültigen Bereichs ({MIN_FREQUENCY}-{MAX_FREQUENCY} Hz)")
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
    Aktiviert die gewählte Wellenform und steuert PIN24
    
    WICHTIG: Dies muss NACH der Frequenzeinstellung erfolgen!
    Die Wellenform-Aktivierung beendet den Reset-Zustand.
    """
    waveform_names = {
        SINE_WAVE: "Sinuswelle",
        TRIANGLE_WAVE: "Dreieckswelle", 
        SQUARE_WAVE: "Rechteckwelle"
    }
    
    try:
        # PIN24 entsprechend der Wellenform setzen
        if not set_waveform_control_pin(waveform):
            print("Warnung: PIN24 konnte nicht gesetzt werden")
        
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
    print(f"Zielfrequenz: {freq_hz} Hz")
    
    try:
        # Schritt 1: Frequenz einstellen (beinhaltet Reset und Frequenz-Setup)
        print("Setze Frequenz...")
        if not set_ad9833_frequency(freq_hz):
            print("Frequenz-Einstellung fehlgeschlagen")
            return False
        
        # Schritt 2: Wellenform aktivieren (beendet Reset, startet Ausgabe, steuert PIN24)
        print("Aktiviere Wellenform und setze PIN24...")
        if not activate_waveform(waveform):
            print("Wellenform-Aktivierung fehlgeschlagen")
            return False
        
        print(f"AD9833 Konfiguration abgeschlossen")
        return True
        
    except Exception as e:
        print(f"Fehler bei der Konfiguration: {e}")
        return False

def cleanup_AD9833():
    """Räumt GPIO und SPI Ressourcen auf"""
    global gpio_handle, spi
    
    try:
        # AD9833 zurücksetzen vor dem Beenden
        if gpio_handle is not None and spi is not None:
            print("Setze AD9833 zurück...")
            write_to_AD9833(RESET)
            time.sleep(0.1)
        
        # GPIO freigeben
        if gpio_handle is not None:
            lgpio.gpio_free(gpio_handle, FSYNC_PIN)
            lgpio.gpio_free(gpio_handle, WAVEFORM_CONTROL_PIN)  # PIN24 auch freigeben
            lgpio.gpiochip_close(gpio_handle)
            gpio_handle = None
            print("GPIO Ressourcen freigegeben")
        
        # SPI schließen
        if spi is not None:
            spi.close()
            spi = None
            print("SPI Schnittstelle geschlossen")
            
    except Exception as e:
        print(f"Fehler beim Cleanup: {e}")

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
                continue
        except ValueError:
            print("Bitte geben Sie eine gültige Zahl ein.")
        except KeyboardInterrupt:
            print("\n\nProgramm durch Benutzer abgebrochen.")
            return None

def main():
    """Hauptfunktion des Funktionsgenerators - einmalige Konfiguration"""
    print("=" * 60)
    print("AD9833 FUNKTIONSGENERATOR")
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
        print(f"Frequenz: {freq} Hz")
        print(f"Wellenform: {waveform_name}")
        
        # PIN24 Status anzeigen
        if waveform_code == SQUARE_WAVE:
            print(f"PIN{WAVEFORM_CONTROL_PIN} wird auf HIGH gesetzt (Rechteckwelle)")
        else:
            print(f"PIN{WAVEFORM_CONTROL_PIN} wird auf LOW gesetzt (Sinus/Dreieckswelle)")

        config_success = configure_AD9833(freq, waveform_code)
        
        if config_success:
            print(f"\nFUNKTIONSGENERATOR ERFOLGREICH KONFIGURIERT:")
            print(f"Frequenz: {freq} Hz")
            print(f"Wellenform: {waveform_name}")
            pin_status = "HIGH" if waveform_code == SQUARE_WAVE else "LOW"
            print(f"PIN{WAVEFORM_CONTROL_PIN} Status: {pin_status}")
            print(f"Signal wird ausgegeben!")
            print(f"\nFür neue Einstellungen starten Sie das Programm erneut.")
        else:
            print("Konfiguration fehlgeschlagen")
            
        # Warten auf Benutzeraktion vor dem Beenden
        print("\n" + "─" * 40)
        input("Drücken Sie Enter zum Beenden...")
                
    except KeyboardInterrupt:
        print("\n\nProgramm durch Benutzer abgebrochen.")
    finally:
        cleanup_AD9833()

if __name__ == "__main__":
    main()