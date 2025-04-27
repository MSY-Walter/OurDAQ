#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Funktionsgenerator für AD9833
Ein LabVIEW-ähnlicher Signalgenerator für Sinuswelle, Rechteckwelle und Dreieckwelle
Optimiert für den AD9833 DDS-Chip, der keine Sägezahnwelle und keine variable Duty-Cycle unterstützt
"""

import sys
import math
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                           QComboBox, QGroupBox, QSlider,
                           QDoubleSpinBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPalette, QColor
import pyqtgraph as pg


class WellenformVisualisierung(QWidget):
    """Widget zur Visualisierung der aktuellen Wellenform"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Layout erstellen
        layout = QVBoxLayout(self)
        
        # Pyqtgraph Plot-Widget
        self.plotWidget = pg.PlotWidget()
        self.plotWidget.setBackground('black')
        self.plotWidget.showGrid(x=True, y=True, alpha=0.3)
        self.plotWidget.setLabel('bottom', 'Zeit', units='s')
        self.plotWidget.setLabel('left', 'Amplitude', units='V')
        self.plot = self.plotWidget.plot(pen=pg.mkPen(color=(0, 210, 210), width=2))
        
        # Widget zum Layout hinzufügen
        layout.addWidget(self.plotWidget)
        
        # Daten initialisieren
        self.aktualisiere_daten(np.zeros(1000), 0, 1)
        
        # Aktuelle Periodenzahl für die Anzeige
        self.perioden_anzeige = 2.0
        
    def aktualisiere_daten(self, daten, t_start, t_end):
        """Aktualisiert die Visualisierung mit neuen Daten"""
        # Zeitachse erstellen
        zeit = np.linspace(t_start, t_end, len(daten))
        
        # Daten aktualisieren
        self.plot.setData(zeit, daten)
        
        # Achsen aktualisieren
        max_amplitude = max(abs(np.max(daten)), abs(np.min(daten)))
        self.plotWidget.setYRange(-max_amplitude*1.1, max_amplitude*1.1)
        
    def setze_frequenz_anzeige(self, frequenz):
        """Passt die X-Achse an, um eine konstante Anzahl von Perioden anzuzeigen"""
        if frequenz <= 0:
            frequenz = 0.1  # Mindestfrequenz, um Division durch Null zu vermeiden
            
        # Berechne Zeitfenster basierend auf Frequenz und gewünschter Periodenzahl
        periode = 1.0 / frequenz
        x_bereich = periode * self.perioden_anzeige
        
        # X-Achse aktualisieren
        self.plotWidget.setXRange(0, x_bereich)


class KontriolleBox(QGroupBox):
    """Eine Gruppe von Steuerelementen für den Funktionsgenerator"""
    
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.layout = QGridLayout(self)


