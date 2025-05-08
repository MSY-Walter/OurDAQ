# -*- coding: utf-8 -*-

"""
Digitaler Multimeter für MCC 118
Ein LabVIEW-ähnlicher DMM für Spannungs- und Strommessungen
Mit Überlastungswarnung, Diagrammanzeige und CSV-Datenspeicherung
Verwendet echte Messdaten vom MCC 118 HAT
"""

import sys
import time
import os
import csv
from datetime import datetime
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                           QComboBox, QGroupBox, QStatusBar,
                           QFileDialog, QMessageBox, QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen, QBrush
import pyqtgraph as pg  # Für die Diagrammanzeige

# Versuche den MCC Datenleser zu importieren, bei Fehler fallback zum Simulator
try:
    from MCC_Datenleser import MCC118Datenleser
    # Importiere auch den Simulator als Fallback
    from Spannung_Strom_Generator import DatenSimulator
    HARDWARE_MODUS = True
    print("MCC 118 Hardware-Modus aktiviert")
except ImportError:
    from Spannung_Strom_Generator import DatenSimulator
    HARDWARE_MODUS = False
    print("Simulator-Modus aktiviert (MCC 118 Bibliothek nicht gefunden)")

class MesswertAnzeige(QWidget):
    """Widget zur Anzeige des aktuellen Messwerts mit LabVIEW-ähnlicher Darstellung"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.wert = 0.0
        self.einheit = "V DC"
        self.bereich = 20.0
        self.ueberlast = False  # Neuer Zustand für Überlast
        self.setMinimumHeight(120)
        self.setMinimumWidth(400)
        
        # Farbe für die Anzeige (Türkis ähnlich wie in LabVIEW)
        self.farbe = QColor(0, 210, 210)
        self.farbe_ueberlast = QColor(255, 50, 50)  # Rote Farbe für Überlast
        
        # Setze schwarzen Hintergrund
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, Qt.black)
        self.setPalette(palette)
    
    def set_wert(self, wert, ueberlast=False):
        """Setzt den anzuzeigenden Wert und Überlastzustand"""
        self.wert = wert
        self.ueberlast = ueberlast
        self.update()
    
    def set_einheit(self, einheit):
        """Setzt die anzuzeigende Einheit"""
        self.einheit = einheit
        self.update()
    
    def set_bereich(self, bereich):
        """Setzt den Messbereich"""
        self.bereich = bereich
        self.update()
    
    def paintEvent(self, event):
        """Zeichnet die Anzeige"""
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        # Wähle die richtige Farbe basierend auf Überlastzustand
        aktuelle_farbe = self.farbe_ueberlast if self.ueberlast else self.farbe
        
        # Zeichne den Wert
        font = QFont("Arial", 32, QFont.Bold)
        qp.setFont(font)
        qp.setPen(aktuelle_farbe)
        
        # Zeige Überlast-Text oder normalen Wert
        if self.ueberlast:
            text = "ÜBERLAST!"
        else:
            text = f"{self.wert:.2f} {self.einheit}"
            
        qp.drawText(self.rect(), Qt.AlignCenter, text)
        
        # Zeichne den Balken
        balken_hoehe = 10
        balken_y = self.height() - balken_hoehe - 30
        balken_breite = self.width() - 40
        balken_x = 20
        
        qp.setPen(QPen(aktuelle_farbe, 1))
        qp.drawRect(balken_x, balken_y, balken_breite, balken_hoehe)
        
        # Fülle den Balken entsprechend dem Wert (bei Überlast komplett)
        if self.ueberlast:
            prozent = 1.0
        else:
            prozent = min(max(0, abs(self.wert) / self.bereich), 1.0)
            
        qp.setBrush(QBrush(aktuelle_farbe))
        qp.drawRect(balken_x, balken_y, int(balken_breite * prozent), balken_hoehe)
        
        # Zeichne Markierungen auf dem Balken
        qp.setPen(QPen(aktuelle_farbe, 1))
        for i in range(11):
            x = balken_x + (balken_breite * i) // 10
            qp.drawLine(x, balken_y - 2, x, balken_y + balken_hoehe + 2)
        
        # Zeichne "% FS" (Full Scale) rechts
        qp.setPen(aktuelle_farbe)
        qp.setFont(QFont("Arial", 10))
        qp.drawText(balken_x + balken_breite + 5, balken_y + balken_hoehe, "% FS")


class BananaJackVisualisierung(QWidget):
    """Visualisiert die Banana-Jack-Anschlüsse wie im Labview-Interface"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 120)
        
    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        # Hintergrund
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(QColor(240, 240, 240)))
        qp.drawRect(0, 0, self.width(), self.height())
        
        # Verbindungsleiste
        qp.setPen(QPen(Qt.black, 2))
        qp.drawLine(50, 50, self.width() - 50, 50)
        
        # Anschlüsse
        # Volt links (rot)
        qp.setBrush(QBrush(QColor(255, 0, 0)))
        qp.drawEllipse(40, 40, 20, 20)
        qp.setFont(QFont("Arial", 8, QFont.Bold))
        qp.drawText(30, 80, 40, 20, Qt.AlignCenter, "V")
        
        # COM in der Mitte (schwarz/grau)
        qp.setBrush(QBrush(QColor(50, 50, 50)))
        qp.drawEllipse(self.width()//2 - 10, 40, 20, 20)
        qp.drawText(self.width()//2 - 20, 80, 40, 20, Qt.AlignCenter, "COM")
        
        # Ampere rechts (rot)
        qp.setBrush(QBrush(QColor(255, 0, 0)))
        qp.drawEllipse(self.width() - 60, 40, 20, 20)
        qp.drawText(self.width() - 70, 80, 40, 20, Qt.AlignCenter, "A")


class DiagrammAnzeige(QWidget):
    """Widget zur Anzeige eines zeitlichen Verlaufs der Messwerte"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.aktiv = False  # Flag zur Steuerung der Diagrammaktivierung
        
        # Layout erstellen
        layout = QVBoxLayout(self)
        
        # PyQtGraph Plot-Widget erstellen
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')  # Weißer Hintergrund
        self.plot_widget.setLabel('left', 'Wert')
        self.plot_widget.setLabel('bottom', 'Zeit (s)')
        self.plot_widget.showGrid(x=True, y=True)
        
        # Status-Label hinzufügen
        self.status_label = QLabel("Diagramm wird angezeigt, wenn Datenaufnahme aktiviert ist")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: #555;")
        
        # Datenreihe für den Plot
        self.kurve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 210, 210), width=3))
        
        # X- und Y-Daten initialisieren
        self.x_daten = np.zeros(100)  # Zeit in Sekunden
        self.y_daten = np.zeros(100)  # Messwerte
        self.start_zeit = time.time()
        
        # Layout aufbauen - zuerst nur Status-Label anzeigen
        layout.addWidget(self.status_label)
        layout.addWidget(self.plot_widget)
        self.plot_widget.hide()  # Plot-Widget initial verstecken
    
    def set_aktiv(self, aktiv):
        """Aktiviert oder deaktiviert das Diagramm"""
        self.aktiv = aktiv
        if aktiv:
            self.status_label.hide()
            self.plot_widget.show()
            self.reset_diagramm()  # Diagramm zurücksetzen beim Aktivieren
        else:
            self.status_label.show()
            self.plot_widget.hide()
    
    def aktualisiere_diagramm(self, wert):
        """Aktualisiert das Diagramm mit einem neuen Messwert"""
        if not self.aktiv:
            return  # Nichts aktualisieren, wenn nicht aktiv
            
        # Aktuelle Zeit seit Start berechnen
        aktuelle_zeit = time.time() - self.start_zeit
        
        # Daten nach links verschieben
        self.x_daten[:-1] = self.x_daten[1:]
        self.y_daten[:-1] = self.y_daten[1:]
        
        # Neuen Wert hinzufügen
        self.x_daten[-1] = aktuelle_zeit
        self.y_daten[-1] = wert
        
        # Diagramm aktualisieren
        self.kurve.setData(self.x_daten, self.y_daten)
    
    def reset_diagramm(self):
        """Setzt das Diagramm zurück"""
        self.x_daten = np.zeros(100)
        self.y_daten = np.zeros(100)
        self.start_zeit = time.time()
        self.kurve.setData(self.x_daten, self.y_daten)


class HardwareKonfigDialog(QMainWindow):
    """Dialog zur Konfiguration der Hardware-Einstellungen"""
    
    def __init__(self, parent=None, mcc_leser=None):
        super().__init__(parent)
        self.setWindowTitle("Hardware-Konfiguration")
        self.setWindowModality(Qt.ApplicationModal)
        self.setGeometry(200, 200, 400, 300)
        
        self.mcc_leser = mcc_leser
        
        # Zentrales Widget und Layout
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        
        # Kanalanzeigen
        kanal_gruppe = QGroupBox("MCC 118 Kanalkonfiguration")
        kanal_layout = QGridLayout(kanal_gruppe)
        
        # Spannung Kanal Auswahl
        kanal_layout.addWidget(QLabel("Kanal für Spannungsmessung:"), 0, 0)
        self.spannung_kanal_spin = QSpinBox()
        self.spannung_kanal_spin.setRange(0, 7)  # MCC 118 hat 8 Kanäle (0-7)
        self.spannung_kanal_spin.setValue(mcc_leser.aktiver_kanal_spannung if mcc_leser else 0)
        kanal_layout.addWidget(self.spannung_kanal_spin, 0, 1)
        
        # Strom Kanal Auswahl
        kanal_layout.addWidget(QLabel("Kanal für Strommessung:"), 1, 0)
        self.strom_kanal_spin = QSpinBox()
        self.strom_kanal_spin.setRange(0, 7)  # MCC 118 hat 8 Kanäle (0-7)
        self.strom_kanal_spin.setValue(mcc_leser.aktiver_kanal_strom if mcc_leser else 1)
        kanal_layout.addWidget(self.strom_kanal_spin, 1, 1)
        
        # Shunt-Widerstand Einstellung
        kanal_layout.addWidget(QLabel("Shunt-Widerstand (Ohm):"), 2, 0)
        self.shunt_widerstand_spin = QDoubleSpinBox()
        self.shunt_widerstand_spin.setRange(0.01, 1000.0)  
        self.shunt_widerstand_spin.setDecimals(2)
        self.shunt_widerstand_spin.setValue(mcc_leser.shunt_widerstand if mcc_leser else 1.0)
        kanal_layout.addWidget(self.shunt_widerstand_spin, 2, 1)
        
        # Hardware Status
        status_gruppe = QGroupBox("Hardware Status")
        status_layout = QVBoxLayout(status_gruppe)
        
        if mcc_leser and mcc_leser.hat_gefunden:
            status_text = f"MCC 118 HAT gefunden an Adresse {mcc_leser.address}"
            status_farbe = "darkgreen"
        else:
            status_text = "Kein MCC 118 HAT gefunden, im Simulationsmodus"
            status_farbe = "darkred"
        
        self.status_label = QLabel(status_text)
        self.status_label.setStyleSheet(f"color: {status_farbe}; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.speichern_btn = QPushButton("Speichern")
        self.speichern_btn.clicked.connect(self.speichern)
        
        self.abbrechen_btn = QPushButton("Abbrechen")
        self.abbrechen_btn.clicked.connect(self.close)
        
        button_layout.addWidget(self.speichern_btn)
        button_layout.addWidget(self.abbrechen_btn)
        
        # Layout zusammenbauen
        haupt_layout.addWidget(kanal_gruppe)
        haupt_layout.addWidget(status_gruppe)
        haupt_layout.addStretch(1)
        haupt_layout.addLayout(button_layout)
    
    def speichern(self):
        """Speichert die Konfiguration und schließt den Dialog"""
        if self.mcc_leser:
            # Kanäle setzen
            self.mcc_leser.set_spannung_kanal(self.spannung_kanal_spin.value())
            self.mcc_leser.set_strom_kanal(self.strom_kanal_spin.value())
            self.mcc_leser.set_shunt_widerstand(self.shunt_widerstand_spin.value())
            print("Hardware-Konfiguration gespeichert")
        self.close()


class DigitalMultimeter(QMainWindow):
    """Hauptfenster des Digitalen Multimeters"""
    
    def __init__(self):
        super().__init__()
        
        # Fenstereigenschaften festlegen
        self.setWindowTitle("Digital Multimeter")
        self.setGeometry(100, 100, 800, 700)  # Angepasste Fenstergröße
        
        # Stelle sicher, dass PyQtGraph dunkles Hintergrundthema verwendet
        pg.setConfigOption('background', 'w')  # Weißer Hintergrund für alle Plots
        pg.setConfigOption('foreground', 'k')  # Schwarze Linien und Text
        
        # Messungsmodus (Spannung oder Strom)
        self.modus = "Spannung DC"
        self.bereich = 20.0  # Standardbereich für Spannung in V
        
        # Hardware oder Simulator initialisieren
        if HARDWARE_MODUS:
            try:
                self.datenleser = MCC118Datenleser()
                if not self.datenleser.hat_gefunden:
                    print("Kein MCC 118 HAT gefunden, fallback zum Simulator")
                    self.simulator = DatenSimulator()
            except Exception as e:
                print(f"Fehler bei der Initialisierung des MCC 118: {e}")
                print("Fallback zum Simulator")
                self.datenleser = None
                self.simulator = DatenSimulator()
        else:
            self.datenleser = None
            self.simulator = DatenSimulator()
        
        # Timer für Messungen
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.aktualisiere_messung)
        self.timer.start(100)  # Alle 100 ms aktualisieren
        
        # Flag für Überlast-Zustand
        self.ueberlast_status = False
        
        # Daten für CSV-Export
        self.messdaten = []
        self.datenerfassung_aktiv = False
        
        # UI einrichten
        self.setup_ui()
        
        # Statusleiste initialisieren
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Status anzeigen, ob Hardware oder Simulator verwendet wird
        if self.datenleser and self.datenleser.hat_gefunden:
            self.statusBar.showMessage("Bereit - MCC 118 Hardware-Modus - Keine Datenaufnahme aktiv")
        else:
            self.statusBar.showMessage("Bereit - Simulator-Modus - Keine Datenaufnahme aktiv")
    
    def setup_ui(self):
        """Richtet die Benutzeroberfläche ein"""
        # Hauptwidget und Layout
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        haupt_layout.setSpacing(15)  # Mehr Abstand zwischen Elementen
        
        # Messwertanzeige
        self.messwert_anzeige = MesswertAnzeige()
        haupt_layout.addWidget(self.messwert_anzeige)
        
        # Diagrammanzeige hinzufügen
        self.diagramm_anzeige = DiagrammAnzeige()
        haupt_layout.addWidget(self.diagramm_anzeige)
        
        # Messungseinstellungen-Gruppe
        einstellungen_gruppe = QGroupBox("Messeinstellungen")
        einstellungen_layout = QHBoxLayout(einstellungen_gruppe)  # Horizontales Layout
        
        # Linke Seite: Buttons für Messmodus
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)  # Mehr Abstand zwischen Buttons
        
        # Label für Messmodus
        modus_label = QLabel("Messmodus:")
        modus_label.setFont(QFont("Arial", 10, QFont.Bold))
        buttons_layout.addWidget(modus_label)
        
        # Button-Grid erstellen - 2x2 Layout
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
        # Buttons mit verbessertem Design
        button_style = """
        QPushButton {
            background-color: #f0f0f0;
            border: 1px solid #a0a0a0;
            border-radius: 5px;
            padding: 8px;
            font-weight: bold;
        }
        QPushButton:checked {
            background-color: #c0e0ff;
            border: 2px solid #4080ff;
        }
        """
        
        # Spannung DC-Button
        self.spannung_dc_btn = QPushButton("DC Spannung (V)")
        self.spannung_dc_btn.setFixedSize(150, 45)
        self.spannung_dc_btn.setCheckable(True)
        self.spannung_dc_btn.setChecked(True)  # Standardmäßig ausgewählt
        self.spannung_dc_btn.setStyleSheet(button_style)
        self.spannung_dc_btn.clicked.connect(lambda: self.setze_modus("Spannung DC"))