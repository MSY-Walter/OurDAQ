#!/usr/bin/env python3
"""
Funktionsgenerator mit AD9833
"""

import lgpio
import time
import sys

class AD9833:
    """Klasse zur Steuerung des AD9833 DDS-Generators"""
    
    # AD9833 Register-Adressen
    CONTROL_REG = 0x2000
    FREQ0_REG = 0x4000
    FREQ1_REG = 0x8000
    PHASE0_REG = 0xC000
    PHASE1_REG = 0xE000
    
    # Wellenform-Konstanten
    SINUS = 0x0000
    DREIECK = 0x0002
    RECHTECK = 0x0020
    
    # Kontroll-Bits
    B28 = 0x2000    # 28-Bit Frequenz laden
    HLB = 0x1000    # MSB/LSB Auswahl
    FSEL = 0x0800   # Frequenzregister auswählen
    PSEL = 0x0400   # Phasenregister auswählen
    RESET = 0x0100  # Reset
    SLEEP1 = 0x0080 # Sleep (interne Takt)
    SLEEP12 = 0x0040 # Sleep (DAC)
    OPBITEN = 0x0020 # Rechteck-Ausgang
    DIV2 = 0x0008   # Div2
    MODE = 0x0002   # Dreieck-Ausgang
    
    def __init__(self, spi_kanal=0, spi_geschwindigkeit=1000000, fcn_pin=25):
        """
        Initialisiert den AD9833
        
        Args:
            spi_kanal: SPI-Kanal (0 oder 1)
            spi_geschwindigkeit: SPI-Geschwindigkeit in Hz
            fcn_pin: GPIO-Pin für FCN (Chip Select)
        """
        self.fcn_pin = fcn_pin
        self.mclk = 25000000  # 25MHz Referenztakt
        
        # GPIO initialisieren
        self.gpio_handle = lgpio.gpiochip_open(0)
        if self.gpio_handle < 0:
            raise RuntimeError("Fehler beim Öffnen des GPIO-Chips")
            
        # FCN Pin als Ausgang konfigurieren
        lgpio.gpio_claim_output(self.gpio_handle, self.fcn_pin, 1)
        
        # SPI initialisieren
        self.spi_handle = lgpio.spi_open(0, spi_kanal, spi_geschwindigkeit, 0)
        if self.spi_handle < 0:
            raise RuntimeError("Fehler beim Öffnen der SPI-Schnittstelle")
        
        # AD9833 initialisieren
        self._initialisieren()
    
    def _initialisieren(self):
        """Initialisiert den AD9833 mit Standardwerten"""
        # Reset setzen
        self._schreibe_register(self.CONTROL_REG | self.RESET)
        time.sleep(0.001)
        
        # B28-Bit für 28-Bit Frequenzmodus setzen
        self._schreibe_register(self.CONTROL_REG | self.B28)
    
    def _schreibe_register(self, daten):
        """
        Schreibt Daten in ein AD9833-Register
        
        Args:
            daten: 16-Bit Registerwert
        """
        # FCN auf LOW setzen (Chip auswählen)
        lgpio.gpio_write(self.gpio_handle, self.fcn_pin, 0)
        time.sleep(0.00001)  # 10µs warten
        
        # 16-Bit Daten über SPI senden (MSB zuerst)
        daten_bytes = [(daten >> 8) & 0xFF, daten & 0xFF]
        lgpio.spi_write(self.spi_handle, daten_bytes)
        
        # FCN auf HIGH setzen (Chip freigeben)
        time.sleep(0.00001)  # 10µs warten
        lgpio.gpio_write(self.gpio_handle, self.fcn_pin, 1)
        time.sleep(0.00001)  # 10µs warten
    
    def setze_frequenz(self, frequenz):
        """
        Setzt die Ausgangsfrequenz
        
        Args:
            frequenz: Gewünschte Frequenz in Hz (0.1 Hz bis 12.5 MHz)
        """
        if frequenz < 0.1 or frequenz > 12500000:
            raise ValueError("Frequenz muss zwischen 0.1 Hz und 12.5 MHz liegen")
        
        # Frequenzregister-Wert berechnen
        freq_reg = int((frequenz * (2**28)) / self.mclk)
        
        # Frequenz in zwei 14-Bit Wörtern senden
        lsb = freq_reg & 0x3FFF
        msb = (freq_reg >> 14) & 0x3FFF
        
        # LSB senden
        self._schreibe_register(self.FREQ0_REG | lsb)
        # MSB senden
        self._schreibe_register(self.FREQ0_REG | msb)
    
    def setze_wellenform(self, wellenform_typ):
        """
        Setzt die Wellenform
        
        Args:
            wellenform_typ: 'sinus', 'dreieck' oder 'rechteck'
        """
        if wellenform_typ.lower() == 'sinus':
            control_wert = self.CONTROL_REG | self.B28
        elif wellenform_typ.lower() == 'dreieck':
            control_wert = self.CONTROL_REG | self.B28 | self.MODE
        elif wellenform_typ.lower() == 'rechteck':
            control_wert = self.CONTROL_REG | self.B28 | self.OPBITEN | self.DIV2
        else:
            raise ValueError("Ungültige Wellenform. Verwenden Sie 'sinus', 'dreieck' oder 'rechteck'")
        
        self._schreibe_register(control_wert)
        print(f"Wellenform auf '{wellenform_typ}' gesetzt.")
    
    def ausschalten(self):
        """Schaltet den AD9833-Ausgang aus"""
        self._schreibe_register(self.CONTROL_REG | self.SLEEP12 | self.SLEEP1)
        print("AD9833 Ausgang ausgeschaltet.")
    
    def einschalten(self):
        """Schaltet den AD9833-Ausgang ein"""
        self._schreibe_register(self.CONTROL_REG | self.B28)
        print("AD9833 Ausgang eingeschaltet.")
    
    def schließen(self):
        """Schließt alle Verbindungen und gibt Ressourcen frei"""
        self.ausschalten()
        lgpio.spi_close(self.spi_handle)
        lgpio.gpio_free(self.gpio_handle, self.fcn_pin)
        lgpio.gpiochip_close(self.gpio_handle)