class Funktionsgenerator(QMainWindow):
    """Hauptfenster des Funktionsgenerators"""
    
    def __init__(self):
        super().__init__()
        
        # Fenstereigenschaften festlegen
        self.setWindowTitle("Funktionsgenerator für AD9833")
        self.setGeometry(100, 100, 900, 700)  # Vergrößerte Startgröße
        
        # Signalgeneratorparameter
        self.wellenform = "Sinus"
        self.frequenz = 1000.0  # Hz
        self.amplitude = 5.0    # V
        self.offset = 0.0       # V
        self.phase = 0.0        # Grad
        self.abtastrate = 44100 # Hz
        self.signal_laenge = 1.0 # Sekunden
        
        # Aktuelle Daten
        self.update_daten()
        
        # Timer für Aktualisierung
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.aktualisiere_anzeige)
        
        # Generierungsstatus
        self.generierung_aktiv = False
        
        # UI einrichten
        self.setup_ui()
    
    def setup_ui(self):
        """Richtet die Benutzeroberfläche ein"""
        # Hauptwidget und Layout
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        
        # Wellenform-Visualisierung
        self.wellenform_visual = WellenformVisualisierung()
        self.wellenform_visual.setMinimumHeight(300)  # Größere Mindesthöhe
        haupt_layout.addWidget(self.wellenform_visual)
        
        # Haupteinstellungen in einem Grid
        einstellungen_gruppe = QGroupBox("Signaleinstellungen")
        einstellungen_layout = QGridLayout(einstellungen_gruppe)
        
        # Wellenform-Auswahl
        einstellungen_layout.addWidget(QLabel("Wellenform:"), 0, 0)
        self.wellenform_combo = QComboBox()
        self.wellenform_combo.addItems(["Sinus", "Rechteck", "Dreieck"])
        self.wellenform_combo.currentTextChanged.connect(self.wellenform_geaendert)
        einstellungen_layout.addWidget(self.wellenform_combo, 0, 1)
        
        # Frequenz-Einstellung
        einstellungen_layout.addWidget(QLabel("Frequenz (Hz):"), 1, 0)
        self.frequenz_spin = QDoubleSpinBox()
        self.frequenz_spin.setRange(0.1, 25000000.0)  # AD9833 kann bis zu 25 MHz
        self.frequenz_spin.setValue(self.frequenz)
        self.frequenz_spin.setSingleStep(10)
        self.frequenz_spin.setDecimals(1)
        self.frequenz_spin.valueChanged.connect(self.frequenz_geaendert)
        einstellungen_layout.addWidget(self.frequenz_spin, 1, 1)
        
        # Frequenz-Slider
        self.frequenz_slider = QSlider(Qt.Horizontal)
        self.frequenz_slider.setRange(1, 2000)  # 0.1 - 20000 Hz in logarithmischer Skala
        self.frequenz_slider.setValue(self.log_to_slider(self.frequenz))
        self.frequenz_slider.valueChanged.connect(self.frequenz_slider_geaendert)
        einstellungen_layout.addWidget(self.frequenz_slider, 2, 0, 1, 4)
        
        # Amplitude-Einstellung
        einstellungen_layout.addWidget(QLabel("Amplitude (V):"), 3, 0)
        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(0.0, 10.0)  # 0-10V Bereich für Amplitude
        self.amplitude_spin.setValue(self.amplitude)
        self.amplitude_spin.setSingleStep(0.1)
        self.amplitude_spin.valueChanged.connect(self.amplitude_geaendert)
        einstellungen_layout.addWidget(self.amplitude_spin, 3, 1)
        
        einstellungen_layout.addWidget(QLabel("Offset (V):"), 3, 2)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-10.0, 10.0)  # ±10V Bereich für Offset
        self.offset_spin.setValue(self.offset)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.valueChanged.connect(self.offset_geaendert)
        einstellungen_layout.addWidget(self.offset_spin, 3, 3)
        
        # Spannungsbegrenzungs-Label hinzufügen
        spannung_label = QLabel("Hinweis: Amplitude + |Offset| sollte 10V nicht überschreiten")
        spannung_label.setStyleSheet("color: yellow; font-style: italic;")
        einstellungen_layout.addWidget(spannung_label, 5, 0, 1, 4)
        
        einstellungen_layout.addWidget(QLabel("Phase (Grad):"), 4, 0)
        self.phase_spin = QDoubleSpinBox()
        self.phase_spin.setRange(0.0, 360.0)
        self.phase_spin.setValue(self.phase)
        self.phase_spin.setSingleStep(15)
        self.phase_spin.valueChanged.connect(self.phase_geaendert)
        einstellungen_layout.addWidget(self.phase_spin, 4, 1)
        
        haupt_layout.addWidget(einstellungen_gruppe)
        
        # Steuerungsbereich am unteren Rand
        steuerung_layout = QHBoxLayout()
        
        # Steuerungsbuttons
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet("background-color: green; color: white;")
        self.start_btn.setFixedSize(100, 40)
        self.start_btn.clicked.connect(self.starten)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: red; color: white;")
        self.stop_btn.setFixedSize(100, 40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stoppen)
        
        self.hilfe_btn = QPushButton("Hilfe")
        self.hilfe_btn.setFixedSize(100, 40)
        self.hilfe_btn.clicked.connect(self.hilfe_anzeigen)
        
        steuerung_layout.addStretch(1)
        steuerung_layout.addWidget(self.start_btn)
        steuerung_layout.addWidget(self.stop_btn)
        steuerung_layout.addWidget(self.hilfe_btn)
        steuerung_layout.addStretch(1)
        
        haupt_layout.addLayout(steuerung_layout)
        
        # Statusbar
        self.statusBar().showMessage("Bereit")
    
    def log_to_slider(self, frequenz):
        """Konvertiert Frequenz (Hz) zu logarithmischer Slider-Position"""
        min_freq = 0.1
        max_freq = 25000000.0  # Max. Frequenz des AD9833 (25 MHz)
        min_slider = 1
        max_slider = 2000
        
        # Logarithmische Skalierung
        logmin = math.log10(min_freq)
        logmax = math.log10(max_freq)
        logfreq = math.log10(frequenz)
        
        # Position berechnen
        position = (logfreq - logmin) / (logmax - logmin) * (max_slider - min_slider) + min_slider
        return int(position)
    
    def slider_to_log(self, position):
        """Konvertiert Slider-Position zu Frequenz (Hz) in logarithmischer Skala"""
        min_freq = 0.1
        max_freq = 25000000.0  # Max. Frequenz des AD9833 (25 MHz)
        min_slider = 1
        max_slider = 2000
        
        # Logarithmische Skalierung
        logmin = math.log10(min_freq)
        logmax = math.log10(max_freq)
        
        # Frequenz berechnen
        logfreq = (position - min_slider) / (max_slider - min_slider) * (logmax - logmin) + logmin
        return 10 ** logfreq
    
    def wellenform_geaendert(self, wellenform):
        """Wird aufgerufen, wenn die Wellenform geändert wird"""
        self.wellenform = wellenform
        
        # Daten aktualisieren
        self.update_daten()
        self.aktualisiere_anzeige()
    
    def frequenz_geaendert(self, frequenz):
        """Wird aufgerufen, wenn die Frequenz im Spinbox geändert wird"""
        self.frequenz = frequenz
        
        # Slider aktualisieren, ohne Signalschleifen zu erzeugen
        self.frequenz_slider.blockSignals(True)
        self.frequenz_slider.setValue(self.log_to_slider(frequenz))
        self.frequenz_slider.blockSignals(False)
        
        # Daten aktualisieren
        self.update_daten()
        self.aktualisiere_anzeige()
    
    def frequenz_slider_geaendert(self, position):
        """Wird aufgerufen, wenn der Frequenz-Slider bewegt wird"""
        frequenz = self.slider_to_log(position)
        
        # Spinbox aktualisieren, ohne Signalschleifen zu erzeugen
        self.frequenz_spin.blockSignals(True)
        self.frequenz_spin.setValue(round(frequenz, 1))
        self.frequenz_spin.blockSignals(False)
        
        # Frequenz setzen und Daten aktualisieren
        self.frequenz = frequenz
        self.update_daten()
        self.aktualisiere_anzeige()
    
    def amplitude_geaendert(self, amplitude):
        """Wird aufgerufen, wenn die Amplitude geändert wird"""
        self.amplitude = amplitude
        self.update_daten()
        self.aktualisiere_anzeige()
        
        # Überprüfen, ob die Gesamtausgangsspannung im gültigen Bereich liegt
        self.validate_voltage_range()
    
    def offset_geaendert(self, offset):
        """Wird aufgerufen, wenn der Offset geändert wird"""
        self.offset = offset
        self.update_daten()
        self.aktualisiere_anzeige()
        
        # Überprüfen, ob die Gesamtausgangsspannung im gültigen Bereich liegt
        self.validate_voltage_range()
    
    def validate_voltage_range(self):
        """Überprüft, ob die Kombination aus Amplitude und Offset gültig ist"""
        max_signal = self.amplitude + abs(self.offset)
        
        # Wenn das Signal den ±10V Bereich überschreiten könnte
        if max_signal > 10.0:
            self.statusBar().showMessage(f"Warnung: Amplitude + |Offset| = {max_signal:.2f}V überschreitet den ±10V Bereich!", 3000)
            
            # Ändere die Textfarbe im StatusBar, um die Warnung hervorzuheben
            self.statusBar().setStyleSheet("color: yellow;")
        else:
            # Normale Statusanzeige wiederherstellen
            self.statusBar().setStyleSheet("")
            
            # Normalen Status wiederherstellen (nach 3 Sekunden)
            QTimer.singleShot(3000, lambda: self.statusBar().showMessage(f"{self.wellenform} {self.frequenz:.1f} Hz, {self.amplitude:.2f} V"))
    
    def phase_geaendert(self, phase):
        """Wird aufgerufen, wenn die Phase geändert wird"""
        self.phase = phase
        self.update_daten()
        self.aktualisiere_anzeige()
    
    def abtastrate_geaendert(self, abtastrate):
        """Wird aufgerufen, wenn die Abtastrate geändert wird"""
        self.abtastrate = int(abtastrate)
        self.update_daten()
        self.aktualisiere_anzeige()
    
    def signallaenge_geaendert(self, laenge):
        """Wird aufgerufen, wenn die Signallänge geändert wird"""
        self.signal_laenge = laenge
        self.update_daten()
        self.aktualisiere_anzeige()
    
    def update_daten(self):
        """Berechnet die Signaldaten basierend auf den aktuellen Parametern"""
        # Berechnen von Samples basierend auf aktueller Frequenz
        # Bei höheren Frequenzen brauchen wir mehr Samples pro Periode für eine gute Darstellung
        # Wir berechnen genug Samples für eine vollständige Anzeige mit konstanter Auflösung
        
        # Bestimme die Anzahl der Perioden, die angezeigt werden sollen
        perioden_anzeige = 2.0  # Konstante Anzahl von Perioden in der Anzeige
        
        # Berechne die Dauer einer Periode
        periode_dauer = 1.0 / self.frequenz if self.frequenz > 0 else 1.0
        
        # Berechne die Gesamtdauer für die Darstellung
        anzeige_dauer = periode_dauer * perioden_anzeige
        
        # Stelle sicher, dass wir genügend Samples für eine flüssige Darstellung haben
        # Je höher die Frequenz, desto mehr Samples pro Periode benötigen wir
        min_samples_per_periode = 100  # Mindestanzahl von Samples pro Periode
        samples = int(max(min_samples_per_periode * perioden_anzeige, 
                          self.abtastrate * min(anzeige_dauer, self.signal_laenge)))
        
        # Zeitachse erstellen
        zeit = np.linspace(0, anzeige_dauer, samples, endpoint=False)
        
        # Phasenverschiebung in Radianten umrechnen
        phase_rad = self.phase * (math.pi / 180.0)
        
        # Wellenform generieren
        if self.wellenform == "Sinus":
            # Sinuswelle: A * sin(2π * f * t + φ) + offset
            self.daten = self.amplitude * np.sin(2 * np.pi * self.frequenz * zeit + phase_rad) + self.offset
        
        elif self.wellenform == "Rechteck":
            # Rechteckwelle mit festem 50% Duty-Cycle (AD9833 spezifisch)
            self.daten = self.amplitude * np.sign(np.sin(2 * np.pi * self.frequenz * zeit + phase_rad)) + self.offset
        
        elif self.wellenform == "Dreieck":
            # Dreieckwelle: 2A/π * arcsin(sin(2π * f * t + φ)) + offset
            self.daten = (2 * self.amplitude / np.pi) * np.arcsin(
                np.sin(2 * np.pi * self.frequenz * zeit + phase_rad)) + self.offset
    
    def aktualisiere_anzeige(self):
        """Aktualisiert die Wellenform-Visualisierung"""
        # Berechne die Anzeige-Dauer basierend auf der Frequenz
        perioden_anzeige = 2.0  # Konstante Anzahl von Perioden in der Anzeige
        if self.frequenz > 0:
            anzeige_dauer = perioden_anzeige / self.frequenz
        else:
            anzeige_dauer = self.signal_laenge
        
        # Aktualisiere Daten im Visualisierungs-Widget
        self.wellenform_visual.aktualisiere_daten(self.daten, 0, anzeige_dauer)
        
        # X-Achse entsprechend der Frequenz anpassen
        self.wellenform_visual.setze_frequenz_anzeige(self.frequenz)
        
        # Statusbar-Info aktualisieren
        status_text = f"{self.wellenform} {self.frequenz:.1f} Hz, {self.amplitude:.2f} V"
        self.statusBar().showMessage(status_text)
    
    def starten(self):
        """Startet die Signalgenerierung"""
        self.generierung_aktiv = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # Statusanzeige updaten
        self.statusBar().showMessage("Generiere Signal: " + self.statusBar().currentMessage())
        
        # Timer starten (für Animation, in echter Anwendung würde hier die AD9833-Steuerung gestartet)
        self.timer.start(100)
    
    def stoppen(self):
        """Stoppt die Signalgenerierung"""
        self.generierung_aktiv = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        # Timer stoppen
        self.timer.stop()
        
        # Statusanzeige updaten
        aktuelle_nachricht = self.statusBar().currentMessage()
        self.statusBar().showMessage(aktuelle_nachricht.replace("Generiere Signal: ", ""))
    
    def hilfe_anzeigen(self):
        """Zeigt Hilfeinformationen an"""
        from PyQt5.QtWidgets import QMessageBox
        
        hilfe_text = """
        Funktionsgenerator für AD9833
        
        Bedienung:
        1. Wählen Sie die gewünschte Wellenform (Sinus, Rechteck oder Dreieck)
        2. Stellen Sie Frequenz (bis zu 25 MHz), Amplitude, Offset und Phase ein
        3. Drücken Sie 'Start', um die Generierung zu starten
        4. Drücken Sie 'Stop', um die Generierung zu beenden
        
        Spannungsbegrenzungen:
        - Die Kombination aus Amplitude und Offset sollte im Bereich von ±10V liegen
        - Formel: Amplitude + |Offset| ≤ 10V für gültige Ausgangssignale
        
        AD9833 Eigenschaften:
        - Unterstützt Sinus-, Rechteck- und Dreieckwellen
        - Rechteckwellen haben festen 50% Duty-Cycle
        - Keine direkte Unterstützung für Sägezahnwellen
        - Frequenzbereich: 0.1 Hz bis 25 MHz
        
        Hinweis: Die generierten digitalen Signale können über den AD9833 DDS-Chip
        in analoge Signale umgewandelt werden.
        """
        
        QMessageBox.information(self, "Hilfe - Funktionsgenerator", hilfe_text)


