# -*- coding: utf-8 -*-

"""
Signal Generator für das Oszilloskop
Erzeugt verschiedene Testsignale für die Simulation ohne echte Hardware
"""

import numpy as np
import math
import random
import time

class SignalGenerator:
    """Klasse zur Erzeugung verschiedener Testsignale für das Oszilloskop"""
    
    def __init__(self):
        # Standard-Signalparameter für Kanal 1
        self.signal1_typ = "Sinus"
        self.signal1_frequenz = 1000  # Hz
        self.signal1_amplitude = 2.0  # V
        self.signal1_offset = 0.0     # V
        self.signal1_phase = 0.0      # Grad
        self.signal1_rauschen = 0.05  # Rausch-Amplitude in V
        
        # Standard-Signalparameter für Kanal 2
        self.signal2_typ = "Rechteck"
        self.signal2_frequenz = 200   # Hz
        self.signal2_amplitude = 1.5  # V
        self.signal2_offset = 0.0     # V
        self.signal2_phase = 0.0      # Grad
        self.signal2_rauschen = 0.05  # Rausch-Amplitude in V
        
        # Zeitbasis für langsame Änderungen
        self.start_zeit = time.time()
        self.drift_faktor = 0.01
        
        # Flag für zufällige Signalstörungen
        self.stoerungen_aktiv = True
    
    def get_signal1(self, zeit_array):
        """
        Gibt Signal für Kanal 1 zurück
        
        Parameter:
            zeit_array: Array mit Zeitpunkten in Sekunden
        """
        # Zeitverschiebung für langsame Änderungen
        zeit_diff = time.time() - self.start_zeit
        
        # Leichte Frequenzänderungen simulieren
        aktuelle_frequenz = self.signal1_frequenz * (1 + math.sin(zeit_diff * 0.1) * self.drift_faktor * 0.5)
        
        # Basiswert erzeugen
        if self.signal1_typ == "Sinus":
            signal = self.sinus(zeit_array, aktuelle_frequenz, self.signal1_amplitude, 
                              self.signal1_offset, self.signal1_phase)
        elif self.signal1_typ == "Rechteck":
            signal = self.rechteck(zeit_array, aktuelle_frequenz, self.signal1_amplitude, 
                                self.signal1_offset, self.signal1_phase)
        elif self.signal1_typ == "Dreieck":
            signal = self.dreieck(zeit_array, aktuelle_frequenz, self.signal1_amplitude, 
                               self.signal1_offset, self.signal1_phase)
        elif self.signal1_typ == "Sägezahn":
            signal = self.saegezahn(zeit_array, aktuelle_frequenz, self.signal1_amplitude, 
                                 self.signal1_offset, self.signal1_phase)
        else:
            # Standardmäßig Sinus zurückgeben
            signal = self.sinus(zeit_array, aktuelle_frequenz, self.signal1_amplitude, 
                              self.signal1_offset, self.signal1_phase)
        
        # Rauschen hinzufügen
        if self.signal1_rauschen > 0:
            signal += np.random.normal(0, self.signal1_rauschen, size=len(zeit_array))
        
        # Zufällige Störungen hinzufügen (z.B. Spikes oder kurze Aussetzer)
        if self.stoerungen_aktiv and random.random() < 0.02:  # 2% Chance pro Aufruf
            # Zufälligen Index wählen
            idx = random.randint(0, len(zeit_array) - 1)
            # Entweder Spike oder Aussetzer
            if random.random() < 0.5:
                # Spike: ~2x Amplitude
                signal[idx] = self.signal1_amplitude * 2 * random.choice([-1, 1]) + self.signal1_offset
            else:
                # Aussetzer: Signal kurz auf Offset-Wert
                aussetzer_länge = min(len(zeit_array) - idx, random.randint(5, 20))
                signal[idx:idx+aussetzer_länge] = self.signal1_offset
        
        return signal
    
    def get_signal2(self, zeit_array):
        """
        Gibt Signal für Kanal 2 zurück
        
        Parameter:
            zeit_array: Array mit Zeitpunkten in Sekunden
        """
        # Zeitverschiebung für langsame Änderungen
        zeit_diff = time.time() - self.start_zeit
        
        # Leichte Amplitudenänderungen simulieren
        aktuelle_amplitude = self.signal2_amplitude * (1 + math.sin(zeit_diff * 0.2) * self.drift_faktor)
        
        # Basiswert erzeugen
        if self.signal2_typ == "Sinus":
            signal = self.sinus(zeit_array, self.signal2_frequenz, aktuelle_amplitude, 
                              self.signal2_offset, self.signal2_phase)
        elif self.signal2_typ == "Rechteck":
            signal = self.rechteck(zeit_array, self.signal2_frequenz, aktuelle_amplitude, 
                                self.signal2_offset, self.signal2_phase)
        elif self.signal2_typ == "Dreieck":
            signal = self.dreieck(zeit_array, self.signal2_frequenz, aktuelle_amplitude, 
                               self.signal2_offset, self.signal2_phase)
        elif self.signal2_typ == "Sägezahn":
            signal = self.saegezahn(zeit_array, self.signal2_frequenz, aktuelle_amplitude, 
                                 self.signal2_offset, self.signal2_phase)
        else:
            # Standardmäßig Rechteck zurückgeben
            signal = self.rechteck(zeit_array, self.signal2_frequenz, aktuelle_amplitude, 
                                self.signal2_offset, self.signal2_phase)
        
        # Rauschen hinzufügen
        if self.signal2_rauschen > 0:
            signal += np.random.normal(0, self.signal2_rauschen, size=len(zeit_array))
        
        return signal
    
    def set_signal_params(self, kanal, typ=None, frequenz=None, amplitude=None, 
                         offset=None, phase=None, rauschen=None):
        """
        Setzt die Parameter für das angegebene Signal
        
        Parameter:
            kanal: 1 oder 2 (Kanalnummer)
            typ: "Sinus", "Rechteck", "Dreieck" oder "Sägezahn"
            frequenz: Frequenz in Hz
            amplitude: Amplitude in V
            offset: DC-Offset in V
            phase: Phasenverschiebung in Grad
            rauschen: Rausch-Amplitude in V
        """
        if kanal == 1:
            if typ is not None:
                self.signal1_typ = typ
            if frequenz is not None:
                self.signal1_frequenz = frequenz
            if amplitude is not None:
                self.signal1_amplitude = amplitude
            if offset is not None:
                self.signal1_offset = offset
            if phase is not None:
                self.signal1_phase = phase
            if rauschen is not None:
                self.signal1_rauschen = rauschen
        elif kanal == 2:
            if typ is not None:
                self.signal2_typ = typ
            if frequenz is not None:
                self.signal2_frequenz = frequenz
            if amplitude is not None:
                self.signal2_amplitude = amplitude
            if offset is not None:
                self.signal2_offset = offset
            if phase is not None:
                self.signal2_phase = phase
            if rauschen is not None:
                self.signal2_rauschen = rauschen
    
    def set_drift(self, faktor):
        """
        Setzt den Drift-Faktor für langsame Änderungen
        
        Parameter:
            faktor: Drift-Faktor (0 = keine Änderungen, 1 = maximale Änderungen)
        """
        self.drift_faktor = max(0, min(1, faktor))
    
    def set_stoerungen(self, aktiv):
        """
        Aktiviert oder deaktiviert zufällige Signalstörungen
        
        Parameter:
            aktiv: True oder False
        """
        self.stoerungen_aktiv = aktiv
    
    def reset_zeit(self):
        """Setzt die Referenzzeit zurück"""
        self.start_zeit = time.time()
    
    def sinus(self, zeit, frequenz, amplitude, offset, phase):
        """Erzeugt eine Sinuswelle"""
        # Phase in Radianten umrechnen
        phase_rad = phase * (math.pi / 180.0)
        return amplitude * np.sin(2 * np.pi * frequenz * zeit + phase_rad) + offset
    
    def rechteck(self, zeit, frequenz, amplitude, offset, phase):
        """Erzeugt eine Rechteckwelle"""
        # Phase in Radianten umrechnen
        phase_rad = phase * (math.pi / 180.0)
        return amplitude * np.sign(np.sin(2 * np.pi * frequenz * zeit + phase_rad)) + offset
    
    def dreieck(self, zeit, frequenz, amplitude, offset, phase):
        """Erzeugt eine Dreieckwelle"""
        # Phase in Radianten umrechnen
        phase_rad = phase * (math.pi / 180.0)
        return (2 * amplitude / np.pi) * np.arcsin(np.sin(2 * np.pi * frequenz * zeit + phase_rad)) + offset
    
    def saegezahn(self, zeit, frequenz, amplitude, offset, phase):
        """Erzeugt eine Sägezahnwelle"""
        # Phase in Radianten umrechnen
        phase_rad = phase * (math.pi / 180.0)
        # Sägezahn-Funktion: 2 * (t * f - floor(0.5 + t * f))
        t_phase = zeit + phase_rad / (2 * np.pi * frequenz)
        return amplitude * (2 * (t_phase * frequenz - np.floor(0.5 + t_phase * frequenz))) + offset


