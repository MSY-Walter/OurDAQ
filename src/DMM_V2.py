#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Digitaler Multimeter für MCC 118
Ein LabVIEW-ähnlicher DMM für Spannungs- und Strommessungen
Mit Überlastungswarnung
"""

import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                           QComboBox, QCheckBox, QFrame, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPen, QBrush

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


class DigitalMultimeter(QMainWindow):
    """Hauptfenster des Digitalen Multimeters"""
    
    def __init__(self):
        super().__init__()
        
        # Fenstereigenschaften festlegen
        self.setWindowTitle("Digital Multimeter")
        self.setGeometry(100, 100, 600, 600)
        
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
        
        # UI einrichten
        self.setup_ui()
    
    def setup_ui(self):
        """Richtet die Benutzeroberfläche ein"""
        # Hauptwidget und Layout
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        haupt_layout = QVBoxLayout(zentral_widget)
        
        # Messwertanzeige
        self.messwert_anzeige = MesswertAnzeige()
        haupt_layout.addWidget(self.messwert_anzeige)
        
        # Messungseinstellungen-Gruppe
        einstellungen_gruppe = QGroupBox("Messeinstellungen")
        einstellungen_layout = QGridLayout(einstellungen_gruppe)
        
        # Messmodus-Buttons
        modus_layout = QHBoxLayout()
        
        # Spannung DC-Button
        self.spannung_dc_btn = QPushButton("DC Spannung (V)")
        self.spannung_dc_btn.setFixedSize(100, 40)
        self.spannung_dc_btn.setCheckable(True)
        self.spannung_dc_btn.setChecked(True)  # Standardmäßig ausgewählt
        self.spannung_dc_btn.clicked.connect(lambda: self.setze_modus("Spannung DC"))
        
        # Spannung AC-Button
        self.spannung_ac_btn = QPushButton("AC Spannung (V)")
        self.spannung_ac_btn.setFixedSize(100, 40)
        self.spannung_ac_btn.setCheckable(True)
        self.spannung_ac_btn.clicked.connect(lambda: self.setze_modus("Spannung AC"))
        
        # Strom DC-Button
        self.strom_dc_btn = QPushButton("DC Strom (A)")
        self.strom_dc_btn.setFixedSize(100, 40)
        self.strom_dc_btn.setCheckable(True)
        self.strom_dc_btn.clicked.connect(lambda: self.setze_modus("Strom DC"))
        
        # Strom AC-Button
        self.strom_ac_btn = QPushButton("AC Strom (A)")
        self.strom_ac_btn.setFixedSize(100, 40)
        self.strom_ac_btn.setCheckable(True)
        self.strom_ac_btn.clicked.connect(lambda: self.setze_modus("Strom AC"))
        
        # Buttons zum Layout hinzufügen
        modus_layout.addWidget(self.spannung_dc_btn)
        modus_layout.addWidget(self.spannung_ac_btn)
        modus_layout.addWidget(self.strom_dc_btn)
        modus_layout.addWidget(self.strom_ac_btn)
        
        einstellungen_layout.addLayout(modus_layout, 0, 0, 1, 2)
        
        # Modus-Label und Bereichseinstellung
        einstellungen_layout.addWidget(QLabel("Mode"), 1, 0)
        self.modus_combo = QComboBox()
        self.modus_combo.addItem("Messbereich")
        self.modus_combo.setEnabled(True)
        einstellungen_layout.addWidget(self.modus_combo, 1, 1)
        
        # Bereichs-Label und Dropdown
        einstellungen_layout.addWidget(QLabel("Messbereich"), 2, 0)
        self.bereich_combo = QComboBox()
        self.aktualisiere_bereiche()
        self.bereich_combo.currentIndexChanged.connect(self.bereich_geaendert)
        einstellungen_layout.addWidget(self.bereich_combo, 2, 1)
        
        # Null-Offset Checkbox
        einstellungen_layout.addWidget(QCheckBox("Null Offset"), 3, 0)
        
        # Banana Jack Visualisierung
        self.banana_visual = BananaJackVisualisierung()
        einstellungen_layout.addWidget(self.banana_visual, 1, 2, 2, 1)
        
        haupt_layout.addWidget(einstellungen_gruppe)
        
        # Gerätekontrolle-Gruppe
        kontrolle_gruppe = QGroupBox("Instrumentensteuerung")
        kontrolle_layout = QGridLayout(kontrolle_gruppe)
        
        # Geräteauswahl
        kontrolle_layout.addWidget(QLabel("Gerät"), 0, 0)
        geraet_combo = QComboBox()
        geraet_combo.addItem("MCC 118")
        kontrolle_layout.addWidget(geraet_combo, 0, 1)
        
        # Run/Stop/Help Buttons
        run_btn = QPushButton("Start")
        run_btn.setStyleSheet("background-color: green; color: white;")
        run_btn.setFixedSize(80, 40)
        run_btn.clicked.connect(self.starten)
        
        stop_btn = QPushButton("Stop")
        stop_btn.setStyleSheet("background-color: red; color: white;")
        stop_btn.setFixedSize(80, 40)
        stop_btn.clicked.connect(self.stoppen)
        
        help_btn = QPushButton("Hilfe")
        help_btn.setFixedSize(80, 40)
        help_btn.clicked.connect(self.hilfe_anzeigen)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(run_btn)
        button_layout.addWidget(stop_btn)
        button_layout.addWidget(help_btn)
        
        kontrolle_layout.addLayout(button_layout, 1, 0, 1, 4)
        
        haupt_layout.addWidget(kontrolle_gruppe)
    
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
        else:
            # Wenn nicht mehr überlastet, Überlast-Status zurücksetzen
            if self.ueberlast_status:
                self.ueberlast_status = False
            
            # Normalen Wert anzeigen
            self.messwert_anzeige.set_wert(wert, False)
    
    def zeige_ueberlast_warnung(self):
        """Zeigt eine Warnungsmeldung an, wenn Überlast erkannt wird"""
        # Optional: Akustisches Signal abspielen (wenn verfügbar)
        try:
            from PyQt5.QtMultimedia import QSound
            QSound.play("alarm.wav")
        except:
            pass  # Ignoriere Fehler, wenn Sound nicht unterstützt wird
    
    def starten(self):
        """Startet die Messung"""
        self.timer.start(100)
    
    def stoppen(self):
        """Stoppt die Messung"""
        self.timer.stop()
    
    def hilfe_anzeigen(self):
        """Zeigt Hilfeinformationen an"""
        from PyQt5.QtWidgets import QMessageBox
        
        hilfe_text = """
        Digitaler Multimeter
        
        Bedienung:
        1. Wählen Sie den Messmodus durch Klicken 
           auf die entsprechenden Tasten
        2. Wählen Sie den gewünschten Messbereich
        3. Drücken Sie 'Start', um die Messung zu starten
        4. Drücken Sie 'Stop', um die Messung zu beenden
        
        Hinweise: 
        - Bei Überschreitung des Messbereichs wird "ÜBERLAST!"
          angezeigt und die Anzeige wechselt auf rot
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