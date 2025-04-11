#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simulationsdaten für den digitalen Multimeter
Erstellt simulierte Spannungs- und Strommesswerte für Tests
"""

import time
import random
import math

class DatenSimulator:
    def __init__(self):
        # Anfangswerte
        self._spannung = 8.86
        self._strom = 0.25
        # Simulationsparameter
        self._zeit = 0
        self._rauschen_amplitude = 0.05
        self._schwingung_amplitude = 0.3
        self._schwingung_periode = 5.0  # in Sekunden
    
    def get_spannung(self, bereich=20):
        """
        Gibt einen simulierten Spannungswert zurück (V)
        
        Parameter:
            bereich: Der ausgewählte Messbereich (Volt)
        """
        # Basiswert mit simuliertem Rauschen und langsamer Schwingung
        rauschen = random.uniform(-self._rauschen_amplitude, self._rauschen_amplitude)
        schwingung = self._schwingung_amplitude * math.sin(2 * math.pi * self._zeit / self._schwingung_periode)
        
        # Zeit aktualisieren
        self._zeit += 0.1
        
        # Wert innerhalb des Bereichs begrenzen
        wert = self._spannung + rauschen + schwingung
        if wert > bereich:
            wert = bereich
        elif wert < -bereich:
            wert = -bereich
            
        return wert
    
    def get_strom(self, bereich=1):
        """
        Gibt einen simulierten Stromwert zurück (A)
        
        Parameter:
            bereich: Der ausgewählte Messbereich (Ampere)
        """
        # Basiswert mit simuliertem Rauschen
        rauschen = random.uniform(-0.01, 0.01)
        schwingung = 0.05 * math.cos(2 * math.pi * self._zeit / self._schwingung_periode)
        
        # Wert innerhalb des Bereichs begrenzen
        wert = self._strom + rauschen + schwingung
        if wert > bereich:
            wert = bereich
        elif wert < -bereich:
            wert = -bereich
            
        return wert
    
    def set_spannung_basis(self, wert):
        """Setzt den Basiswert für die Spannung"""
        self._spannung = wert
    
    def set_strom_basis(self, wert):
        """Setzt den Basiswert für den Strom"""
        self._strom = wert

    def set_rauschen(self, amplitude):
        """Stellt die Rausch-Amplitude ein"""
        self._rauschen_amplitude = max(0, amplitude)

    def set_schwingung(self, amplitude, periode):
        """Stellt die Schwingungsparameter ein"""
        self._schwingung_amplitude = amplitude
        self._schwingung_periode = max(0.1, periode)

# Beispiel für die Verwendung
if __name__ == "__main__":
    simulator = DatenSimulator()
    
    # Werte für 5 Sekunden ausgeben
    for _ in range(50):
        spannung = simulator.get_spannung()
        strom = simulator.get_strom()
        print(f"Spannung: {spannung:.3f} V, Strom: {strom:.3f} A")
        time.sleep(0.1)
