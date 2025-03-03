"""
Modul zur Generierung von simulierten Messdaten
für Diodenkennlinien und Temperaturmessungen.
"""

from datetime import datetime
import random
import numpy as np

class DiodenSimulation:
    """
    Klasse zur Simulation von Diodenkennlinien.
    """
    
    def __init__(self):
        self.temperatur = 25.0  # Starttemperatur in °C
        self.sperrspannung = 0.7  # Typische Sperrspannung in V
        
    def generiere_kennlinie(self, anzahl_punkte=100):
        """
        Generiert eine simulierte Diodenkennlinie.
        
        Args:
            anzahl_punkte (int): Anzahl der Datenpunkte
            
        Returns:
            tuple: (spannungen, stroeme) in V und A
        """
        spannungen = np.linspace(0, self.sperrspannung, anzahl_punkte)
        stroeme = self._berechne_diodenstrom(spannungen)
        
        # Füge Rauschen hinzu
        stroeme += np.random.normal(0, 1e-6, anzahl_punkte)
        
        return spannungen, stroeme
        
    def _berechne_diodenstrom(self, spannungen):
        """
        Berechnet den Diodenstrom nach der Shockley-Gleichung.
        
        Args:
            spannungen (np.array): Angelegte Spannungen
            
        Returns:
            np.array: Diodenströme
        """
        is_s = 1e-12  # Sättigungssperrstrom
        n = 1.0       # Emissionskoeffizient
        vt = 0.0257   # Temperaturspannung bei 25°C
        
        return is_s * (np.exp(spannungen / (n * vt)) - 1)
        
    def aktualisiere_temperatur(self, delta_temp):
        """
        Aktualisiert die Temperatur der Diode.
        
        Args:
            delta_temp (float): Temperaturänderung in °C
        """
        self.temperatur += delta_temp
        # Anpassung der Sperrspannung basierend auf Temperatur
        self.sperrspannung -= 0.002 * delta_temp

class TemperaturSensor:
    """
    Klasse zur Simulation eines Temperatursensors.
    """
    
    def __init__(self):
        self.temperatur = 25.0  # Starttemperatur in °C
        
    def lese_temperatur(self):
        """
        Liest die aktuelle Temperatur mit simuliertem Rauschen.
        
        Returns:
            float: Temperatur in °C
        """
        return self.temperatur + random.gauss(0, 0.1)
        
    def setze_temperatur(self, neue_temp):
        """
        Setzt die Temperatur des Sensors.
        
        Args:
            neue_temp (float): Neue Temperatur in °C
        """
        self.temperatur = neue_temp


class DataGenerator:
    """
    Klasse zur Generierung von Echtzeit-Messdaten.
    """
    
    def __init__(self):
        self.diode = DiodenSimulation()
        self.temp_sensor = TemperaturSensor()
        self.historie = []
        
    def generiere_messdaten(self):
        """
        Generiert kontinuierlich Messdaten im 0.1-Sekunden-Takt.
        
        Returns:
            dict: Aktuelle Messdaten mit Zeitstempel
        """
        # Generiere zufällige Spannung und Strom
        spannung = random.uniform(0.6, 0.8)
        strom = self.diode._berechne_diodenstrom(spannung)
        
        # Temperaturänderung basierend auf Strom
        temp_aenderung = strom * 0.001
        self.temp_sensor.setze_temperatur(
            self.temp_sensor.temperatur + temp_aenderung
        )
        
        # Erstelle Datenpunkt
        daten = {
            'zeit': datetime.now().strftime('%H:%M:%S.%f'),
            'spannung': round(spannung, 4),
            'strom': round(strom, 8),
            'temperatur': round(self.temp_sensor.lese_temperatur(), 2)
        }
        
        # Füge Daten zur Historie hinzu
        self.historie.append(daten)
        if len(self.historie) > 50:  # Begrenze Historie auf 50 Punkte
            self.historie.pop(0)
            
        return daten
