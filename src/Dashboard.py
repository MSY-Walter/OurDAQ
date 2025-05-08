# -*- coding: utf-8 -*-

"""
Dashboard für das Datenerfassungssystem auf Raspberry Pi
Verbindet die verschiedenen Module des OurDAQ-Systems in einer zentralen Oberfläche
Mit Zugriff auf Digitales Multimeter und Funktionsgenerator
"""

import sys
import os
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                           QGroupBox, QFrame, QSpacerItem, QSizePolicy,
                           QMessageBox)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QFont, QPalette, QColor

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
# Verzeichnisse für Ressourcen
RESOURCES_DIR = os.path.join(APP_ROOT, "resources")
IMAGES_DIR = os.path.join(RESOURCES_DIR, "images")
ICONS_DIR = os.path.join(RESOURCES_DIR, "icons")

class ModuleCard(QFrame):
    """Karte für ein Modul mit Icon, Titel und Beschreibung"""
    
    def __init__(self, titel, beschreibung, icon_pfad=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)  # Rahmenform entfernen
        self.setFrameShadow(QFrame.Plain)   # Schatten entfernen
        self.setMinimumSize(280, 150)
        self.setMaximumSize(400, 220)
        
        # Hintergrundfarbe und abgerundete Ecken, aber ohne Rahmen
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        self.setPalette(palette)
        self.setStyleSheet("QFrame { border-radius: 8px; }")  # Rahmen entfernen, abgerundete Ecken beibehalten
        
        # Layout erstellen
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Header mit Icon und Titel
        header_layout = QHBoxLayout()
        
        # Icon hinzufügen, falls vorhanden
        if icon_pfad and os.path.exists(icon_pfad):
            icon_label = QLabel()
            pixmap = QPixmap(icon_pfad)
            # Icongröße auf 64x64 Pixel erhöhen, um vollständige Anzeige zu gewährleisten
            icon_label.setPixmap(pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_label.setFixedSize(48, 48)  # Feste Größe für das Label
            header_layout.addWidget(icon_label)
        
        # Titel hinzufügen
        titel_label = QLabel(titel)
        titel_label.setFont(QFont("Arial", 12, QFont.Bold))
        header_layout.addWidget(titel_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Trennlinie
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Beschreibung
        beschreibung_label = QLabel(beschreibung)
        beschreibung_label.setWordWrap(True)
        beschreibung_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(beschreibung_label)
        
        # Abstand vor dem Button
        layout.addSpacing(10)
        
        # Button zum Öffnen
        self.button = QPushButton("Öffnen")
        self.button.setMinimumHeight(36)
        self.button.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border-radius: 5px;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #0077ee;
            }
            QPushButton:pressed {
                background-color: #0055aa;
            }
        """)
        layout.addWidget(self.button)

class OurDAQDashboard(QMainWindow):
    """Hauptfenster für das OurDAQ Dashboard"""
    
    def __init__(self):
        super().__init__()
        
        # 设置窗口标志，禁用最大化按钮
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        
        # Erstelle Ressourcenverzeichnisse, falls sie nicht existieren
        self.erstelle_ressourcen_verzeichnisse()
        
        # Fenstereigenschaften festlegen
        self.setWindowTitle("OurDAQ Dashboard")
        self.setGeometry(100, 100, 1000, 700)
        
        # 设置最小窗口大小
        self._minimumSize = QSize(1000, 700)
        # 设置建议的窗口大小（应大于最小大小）
        self.resize(1000, 700)
        
        # Haupt-Widget und Layout
        zentral_widget = QWidget()
        self.setCentralWidget(zentral_widget)
        
        haupt_layout = QVBoxLayout(zentral_widget)
        haupt_layout.setSpacing(20)
        haupt_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        self.erstelle_header(haupt_layout)
        
        # Module-Bereich
        self.erstelle_module_bereich(haupt_layout)
        
        # Footer
        self.erstelle_footer(haupt_layout)
    
    def resizeEvent(self, event):
        """重写resize事件，强制执行最小大小限制"""
        current_width = event.size().width()
        current_height = event.size().height()
        min_width = self._minimumSize.width()
        min_height = self._minimumSize.height()
        
        # 检查新的大小是否小于最小大小
        if current_width < min_width or current_height < min_height:
            # 如果是，将大小设置为最小大小
            new_width = max(current_width, min_width)
            new_height = max(current_height, min_height)
            self.resize(new_width, new_height)
        else:
            # 否则调用正常的resize事件处理
            super().resizeEvent(event)
    
    def erstelle_ressourcen_verzeichnisse(self):
        """Erstellt die Ressourcenverzeichnisse, falls sie noch nicht existieren"""
        for directory in [RESOURCES_DIR, IMAGES_DIR, ICONS_DIR]:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                    print(f"Verzeichnis erstellt: {directory}")
                except Exception as e:
                    print(f"Fehler beim Erstellen des Verzeichnisses {directory}: {str(e)}")
    
    def erstelle_header(self, haupt_layout):
        """Erstellt den Header-Bereich mit Titel und Beschreibung"""
        header_gruppe = QGroupBox()
        header_gruppe.setStyleSheet("QGroupBox { border: none; }")
        header_layout = QHBoxLayout(header_gruppe)
        header_layout.setContentsMargins(50, 0, 0, 0)
        
        # OurDAQ Logo erstellen und hinzufügen
        logo_label = QLabel()
        # Pfad zum Logo im Ressourcenverzeichnis
        logo_pfad = os.path.join(IMAGES_DIR, "OurDAQ_logo.png")
        
        # Fallback: Wenn das Logo nicht gefunden wird, erstellen wir ein Text-basiertes Logo
        if os.path.exists(logo_pfad):
            pixmap = QPixmap(logo_pfad)
            logo_label.setPixmap(pixmap.scaled(200, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # Text-basiertes Logo als Fallback
            logo_label = QLabel("OurDAQ")
            logo_label.setFont(QFont("Arial", 20, QFont.Bold))
            logo_label.setStyleSheet("QLabel { color: #0066cc; background-color: #f0f0f0; padding: 10px; border-radius: 10px; }")
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setFixedSize(200, 80)
            
            # Hinweis ausgeben, dass das Logo nicht gefunden wurde
            print(f"Logo nicht gefunden: {logo_pfad}")
            print(f"Verwende Text-Logo als Fallback.")
        
        header_layout.addWidget(logo_label)

        spacer = QSpacerItem(100, 20, QSizePolicy.Fixed, QSizePolicy.Minimum)
        header_layout.addItem(spacer)   
        
        # Text-Bereich für Titel und Beschreibung
        text_layout = QVBoxLayout()
        
        # Titel
        titel_label = QLabel("OurDAQ Datenerfassungssystem")
        titel_label.setFont(QFont("Arial", 18, QFont.Bold))
        titel_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        text_layout.addWidget(titel_label)
        
        # Beschreibung
        beschreibung_label = QLabel(
            "Ein prototypisches Messdatenerfassungssystem basierend auf Raspberry Pi und Digilent MCC DAQ HATs."
        )
        beschreibung_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        beschreibung_label.setWordWrap(True)
        text_layout.addWidget(beschreibung_label)
        
        header_layout.addLayout(text_layout)
        header_layout.addStretch()
        
        haupt_layout.addWidget(header_gruppe)
    
    def erstelle_module_bereich(self, haupt_layout):
        """Erstellt den Bereich mit den verfügbaren Modulen"""
        module_gruppe = QGroupBox("Verfügbare Module")
        module_gruppe.setFont(QFont("Arial", 11, QFont.Bold))
        module_layout = QGridLayout(module_gruppe)
        module_layout.setSpacing(20)  # Erhöhter Abstand zwischen Komponenten
        module_layout.setContentsMargins(20, 30, 20, 20)  # Erhöhte Ränder
        
        # Pfade zu den Modul-Icons
        dmm_icon = os.path.join(ICONS_DIR, "dmm_icon.png")
        fgen_icon = os.path.join(ICONS_DIR, "fgen_icon.png")
        oscope_icon = os.path.join(ICONS_DIR, "oscope_icon.png")
        kennlinie_icon = os.path.join(ICONS_DIR, "kennlinie_icon.png")
        
        # Digitales Multimeter
        dmm_card = ModuleCard(
            "Digitales Multimeter",
            "Messen Sie Spannung und Strom mit diesem digitalen Multimeter. "
            "Mit Überlastungswarnung, Diagrammanzeige und CSV-Datenspeicherung.",
            dmm_icon if os.path.exists(dmm_icon) else None
        )
        dmm_card.button.clicked.connect(self.starte_dmm)
        module_layout.addWidget(dmm_card, 0, 0)
        
        # Funktionsgenerator
        fgen_card = ModuleCard(
            "Funktionsgenerator",
            "Erzeugen Sie verschiedene Signalformen (Sinus, Rechteck, Dreieck) "
            "mit einstellbarer Frequenz, Amplitude und Offset.",
            fgen_icon if os.path.exists(fgen_icon) else None
        )
        fgen_card.button.clicked.connect(self.starte_funktionsgenerator)
        module_layout.addWidget(fgen_card, 0, 1)
        
        # Oszilloskop
        oscope_card = ModuleCard(
            "Oszilloskop",
            "Visualisieren Sie Signale in Echtzeit. "
            "Mit Trigger-Funktionalität und CSV-Export für beide Kanäle.",
            oscope_icon if os.path.exists(oscope_icon) else None
        )
        oscope_card.button.clicked.connect(self.starte_oszilloskop)
        module_layout.addWidget(oscope_card, 1, 0)
        
        # Kennlinienmessung
        kennlinie_card = ModuleCard(
            "Kennlinienmessung",
            "Messen und plotten Sie Kennlinien wie Dioden- oder Filterkennlinien. ",
            kennlinie_icon if os.path.exists(kennlinie_icon) else None
        )
        kennlinie_card.button.setText("Bald verfügbar")
        kennlinie_card.button.setEnabled(False)
        kennlinie_card.button.setStyleSheet("QPushButton { background-color: #999999; color: white; border-radius: 5px; padding: 8px; }")
        module_layout.addWidget(kennlinie_card, 1, 1)
        
        haupt_layout.addWidget(module_gruppe)
    
    def erstelle_footer(self, haupt_layout):
        """Erstellt den Footer-Bereich mit Hinweise und Hilfe-Button"""
        footer_gruppe = QGroupBox()
        footer_gruppe.setStyleSheet("QGroupBox { border: none; }")
        footer_layout = QHBoxLayout(footer_gruppe)
        
        # Hilfe-Button
        hilfe_button = QPushButton("Hilfe")
        hilfe_button.setFixedSize(100, 36)
        hilfe_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        hilfe_button.clicked.connect(self.zeige_hilfe)
        
        # OHM Logo hinzufügen
        ohm_logo_label = QLabel()
        ohm_logo_pfad = os.path.join(IMAGES_DIR, "OHM_logo.png")
        
        if os.path.exists(ohm_logo_pfad):
            pixmap = QPixmap(ohm_logo_pfad)
            ohm_logo_label.setPixmap(pixmap.scaled(200, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # Fallback-Text, falls das Logo nicht gefunden wird
            ohm_logo_label.setText("TH Nürnberg")
            ohm_logo_label.setFont(QFont("Arial", 10, QFont.Bold))
            
            # Hinweis ausgeben, dass das Logo nicht gefunden wurde
            print(f"OHM Logo nicht gefunden: {ohm_logo_pfad}")
            print(f"Verwende Text-Label als Fallback.")
        
        # Hinweis-Label
        hinweis_label = QLabel("OurDAQ Version 2.0 - Technische Hochschule Nürnberg")
        hinweis_label.setAlignment(Qt.AlignCenter)
        
        # Layout aufbauen
        footer_layout.addWidget(hilfe_button)
        footer_layout.addWidget(ohm_logo_label)
        footer_layout.addStretch()
        footer_layout.addWidget(hinweis_label)
        footer_layout.addStretch()
        
        # Exit-Button
        exit_button = QPushButton("Beenden")
        exit_button.setFixedSize(100, 36)
        exit_button.setStyleSheet("""
            QPushButton {
                background-color: #cc4444;
                color: white;
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #ee5555;
            }
        """)
        exit_button.clicked.connect(self.close)
        footer_layout.addWidget(exit_button)
        
        haupt_layout.addWidget(footer_gruppe)
    
    def starte_dmm(self):
        """Startet das Digitale Multimeter"""
        try:
            # Pfad zum DMM.py relativ zum aktuellen Verzeichnis
            dmm_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DMM.py")
            
            if os.path.exists(dmm_pfad):
                # Starte das DMM-Modul als separaten Prozess
                subprocess.Popen([sys.executable, dmm_pfad])
            else:
                QMessageBox.warning(
                    self, "Datei nicht gefunden", 
                    f"Die Datei DMM.py wurde nicht gefunden.\nGesucht in: {dmm_pfad}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Fehler beim Starten", 
                f"Beim Starten des Digitalen Multimeters ist ein Fehler aufgetreten:\n{str(e)}"
            )
    
    def starte_funktionsgenerator(self):
        """Startet den Funktionsgenerator"""
        try:
            # Pfad zum Funktionsgenerator.py relativ zum aktuellen Verzeichnis
            fgen_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Funktionsgenerator.py")
            
            if os.path.exists(fgen_pfad):
                # Starte den Funktionsgenerator als separaten Prozess
                subprocess.Popen([sys.executable, fgen_pfad])
            else:
                QMessageBox.warning(
                    self, "Datei nicht gefunden", 
                    f"Die Datei Funktionsgenerator.py wurde nicht gefunden.\nGesucht in: {fgen_pfad}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Fehler beim Starten", 
                f"Beim Starten des Funktionsgenerators ist ein Fehler aufgetreten:\n{str(e)}"
            )

    def starte_oszilloskop(self):
        """Startet das Oszilloskop"""
        try:
            # Pfad zum Oszilloskop.py relativ zum aktuellen Verzeichnis
            oscope_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Oszilloskop.py")
            
            if os.path.exists(oscope_pfad):
                # Starte das Oszilloskop-Modul als separaten Prozess
                subprocess.Popen([sys.executable, oscope_pfad])
            else:
                QMessageBox.warning(
                    self, "Datei nicht gefunden", 
                    f"Die Datei Oszilloskop.py wurde nicht gefunden.\nGesucht in: {oscope_pfad}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Fehler beim Starten", 
                f"Beim Starten des Oszilloskops ist ein Fehler aufgetreten:\n{str(e)}"
            )

    def zeige_hilfe(self):
        """Zeigt Hilfeinformationen an"""
        hilfe_text = """
        OurDAQ Dashboard - Hilfe
        
        Dieses Dashboard dient als zentraler Zugriffspunkt auf die verschiedenen
        Module des OurDAQ Datenerfassungssystems.
        
        Verfügbare Module:
        
        1. Digitales Multimeter
           - Messen von Spannung und Strom
           - Anzeige von Messwerten in Diagrammen
           - Speichern von Messdaten als CSV
        
        2. Funktionsgenerator
           - Erzeugen von Sinus-, Rechteck- und Dreieckwellen
           - Einstellbare Frequenz, Amplitude und Offset
           - Optimiert für den AD9833 DDS-Chip
        
        Weitere Module (Oszilloskop, Kennlinienmessung) sind derzeit
        in Entwicklung und werden in zukünftigen Versionen verfügbar sein.
        
        Bei Fragen oder Problemen wenden Sie sich bitte an die Projektbetreuer.
        """
        
        QMessageBox.information(self, "OurDAQ Dashboard - Hilfe", hilfe_text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Stil für die Anwendung festlegen
    app.setStyle("Fusion")
    
    # Hauptfenster erstellen und anzeigen
    dashboard = OurDAQDashboard()
    dashboard.show()
    
    sys.exit(app.exec_())