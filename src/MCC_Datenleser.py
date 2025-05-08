# -*- coding: utf-8 -*-

"""
MCC 118 Datenleser
Ermöglicht das Auslesen von echten Daten vom MCC 118 HAT für den digitalen Multimeter
"""

import time
import numpy as np
from daqhats import mcc118, OptionFlags, HatIDs, HatError

class MCC118Datenleser:
    """Klasse zum Auslesen von Daten vom MCC 118 HAT"""
    
    def __init__(self):
        # Versuche eine Verbindung zum MCC 118 HAT herzustellen
        self.hat_gefunden = False
        self.aktiver_kanal_spannung = 0  # Standard-Kanal für Spannungsmessungen
        self.aktiver_kanal_strom = 1     # Standard-Kanal für Strommessungen (mit Shunt-Widerstand)
        self.shunt_widerstand = 1.0      # Shunt-Widerstand für Strommessungen in Ohm
        
        # MCC 118 suchen und initialisieren
        self._init_mcc118()
    
    def _init_mcc118(self):
        """Initialisiert die Verbindung zum MCC 118 HAT"""
        try:
            # Verfügbare HATs auflisten
            hats = mcc118.hat_list(filter_by_id=HatIDs.MCC_118)
            if not hats:
                print("Kein MCC 118 HAT gefunden")
                self.hat_gefunden = False
                self.mcc = None
                return
            
            # Ersten gefundenen HAT verwenden
            self.address = hats[0].address
            self.mcc = mcc118(self.address)
            self.hat_gefunden = True
            print(f"MCC 118 HAT gefunden an Adresse {self.address}")
            
            # Konfiguration
            self.kanäle = self.mcc.info().NUM_AI_CHANNELS
            self.abtastrate = 1000  # Hz
            
            # Analogeingang konfigurieren
            # Die MCC 118 hat keinen expliziten Konfigurationsschritt vor dem Lesen
            
        except (HatError, Exception) as error:
            print(f"Fehler bei der Initialisierung des MCC 118: {error}")
            self.hat_gefunden = False
            self.mcc = None
    
    def get_spannung(self, bereich=20):
        """
        Liest eine Spannung vom MCC 118 HAT
        
        Parameter:
            bereich: Der Messbereich (wird für Skalenberechnung verwendet)
        
        Returns:
            float: Gemessene Spannung in Volt
        """
        if not self.hat_gefunden or self.mcc is None:
            # Bei fehlender Hardware simulierte Werte zurückgeben
            return self._simuliere_spannung(bereich)
        
        try:
            # MCC 118 hat einen festen Eingangsbereich von ±10V
            # Wir lesen den Kanal für Spannungsmessungen
            spannung = self.mcc.a_in_read(self.aktiver_kanal_spannung)
            
            # Optional: Bei Bedarf eigene Skalierung anwenden
            # Wenn der gewünschte Bereich kleiner als der MCC-Bereich ist, 
            # könnte man hier eine Software-Skalierung implementieren
            
            return spannung
            
        except (HatError, Exception) as error:
            print(f"Fehler beim Lesen der Spannung: {error}")
            return self._simuliere_spannung(bereich)
    
    def get_strom(self, bereich=1):
        """
        Liest einen Strom vom MCC 118 HAT
        Verwendet einen Shunt-Widerstand zur Strommessung
        
        Parameter:
            bereich: Der Messbereich (wird für Skalenberechnung verwendet)
        
        Returns:
            float: Berechneter Strom in Ampere
        """
        if not self.hat_gefunden or self.mcc is None:
            # Bei fehlender Hardware simulierte Werte zurückgeben
            return self._simuliere_strom(bereich)
        
        try:
            # Wir lesen die Spannung am Shunt-Widerstand
            spannung = self.mcc.a_in_read(self.aktiver_kanal_strom)
            
            # Strom berechnen nach dem Ohmschen Gesetz: I = U/R
            strom = spannung / self.shunt_widerstand
            
            return strom
            
        except (HatError, Exception) as error:
            print(f"Fehler beim Lesen des Stroms: {error}")
            return self._simuliere_strom(bereich)
    
    def set_spannung_kanal(self, kanal):
        """Setzt den Kanal für Spannungsmessungen"""
        if kanal >= 0 and kanal < 8:  # MCC 118 hat 8 Kanäle
            self.aktiver_kanal_spannung = kanal
    
    def set_strom_kanal(self, kanal):
        """Setzt den Kanal für Strommessungen"""
        if kanal >= 0 and kanal < 8:  # MCC 118 hat 8 Kanäle
            self.aktiver_kanal_strom = kanal
    
    def set_shunt_widerstand(self, wert):
        """Setzt den Wert des Shunt-Widerstands für Strommessungen"""
        if wert > 0:
            self.shunt_widerstand = wert
    
    def _simuliere_spannung(self, bereich):
        """Erzeugt eine simulierte Spannung wenn keine Hardware verfügbar ist"""
        # Einfache Simulation mit leichtem Rauschen um 5V
        rauschen = np.random.uniform(-0.05, 0.05)
        schwingung = 0.3 * np.sin(2 * np.pi * time.time() / 5)
        return 8.86 + rauschen + schwingung
    
    def _simuliere_strom(self, bereich):
        """Erzeugt einen simulierten Strom wenn keine Hardware verfügbar ist"""
        # Einfache Simulation mit leichtem Rauschen um 0.25A
        rauschen = np.random.uniform(-0.01, 0.01)
        schwingung = 0.05 * np.cos(2 * np.pi * time.time() / 5)
        return 0.25 + rauschen + schwingung

# Beispiel für die Verwendung
if __name__ == "__main__":
    datenleser = MCC118Datenleser()
    
    # Werte für 5 Sekunden ausgeben
    for _ in range(50):
        spannung = datenleser.get_spannung()
        strom = datenleser.get_strom()
        print(f"Spannung: {spannung:.3f} V, Strom: {strom:.3f} A")
        time.sleep(0.1)