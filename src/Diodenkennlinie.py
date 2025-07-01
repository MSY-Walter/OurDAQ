# -*- coding: utf-8 -*-
from __future__ import print_function
import spidev
import time
import lgpio
import matplotlib.pyplot as plt
import numpy as np

class DiodenmessungMitLgpio:
    def __init__(self):
        """Initialisierung mit lgpio und SPI ADC"""
        # SPI für DAC Setup
        self.spi_dac = spidev.SpiDev()
        self.spi_dac.open(0, 0)  # SPI Bus 0, Device 0 für DAC
        self.spi_dac.max_speed_hz = 1000000
        self.spi_dac.mode = 0b00
        
        # SPI für ADC Setup (separater CS Pin)
        self.spi_adc = spidev.SpiDev()
        self.spi_adc.open(0, 1)  # SPI Bus 0, Device 1 für ADC
        self.spi_adc.max_speed_hz = 1000000
        
        # GPIO Setup mit lgpio
        self.gpio_chip = lgpio.gpiochip_open(0)
        self.cs_dac_pin = 22    # CS für DAC
        self.cs_adc_pin = 8     # CS für ADC (falls nicht über SPI Device gesteuert)
        
        # GPIO Pins als Ausgänge konfigurieren
        lgpio.gpio_claim_output(self.gpio_chip, self.cs_dac_pin, lgpio.SET_PULL_NONE)
        lgpio.gpio_claim_output(self.gpio_chip, self.cs_adc_pin, lgpio.SET_PULL_NONE)
        
        # CS Pins initial auf HIGH setzen
        lgpio.gpio_write(self.gpio_chip, self.cs_dac_pin, 1)
        lgpio.gpio_write(self.gpio_chip, self.cs_adc_pin, 1)
        
        # Konstanten
        self.MAX_DAC_VALUE = 4095
        self.MAX_DAC_SPANNUNG = 10.7  # Volt
        self.ADC_REFERENZ = 3.3       # Volt für ADC
        self.ADC_AUFLOESUNG = 4095    # 12-Bit ADC
        
    def dac_schreiben(self, wert):
        """DAC Wert über SPI setzen"""
        assert 0 <= wert <= self.MAX_DAC_VALUE
        
        # DAC Steuerregister aufbauen (MCP4821 Format)
        steuerung = 0
        steuerung |= 0 << 15  # Kanal A
        steuerung |= 1 << 14  # Gepuffert
        steuerung |= 0 << 13  # Verstärkung = 2x (0)
        steuerung |= 1 << 12  # Normal Betrieb
        
        daten = steuerung | (wert & 0xFFF)
        high_byte = (daten >> 8) & 0xFF
        low_byte = daten & 0xFF
        
        print(f"DAC schreiben: {daten:016b} (0x{high_byte:02X} {low_byte:02X})")
        
        # SPI Übertragung mit manueller CS Steuerung
        lgpio.gpio_write(self.gpio_chip, self.cs_dac_pin, 0)
        self.spi_dac.xfer2([high_byte, low_byte])
        lgpio.gpio_write(self.gpio_chip, self.cs_dac_pin, 1)
    
    def adc_lesen(self, kanal):
        """ADC Kanal lesen (MCP3208 Beispiel)"""
        if kanal < 0 or kanal > 7:
            raise ValueError("ADC Kanal muss zwischen 0 und 7 liegen")
        
        # MCP3208 Kommando zusammenstellen
        kommando = [1, (8 + kanal) << 4, 0]
        
        # SPI Übertragung
        lgpio.gpio_write(self.gpio_chip, self.cs_adc_pin, 0)
        antwort = self.spi_adc.xfer2(kommando)
        lgpio.gpio_write(self.gpio_chip, self.cs_adc_pin, 1)
        
        # 12-Bit Wert extrahieren
        adc_wert = ((antwort[1] & 3) << 8) + antwort[2]
        spannung = (adc_wert / self.ADC_AUFLOESUNG) * self.ADC_REFERENZ
        return spannung
    
    def spannungsteiler_kalibrieren(self):
        """Spannungsteiler zur Anpassung an ADC Eingangsspannung kalibrieren"""
        print("Spannungsteiler Kalibrierung...")
        print("Bitte 5V an ADC Kanal 0 anlegen für Kalibrierung")
        input("Enter drücken wenn bereit...")
        
        gemessene_spannung = self.adc_lesen(0)
        tatsaechliche_spannung = float(input("Tatsächliche angelegte Spannung (V): "))
        
        self.spannungsteiler_faktor = tatsaechliche_spannung / gemessene_spannung
        print(f"Kalibrierungsfaktor: {self.spannungsteiler_faktor:.3f}")
        return self.spannungsteiler_faktor
    
    def diodenkennlinie_messen(self):
        """Komplette Diodenkennlinie aufnehmen"""
        print("### Diodenkennlinie Messung mit lgpio ###\n")
        
        try:
            # Parameter eingeben
            r_serie = float(input("Wert des Serienwiderstands in Ohm (z.B. 100): "))
            anzahl_punkte = int(input("Anzahl der Spannungspunkte (mind. 15): "))
            
            if anzahl_punkte < 15:
                print("Mindestens 15 Punkte erforderlich – setze auf 15.")
                anzahl_punkte = 15
            
            spannung_max = float(input(f"Maximale Spannung in V (max {self.MAX_DAC_SPANNUNG} V): "))
            if spannung_max > self.MAX_DAC_SPANNUNG:
                print(f"Begrenze auf {self.MAX_DAC_SPANNUNG} V.")
                spannung_max = self.MAX_DAC_SPANNUNG
            
            # Optional: Spannungsteiler kalibrieren
            kalibrieren = input("Spannungsteiler kalibrieren? (j/n): ").lower().startswith('j')
            if kalibrieren:
                self.spannungsteiler_kalibrieren()
            else:
                self.spannungsteiler_faktor = 1.0
            
            # Messdaten-Listen
            eingestellte_spannungen = []
            diodenspannungen = []
            stroeme = []
            
            print(f"\nMCC 118 durch ADC Kanal 0 ersetzt.")
            print("Verbindung: Diode Kathode an ADC Kanal 0")
            print("Messung läuft...\n")
            
            for i in range(anzahl_punkte):
                # DAC Spannung berechnen und setzen
                spannung_dac = i * spannung_max / (anzahl_punkte - 1)
                dac_wert = int((spannung_dac / self.MAX_DAC_SPANNUNG) * self.MAX_DAC_VALUE)
                self.dac_schreiben(dac_wert)
                
                # Einschwingzeit abwarten
                time.sleep(0.1)
                
                # Spannung über Diode messen (mehrfach für bessere Genauigkeit)
                spannungen = []
                for _ in range(5):
                    raw_spannung = self.adc_lesen(0)
                    kalibrierte_spannung = raw_spannung * self.spannungsteiler_faktor
                    spannungen.append(kalibrierte_spannung)
                    time.sleep(0.01)
                
                spannung_diode = np.mean(spannungen)
                
                # Strom durch Diode berechnen
                strom = (spannung_dac - spannung_diode) / r_serie
                
                # Werte speichern
                eingestellte_spannungen.append(spannung_dac)
                diodenspannungen.append(spannung_diode)
                stroeme.append(strom)
                
                print(f"Punkt {i+1:2d}: DAC={spannung_dac:.3f}V | "
                      f"Diode={spannung_diode:.5f}V | "
                      f"Strom={strom:.6f}A ({strom*1000:.3f}mA)")
            
            # DAC auf 0 zurücksetzen
            self.dac_schreiben(0)
            
            print("\nMessung abgeschlossen. Erstelle Diagramm...")
            
            # Ergebnisse plotten
            self.ergebnisse_plotten(eingestellte_spannungen, diodenspannungen, stroeme, spannung_max)
            
            return eingestellte_spannungen, diodenspannungen, stroeme
            
        except KeyboardInterrupt:
            print("\nMessung abgebrochen.")
            self.dac_schreiben(0)
        except Exception as e:
            print(f"Fehler: {e}")
            self.dac_schreiben(0)
    
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
        self.dac_schreiben(0)  # DAC auf 0 setzen
        self.spi_dac.close()
        self.spi_adc.close()
        lgpio.gpiochip_close(self.gpio_chip)
        print("GPIO und SPI Ressourcen freigegeben.")

def main():
    """Hauptprogramm"""
    messgeraet = DiodenmessungMitLgpio()
    
    try:
        messgeraet.diodenkennlinie_messen()
    finally:
        messgeraet.schliessen()

if __name__ == "__main__":
    main()