# Beispiel für die Verwendung
if __name__ == "__main__":
    # Dieses Skript kann auch als Standalone-Programm für Testzwecke verwendet werden
    
    import matplotlib.pyplot as plt
    
    # SignalGenerator erstellen
    generator = SignalGenerator()
    
    # Zeitpunkte für die Signalgenerierung
    zeit = np.linspace(0, 0.01, 1000)  # 10ms mit 1000 Punkten
    
    # Signale erzeugen
    signal1 = generator.get_signal1(zeit)
    signal2 = generator.get_signal2(zeit)
    
    # Signale plotten
    plt.figure(figsize=(10, 6))
    
    plt.subplot(2, 1, 1)
    plt.plot(zeit * 1000, signal1, 'g-')  # Zeit in ms für die Anzeige
    plt.title('Kanal 1: ' + generator.signal1_typ)
    plt.xlabel('Zeit (ms)')
    plt.ylabel('Spannung (V)')
    plt.grid(True)
    
    plt.subplot(2, 1, 2)
    plt.plot(zeit * 1000, signal2, 'y-')  # Zeit in ms für die Anzeige
    plt.title('Kanal 2: ' + generator.signal2_typ)
    plt.xlabel('Zeit (ms)')
    plt.ylabel('Spannung (V)')
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()