def main():
    """Hauptprogramm mit Benutzerinteraktion"""
    print("=" * 50)
    print("AD9833 Wellenformgenerator")
    print("Raspberry Pi 5 mit lgpio")
    print("=" * 50)
    
    try:
        # AD9833 initialisieren
        print("Initialisiere AD9833...")
        generator = AD9833(fcn_pin=25)
        print("AD9833 erfolgreich initialisiert!\n")
        
        while True:
            print("\nVerfügbare Wellenformen:")
            print("1. Sinus")
            print("2. Dreieck")
            print("3. Rechteck")
            print("4. Beenden")
            
            auswahl = input("\nBitte wählen Sie eine Wellenform (1-4): ").strip()
            
            if auswahl == '4':
                print("Programm wird beendet...")
                break
            elif auswahl not in ['1', '2', '3']:
                print("Ungültige Auswahl! Bitte wählen Sie 1-4.")
                continue
            
            # Wellenform-Mapping
            wellenformen = {'1': 'sinus', '2': 'dreieck', '3': 'rechteck'}
            gewählte_wellenform = wellenformen[auswahl]
            
            # Frequenz eingeben
            try:
                frequenz_str = input("Gewünschte Frequenz eingeben (0.1 Hz - 12.5 MHz): ").strip()
                frequenz = float(frequenz_str)
                
                if frequenz < 0.1 or frequenz > 12500000:
                    print("Fehler: Frequenz muss zwischen 0.1 Hz und 12.5 MHz liegen!")
                    continue
                
            except ValueError:
                print("Fehler: Ungültige Frequenzeingabe!")
                continue
            
            # Konfiguration bestätigen
            print(f"\nKonfiguration:")
            print(f"Wellenform: {gewählte_wellenform.capitalize()}")
            print(f"Frequenz: {frequenz} Hz")
            
            bestätigung = input("Konfiguration anwenden? (j/n): ").strip().lower()
            
            if bestätigung in ['j', 'ja', 'y', 'yes']:
                try:
                    # Wellenform und Frequenz setzen
                    generator.setze_wellenform(gewählte_wellenform)
                    generator.setze_frequenz(frequenz)
                    generator.einschalten()
                    
                    print(f"\n✓ {gewählte_wellenform.capitalize()}-Welle mit {frequenz} Hz wird ausgegeben!")
                    print("Drücken Sie Enter für eine neue Konfiguration...")
                    input()
                    
                except Exception as e:
                    print(f"Fehler bei der Konfiguration: {e}")
            else:
                print("Konfiguration abgebrochen.")
    
    except KeyboardInterrupt:
        print("\n\nProgramm durch Benutzer unterbrochen.")
    except Exception as e:
        print(f"Fehler: {e}")
    finally:
        # Aufräumen
        try:
            generator.schließen()
            print("Ressourcen freigegeben.")
        except:
            pass


if __name__ == "__main__":
    main()