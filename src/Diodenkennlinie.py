#!/usr/bin/env python3
"""
Diodenkennlinie Messung
"""

import lgpio
import spidev
import time
import numpy as np
import matplotlib.pyplot as plt
import sys
import signal

class DiodenmessungMitLgpio:
    def __init__(self, gpio_chip=0, cs_dac_pin=8, cs_adc_pin=7):
        """
        Initialisierung der Diodenmessung
        
        Args:
            gpio_chip: GPIO Chip Nummer (standardmäßig 0)
            cs_dac_pin: CS Pin für DAC (standardmäßig Pin 8)  
            cs_adc_pin: CS Pin für ADC (standardmäßig Pin 7)
        """
        self.gpio_chip_num = gpio_chip
        self.cs_dac_pin = cs_dac_pin
        self.cs_adc_pin = cs_adc_pin
        self.gpio_chip = None
        self.spi_dac = None
        self.spi_adc = None
        
        # Messkonfiguration
        self.vorwiderstand = 1000.0  # 1kΩ Vorwiderstand in Ohm
        self.vref_dac = 3.3          # DAC Referenzspannung in V
        self.vref_adc = 3.3          # ADC Referenzspannung in V
        self.dac_aufloesung = 4096   # 12-bit DAC
        self.adc_aufloesung = 4096   # 12-bit ADC
        
        # Signal Handler für sauberes Beenden
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Signal Handler für sauberes Beenden"""
        print(f"\nSignal {signum} empfangen. Beende Messung sauber...")
        self.schliessen()
        sys.exit(0)
    
    def gpio_cleanup_force(self):
        """Erzwungene GPIO Bereinigung - falls Pins hängen bleiben"""
        print("Führe GPIO Notfall-Bereinigung durch...")
        try:
            # Versuche verschiedene GPIO Chips
            for chip_num in range(5):
                try:
                    temp_handle = lgpio.gpiochip_open(chip_num)
                    # Versuche beide CS Pins freizugeben
                    for pin in [self.cs_dac_pin, self.cs_adc_pin]:
                        try:
                            lgpio.gpio_free(temp_handle, pin)
                        except:
                            pass
                    lgpio.gpiochip_close(temp_handle)
                except:
                    continue
        except Exception as e:
            print(f"Warnung bei GPIO Notfall-Bereinigung: {e}")
    
    def initialisieren(self):
        """Hardware initialisieren"""
        try:
            print("Initialisiere GPIO und SPI...")
            
            # GPIO Notfall-Bereinigung vor Start
            self.gpio_cleanup_force()
            time.sleep(0.1)
            
            # GPIO Chip öffnen
            self.gpio_chip = lgpio.gpiochip_open(self.gpio_chip_num)
            
            # CS Pins als Output konfigurieren
            # Versuche erst freizugeben falls bereits belegt
            for pin in [self.cs_dac_pin, self.cs_adc_pin]:
                try:
                    lgpio.gpio_free(self.gpio_chip, pin)
                except:
                    pass  # Pin war nicht belegt
                
                # Pin als Output konfigurieren
                lgpio.gpio_claim_output(self.gpio_chip, pin, lgpio.SET_PULL_NONE)
                lgpio.gpio_write(self.gpio_chip, pin, 1)  # CS initial high
            
            # SPI Verbindungen initialisieren
            self.spi_dac = spidev.SpiDev()
            self.spi_dac.open(0, 0)  # SPI Bus 0, Device 0 für DAC
            self.spi_dac.max_speed_hz = 1000000  # 1 MHz
            self.spi_dac.mode = 0
            
            self.spi_adc = spidev.SpiDev()
            self.spi_adc.open(0, 1)  # SPI Bus 0, Device 1 für ADC
            self.spi_adc.max_speed_hz = 1000000  # 1 MHz
            self.spi_adc.mode = 0
            
            print("GPIO und SPI erfolgreich initialisiert.")
            return True
            
        except Exception as e:
            print(f"Fehler bei der Initialisierung: {e}")
            self.schliessen()
            return False
    
    def dac_schreiben(self, spannung):
        """
        Spannung an DAC ausgeben
        
        Args:
            spannung: Ausgangsspannung in Volt (0.0 bis self.vref_dac)
        """
        try:
            # Spannung in DAC Wert umrechnen
            if spannung < 0:
                spannung = 0
            elif spannung > self.vref_dac:
                spannung = self.vref_dac
            
            dac_wert = int((spannung / self.vref_dac) * (self.dac_aufloesung - 1))
            
            # MCP4822 Protokoll: 12-bit DAC
            # Bit 15: /SHDN = 1 (aktiv)
            # Bit 14: /GA = 1 (1x Verstärkung) 
            # Bit 13: BUF = 1 (gepuffert)
            # Bit 12: Kanal A = 0
            # Bit 11-0: Daten
            kommando = 0x7000 | (dac_wert & 0x0FFF)
            
            # 16-bit Kommando in 2 Bytes aufteilen
            high_byte = (kommando >> 8) & 0xFF
            low_byte = kommando & 0xFF
            
            # CS low, Daten senden, CS high
            lgpio.gpio_write(self.gpio_chip, self.cs_dac_pin, 0)
            time.sleep(0.000001)  # 1µs warten
            self.spi_dac.xfer2([high_byte, low_byte])
            time.sleep(0.000001)  # 1µs warten
            lgpio.gpio_write(self.gpio_chip, self.cs_dac_pin, 1)
            
        except Exception as e:
            print(f"Fehler beim DAC schreiben: {e}")
    
    def adc_lesen(self, kanal=0):
        """
        Spannung vom ADC lesen
        
        Args:
            kanal: ADC Kanal (0 oder 1)
            
        Returns:
            float: Gemessene Spannung in Volt
        """
        try:
            # MCP3202 Protokoll: 12-bit ADC
            # Start bit = 1, Single/Diff = 1, Channel = kanal, MSBF = 1
            if kanal == 0:
                kommando = 0x68  # 01101000
            else:
                kommando = 0x78  # 01111000
            
            # CS low, Daten austauschen, CS high
            lgpio.gpio_write(self.gpio_chip, self.cs_adc_pin, 0)
            time.sleep(0.000001)  # 1µs warten
            antwort = self.spi_adc.xfer2([kommando, 0x00, 0x00])
            time.sleep(0.000001)  # 1µs warten
            lgpio.gpio_write(self.gpio_chip, self.cs_adc_pin, 1)
            
            # 12-bit Wert extrahieren
            adc_wert = ((antwort[1] & 0x0F) << 8) | antwort[2]
            
            # In Spannung umrechnen
            spannung = (adc_wert / (self.adc_aufloesung - 1)) * self.vref_adc
            
            return spannung
            
        except Exception as e:
            print(f"Fehler beim ADC lesen: {e}")
            return 0.0
    
    def mehrfach_messen(self, kanal, anzahl_messungen=10):
        """
        Mehrfache ADC Messung für bessere Genauigkeit
        
        Args:
            kanal: ADC Kanal
            anzahl_messungen: Anzahl der Einzelmessungen
            
        Returns:
            float: Gemittelte Spannung
        """
        messungen = []
        for _ in range(anzahl_messungen):
            messungen.append(self.adc_lesen(kanal))
            time.sleep(0.001)  # 1ms zwischen Messungen
        
        return np.mean(messungen)
    
    def diodenkennlinie_messen(self):
        """Hauptmessfunktion für Diodenkennlinie"""
        if not self.initialisieren():
            return None, None, None
        
        try:
            print("\n=== Diodenkennlinie Messung ===")
            
            # Benutzer Parameter abfragen
            print("Standard-Parameter:")
            print(f"- Vorwiderstand: {self.vorwiderstand} Ω")
            print(f"- Maximale DAC Spannung: {self.vref_dac} V")
            
            verwende_standard = input("Standard-Parameter verwenden? (j/n): ").lower().strip()
            
            if verwende_standard != 'j':
                try:
                    self.vorwiderstand = float(input("Vorwiderstand in Ω: "))
                    max_spannung = float(input(f"Maximale Spannung (0 bis {self.vref_dac}V): "))
                    max_spannung = min(max_spannung, self.vref_dac)
                except ValueError:
                    print("Ungültige Eingabe, verwende Standard-Werte.")
                    max_spannung = 2.0
            else:
                max_spannung = 2.0  # Sichere Maximalspannung für Dioden
            
            anzahl_punkte = 50  # Fixe Anzahl für konsistente Messungen
            
            print(f"\nStarte Messung mit {anzahl_punkte} Punkten bis {max_spannung}V...")
            print("Drücke Ctrl+C zum Abbrechen.\n")
            
            # Messwerte Arrays
            eingestellte_spannungen = []
            diodenspannungen = []
            stroeme = []
            
            # Spannungsschritte berechnen
            spannungsschritte = np.linspace(0, max_spannung, anzahl_punkte)
            
            for i, spannung in enumerate(spannungsschritte):
                # DAC Spannung einstellen
                self.dac_schreiben(spannung)
                time.sleep(0.05)  # 50ms Einschwingzeit
                
                # Spannungen messen
                v_vorwiderstand = self.mehrfach_messen(0, 5)  # Spannung über Vorwiderstand
                v_diode = self.mehrfach_messen(1, 5)         # Spannung über Diode
                
                # Strom berechnen (Ohmsches Gesetz)
                if v_vorwiderstand > 0:
                    strom = v_vorwiderstand / self.vorwiderstand
                else:
                    strom = 0.0
                
                # Daten speichern
                eingestellte_spannungen.append(spannung)
                diodenspannungen.append(v_diode)
                stroeme.append(strom)
                
                # Fortschritt anzeigen
                if i % 5 == 0 or i == anzahl_punkte - 1:
                    print(f"Punkt {i+1:2d}/{anzahl_punkte}: "
                          f"U_DAC={spannung:.3f}V, U_Diode={v_diode:.3f}V, "
                          f"I={strom*1000:.3f}mA")
            
            print("\nMessung abgeschlossen. Erstelle Diagramm...")
            
            # Ergebnisse plotten
            self.ergebnisse_plotten(eingestellte_spannungen, diodenspannungen, stroeme, max_spannung)
            
            return eingestellte_spannungen, diodenspannungen, stroeme
            
        except KeyboardInterrupt:
            print("\nMessung abgebrochen.")
            self.dac_schreiben(0)
        except Exception as e:
            print(f"Fehler: {e}")
            self.dac_schreiben(0)
        finally:
            self.schliessen()
    
    def ergebnisse_plotten(self, eingestellt, diode, strom, max_spannung):
        """Messergebnisse grafisch darstellen"""
        plt.figure(figsize=(15, 5))
        
        # Subplot 1: Klassische Diodenkennlinie
        plt.subplot(1, 3, 1)
        plt.plot(diode, np.array(strom) * 1000, marker='.', markersize=8)
        plt.xlabel("Spannung über Diode (V)")
        plt.ylabel("Strom durch Diode (mA)")
        plt.title("Diodenkennlinie")
        plt.grid(True, alpha=0.3)
        plt.xlim(0, max(diode) * 1.1 if diode else 1)
        
        # Subplot 2: Eingestellte Spannung vs Strom
        plt.subplot(1, 3, 2)
        plt.plot(eingestellt, np.array(strom) * 1000, marker='.', color='orange', markersize=8)
        plt.xlabel("Eingestellte DAC Spannung (V)")
        plt.ylabel("Strom durch Diode (mA)")
        plt.title("DAC Spannung vs. Strom")
        plt.xlim(0, max_spannung)
        plt.grid(True, alpha=0.3)
        
        # Subplot 3: Logarithmische Darstellung
        plt.subplot(1, 3, 3)
        # Nur positive Ströme für Log-Darstellung
        positive_indices = np.array(strom) > 1e-9  # 1nA Schwelle
        if np.any(positive_indices):
            plt.semilogy(np.array(diode)[positive_indices], 
                        np.array(strom)[positive_indices] * 1000, 
                        marker='.', color='red', markersize=8)
            plt.xlabel("Spannung über Diode (V)")
            plt.ylabel("Strom durch Diode (mA, log)")
            plt.title("Diodenkennlinie (logarithmisch)")
            plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
        
        # Zusätzliche Analyse ausgeben
        self.analyse_ausgeben(diode, strom)
    
    def analyse_ausgeben(self, spannungen, stroeme):
        """Zusätzliche Analyse der Diodenkennlinie"""
        print("\n=== Dioden-Analyse ===")
        
        # Durchlassspannung bei verschiedenen Strömen finden
        stroeme_ma = np.array(stroeme) * 1000
        spannungen = np.array(spannungen)
        
        ziel_stroeme = [0.1, 1.0, 10.0, 20.0]  # mA
        
        for ziel_strom in ziel_stroeme:
            # Nächstgelegenen Strom finden
            if max(stroeme_ma) >= ziel_strom:
                idx = np.argmin(np.abs(stroeme_ma - ziel_strom))
                print(f"Durchlassspannung bei {ziel_strom:4.1f} mA: {spannungen[idx]:.3f} V")
        
        # Maximale Werte
        max_strom_idx = np.argmax(stroeme_ma)
        print(f"\nMaximaler Strom: {stroeme_ma[max_strom_idx]:.3f} mA bei {spannungen[max_strom_idx]:.3f} V")
        
        # Widerstand im linearen Bereich schätzen
        if len(stroeme) > 5:
            # Letzte 5 Punkte für Widerstandsberechnung
            delta_v = spannungen[-1] - spannungen[-5]
            delta_i = stroeme[-1] - stroeme[-5]
            if delta_i != 0:
                dynamischer_widerstand = delta_v / delta_i
                print(f"Dynamischer Widerstand (letzte 5 Punkte): {dynamischer_widerstand:.1f} Ω")
    
    def schliessen(self):
        """Ressourcen freigeben"""
        print("Gebe Ressourcen frei...")
        
        try:
            # DAC auf 0 setzen
            if self.spi_dac:
                self.dac_schreiben(0)
        except:
            pass
        
        try:
            # SPI Verbindungen schließen
            if self.spi_dac:
                self.spi_dac.close()
            if self.spi_adc:
                self.spi_adc.close()
        except:
            pass
        
        try:
            # GPIO Pins freigeben
            if self.gpio_chip:
                for pin in [self.cs_dac_pin, self.cs_adc_pin]:
                    try:
                        lgpio.gpio_free(self.gpio_chip, pin)
                    except:
                        pass
                
                # GPIO Chip schließen
                lgpio.gpiochip_close(self.gpio_chip)
        except:
            pass
        
        print("Ressourcen erfolgreich freigegeben.")

def main():
    """Hauptprogramm"""
    print("=== Diodenkennlinie Messsystem ===")
    print("Verwendet lgpio für robuste GPIO Verwaltung")
    print("Drücke Ctrl+C zum Beenden\n")
    
    messgeraet = DiodenmessungMitLgpio()
    
    try:
        messgeraet.diodenkennlinie_messen()
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
    finally:
        messgeraet.schliessen()

if __name__ == "__main__":
    main()