# -*- coding: utf-8 -*-

"""
Oszilloskop für MCC 118
Ein LabVIEW-ähnliches Oszilloskop für zwei Kanäle
Mit Trigger-Funktionalität, Zeitbasis-Einstellung und CSV-Datenspeicherung
"""

import sys
import time
import os
import csv
from datetime import datetime
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                           QComboBox, QGroupBox, QStatusBar, QCheckBox,
                           QFileDialog, QMessageBox, QSlider, QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPalette, QColor, QFont
import pyqtgraph as pg  # Für die Diagrammanzeige

# Importiere den Datensimulator (für Testzwecke ohne echte Hardware)
from Signal_Generator import SignalGenerator

class OszilloskopDisplay(QWidget):
    """Widget zur Anzeige der Oszilloskop-Kurven"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.setMinimumWidth(600)
        
        # Layout erstellen
        layout = QVBoxLayout(self)
        
        # PyQtGraph Plot-Widget erstellen
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('k')  # Schwarzer Hintergrund
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Spannung', units='V')
        self.plot_widget.setLabel('bottom', 'Zeit', units='s')
        
        # Datenreihen für beide Kanäle
        self.kanal1_kurve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 255, 0), width=2), name="Kanal 1")
        self.kanal2_kurve = self.plot_widget.plot(pen=pg.mkPen(color=(255, 255, 0), width=2), name="Kanal 2")
        
        # Trigger-Linie
        self.trigger_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color=(255, 0, 0), width=1, style=Qt.DashLine))
        self.trigger_line.setVisible(False)
        self.plot_widget.addItem(self.trigger_line)
        
        # Legende hinzufügen
        self.legende = self.plot_widget.addLegend()
        
        # Layout aufbauen
        layout.addWidget(self.plot_widget)
        
        # Datenarrays initialisieren
        self.x_daten = np.zeros(1000)
        self.y_daten_kanal1 = np.zeros(1000)
        self.y_daten_kanal2 = np.zeros(1000)
        
        # Kanal-Sichtbarkeit
        self.kanal1_aktiv = True
        self.kanal2_aktiv = True
    
    def aktualisiere_daten(self, x_daten, y_daten_kanal1, y_daten_kanal2=None):
        """Aktualisiert die Daten im Display"""
        self.x_daten = x_daten
        self.y_daten_kanal1 = y_daten_kanal1
        
        # Kanal 1 aktualisieren
        if self.kanal1_aktiv:
            self.kanal1_kurve.setData(x_daten, y_daten_kanal1)
            self.kanal1_kurve.setVisible(True)
        else:
            self.kanal1_kurve.setVisible(False)
        
        # Kanal 2 aktualisieren, falls Daten vorhanden
        if y_daten_kanal2 is not None:
            self.y_daten_kanal2 = y_daten_kanal2
            if self.kanal2_aktiv:
                self.kanal2_kurve.setData(x_daten, y_daten_kanal2)
                self.kanal2_kurve.setVisible(True)
            else:
                self.kanal2_kurve.setVisible(False)
        else:
            self.kanal2_kurve.setVisible(False)
    
    def set_trigger_level(self, level):
        """Setzt die Trigger-Level-Linie"""
        self.trigger_line.setValue(level)
        self.trigger_line.setVisible(True)
    
    def set_kanal_sichtbarkeit(self, kanal, aktiv):
        """Setzt die Sichtbarkeit eines Kanals"""
        if kanal == 1:
            self.kanal1_aktiv = aktiv
        elif kanal == 2:
            self.kanal2_aktiv = aktiv
            
        # Daten neu zeichnen
        self.kanal1_kurve.setVisible(self.kanal1_aktiv)
        self.kanal2_kurve.setVisible(self.kanal2_aktiv)


class Oszilloskop(QMainWindow):
    """Hauptfenster des Oszilloskops"""
    
    def __init__(self):
        super().__init__()
        
        # Fenstereigenschaften festlegen
        self.setWindowTitle("Oszilloskop")
        self.setGeometry(100, 100, 1000, 800)  # Größeres Fenster für mehr Details
        
        # Stelle sicher, dass PyQtGraph dunkles Hintergrundthema verwendet
        pg.setConfigOption('background', 'k')  # Schwarzer Hintergrund für alle Plots
        pg.setConfigOption('foreground', 'w')  # Weiße Linien und Text
        
        # Messparameter
        self.zeitbasis = 10.0  # ms pro Division (10 Divisionen insgesamt)
        self.abtastrate = 100000  # Hz
        self.volt_pro_div_kanal1 = 1.0  # V pro Division (8 Divisionen insgesamt)
        self.volt_pro_div_kanal2 = 1.0  # V pro Division
        self.offset_kanal1 = 0.0  # V Offset
        self.offset_kanal2 = 0.0  # V Offset
        
        # Trigger-Parameter
        self.trigger_aktiv = False
        self.trigger_kanal = 1  # 1 für Kanal 1, 2 für Kanal 2
        self.trigger_level = 0.0  # V
        self.trigger_typ = "Steigende Flanke"  # Oder "Fallende Flanke"
        
        # Simulator für Testsignale
        self.signal_generator = SignalGenerator()
        
        # Status des Oszilloskops
        self.running = False
        
        # Timer für Messungen
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.aktualisiere_messung)
        
        # Datenarrays
        self.messdaten_zeit = np.array([])
        self.messdaten_kanal1 = np.array([])
        self.messdaten_kanal2 = np.array([])
        
        # Flag für Einzel-Erfassung (Single Shot)
        self.einzel_erfassung = False
        
        # UI einrichten
        self.setup_ui()
        
        # Statusleiste
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Bereit - Oszilloskop gestoppt")
    
    def setup_ui(self):
        """Richtet die Benutzeroberfläche ein"""
        # Hauptwidget und Layout
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        
        # Oszilloskop-Anzeige
        self.display = OszilloskopDisplay()
        haupt_layout.addWidget(self.display)
        
        # Steuerungsbereich
        steuerung_layout = QHBoxLayout()
        
        # Linke Seite: Zeitbasis und Trigger
        linke_steuerung = QGroupBox("Zeitbasis & Trigger")
        linke_layout = QGridLayout(linke_steuerung)
        
        # Zeitbasis-Bereich
        linke_layout.addWidget(QLabel("Zeitbasis (ms/div):"), 0, 0)
        self.zeitbasis_combo = QComboBox()
        self.zeitbasis_combo.addItems(["0.1", "0.2", "0.5", "1", "2", "5", "10", "20", "50", "100", "200", "500", "1000"])
        self.zeitbasis_combo.setCurrentText("10")  # Standardwert
        self.zeitbasis_combo.currentTextChanged.connect(self.zeitbasis_geaendert)
        linke_layout.addWidget(self.zeitbasis_combo, 0, 1)
        
        # Trigger-Bereich
        linke_layout.addWidget(QLabel("Trigger:"), 1, 0)
        self.trigger_checkbox = QCheckBox("Aktiv")
        self.trigger_checkbox.setChecked(False)
        self.trigger_checkbox.stateChanged.connect(self.trigger_aktiviert)
        linke_layout.addWidget(self.trigger_checkbox, 1, 1)
        
        linke_layout.addWidget(QLabel("Trigger-Kanal:"), 2, 0)
        self.trigger_kanal_combo = QComboBox()
        self.trigger_kanal_combo.addItems(["Kanal 1", "Kanal 2"])
        self.trigger_kanal_combo.currentIndexChanged.connect(self.trigger_kanal_geaendert)
        linke_layout.addWidget(self.trigger_kanal_combo, 2, 1)
        
        linke_layout.addWidget(QLabel("Trigger-Typ:"), 3, 0)
        self.trigger_typ_combo = QComboBox()
        self.trigger_typ_combo.addItems(["Steigende Flanke", "Fallende Flanke"])
        self.trigger_typ_combo.currentTextChanged.connect(self.trigger_typ_geaendert)
        linke_layout.addWidget(self.trigger_typ_combo, 3, 1)
        
        linke_layout.addWidget(QLabel("Trigger-Level (V):"), 4, 0)
        self.trigger_level_spin = QDoubleSpinBox()
        self.trigger_level_spin.setRange(-10.0, 10.0)
        self.trigger_level_spin.setValue(0.0)
        self.trigger_level_spin.setSingleStep(0.1)
        self.trigger_level_spin.valueChanged.connect(self.trigger_level_geaendert)
        linke_layout.addWidget(self.trigger_level_spin, 4, 1)
        
        # Rechte Seite: Kanal-Einstellungen
        rechte_steuerung = QGroupBox("Kanal-Einstellungen")
        rechte_layout = QGridLayout(rechte_steuerung)
        
        # Kanal 1
        rechte_layout.addWidget(QLabel("Kanal 1:"), 0, 0)
        self.kanal1_checkbox = QCheckBox("Aktiv")
        self.kanal1_checkbox.setChecked(True)
        self.kanal1_checkbox.setStyleSheet("QCheckBox { color: green; }")
        self.kanal1_checkbox.stateChanged.connect(lambda state: self.kanal_aktiviert(1, state))
        rechte_layout.addWidget(self.kanal1_checkbox, 0, 1)
        
        rechte_layout.addWidget(QLabel("V/div Kanal 1:"), 1, 0)
        self.kanal1_vdiv_combo = QComboBox()
        self.kanal1_vdiv_combo.addItems(["0.01", "0.02", "0.05", "0.1", "0.2", "0.5", "1", "2", "5", "10"])
        self.kanal1_vdiv_combo.setCurrentText("1")  # Standardwert
        self.kanal1_vdiv_combo.currentTextChanged.connect(lambda value: self.volt_pro_div_geaendert(1, float(value)))
        rechte_layout.addWidget(self.kanal1_vdiv_combo, 1, 1)
        
        rechte_layout.addWidget(QLabel("Offset Kanal 1 (V):"), 2, 0)
        self.kanal1_offset_spin = QDoubleSpinBox()
        self.kanal1_offset_spin.setRange(-10.0, 10.0)
        self.kanal1_offset_spin.setValue(0.0)
        self.kanal1_offset_spin.setSingleStep(0.1)
        self.kanal1_offset_spin.valueChanged.connect(lambda value: self.offset_geaendert(1, value))
        rechte_layout.addWidget(self.kanal1_offset_spin, 2, 1)
        
        # Kanal 2
        rechte_layout.addWidget(QLabel("Kanal 2:"), 3, 0)
        self.kanal2_checkbox = QCheckBox("Aktiv")
        self.kanal2_checkbox.setChecked(True)
        self.kanal2_checkbox.setStyleSheet("QCheckBox { color: yellow; }")
        self.kanal2_checkbox.stateChanged.connect(lambda state: self.kanal_aktiviert(2, state))
        rechte_layout.addWidget(self.kanal2_checkbox, 3, 1)
        
        rechte_layout.addWidget(QLabel("V/div Kanal 2:"), 4, 0)
        self.kanal2_vdiv_combo = QComboBox()
        self.kanal2_vdiv_combo.addItems(["0.01", "0.02", "0.05", "0.1", "0.2", "0.5", "1", "2", "5", "10"])
        self.kanal2_vdiv_combo.setCurrentText("1")  # Standardwert
        self.kanal2_vdiv_combo.currentTextChanged.connect(lambda value: self.volt_pro_div_geaendert(2, float(value)))
        rechte_layout.addWidget(self.kanal2_vdiv_combo, 4, 1)
        
        rechte_layout.addWidget(QLabel("Offset Kanal 2 (V):"), 5, 0)
        self.kanal2_offset_spin = QDoubleSpinBox()
        self.kanal2_offset_spin.setRange(-10.0, 10.0)
        self.kanal2_offset_spin.setValue(0.0)
        self.kanal2_offset_spin.setSingleStep(0.1)
        self.kanal2_offset_spin.valueChanged.connect(lambda value: self.offset_geaendert(2, value))
        rechte_layout.addWidget(self.kanal2_offset_spin, 5, 1)
        
        # Steuerungsgruppenbox zum Layout hinzufügen
        steuerung_layout.addWidget(linke_steuerung)
        steuerung_layout.addWidget(rechte_steuerung)
        haupt_layout.addLayout(steuerung_layout)
        
        # Untere Steuerungsleiste mit Start/Stop, Single und Export
        unteres_layout = QHBoxLayout()
        
        # Button-Style
        button_style = """
        QPushButton {
            padding: 8px;
            font-weight: bold;
            border-radius: 4px;
        }
        """
        
        # Run/Stop-Button
        self.run_stop_btn = QPushButton("Start")
        self.run_stop_btn.setStyleSheet(button_style + "background-color: #00aa00; color: white;")
        self.run_stop_btn.clicked.connect(self.run_stop_toggled)
        unteres_layout.addWidget(self.run_stop_btn)
        
        # Single-Button (Einzel-Erfassung)
        self.single_btn = QPushButton("Einzel")
        self.single_btn.setStyleSheet(button_style + "background-color: #0066cc; color: white;")
        self.single_btn.clicked.connect(self.einzel_erfassung_starten)
        unteres_layout.addWidget(self.single_btn)
        
        # Autoset-Button
        self.autoset_btn = QPushButton("Autoset")
        self.autoset_btn.setStyleSheet(button_style + "background-color: #aa8800; color: white;")
        self.autoset_btn.clicked.connect(self.autoset)
        unteres_layout.addWidget(self.autoset_btn)
        
        # Clear-Button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(button_style + "background-color: #888888; color: white;")
        self.clear_btn.clicked.connect(self.clear_display)
        unteres_layout.addWidget(self.clear_btn)
        
        unteres_layout.addStretch()
        
        # CSV Export-Button
        self.csv_export_btn = QPushButton("CSV Export")
        self.csv_export_btn.setStyleSheet(button_style + "background-color: #888888; color: white;")
        self.csv_export_btn.clicked.connect(self.export_to_csv)
        unteres_layout.addWidget(self.csv_export_btn)
        
        # Hilfe-Button
        self.hilfe_btn = QPushButton("Hilfe")
        self.hilfe_btn.setStyleSheet(button_style)
        self.hilfe_btn.clicked.connect(self.show_help)
        unteres_layout.addWidget(self.hilfe_btn)
        
        haupt_layout.addLayout(unteres_layout)
        
        # Achsen initialisieren
        self.update_display_limits()
    
    def zeitbasis_geaendert(self, wert):
        """Wird aufgerufen, wenn die Zeitbasis geändert wird"""
        self.zeitbasis = float(wert)
        
        # Anzeige-Grenzen aktualisieren
        self.update_display_limits()
        
        # Abtastrate basierend auf Zeitbasis anpassen
        self.update_sample_rate()
        
        # Status aktualisieren
        self.statusBar.showMessage(f"Zeitbasis auf {self.zeitbasis} ms/div gesetzt")
    
    def update_sample_rate(self):
        """Aktualisiert die Abtastrate basierend auf der Zeitbasis"""
        # Für niedrigere Zeitbasen höhere Abtastraten verwenden
        if self.zeitbasis <= 1:
            self.abtastrate = 1000000  # 1 MHz
        elif self.zeitbasis <= 10:
            self.abtastrate = 100000   # 100 kHz
        elif self.zeitbasis <= 100:
            self.abtastrate = 10000    # 10 kHz
        else:
            self.abtastrate = 1000     # 1 kHz
    
    def trigger_aktiviert(self, state):
        """Wird aufgerufen, wenn Trigger aktiviert/deaktiviert wird"""
        self.trigger_aktiv = state == Qt.Checked
        
        # Trigger-Linie anzeigen oder verstecken
        if self.trigger_aktiv:
            self.display.set_trigger_level(self.trigger_level)
            self.statusBar.showMessage(f"Trigger aktiviert - {self.trigger_typ} bei {self.trigger_level}V")
        else:
            self.display.trigger_line.setVisible(False)
            self.statusBar.showMessage("Trigger deaktiviert")
    
    def trigger_kanal_geaendert(self, index):
        """Wird aufgerufen, wenn der Trigger-Kanal geändert wird"""
        self.trigger_kanal = index + 1  # Index 0 = Kanal 1, Index 1 = Kanal 2
        self.statusBar.showMessage(f"Trigger-Kanal auf Kanal {self.trigger_kanal} gesetzt")
    
    def trigger_typ_geaendert(self, typ):
        """Wird aufgerufen, wenn der Trigger-Typ geändert wird"""
        self.trigger_typ = typ
        self.statusBar.showMessage(f"Trigger-Typ auf {self.trigger_typ} gesetzt")
    
    def trigger_level_geaendert(self, level):
        """Wird aufgerufen, wenn der Trigger-Level geändert wird"""
        self.trigger_level = level
        
        # Trigger-Linie aktualisieren, falls Trigger aktiv
        if self.trigger_aktiv:
            self.display.set_trigger_level(level)
        
        self.statusBar.showMessage(f"Trigger-Level auf {level}V gesetzt")
    
    def kanal_aktiviert(self, kanal, state):
        """Wird aufgerufen, wenn ein Kanal aktiviert/deaktiviert wird"""
        aktiv = state == Qt.Checked
        self.display.set_kanal_sichtbarkeit(kanal, aktiv)
        self.statusBar.showMessage(f"Kanal {kanal} {'aktiviert' if aktiv else 'deaktiviert'}")
    
    def volt_pro_div_geaendert(self, kanal, wert):
        """Wird aufgerufen, wenn die Volt/Division-Einstellung geändert wird"""
        if kanal == 1:
            self.volt_pro_div_kanal1 = wert
        else:
            self.volt_pro_div_kanal2 = wert
        
        # Y-Achsen-Grenzen aktualisieren
        self.update_display_limits()
        
        self.statusBar.showMessage(f"Kanal {kanal} auf {wert} V/div gesetzt")
    
    def offset_geaendert(self, kanal, wert):
        """Wird aufgerufen, wenn der Offset geändert wird"""
        if kanal == 1:
            self.offset_kanal1 = wert
        else:
            self.offset_kanal2 = wert
        
        # Y-Achsen-Grenzen aktualisieren
        self.update_display_limits()
        
        self.statusBar.showMessage(f"Offset Kanal {kanal} auf {wert}V gesetzt")
    
    def update_display_limits(self):
        """Aktualisiert die Achsengrenzen der Anzeige"""
        # X-Achse: 10 Divisionen
        x_bereich = (self.zeitbasis / 1000) * 10  # in Sekunden
        self.display.plot_widget.setXRange(0, x_bereich)
        
        # Y-Achse: 8 Divisionen (± 4 Divisionen)
        y_min = min(-4 * self.volt_pro_div_kanal1 + self.offset_kanal1, 
                    -4 * self.volt_pro_div_kanal2 + self.offset_kanal2)
        y_max = max(4 * self.volt_pro_div_kanal1 + self.offset_kanal1, 
                    4 * self.volt_pro_div_kanal2 + self.offset_kanal2)
        
        # Etwas Abstand hinzufügen
        y_abstand = (y_max - y_min) * 0.05
        self.display.plot_widget.setYRange(y_min - y_abstand, y_max + y_abstand)
    
    def run_stop_toggled(self):
        """Wird aufgerufen, wenn der Run/Stop-Button gedrückt wird"""
        self.running = not self.running
        
        if self.running:
            # Start
            self.run_stop_btn.setText("Stop")
            self.run_stop_btn.setStyleSheet("background-color: #aa0000; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
            self.timer.start(50)  # Aktualisierung alle 50ms (20 Hz)
            self.statusBar.showMessage("Oszilloskop gestartet")
        else:
            # Stop
            self.run_stop_btn.setText("Start")
            self.run_stop_btn.setStyleSheet("background-color: #00aa00; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
            self.timer.stop()
            self.statusBar.showMessage("Oszilloskop gestoppt")
    
    def einzel_erfassung_starten(self):
        """Startet eine Einzel-Erfassung (Single Shot)"""
        self.einzel_erfassung = True
        
        # Falls nicht bereits läuft, starten
        if not self.running:
            self.run_stop_toggled()
        
        self.statusBar.showMessage("Einzel-Erfassung gestartet - Warte auf Trigger...")
    
    def autoset(self):
        """Führt einen Autoset durch, um Signale automatisch anzuzeigen"""
        # Hier würde eine echte Implementierung das Signal analysieren
        # und die Parameter anpassen. Für die Simulation setzen wir
        # einfach einige Standard-Parameter.
        
        # Zeitbasis automatisch einstellen
        self.zeitbasis_combo.setCurrentText("5")
        
        # Kanal 1 Amplitude bestimmen und anpassen
        amplitude_kanal1 = np.max(np.abs(self.messdaten_kanal1)) if len(self.messdaten_kanal1) > 0 else 1.0
        
        # Geeigneten V/div-Wert für Kanal 1 wählen
        volt_pro_div = 0.1
        for v in [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]:
            if amplitude_kanal1 < v * 3:  # Signale sollten etwa 3 Divisionen einnehmen
                volt_pro_div = v
                break
        self.kanal1_vdiv_combo.setCurrentText(str(volt_pro_div))
        
        # Ähnlich für Kanal 2
        amplitude_kanal2 = np.max(np.abs(self.messdaten_kanal2)) if len(self.messdaten_kanal2) > 0 else 1.0
        volt_pro_div = 0.1
        for v in [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]:
            if amplitude_kanal2 < v * 3:
                volt_pro_div = v
                break
        self.kanal2_vdiv_combo.setCurrentText(str(volt_pro_div))
        
        # Offsets auf 0 setzen
        self.kanal1_offset_spin.setValue(0)
        self.kanal2_offset_spin.setValue(0)
        
        # Sicherstellen, dass beide Kanäle aktiv sind
        self.kanal1_checkbox.setChecked(True)
        self.kanal2_checkbox.setChecked(True)
        
        # Trigger-Einstellungen zurücksetzen
        self.trigger_checkbox.setChecked(False)
        
        # Oszilloskop starten falls nicht bereits laufend
        if not self.running:
            self.run_stop_toggled()
        
        self.statusBar.showMessage("Autoset durchgeführt")
    
    def clear_display(self):
        """Löscht die Anzeige"""
        # Leere Daten für beide Kanäle
        x_bereich = (self.zeitbasis / 1000) * 10  # in Sekunden
        x_data = np.linspace(0, x_bereich, 1000)
        y_data_kanal1 = np.zeros(1000)
        y_data_kanal2 = np.zeros(1000)
        
        # Anzeige aktualisieren
        self.display.aktualisiere_daten(x_data, y_data_kanal1, y_data_kanal2)
        
        # Messdaten zurücksetzen
        self.messdaten_zeit = np.array([])
        self.messdaten_kanal1 = np.array([])
        self.messdaten_kanal2 = np.array([])
        
        self.statusBar.showMessage("Anzeige gelöscht")
    
    def export_to_csv(self):
        """Exportiert die aktuellen Messdaten als CSV-Datei"""
        if len(self.messdaten_zeit) == 0:
            QMessageBox.warning(self, "Keine Daten", "Es sind keine Messdaten zum Exportieren vorhanden.")
            return
        
        # Dateinamen vorschlagen
        vorschlag = f"Oszilloskop_Daten_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Dialog zum Speichern der Datei öffnen
        dateiname, _ = QFileDialog.getSaveFileName(
            self, "CSV-Datei speichern", vorschlag, "CSV-Dateien (*.csv)"
        )
        
        if dateiname:
            try:
                # CSV-Datei schreiben
                with open(dateiname, 'w', newline='') as csvfile:
                    feldnamen = ['Zeit (s)', 'Kanal 1 (V)', 'Kanal 2 (V)']
                    writer = csv.DictWriter(csvfile, fieldnames=feldnamen)
                    
                    writer.writeheader()
                    for i in range(len(self.messdaten_zeit)):
                        writer.writerow({
                            'Zeit (s)': self.messdaten_zeit[i],
                            'Kanal 1 (V)': self.messdaten_kanal1[i] if i < len(self.messdaten_kanal1) else '',
                            'Kanal 2 (V)': self.messdaten_kanal2[i] if i < len(self.messdaten_kanal2) else ''
                        })
                
                self.statusBar.showMessage(f"Messdaten wurden in {dateiname} exportiert")
            except Exception as e:
                QMessageBox.critical(
                    self, "Fehler beim Exportieren", 
                    f"Beim Exportieren der Daten ist ein Fehler aufgetreten:\n{str(e)}"
                )
    
    def show_help(self):
        """Zeigt Hilfeinformationen an"""
        hilfe_text = """
        Oszilloskop - Hilfe
        
        Bedienung:
        1. Drücken Sie 'Start', um die Messung zu starten
        2. Stellen Sie die Zeitbasis und Volt/Division für jeden Kanal ein
        3. Verwenden Sie die Trigger-Einstellungen, um das Signal zu stabilisieren
        4. 'Einzel' löst eine einmalige Erfassung aus
        5. 'Autoset' versucht, die Einstellungen automatisch anzupassen
        6. 'Clear' löscht die Anzeige
        7. 'CSV Export' speichert die aktuellen Daten als CSV-Datei
        
        Zeitbasis:
        - Wählen Sie die Zeit pro Division (horizontal)
        - 10 Divisionen werden insgesamt angezeigt
        
        Kanal-Einstellungen:
        - V/div: Spannung pro Division (vertikal)
        - Offset: Verschiebung des Signals nach oben/unten
        - Kanal 1 ist grün, Kanal 2 ist gelb
        
        Trigger:
        - Aktivieren Sie den Trigger, um wiederholende Signale zu stabilisieren
        - Wählen Sie steigende oder fallende Flanke
        - Setzen Sie den Trigger-Level, um den Auslösepunkt zu bestimmen
        - Die rote gestrichelte Linie zeigt den Trigger-Level an
        """
        
        QMessageBox.information(self, "Oszilloskop - Hilfe", hilfe_text)
    
    @pyqtSlot()
    def aktualisiere_messung(self):
        """Aktualisiert die Messungen und die Anzeige"""
        # X-Achsen-Bereich berechnen (in Sekunden)
        x_bereich = (self.zeitbasis / 1000) * 10  # 10 Divisionen
        
        # Anzahl der Samples basierend auf der Abtastrate und dem Zeitbereich
        num_samples = int(x_bereich * self.abtastrate)
        
        # Zeitachse erstellen
        x_data = np.linspace(0, x_bereich, num_samples)
        
        # Messdaten von beiden Kanälen holen (simuliert)
        # In einem echten System würden hier MCC 118 API-Calls stehen
        y_data_kanal1 = self.signal_generator.get_signal1(x_data)
        y_data_kanal2 = self.signal_generator.get_signal2(x_data)
        
        # Eigene Offsets anwenden
        y_data_kanal1 += self.offset_kanal1
        y_data_kanal2 += self.offset_kanal2
        
        # Trigger-Prozess, falls aktiviert
        if self.trigger_aktiv:
            # Verwende die Daten vom ausgewählten Trigger-Kanal
            trigger_daten = y_data_kanal1 if self.trigger_kanal == 1 else y_data_kanal2
            
            # Trigger-Index finden
            trigger_idx = None
            
            # Für steigende Flanke suchen
            if self.trigger_typ == "Steigende Flanke":
                for i in range(1, len(trigger_daten)):
                    if trigger_daten[i-1] < self.trigger_level <= trigger_daten[i]:
                        trigger_idx = i
                        break
            # Für fallende Flanke suchen
            else:
                for i in range(1, len(trigger_daten)):
                    if trigger_daten[i-1] >= self.trigger_level > trigger_daten[i]:
                        trigger_idx = i
                        break
            
            # Wenn Triggerpunkt gefunden, Daten neu anordnen
            if trigger_idx is not None:
                # Sicherstellen, dass wir genügend Daten nach dem Trigger haben
                if trigger_idx < len(x_data) - 10:
                    # Zeit vom Trigger auf 0 setzen und restliche Werte anpassen
                    x_data_offset = x_data - x_data[trigger_idx]
                    
                    # Daten ab dem Triggerpunkt nehmen
                    y_data_kanal1 = y_data_kanal1[trigger_idx:]
                    y_data_kanal2 = y_data_kanal2[trigger_idx:]
                    x_data = x_data_offset[trigger_idx:]
                    
                    # Bei Einzel-Erfassung stoppen
                    if self.einzel_erfassung:
                        self.einzel_erfassung = False
                        self.running = False
                        self.timer.stop()
                        self.run_stop_btn.setText("Start")
                        self.run_stop_btn.setStyleSheet("background-color: #00aa00; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
                        self.statusBar.showMessage("Einzel-Erfassung abgeschlossen")
        
        # Messdaten speichern für CSV-Export
        if len(self.messdaten_zeit) == 0:
            # Erste Messung, einfach speichern
            self.messdaten_zeit = x_data
            self.messdaten_kanal1 = y_data_kanal1
            self.messdaten_kanal2 = y_data_kanal2
        elif not self.einzel_erfassung and self.trigger_aktiv and self.running:
            # Bei kontinuierlicher Messung mit Trigger, aktualisieren
            self.messdaten_zeit = x_data
            self.messdaten_kanal1 = y_data_kanal1
            self.messdaten_kanal2 = y_data_kanal2
        
        # Display aktualisieren
        self.display.aktualisiere_daten(x_data, y_data_kanal1, y_data_kanal2)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Dem LabVIEW-Stil ähnlich
    app.setStyle("Fusion")
    
    # Dunkles Farbschema für Oszilloskop-Feeling
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    # Anwendung erstellen und anzeigen
    oszilloskop = Oszilloskop()
    oszilloskop.show()
    
    sys.exit(app.exec_())