class SignalDatenGenerator:
    """Klasse zur Erzeugung verschiedener Signalformen für die AD9833-Steuerung"""
    
    def __init__(self, abtastrate=44100):
        self.abtastrate = abtastrate
    
    def generiere_sinus(self, frequenz, amplitude, dauer, offset=0.0, phase=0.0):
        """Generiert eine Sinuswelle mit den angegebenen Parametern"""
        samples = int(self.abtastrate * dauer)
        t = np.linspace(0, dauer, samples, endpoint=False)
        phase_rad = phase * (np.pi / 180.0)
        return amplitude * np.sin(2 * np.pi * frequenz * t + phase_rad) + offset
    
    def generiere_rechteck(self, frequenz, amplitude, dauer, offset=0.0, phase=0.0):
        """Generiert eine Rechteckwelle mit festem 50% Duty-Cycle (AD9833-spezifisch)"""
        samples = int(self.abtastrate * dauer)
        t = np.linspace(0, dauer, samples, endpoint=False)
        
        # Phasenverschiebung in Sekunden
        phase_rad = phase * (np.pi / 180.0)
        
        # Rechteckwelle mit 50% Duty-Cycle erzeugen
        rechteck = amplitude * np.sign(np.sin(2 * np.pi * frequenz * t + phase_rad))
        
        return rechteck + offset
    
    def generiere_dreieck(self, frequenz, amplitude, dauer, offset=0.0, phase=0.0):
        """Generiert eine Dreieckwelle mit den angegebenen Parametern"""
        samples = int(self.abtastrate * dauer)
        t = np.linspace(0, dauer, samples, endpoint=False)
        phase_rad = phase * (np.pi / 180.0)
        
        # Dreieckwelle über arcsin(sin) erzeugen
        return (2 * amplitude / np.pi) * np.arcsin(np.sin(2 * np.pi * frequenz * t + phase_rad)) + offset


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Dem modernen LabVIEW-Stil ähnlich
    app.setStyle("Fusion")
    
    # Dunkles Farbschema für LabVIEW-ähnliches Aussehen
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)
    
    # Anwendung erstellen und anzeigen
    funktionsgenerator = Funktionsgenerator()
    funktionsgenerator.show()
    
    sys.exit(app.exec_())