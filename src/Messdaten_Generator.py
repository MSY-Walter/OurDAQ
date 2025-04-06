"""
Modul zur Generierung von simulierten Messdaten
für Diodenkennlinien.
"""

from datetime import datetime
import random
import numpy as np

class DiodenSimulation:
    """
    Klasse zur Simulation von Diodenkennlinien.
    """
    
    def __init__(self):
        self.sperrspannung = 0.7  # Typische Sperrspannung in V
        
    def generiere_kennlinie(self, anzahl_punkte=100):
        spannungen = np.linspace(0, self.sperrspannung, anzahl_punkte)
        stroeme = self._berechne_diodenstrom(spannungen)
        
        # Füge Rauschen hinzu
        stroeme += np.random.normal(0, 1e-6, anzahl_punkte)
        
        return spannungen, stroeme
        
    def _berechne_diodenstrom(self, spannungen):
        is_s = 1e-12  # Sättigungssperrstrom
        n = 1.0       # Emissionskoeffizient
        vt = 0.0257   # Temperaturspannung bei 25°C
        
        return is_s * (np.exp(spannungen / (n * vt)) - 1)

class DataGenerator:
    """
    Klasse zur Generierung von Echtzeit-Messdaten.
    """
    
    def __init__(self):
        self.diode = DiodenSimulation()
        self.historie = []
        
    def generiere_messdaten(self):
        # Generiere zufällige Spannung und Strom
        spannung = random.uniform(0.6, 0.8)
        strom = self.diode._berechne_diodenstrom(spannung)
        
        # Erstelle Datenpunkt
        daten = {
            'zeit': datetime.now().strftime('%H:%M:%S.%f'),
            'spannung': round(spannung, 4),
            'strom': round(strom, 8),
        }
        
        # Füge Daten zur Historie hinzu
        self.historie.append(daten)
        if len(self.historie) > 50:  # Begrenze Historie auf 50 Punkte
            self.historie.pop(0)
            
        return daten
