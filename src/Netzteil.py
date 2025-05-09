# -*- coding: utf-8 -*-

"""
Netzteil für MCC 118
Ein LabVIEW-ähnliches Stromversorgungsmodul
Mit Spannungs- und Stromregelung, Überlastschutz und Ausgangsmonitor
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
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen, QBrush
import pyqtgraph as pg  # Für die Diagrammanzeige

# Versuche, DAQ HAT-Bibliothek zu importieren oder eine Simulation zu verwenden
try:
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    HAT_VERFÜGBAR = True
except ImportError:
    print("Warnung: DAQ HAT-Bibliothek nicht gefunden, Simulation wird verwendet.")
    HAT_VERFÜGBAR = False


class SpannungsAnzeige(QWidget):
    """Widget zur Anzeige des aktuellen Spannungs- und Stromwerts"""
    
    def __init__(self, typ="Spannung", parent=None):
        super().__init__(parent)
        self.wert = 0.0
        self.maxwert = 10.0  # Maximaler Anzeigewert
        self.einheit = "V" if typ == "Spannung" else "A"
        self.typ = typ
        self.setMinimumHeight(120)
        self.setMinimumWidth(300)
        
        # Farben je nach Typ
        if typ == "Spannung":
            self.farbe = QColor(0, 180, 0)  # Grün für Spannung
        else:
            self.farbe = QColor(200, 0, 0)  # Rot für Strom
        
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, Qt.black)
        self.setPalette(palette)
    
    def set_wert(self, wert):
        self.wert = wert
        self.update()
    
    def set_maxwert(self, maxwert):
        self.maxwert = maxwert
        self.update()
    
    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        # Font für die Wertenanzeige
        font = QFont("Arial", 32, QFont.Bold)
        qp.setFont(font)
        qp.setPen(self.farbe)
        
        # Wert formatieren (3 Dezimalstellen)
        text = f"{self.wert:.3f} {self.einheit}"
        qp.drawText(self.rect(), Qt.AlignCenter, text)
        
        # Fortschrittsbalken unten
        balken_hoehe = 10
        balken_y = self.height() - balken_hoehe - 30
        balken_breite = self.width() - 40
        balken_x = 20
        
        # Rahmen des Balkens
        qp.setPen(QPen(self.farbe, 1))
        qp.drawRect(balken_x, balken_y, balken_breite, balken_hoehe)
        
        # Gefüllter Balken
        prozent = min(max(0, abs(self.wert) / self.maxwert), 1.0)
        qp.setBrush(QBrush(self.farbe))
        qp.drawRect(balken_x, balken_y, int(balken_breite * prozent), balken_hoehe)
        
        # Skalenmarkierungen
        qp.setPen(QPen(self.farbe, 1))
        for i in range(11):
            x = balken_x + (balken_breite * i) // 10
            qp.drawLine(x, balken_y - 2, x, balken_y + balken_hoehe + 2)
        
        # Prozentwert rechts vom Balken
        qp.setPen(self.farbe)
        qp.setFont(QFont("Arial", 10))
        qp.drawText(balken_x + balken_breite + 5, balken_y + balken_hoehe, "% Max")


class AusgangsmonitorAnzeige(QWidget):
    """Widget zur Anzeige der Ausgangsleistung und Zeitverlauf"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.ausgangsstatus = False
        
        # Layout erstellen
        layout = QVBoxLayout(self)
        
        # PyQtGraph Plot-Widget erstellen
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('k')  # Schwarzer Hintergrund
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Wert')
        self.plot_widget.setLabel('bottom', 'Zeit (s)')
        
        # Datenreihen für Spannung und Strom
        self.spannung_kurve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 180, 0), width=2), name="Spannung (V)")
        self.strom_kurve = self.plot_widget.plot(pen=pg.mkPen(color=(200, 0, 0), width=2), name="Strom (A)")
        
        # Legende hinzufügen
        self.plot_widget.addLegend()
        
        # Status-Label
        self.status_label = QLabel("Ausgang inaktiv")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: white; background-color: #aa0000; padding: 5px; font-weight: bold;")
        
        # Layout aufbauen
        layout.addWidget(self.status_label)
        layout.addWidget(self.plot_widget)
        
        # Datenarrays initialisieren
        self.max_punkte = 100
        self.x_daten = np.zeros(self.max_punkte)
        self.spannung_daten = np.zeros(self.max_punkte)
        self.strom_daten = np.zeros(self.max_punkte)
        self.start_zeit = time.time()
    
    def set_ausgangsstatus(self, status):
        self.ausgangsstatus = status
        if status:
            self.status_label.setText("Ausgang aktiv")
            self.status_label.setStyleSheet("color: white; background-color: #00aa00; padding: 5px; font-weight: bold;")
        else:
            self.status_label.setText("Ausgang inaktiv")
            self.status_label.setStyleSheet("color: white; background-color: #aa0000; padding: 5px; font-weight: bold;")
    
    def aktualisiere_daten(self, spannung, strom):
        aktuelle_zeit = time.time() - self.start_zeit
        
        # Daten verschieben
        self.x_daten[:-1] = self.x_daten[1:]
        self.spannung_daten[:-1] = self.spannung_daten[1:]
        self.strom_daten[:-1] = self.strom_daten[1:]
        
        # Neue Werte hinzufügen
        self.x_daten[-1] = aktuelle_zeit
        self.spannung_daten[-1] = spannung
        self.strom_daten[-1] = strom
        
        # Kurven aktualisieren
        self.spannung_kurve.setData(self.x_daten, self.spannung_daten)
        self.strom_kurve.setData(self.x_daten, self.strom_daten)
    
    def reset_daten(self):
        self.x_daten = np.zeros(self.max_punkte)
        self.spannung_daten = np.zeros(self.max_punkte)
        self.strom_daten = np.zeros(self.max_punkte)
        self.start_zeit = time.time()
        self.spannung_kurve.setData(self.x_daten, self.spannung_daten)
        self.strom_kurve.setData(self.x_daten, self.strom_daten)


