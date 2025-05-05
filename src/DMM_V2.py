# -*- coding: utf-8 -*-

"""
Digitaler Multimeter für MCC 118
Ein LabVIEW-ähnlicher DMM für Spannungs- und Strommessungen
Mit Überlastungswarnung, Diagrammanzeige und CSV-Datenspeicherung
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
                           QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen, QBrush
import pyqtgraph as pg  # Für die Diagrammanzeige

# Importiere den Datensimulator
from Spannung_Strom_Generator import DatenSimulator

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
        
        # Simulator für Messdaten
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
        self.statusBar.showMessage("Bereit - Keine Datenaufnahme aktiv")
    
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
        
        # Spannung AC-Button
        self.spannung_ac_btn = QPushButton("AC Spannung (V)")
        self.spannung_ac_btn.setFixedSize(150, 45)
        self.spannung_ac_btn.setCheckable(True)
        self.spannung_ac_btn.setStyleSheet(button_style)
        self.spannung_ac_btn.clicked.connect(lambda: self.setze_modus("Spannung AC"))
        
        # Strom DC-Button
        self.strom_dc_btn = QPushButton("DC Strom (A)")
        self.strom_dc_btn.setFixedSize(150, 45)
        self.strom_dc_btn.setCheckable(True)
        self.strom_dc_btn.setStyleSheet(button_style)
        self.strom_dc_btn.clicked.connect(lambda: self.setze_modus("Strom DC"))
        
        # Strom AC-Button
        self.strom_ac_btn = QPushButton("AC Strom (A)")
        self.strom_ac_btn.setFixedSize(150, 45)
        self.strom_ac_btn.setCheckable(True)
        self.strom_ac_btn.setStyleSheet(button_style)
        self.strom_ac_btn.clicked.connect(lambda: self.setze_modus("Strom AC"))
        
        # Buttons zum Grid hinzufügen
        button_grid.addWidget(self.spannung_dc_btn, 0, 0)
        button_grid.addWidget(self.spannung_ac_btn, 0, 1)
        button_grid.addWidget(self.strom_dc_btn, 1, 0)
        button_grid.addWidget(self.strom_ac_btn, 1, 1)
        
        buttons_layout.addLayout(button_grid)
        
        # Bereichs-Layout
        bereich_layout = QVBoxLayout()
        bereich_layout.setSpacing(10)
        
        # Label für Messbereich
        bereich_label = QLabel("Messbereich:")
        bereich_label.setFont(QFont("Arial", 10, QFont.Bold))
        bereich_layout.addWidget(bereich_label)
        
        # Bereichs-Dropdown
        self.bereich_combo = QComboBox()
        self.bereich_combo.setFixedHeight(30)
        self.bereich_combo.setStyleSheet("font-size: 10pt;")
        self.aktualisiere_bereiche()
        self.bereich_combo.currentIndexChanged.connect(self.bereich_geaendert)
        bereich_layout.addWidget(self.bereich_combo)
        
        # Fülle den Rest des Bereichs-Layouts mit Leerraum
        bereich_layout.addStretch()
        
        # Banana Jack Visualisierung
        self.banana_visual = BananaJackVisualisierung()
        
        # Füge alle Teile zum Einstellungs-Layout hinzu
        einstellungen_layout.addLayout(buttons_layout, 2)  # 2 Teile für Buttons
        einstellungen_layout.addLayout(bereich_layout, 1)  # 1 Teil für Bereich
        einstellungen_layout.addWidget(self.banana_visual, 1)  # 1 Teil für Banana Jacks
        
        haupt_layout.addWidget(einstellungen_gruppe)
        
        # Steuerungsgruppe
        steuerung_gruppe = QGroupBox("Steuerung")
        steuerung_layout = QHBoxLayout(steuerung_gruppe)
        steuerung_layout.setSpacing(15)  # Mehr Abstand zwischen Buttons
        
        # Button-Styles verbessert
        # Aufnahme Start Button - Grün mit deutlich sichtbarem Text
        self.start_aufnahme_btn = QPushButton("Aufnahme starten")
        self.start_aufnahme_btn.setStyleSheet("""
            QPushButton {
                background-color: darkgreen;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #00b300;
            }
        """)
        self.start_aufnahme_btn.setFixedSize(200, 45)
        self.start_aufnahme_btn.clicked.connect(self.starte_aufnahme)
        
        # Aufnahme Stop Button - Rot mit deutlich sichtbarem Text
        self.stop_aufnahme_btn = QPushButton("Aufnahme stoppen")
        self.stop_aufnahme_btn.setStyleSheet("""
            QPushButton {
                background-color: darkred;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #cc0000;
            }
        """)
        self.stop_aufnahme_btn.setFixedSize(200, 45)
        self.stop_aufnahme_btn.clicked.connect(self.stoppe_aufnahme)
        self.stop_aufnahme_btn.setEnabled(False)  # Initial deaktiviert
        
        # CSV Export Button
        utility_style = """
        QPushButton {
            background-color: #f0f0f0;
            border: 1px solid #a0a0a0;
            border-radius: 5px;
            padding: 8px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        """
        
        self.csv_export_btn = QPushButton("CSV speichern")
        self.csv_export_btn.setStyleSheet(utility_style)
        self.csv_export_btn.setFixedSize(150, 45)
        self.csv_export_btn.clicked.connect(self.csv_speichern)
        
        # Hilfe Button
        help_btn = QPushButton("Hilfe")
        help_btn.setStyleSheet(utility_style)
        help_btn.setFixedSize(100, 45)
        help_btn.clicked.connect(self.hilfe_anzeigen)
        
        # Buttons zum Layout hinzufügen
        steuerung_layout.addWidget(self.start_aufnahme_btn)
        steuerung_layout.addWidget(self.stop_aufnahme_btn)
        steuerung_layout.addWidget(self.csv_export_btn)
        steuerung_layout.addWidget(help_btn)
        steuerung_layout.addStretch()  # Abstand am Ende
        
        haupt_layout.addWidget(steuerung_gruppe)
        
        # Etwas Abstand am Ende hinzufügen
        haupt_layout.addStretch(1)
    
    def setze_modus(self, modus):
        """Setzt den Messmodus und aktualisiert die Benutzeroberfläche"""
        self.modus = modus
        
        # Buttons aktualisieren
        self.spannung_dc_btn.setChecked(modus == "Spannung DC")
        self.spannung_ac_btn.setChecked(modus == "Spannung AC")
        self.strom_dc_btn.setChecked(modus == "Strom DC")
        self.strom_ac_btn.setChecked(modus == "Strom AC")
        
        # Bereiche aktualisieren
        self.aktualisiere_bereiche()
        
        # Einheit aktualisieren
        if "Spannung" in modus:
            if "DC" in modus:
                self.messwert_anzeige.set_einheit("V DC")
            else:
                self.messwert_anzeige.set_einheit("V AC")
        elif "Strom" in modus:
            if "DC" in modus:
                self.messwert_anzeige.set_einheit("A DC")
            else:
                self.messwert_anzeige.set_einheit("A AC")
        
        # Beim Moduswechsel Überlast-Status zurücksetzen
        self.ueberlast_status = False
        
        # Wenn Datenerfassung aktiv ist, Diagramm zurücksetzen
        if self.datenerfassung_aktiv:
            self.diagramm_anzeige.reset_diagramm()
            
            # Messdaten zurücksetzen
            self.messdaten = []
            
            # Frage Benutzer, ob er die Datenerfassung fortsetzen möchte
            antwort = QMessageBox.question(
                self, "Messmode geändert", 
                "Möchten Sie die Datenerfassung mit dem neuen Messmodus fortsetzen?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.Yes
            )
            
            if antwort == QMessageBox.No:
                # Datenerfassung deaktivieren
                self.stoppe_aufnahme()
            else:
                # Status aktualisieren
                self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
    
    def aktualisiere_bereiche(self):
        """Aktualisiert die verfügbaren Messbereiche basierend auf dem Messmodus"""
        self.bereich_combo.clear()
        
        if "Spannung" in self.modus:
            self.bereich_combo.addItems(["20V", "10V", "5V", "2V", "1V", "500mV", "200mV"])
            self.bereich = 20.0
        elif "Strom" in self.modus:
            self.bereich_combo.addItems(["10A", "5A", "1A", "500mA", "200mA", "100mA", "10mA"])
            self.bereich = 10.0
        
        self.bereich_geaendert()
    
    def bereich_geaendert(self):
        """Wird aufgerufen, wenn der Benutzer den Messbereich ändert"""
        bereich_text = self.bereich_combo.currentText()
        
        # Bereich-Wert aus Text extrahieren
        if "V" in bereich_text:
            if "mV" in bereich_text:
                self.bereich = float(bereich_text.replace("mV", "")) / 1000.0
            else:
                self.bereich = float(bereich_text.replace("V", ""))
        elif "A" in bereich_text:
            if "mA" in bereich_text:
                self.bereich = float(bereich_text.replace("mA", "")) / 1000.0
            else:
                self.bereich = float(bereich_text.replace("A", ""))
        
        # Messwertanzeige aktualisieren
        self.messwert_anzeige.set_bereich(self.bereich)
        
        # Überlast-Zustand zurücksetzen
        self.ueberlast_status = False
        
        # Diagramm zurücksetzen
        self.diagramm_anzeige.reset_diagramm()
        
        # Messdaten zurücksetzen, falls Aufnahme aktiv ist
        if self.datenerfassung_aktiv:
            self.messdaten = []
            self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - Messbereich auf {bereich_text} geändert")
    
    @pyqtSlot()
    def aktualisiere_messung(self):
        """Aktualisiert die Messwertanzeige mit neuen Daten"""
        if "Spannung" in self.modus:
            wert = self.simulator.get_spannung(self.bereich * 1.5)  # Erhöhter Bereich für Simulation
        else:  # Strom-Modus
            wert = self.simulator.get_strom(self.bereich * 1.5)  # Erhöhter Bereich für Simulation
        
        # Überprüfe, ob Überlast vorliegt
        if abs(wert) > self.bereich:
            if not self.ueberlast_status:  # Nur einmal Ton ausgeben
                self.ueberlast_status = True
                self.zeige_ueberlast_warnung()
            
            # Anzeige auf Überlast setzen
            self.messwert_anzeige.set_wert(wert, True)
            
            # Statusleiste aktualisieren, wenn Überlast
            if self.datenerfassung_aktiv:
                self.statusBar.showMessage(f"ÜBERLAST! Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
        else:
            # Wenn nicht mehr überlastet, Überlast-Status zurücksetzen
            if self.ueberlast_status:
                self.ueberlast_status = False
                
                # Statusleiste aktualisieren, wenn Überlast vorbei
                if self.datenerfassung_aktiv:
                    self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
            
            # Normalen Wert anzeigen
            self.messwert_anzeige.set_wert(wert, False)
        
        # Diagramm aktualisieren (nur wenn Datenerfassung aktiv ist)
        if self.datenerfassung_aktiv:
            self.diagramm_anzeige.aktualisiere_diagramm(wert)
            
            # Wert zu den Messdaten hinzufügen
            zeit = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Uhrzeit mit Millisekunden
            self.messdaten.append({
                'Zeit': zeit,
                'Wert': wert,
                'Modus': self.modus
            })
            
            # Alle 10 Messpunkte die Statusleiste aktualisieren
            if len(self.messdaten) % 10 == 0:
                self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
    
    def zeige_ueberlast_warnung(self):
        """Zeigt eine Warnungsmeldung an, wenn Überlast erkannt wird"""
        # Status aktualisieren statt Dialog anzeigen
        self.statusBar.showMessage("ÜBERLAST! Messbereichsüberschreitung erkannt!")
        
        # Optional: Akustisches Signal abspielen (wenn verfügbar)
        try:
            from PyQt5.QtMultimedia import QSound
            QSound.play("alarm.wav")
        except:
            pass  # Ignoriere Fehler, wenn Sound nicht unterstützt wird
    
    def starte_aufnahme(self):
        """Startet die Datenaufnahme"""
        self.datenerfassung_aktiv = True
        self.messdaten = []  # Daten zurücksetzen
        
        # Diagramm aktivieren
        self.diagramm_anzeige.set_aktiv(True)
        
        # Button-Status aktualisieren
        self.start_aufnahme_btn.setEnabled(False)
        self.stop_aufnahme_btn.setEnabled(True)
        
        # Start-Zeit zurücksetzen
        self.diagramm_anzeige.reset_diagramm()
        
        # Statusleiste aktualisieren statt Dialog anzeigen
        self.statusBar.showMessage(f"Datenaufnahme für {self.modus} gestartet")
    
    def stoppe_aufnahme(self):
        """Stoppt die Datenaufnahme"""
        if not self.datenerfassung_aktiv:
            return
            
        self.datenerfassung_aktiv = False
        
        # Diagramm deaktivieren
        self.diagramm_anzeige.set_aktiv(False)
        
        # Button-Status aktualisieren
        self.start_aufnahme_btn.setEnabled(True)
        self.stop_aufnahme_btn.setEnabled(False)
        
        # Statusleiste aktualisieren statt Dialog anzeigen
        self.statusBar.showMessage(f"Datenaufnahme gestoppt - {len(self.messdaten)} Messpunkte aufgezeichnet")
    
    def csv_speichern(self):
        """Speichert die gesammelten Messdaten als CSV-Datei"""
        # Prüfen, ob Daten vorhanden sind
        if not self.messdaten:
            QMessageBox.warning(self, "Keine Daten", "Es sind keine Messdaten zum Speichern vorhanden.")
            return
        
        # Prüfen, ob Datenerfassung noch aktiv ist
        if self.datenerfassung_aktiv:
            antwort = QMessageBox.question(
                self, "Datenerfassung aktiv", 
                "Die Datenerfassung ist noch aktiv. Bitte stoppen Sie die Aufnahme vor dem Speichern.\nMöchten Sie die Aufnahme jetzt stoppen?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.Yes
            )
            
            if antwort == QMessageBox.Yes:
                self.stoppe_aufnahme()
            else:
                return  # Benutzer möchte nicht speichern
        
        # Dateinamen vorschlagen basierend auf aktuellem Datum und Modus
        vorschlag = f"Messdaten_{self.modus.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Dialog zum Speichern der Datei öffnen
        dateiname, _ = QFileDialog.getSaveFileName(
            self, "CSV-Datei speichern", vorschlag, "CSV-Dateien (*.csv)"
        )
        
        if dateiname:
            try:
                # CSV-Datei schreiben
                with open(dateiname, 'w', newline='') as csvfile:
                    feldnamen = ['Zeit', 'Wert', 'Modus']
                    writer = csv.DictWriter(csvfile, fieldnames=feldnamen)
                    
                    writer.writeheader()
                    for messung in self.messdaten:
                        writer.writerow(messung)
                
                # Status aktualisieren
                self.statusBar.showMessage(f"Messdaten wurden in {dateiname} gespeichert")
            except Exception as e:
                QMessageBox.critical(
                    self, "Fehler beim Speichern", 
                    f"Beim Speichern der Datei ist ein Fehler aufgetreten:\n{str(e)}"
                )
    
    def hilfe_anzeigen(self):
        """Zeigt Hilfeinformationen an"""
        from PyQt5.QtWidgets import QMessageBox
        
        hilfe_text = """
        Digitaler Multimeter
        
        Bedienung:
        1. Wählen Sie den Messmodus durch Klicken 
           auf die entsprechenden Tasten
        2. Wählen Sie den gewünschten Messbereich
        3. Klicken Sie 'Aufnahme starten', um die Messwerte
           aufzuzeichnen und im Diagramm anzuzeigen
        4. Klicken Sie 'Aufnahme stoppen', um die Aufzeichnung
           zu beenden
        
        Diagramm und Datenerfassung:
        - Das Diagramm wird nur angezeigt, wenn die 
          Datenaufnahme aktiviert ist
        - Bei Änderung des Messmodus werden Sie gefragt, ob 
          Sie die Datenerfassung fortsetzen möchten
        - Mit 'CSV speichern' können Sie die aufgezeichneten Daten 
          in einer CSV-Datei speichern (Zeit, Wert und Modus)
        
        Hinweise: 
        - Bei Überschreitung des Messbereichs wird "ÜBERLAST!"
          angezeigt und die Anzeige wechselt auf rot
        - Der aktuelle Status wird in der Statusleiste am 
          unteren Fensterrand angezeigt
        - Dies ist eine Simulation
        """
        
        QMessageBox.information(self, "Hilfe - Digitaler Multimeter", hilfe_text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Dem modernen LabVIEW-Stil ähnlich
    app.setStyle("Fusion")
    
    # Anwendung erstellen und anzeigen
    dmm = DigitalMultimeter()
    dmm.show()
    
    sys.exit(app.exec_())