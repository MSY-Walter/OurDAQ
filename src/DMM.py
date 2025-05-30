# -*- coding: utf-8 -*-
"""
Digitaler Multimeter für MCC 118
Ein LabVIEW-ähnlicher DMM für Spannungsmessungen mit MCC 118
Mit Überlastungswarnung, Diagrammanzeige und CSV-Datenspeicherung
Erweiterte Messbereich von ±10V bis ±200mV mit verbesserte Präzision
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
from daqhats import mcc118, OptionFlags, HatIDs, HatError

class MesswertAnzeige(QWidget):
    """Widget zur Anzeige des aktuellen Messwerts mit LabVIEW-ähnlicher Darstellung"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.wert = 0.0
        self.einheit = "V DC"
        self.bereich = 10.0  # Geändert von 20V auf 10V als Maximum
        self.ueberlast = False
        self.dezimalstellen = 2  # Standard-Dezimalstellen
        self.setMinimumHeight(120)
        self.setMinimumWidth(400)
        
        self.farbe = QColor(0, 210, 210)
        self.farbe_ueberlast = QColor(255, 50, 50)
        
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, Qt.black)
        self.setPalette(palette)
    
    def set_wert(self, wert, ueberlast=False):
        self.wert = wert
        self.ueberlast = ueberlast
        self.update()
    
    def set_einheit(self, einheit):
        self.einheit = einheit
        self.update()
    
    def set_bereich(self, bereich):
        self.bereich = bereich
        # Dezimalstellen basierend auf dem Messbereich anpassen
        if bereich >= 10.0:
            self.dezimalstellen = 3
        elif bereich >= 1.0:
            self.dezimalstellen = 4
        elif bereich >= 0.5:
            self.dezimalstellen = 5
        else:  # 200mV Bereich
            self.dezimalstellen = 6
        self.update()
    
    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        aktuelle_farbe = self.farbe_ueberlast if self.ueberlast else self.farbe
        
        font = QFont("Arial", 32, QFont.Bold)
        qp.setFont(font)
        qp.setPen(aktuelle_farbe)
        
        if self.ueberlast:
            text = "ÜBERLAST!"
        else:
            # Formatierung mit der entsprechenden Anzahl von Dezimalstellen
            format_string = f"{{:.{self.dezimalstellen}f}} {self.einheit}"
            text = format_string.format(self.wert)
            
        qp.drawText(self.rect(), Qt.AlignCenter, text)
        
        balken_hoehe = 10
        balken_y = self.height() - balken_hoehe - 30
        balken_breite = self.width() - 40
        balken_x = 20
        
        qp.setPen(QPen(aktuelle_farbe, 1))
        qp.drawRect(balken_x, balken_y, balken_breite, balken_hoehe)
        
        if self.ueberlast:
            prozent = 1.0
        else:
            prozent = min(max(0, abs(self.wert) / self.bereich), 1.0)
            
        qp.setBrush(QBrush(aktuelle_farbe))
        qp.drawRect(balken_x, balken_y, int(balken_breite * prozent), balken_hoehe)
        
        qp.setPen(QPen(aktuelle_farbe, 1))
        for i in range(11):
            x = balken_x + (balken_breite * i) // 10
            qp.drawLine(x, balken_y - 2, x, balken_y + balken_hoehe + 2)
        
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
        
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(QColor(240, 240, 240)))
        qp.drawRect(0, 0, self.width(), self.height())
        
        qp.setPen(QPen(Qt.black, 2))
        qp.drawLine(50, 50, self.width() - 50, 50)
        
        qp.setBrush(QBrush(QColor(255, 0, 0)))
        qp.drawEllipse(40, 40, 20, 20)
        qp.setFont(QFont("Arial", 8, QFont.Bold))
        qp.drawText(30, 80, 40, 20, Qt.AlignCenter, "V")
        
        qp.setBrush(QBrush(QColor(50, 50, 50)))
        qp.drawEllipse(self.width()//2 - 10, 40, 20, 20)
        qp.drawText(self.width()//2 - 20, 80, 40, 20, Qt.AlignCenter, "COM")
        
        qp.setBrush(QBrush(QColor(255, 0, 0)))
        qp.drawEllipse(self.width() - 60, 40, 20, 20)
        qp.drawText(self.width() - 70, 80, 40, 20, Qt.AlignCenter, "A")

class DiagrammAnzeige(QWidget):
    """Widget zur Anzeige eines zeitlichen Verlaufs der Messwerte"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.aktiv = False
        
        layout = QVBoxLayout(self)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setLabel('left', 'Spannung (V)')
        self.plot_widget.setLabel('bottom', 'Zeit (s)')
        self.plot_widget.showGrid(x=True, y=True)
        
        self.status_label = QLabel("Diagramm wird angezeigt, wenn Datenaufnahme aktiviert ist")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: #555;")
        
        self.kurve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 210, 210), width=3))
        
        self.x_daten = np.zeros(100)
        self.y_daten = np.zeros(100)
        self.start_zeit = time.time()
        
        layout.addWidget(self.status_label)
        layout.addWidget(self.plot_widget)
        self.plot_widget.hide()
    
    def set_aktiv(self, aktiv):
        self.aktiv = aktiv
        if aktiv:
            self.status_label.hide()
            self.plot_widget.show()
            self.reset_diagramm()
        else:
            self.status_label.show()
            self.plot_widget.hide()
    
    def aktualisiere_diagramm(self, wert):
        if not self.aktiv:
            return
            
        aktuelle_zeit = time.time() - self.start_zeit
        
        self.x_daten[:-1] = self.x_daten[1:]
        self.y_daten[:-1] = self.y_daten[1:]
        
        self.x_daten[-1] = aktuelle_zeit
        self.y_daten[-1] = wert
        
        self.kurve.setData(self.x_daten, self.y_daten)
    
    def reset_diagramm(self):
        self.x_daten = np.zeros(100)
        self.y_daten = np.zeros(100)
        self.start_zeit = time.time()
        self.kurve.setData(self.x_daten, self.y_daten)

class DigitalMultimeter(QMainWindow):
    """Hauptfenster des Digitalen Multimeters"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("OurDAQ - Digitalmultimeter")
        self.setGeometry(100, 100, 800, 700)
        
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        
        # MCC 118 Initialisierung
        self.hat = None
        self.init_mcc118()
        
        self.modus = "Spannung DC"
        self.bereich = 10.0  # Geändert von 20V auf 10V als Maximum
        self.channel = 0  # Standardmäßig Kanal 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.aktualisiere_messung)
        self.timer.start(100)
        
        self.ueberlast_status = False
        self.messdaten = []
        self.datenerfassung_aktiv = False
        
        self.setup_ui()
        
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Bereit - Keine Datenaufnahme aktiv")
    
    def init_mcc118(self):
        """Initialisiert das MCC 118 DAQ HAT"""
        try:
            self.hat = mcc118(0)
            print("MCC 118 erfolgreich initialisiert")
        except HatError as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Initialisieren des MCC 118: {str(e)}")
            sys.exit(1)
    
    def setup_ui(self):
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        haupt_layout.setSpacing(15)
        
        self.messwert_anzeige = MesswertAnzeige()
        haupt_layout.addWidget(self.messwert_anzeige)
        
        self.diagramm_anzeige = DiagrammAnzeige()
        haupt_layout.addWidget(self.diagramm_anzeige)
        
        einstellungen_gruppe = QGroupBox("Messeinstellungen")
        einstellungen_layout = QHBoxLayout(einstellungen_gruppe)
        
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)
        
        modus_label = QLabel("Messmodus:")
        modus_label.setFont(QFont("Arial", 10, QFont.Bold))
        buttons_layout.addWidget(modus_label)
        
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
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
        
        self.spannung_dc_btn = QPushButton("DC Spannung (V)")
        self.spannung_dc_btn.setFixedSize(150, 45)
        self.spannung_dc_btn.setCheckable(True)
        self.spannung_dc_btn.setChecked(True)
        self.spannung_dc_btn.setStyleSheet(button_style)
        self.spannung_dc_btn.clicked.connect(lambda: self.setze_modus("Spannung DC"))
        
        # AC und Strom deaktiviert, da MCC 118 nur DC Spannung misst
        self.spannung_ac_btn = QPushButton("AC Spannung (V)")
        self.spannung_ac_btn.setFixedSize(150, 45)
        self.spannung_ac_btn.setEnabled(False)
        self.spannung_ac_btn.setStyleSheet(button_style)
        
        self.strom_dc_btn = QPushButton("DC Strom (A)")
        self.strom_dc_btn.setFixedSize(150, 45)
        self.strom_dc_btn.setEnabled(False)
        self.strom_dc_btn.setStyleSheet(button_style)
        
        self.strom_ac_btn = QPushButton("AC Strom (A)")
        self.strom_ac_btn.setFixedSize(150, 45)
        self.strom_ac_btn.setEnabled(False)
        self.strom_ac_btn.setStyleSheet(button_style)
        
        button_grid.addWidget(self.spannung_dc_btn, 0, 0)
        button_grid.addWidget(self.spannung_ac_btn, 0, 1)
        button_grid.addWidget(self.strom_dc_btn, 1, 0)
        button_grid.addWidget(self.strom_ac_btn, 1, 1)
        
        buttons_layout.addLayout(button_grid)
        
        bereich_layout = QVBoxLayout()
        bereich_layout.setSpacing(10)
        
        bereich_label = QLabel("Messbereich:")
        bereich_label.setFont(QFont("Arial", 10, QFont.Bold))
        bereich_layout.addWidget(bereich_label)
        
        self.bereich_combo = QComboBox()
        self.bereich_combo.setFixedHeight(30)
        self.bereich_combo.setStyleSheet("font-size: 10pt;")
        self.aktualisiere_bereiche()
        self.bereich_combo.currentIndexChanged.connect(self.bereich_geaendert)
        bereich_layout.addWidget(self.bereich_combo)
        
        kanal_label = QLabel("Kanal:")
        kanal_label.setFont(QFont("Arial", 10, QFont.Bold))
        bereich_layout.addWidget(kanal_label)
        
        self.kanal_combo = QComboBox()
        self.kanal_combo.addItems(["Kanal 0", "Kanal 1", "Kanal 2", "Kanal 3", "Kanal 4", "Kanal 5", "Kanal 6", "Kanal 7"])
        self.kanal_combo.setFixedHeight(30)
        self.kanal_combo.setStyleSheet("font-size: 10pt;")
        self.kanal_combo.currentIndexChanged.connect(self.kanal_geaendert)
        bereich_layout.addWidget(self.kanal_combo)
        
        bereich_layout.addStretch()
        
        self.banana_visual = BananaJackVisualisierung()
        
        einstellungen_layout.addLayout(buttons_layout, 2)
        einstellungen_layout.addLayout(bereich_layout, 1)
        einstellungen_layout.addWidget(self.banana_visual, 1)
        
        haupt_layout.addWidget(einstellungen_gruppe)
        
        steuerung_gruppe = QGroupBox("Steuerung")
        steuerung_layout = QHBoxLayout(steuerung_gruppe)
        steuerung_layout.setSpacing(15)
        
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
        self.stop_aufnahme_btn.setEnabled(False)
        
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
        
        help_btn = QPushButton("Hilfe")
        help_btn.setStyleSheet(utility_style)
        help_btn.setFixedSize(100, 45)
        help_btn.clicked.connect(self.hilfe_anzeigen)
        
        steuerung_layout.addWidget(self.start_aufnahme_btn)
        steuerung_layout.addWidget(self.stop_aufnahme_btn)
        steuerung_layout.addWidget(self.csv_export_btn)
        steuerung_layout.addWidget(help_btn)
        steuerung_layout.addStretch()
        
        haupt_layout.addWidget(steuerung_gruppe)
        haupt_layout.addStretch(1)
    
    def setze_modus(self, modus):
        self.modus = modus
        
        self.spannung_dc_btn.setChecked(modus == "Spannung DC")
        self.spannung_ac_btn.setChecked(modus == "Spannung AC")
        self.strom_dc_btn.setChecked(modus == "Strom DC")
        self.strom_ac_btn.setChecked(modus == "Strom AC")
        
        self.aktualisiere_bereiche()
        
        if "Spannung" in modus:
            self.messwert_anzeige.set_einheit("V DC")
        else:
            self.messwert_anzeige.set_einheit("A DC")
        
        self.ueberlast_status = False
        
        if self.datenerfassung_aktiv:
            self.diagramm_anzeige.reset_diagramm()
            self.messdaten = []
            antwort = QMessageBox.question(
                self, "Messmode geändert", 
                "Möchten Sie die Datenerfassung mit dem neuen Messmodus fortsetzen?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.Yes
            )
            
            if antwort == QMessageBox.No:
                self.stoppe_aufnahme()
            else:
                self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
    
    def aktualisiere_bereiche(self):
        self.bereich_combo.clear()
        
        if "Spannung" in self.modus:
            # Geänderte Messbereiche ohne 20V und mit ±-Symbol
            self.bereich_combo.addItems(["±10V", "±2V", "±1V", "±500mV", "±200mV"])
            self.bereich = 10.0
        elif "Strom" in self.modus:
            self.bereich_combo.addItems(["±1A", "±500mA", "±200mA", "±100mA"])
            self.bereich = 1.0
        
        self.bereich_geaendert()
    
    def bereich_geaendert(self):
        bereich_text = self.bereich_combo.currentText()
        
        # Entfernen des ±-Symbols für die numerische Verarbeitung
        bereich_text_ohne_plus_minus = bereich_text.replace("±", "")
        
        if "V" in bereich_text_ohne_plus_minus:
            if "mV" in bereich_text_ohne_plus_minus:
                self.bereich = float(bereich_text_ohne_plus_minus.replace("mV", "")) / 1000.0
            else:
                self.bereich = float(bereich_text_ohne_plus_minus.replace("V", ""))
        elif "A" in bereich_text_ohne_plus_minus:
            if "mA" in bereich_text_ohne_plus_minus:
                self.bereich = float(bereich_text_ohne_plus_minus.replace("mA", "")) / 1000.0
            else:
                self.bereich = float(bereich_text_ohne_plus_minus.replace("A", ""))
        
        self.messwert_anzeige.set_bereich(self.bereich)
        self.ueberlast_status = False
        self.diagramm_anzeige.reset_diagramm()
        
        if self.datenerfassung_aktiv:
            self.messdaten = []
            self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - Messbereich auf {bereich_text} geändert")
    
    def kanal_geaendert(self):
        kanal_text = self.kanal_combo.currentText()
        self.channel = int(kanal_text.replace("Kanal ", ""))
        self.diagramm_anzeige.reset_diagramm()
        self.messdaten = []
        if self.datenerfassung_aktiv:
            self.statusBar.showMessage(f"Datenaufnahme für {self.modus} auf {kanal_text} - {len(self.messdaten)} Messpunkte")
    
    @pyqtSlot()
    def aktualisiere_messung(self):
        try:
            wert = self.hat.a_in_read(self.channel, OptionFlags.DEFAULT)
            
            if abs(wert) > self.bereich:
                if not self.ueberlast_status:
                    self.ueberlast_status = True
                    self.zeige_ueberlast_warnung()
                
                self.messwert_anzeige.set_wert(wert, True)
                
                if self.datenerfassung_aktiv:
                    self.statusBar.showMessage(f"ÜBERLAST! Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
            else:
                if self.ueberlast_status:
                    self.ueberlast_status = False
                    if self.datenerfassung_aktiv:
                        self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
                
                self.messwert_anzeige.set_wert(wert, False)
            
            if self.datenerfassung_aktiv:
                self.diagramm_anzeige.aktualisiere_diagramm(wert)
                
                zeit = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self.messdaten.append({
                    'Zeit': zeit,
                    'Wert': wert,
                    'Modus': self.modus,
                    'Kanal': self.channel,
                    'Bereich': self.bereich
                })
                
                if len(self.messdaten) % 10 == 0:
                    self.statusBar.showMessage(f"Datenaufnahme für {self.modus} aktiv - {len(self.messdaten)} Messpunkte")
                    
        except HatError as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Lesen der Messwerte: {str(e)}")
            self.stoppe_aufnahme()
    
    def zeige_ueberlast_warnung(self):
        self.statusBar.showMessage("ÜBERLAST! Messbereichsüberschreitung erkannt!")
        
        try:
            from PyQt5.QtMultimedia import QSound
            QSound.play("alarm.wav")
        except:
            pass
    
    def starte_aufnahme(self):
        self.datenerfassung_aktiv = True
        self.messdaten = []
        
        self.diagramm_anzeige.set_aktiv(True)
        
        self.start_aufnahme_btn.setEnabled(False)
        self.stop_aufnahme_btn.setEnabled(True)
        
        self.diagramm_anzeige.reset_diagramm()
        
        self.statusBar.showMessage(f"Datenaufnahme für {self.modus} gestartet")
    
    def stoppe_aufnahme(self):
        if not self.datenerfassung_aktiv:
            return
            
        self.datenerfassung_aktiv = False
        
        self.diagramm_anzeige.set_aktiv(False)
        
        self.start_aufnahme_btn.setEnabled(True)
        self.stop_aufnahme_btn.setEnabled(False)
        
        self.statusBar.showMessage(f"Datenaufnahme gestoppt - {len(self.messdaten)} Messpunkte aufgezeichnet")
    
    def csv_speichern(self):
        if not self.messdaten:
            QMessageBox.warning(self, "Keine Daten", "Es sind keine Messdaten zum Speichern vorhanden.")
            return
        
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
                return
        
        vorschlag = f"Messdaten_{self.modus.replace(' ', '_')}_Kanal{self.channel}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        dateiname, _ = QFileDialog.getSaveFileName(
            self, "CSV-Datei speichern", vorschlag, "CSV-Dateien (*.csv)"
        )
        
        if dateiname:
            try:
                with open(dateiname, 'w', newline='') as csvfile:
                    feldnamen = ['Zeit', 'Wert', 'Modus', 'Kanal', 'Bereich']
                    writer = csv.DictWriter(csvfile, fieldnames=feldnamen)
                    
                    writer.writeheader()
                    for messung in self.messdaten:
                        writer.writerow(messung)
                
                self.statusBar.showMessage(f"Messdaten wurden in {dateiname} gespeichert")
            except Exception as e:
                QMessageBox.critical(
                    self, "Fehler beim Speichern", 
                    f"Beim Speichern der Datei ist ein Fehler aufgetreten:\n{str(e)}"
                )
    
    def hilfe_anzeigen(self):
        hilfe_text = """
        Digitaler Multimeter für MCC 118
        
        Bedienung:
        1. Wählen Sie den Messmodus (derzeit nur DC Spannung)
        2. Wählen Sie den Messbereich (±10V, ±2V, ±1V, ±500mV, ±200mV)
        3. Wählen Sie den Kanal (Kanal 0 bis Kanal 7)
        4. Klicken Sie 'Aufnahme starten', um Messwerte aufzuzeichnen
        5. Klicken Sie 'Aufnahme stoppen', um die Aufzeichnung zu beenden
        
        Diagramm und Datenerfassung:
        - Das Diagramm zeigt Messwerte nur bei aktiver Datenaufnahme
        - Bei Änderung von Modus, Bereich oder Kanal wird das Diagramm zurückgesetzt
        - Mit 'CSV speichern' können Sie die Daten (Zeit, Wert, Modus, Kanal, Bereich) speichern
        
        Hinweise: 
        - Überlast wird angezeigt, wenn die Spannung den Messbereich überschreitet
        - Der MCC 118 misst Spannungen bis ±10 V
        - Die Anzahl der Dezimalstellen passt sich automatisch an den Messbereich an
        - Strommessungen erfordern externe Hardware (Shunt-Widerstand)
        """
        
        QMessageBox.information(self, "Hilfe", hilfe_text)
    
    def closeEvent(self, event):
        self.stoppe_aufnahme()
        if self.hat:
            del self.hat
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    dmm = DigitalMultimeter()
    dmm.show()
    sys.exit(app.exec_())