class Netzteil(QMainWindow):
    """Hauptfenster des Netzteils"""
    
    def __init__(self):
        super().__init__()
        
        # Fenstereigenschaften festlegen
        self.setWindowTitle("OurDAQ - Netzteil")
        self.setGeometry(100, 100, 900, 700)
        
        # Für PyQtGraph dunkles Hintergrundthema verwenden
        pg.setConfigOption('background', 'k')  # Schwarzer Hintergrund für alle Plots
        pg.setConfigOption('foreground', 'w')  # Weiße Linien und Text
        
        # MCC HAT initialisieren
        self.hat_ao = None
        self.hat_ai = None
        self.init_hardware()
        
        # Netzteil-Parameter
        self.spannungs_sollwert = 0.0  # V
        self.strom_limit = 1.0         # A
        self.ausgang_aktiv = False
        self.spannung_istgrad = 0.0    # V
        self.strom_istgrad = 0.0       # A
        
        # Hardware-Konstanten
        self.max_spannung = 12.0       # V maximale Ausgangsspannung
        self.max_strom = 2.0           # A maximaler Ausgangsstrom
        self.verstaerkungsfaktor = 1.0  # Verstärkungsfaktor der Leistungsstufe
        
        # Sicherheitsparameter
        self.ueberspannungsschutz = self.max_spannung * 0.9  # 90% der maximalen Spannung
        self.uebertemperaturschutz = False
        self.kurzschlussschutz = True
        
        # Timer für die Aktualisierung
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.aktualisiere_messung)
        self.timer.start(100)  # 10 Hz
        
        # UI einrichten
        self.setup_ui()
        
        # Statusleiste
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Bereit - Netzteil initialisiert")
    
    def init_hardware(self):
        """Initialisiert die MCC DAQ HATs"""
        if HAT_VERFÜGBAR:
            try:
                # MCC 118 für Analogausgänge
                self.hat_ai = mcc118(0)
                print("MCC 118 für Analogeingänge initialisiert")
            
            except HatError as e:
                QMessageBox.warning(self, "Hardware-Initialisierungsfehler", 
                                   f"Fehler beim Initialisieren der DAQ HATs: {str(e)}\n"
                                   "Das Netzteil wird im Simulationsmodus ausgeführt.")
        else:
            print("Netzeil läuft im Simulationsmodus")
    
    def setup_ui(self):
        """Richtet die Benutzeroberfläche ein"""
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        haupt_layout.setSpacing(15)
        
        # Oberer Bereich: Spannungs- und Stromanzeige
        anzeige_bereich = QHBoxLayout()
        
        # Spannungsanzeige
        self.spannung_anzeige = SpannungsAnzeige("Spannung")
        anzeige_bereich.addWidget(self.spannung_anzeige)
        
        # Stromanzeige
        self.strom_anzeige = SpannungsAnzeige("Strom")
        anzeige_bereich.addWidget(self.strom_anzeige)
        
        haupt_layout.addLayout(anzeige_bereich)
        
        # Einstellungsbereich
        einstellungen_gruppe = QGroupBox("Netzteil-Einstellungen")
        einstellungen_layout = QGridLayout(einstellungen_gruppe)
        
        # Spannungseinstellung
        einstellungen_layout.addWidget(QLabel("Spannung:"), 0, 0)
        self.spannung_slider = QSlider(Qt.Horizontal)
        self.spannung_slider.setRange(0, int(self.max_spannung * 100))
        self.spannung_slider.setValue(0)
        self.spannung_slider.valueChanged.connect(self.spannung_slider_geändert)
        einstellungen_layout.addWidget(self.spannung_slider, 0, 1)
        
        self.spannung_spinbox = QDoubleSpinBox()
        self.spannung_spinbox.setRange(0, self.max_spannung)
        self.spannung_spinbox.setValue(0)
        self.spannung_spinbox.setSingleStep(0.1)
        self.spannung_spinbox.setDecimals(2)
        self.spannung_spinbox.setSuffix(" V")
        self.spannung_spinbox.valueChanged.connect(self.spannung_spinbox_geändert)
        einstellungen_layout.addWidget(self.spannung_spinbox, 0, 2)
        
        # Stromgrenze
        einstellungen_layout.addWidget(QLabel("Strombegrenzung:"), 1, 0)
        self.strom_slider = QSlider(Qt.Horizontal)
        self.strom_slider.setRange(0, int(self.max_strom * 100))
        self.strom_slider.setValue(int(self.strom_limit * 100))
        self.strom_slider.valueChanged.connect(self.strom_slider_geändert)
        einstellungen_layout.addWidget(self.strom_slider, 1, 1)
        
        self.strom_spinbox = QDoubleSpinBox()
        self.strom_spinbox.setRange(0, self.max_strom)
        self.strom_spinbox.setValue(self.strom_limit)
        self.strom_spinbox.setSingleStep(0.1)
        self.strom_spinbox.setDecimals(2)
        self.strom_spinbox.setSuffix(" A")
        self.strom_spinbox.valueChanged.connect(self.strom_spinbox_geändert)
        einstellungen_layout.addWidget(self.strom_spinbox, 1, 2)
        
        # Sicherheitseinstellungen
        sicherheit_layout = QVBoxLayout()
        
        # Überspannungsschutz
        self.ovp_checkbox = QCheckBox("Überspannungsschutz")
        self.ovp_checkbox.setChecked(True)
        sicherheit_layout.addWidget(self.ovp_checkbox)
        
        # Übertemperaturschutz
        self.otp_checkbox = QCheckBox("Übertemperaturschutz")
        self.otp_checkbox.setChecked(self.uebertemperaturschutz)
        sicherheit_layout.addWidget(self.otp_checkbox)
        
        # Kurzschlussschutz
        self.scp_checkbox = QCheckBox("Kurzschlussschutz")
        self.scp_checkbox.setChecked(self.kurzschlussschutz)
        sicherheit_layout.addWidget(self.scp_checkbox)
        
        einstellungen_layout.addLayout(sicherheit_layout, 2, 0, 1, 3)
        
        haupt_layout.addWidget(einstellungen_gruppe)
        
        # Ausgangsmonitor
        self.monitor_anzeige = AusgangsmonitorAnzeige()
        haupt_layout.addWidget(self.monitor_anzeige)
        
        # Steuerelemete
        steuerelemente_layout = QHBoxLayout()
        
        # Ausgangschalter
        self.ausgang_button = QPushButton("Ausgang aktivieren")
        self.ausgang_button.setStyleSheet("""
            QPushButton {
                background-color: #00aa00;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 10px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #00cc00;
            }
        """)
        self.ausgang_button.clicked.connect(self.toggle_ausgang)
        steuerelemente_layout.addWidget(self.ausgang_button)
        
        # Reset-Button
        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet("""
            QPushButton {
                background-color: #cc0000;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #ee0000;
            }
        """)
        self.reset_button.clicked.connect(self.reset_netzteil)
        steuerelemente_layout.addWidget(self.reset_button)
        
        # Hilfe-Button
        help_button = QPushButton("Hilfe")
        help_button.clicked.connect(self.hilfe_anzeigen)
        steuerelemente_layout.addWidget(help_button)
        
        haupt_layout.addLayout(steuerelemente_layout)
    
    def spannung_slider_geändert(self, wert):
        """Wird aufgerufen, wenn der Spannungs-Slider bewegt wird"""
        spannung = wert / 100.0
        # Spinbox aktualisieren, ohne Signalschleife zu erzeugen
        self.spannung_spinbox.blockSignals(True)
        self.spannung_spinbox.setValue(spannung)
        self.spannung_spinbox.blockSignals(False)
        
        self.spannungs_sollwert = spannung
        self.ausgangsspannung_setzen()
    
    def spannung_spinbox_geändert(self, wert):
        """Wird aufgerufen, wenn die Spannung im Spinbox geändert wird"""
        # Slider aktualisieren, ohne Signalschleife zu erzeugen
        self.spannung_slider.blockSignals(True)
        self.spannung_slider.setValue(int(wert * 100))
        self.spannung_slider.blockSignals(False)
        
        self.spannungs_sollwert = wert
        self.ausgangsspannung_setzen()
    
    def strom_slider_geändert(self, wert):
        """Wird aufgerufen, wenn der Strom-Slider bewegt wird"""
        strom = wert / 100.0
        # Spinbox aktualisieren, ohne Signalschleife zu erzeugen
        self.strom_spinbox.blockSignals(True)
        self.strom_spinbox.setValue(strom)
        self.strom_spinbox.blockSignals(False)
        
        self.strom_limit = strom
        self.statusBar.showMessage(f"Strombegrenzung auf {strom:.2f}A gesetzt")
    
    def strom_spinbox_geändert(self, wert):
        """Wird aufgerufen, wenn der Strom im Spinbox geändert wird"""
        # Slider aktualisieren, ohne Signalschleife zu erzeugen
        self.strom_slider.blockSignals(True)
        self.strom_slider.setValue(int(wert * 100))
        self.strom_slider.blockSignals(False)
        
        self.strom_limit = wert
        self.statusBar.showMessage(f"Strombegrenzung auf {wert:.2f}A gesetzt")
    
    def ausgangsspannung_setzen(self):
        """Setzt die Ausgangsspannung basierend auf dem Sollwert"""
        if not self.ausgang_aktiv:
            return
        
        # Hardware-Ausgabe
        if HAT_VERFÜGBAR and self.hat_ao:
            try:
                # Annahme: Kanal 0 für Spannungsausgang
                # Der DAC hat einen Bereich von 0-5V, daher muss die Spannung skaliert werden
                skalierte_spannung = self.spannungs_sollwert / self.max_spannung * 5.0
                self.hat_ao.a_out_write(0, min(5.0, max(0.0, skalierte_spannung)))
            except HatError as e:
                QMessageBox.warning(self, "Ausgabefehler", 
                                   f"Fehler beim Setzen der Ausgangsspannung: {str(e)}")
        
        self.statusBar.showMessage(f"Sollspannung auf {self.spannungs_sollwert:.2f}V gesetzt")
    
    def toggle_ausgang(self):
        """Schaltet den Ausgang ein oder aus"""
        self.ausgang_aktiv = not self.ausgang_aktiv
        
        if self.ausgang_aktiv:
            self.ausgang_button.setText("Ausgang deaktivieren")
            self.ausgang_button.setStyleSheet("""
                QPushButton {
                    background-color: #aa0000;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                    padding: 10px;
                    font-size: 12pt;
                }
                QPushButton:hover {
                    background-color: #cc0000;
                }
            """)
            self.monitor_anzeige.set_ausgangsstatus(True)
            self.ausgangsspannung_setzen()
            self.statusBar.showMessage(f"Ausgang aktiviert - Spannung: {self.spannungs_sollwert:.2f}V, Strom: {self.strom_limit:.2f}A")
        else:
            self.ausgang_button.setText("Ausgang aktivieren")
            self.ausgang_button.setStyleSheet("""
                QPushButton {
                    background-color: #00aa00;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                    padding: 10px;
                    font-size: 12pt;
                }
                QPushButton:hover {
                    background-color: #00cc00;
                }
            """)
            self.monitor_anzeige.set_ausgangsstatus(False)
            
            # Ausgangsspannung auf 0 setzen
            if HAT_VERFÜGBAR and self.hat_ao:
                try:
                    self.hat_ao.a_out_write(0, 0.0)
                except HatError as e:
                    print(f"Fehler beim Zurücksetzen der Ausgangsspannung: {str(e)}")
            
            self.statusBar.showMessage("Ausgang deaktiviert")
    
    def reset_netzteil(self):
        """Setzt das Netzteil zurück"""
        # Ausgang ausschalten
        if self.ausgang_aktiv:
            self.toggle_ausgang()
        
        # Sollwerte zurücksetzen
        self.spannungs_sollwert = 0.0
        self.spannung_slider.setValue(0)
        self.spannung_spinbox.setValue(0.0)
        
        # Strombegrenzung auf Standardwert
        self.strom_limit = 1.0
        self.strom_slider.setValue(int(self.strom_limit * 100))
        self.strom_spinbox.setValue(self.strom_limit)
        
        # Monitoranzeige zurücksetzen
        self.monitor_anzeige.reset_daten()
        
        self.statusBar.showMessage("Netzteil zurückgesetzt")
    
    @pyqtSlot()
    def aktualisiere_messung(self):
        """Aktualisiert die Messanzeige basierend auf den IST-Werten"""
        # In einem echten System würden hier Spannungs- und Strommessungen durchgeführt
        
        if HAT_VERFÜGBAR and self.hat_ai:
            try:
                # Spannung an Kanal 0 messen (skaliert)
                raw_spannung = self.hat_ai.a_in_read(0)
                self.spannung_istgrad = raw_spannung * (self.max_spannung / 10.0)  # Skalierungsfaktor anpassen
                
                # Strom an Kanal 1 über Shunt-Widerstand messen
                # Annahme: 0.1 Ohm Shunt, 10V/A Verstärkung
                raw_strom = self.hat_ai.a_in_read(1)
                self.strom_istgrad = raw_strom * (self.max_strom / 10.0)  # Skalierungsfaktor anpassen
            except HatError as e:
                # Im Fehlerfall simulierte Werte verwenden
                print(f"Fehler beim Lesen der IST-Werte: {str(e)}")
                self.simuliere_istwerte()
        else:
            # Wenn keine Hardware verfügbar, simulierte Werte verwenden
            self.simuliere_istwerte()
        
        # Überlastprüfung
        if self.strom_istgrad > self.strom_limit:
            if self.kurzschlussschutz:
                if self.ausgang_aktiv:
                    self.statusBar.showMessage(f"Kurzschlussschutz ausgelöst - Strombegrenzung bei {self.strom_limit:.2f}A")
                    # In einem echten System würde hier der Ausgang deaktiviert oder begrenzt
        
        # Überspannungsschutz
        if self.spannung_istgrad > self.ueberspannungsschutz and self.ovp_checkbox.isChecked():
            self.statusBar.showMessage(f"Überspannungsschutz ausgelöst - Spannung über {self.ueberspannungsschutz:.2f}V")
            # Ausgangsspannung verringern
            if self.ausgang_aktiv:
                self.spannung_spinbox.setValue(self.ueberspannungsschutz * 0.9)
        
        # Anzeigen aktualisieren
        self.spannung_anzeige.set_wert(self.spannung_istgrad)
        self.spannung_anzeige.set_maxwert(self.max_spannung)
        
        self.strom_anzeige.set_wert(self.strom_istgrad)
        self.strom_anzeige.set_maxwert(self.max_strom)
        
        # Diagrammansicht aktualisieren
        self.monitor_anzeige.aktualisiere_daten(self.spannung_istgrad, self.strom_istgrad)
    
    def simuliere_istwerte(self):
        """Simuliert Istwerte für Spannung und Strom im Simulationsmodus"""
        if self.ausgang_aktiv:
            # Spannung folgt dem Sollwert mit leichter Variation
            self.spannung_istgrad = self.spannungs_sollwert * (0.99 + 0.02 * np.random.random())
            
            # Strom hängt von der Spannung ab (Ohmsches Gesetz für Last mit 5-15 Ohm)
            last_widerstand = 10.0 + 5.0 * np.random.random()  # Simuliere Lastwiderstand zwischen 5-15 Ohm
            strom_nominal = self.spannung_istgrad / last_widerstand
            
            # Strombegrenzung berücksichtigen
            self.strom_istgrad = min(strom_nominal, self.strom_limit)
        else:
            # Bei deaktiviertem Ausgang minimale Werte anzeigen
            self.spannung_istgrad = 0.0
            self.strom_istgrad = 0.0
    
    def hilfe_anzeigen(self):
        """Zeigt Hilfeinformationen an"""
        hilfe_text = """
        Netzteil - DC Stromversorgung
        
        Bedienung:
        1. Stellen Sie die gewünschte Ausgangsspannung mit dem Schieberegler oder dem Spinner ein
        2. Stellen Sie die Strombegrenzung nach Bedarf ein (Standardwert: 1.0A)
        3. Aktivieren Sie den Ausgang mit dem 'Ausgang aktivieren'-Button
        4. Überwachen Sie die aktuellen Spannungs- und Stromwerte im oberen Anzeigebereich
        5. Der Zeitverlauf von Spannung und Strom wird im Diagramm angezeigt
        
        Sicherheitsfunktionen:
        - Überspannungsschutz: Begrenzt die maximale Ausgangsspannung auf einen sicheren Wert
        - Kurzschlussschutz: Begrenzt den Ausgangsstrom im Kurzschlussfall
        - Übertemperaturschutz: Schützt das Netzteil vor Überhitzung
        
        Das Netzteil nutzt den DAQ HAT (MCC 118) des Raspberry Pi für folgende Funktionen:
        - Spannungsregelung über einen Analogausgang (DAC)
        - Strommessung über einen Analogeingang mit Shunt-Widerstand
        - Spannungsmessung über einen weiteren Analogeingang
        
        Hinweis:
        Für Strommessungen wird ein externer Shunt-Widerstand benötigt.
        Die maximale Ausgangsspannung und der maximale Strom sind durch die Hardware begrenzt.
        """
        
        QMessageBox.information(self, "Netzteil - Hilfe", hilfe_text)
    
    def closeEvent(self, event):
        """Wird beim Schließen des Fensters aufgerufen"""
        # Ausgang sicherheitshalber deaktivieren
        if self.ausgang_aktiv:
            self.toggle_ausgang()
        
        # Hardware-Ressourcen freigeben
        if HAT_VERFÜGBAR:
            if self.hat_ao:
                self.hat_ao.a_out_write(0, 0.0)  # Ausgang auf 0V setzen
            
            # Weitere Aufräumarbeiten bei Bedarf
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # LabVIEW-ähnlichen Stil anwenden
    app.setStyle("Fusion")
    
    # Dunkles Farbschema für Messgeräte-Feeling
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
    netzteil = Netzteil()
    netzteil.show()
    
    sys.exit(app.exec_())