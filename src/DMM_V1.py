# -*- coding: utf-8 -*-
import sys
import os
import time
import math
import numpy as np
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QLabel,
                             QVBoxLayout, QHBoxLayout, QComboBox, QFrame)
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QLinearGradient, QBrush, QFontMetrics
from PyQt5.QtCore import Qt, QRectF, QPointF, QTimer
import pyqtgraph as pg
import pandas as pd

class LogoWidget(QWidget):
    """Widget zum Zeichnen des OurDAQ-Logos"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(100, 60)
    
    def paintEvent(self, event):
        """Zeichnet das Logo programmatisch"""
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2
        
        # Logo-Hintergrund mit Farbverlauf
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0, QColor(0, 51, 102, 200))
        gradient.setColorAt(1, QColor(0, 102, 204, 200))
        
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(gradient))
        qp.drawRoundedRect(0, 0, width, height, 10, 10)
        
        # Wellenform im Logo
        path = QPainterPath()
        path.moveTo(width*0.1, center_y)
        
        # Sinuswelle zeichnen
        for i in range(100):
            x = width * (0.1 + i * 0.8 / 99)
            y = center_y + height * 0.2 * np.sin(i * np.pi / 15)
            path.lineTo(x, y)
        
        qp.setPen(QPen(QColor(255, 255, 255, 220), 3))
        qp.drawPath(path)
        
        # Logo-Text
        qp.setFont(QFont("Arial", int(height/3), QFont.Bold))
        qp.setPen(QPen(QColor(255, 255, 255), 1))
        qp.drawText(QRectF(0, 0, width, height), Qt.AlignCenter, "OurDAQ")

class DataGenerator:
    def __init__(self):
        self.zeit = 0
        self.base_spannung = 5.0
        self.base_strom = 0.5
        self.frequency = 50  # 50 Hz für AC

    def generiere_messdaten(self, mode, ac_dc):
        self.zeit += 1
        if ac_dc == "DC":
            # DC: Konstante Werte mit Rauschen
            spannung = self.base_spannung + 0.5 * np.sin(self.zeit / 10) + np.random.normal(0, 0.1)
            strom = self.base_strom + 0.1 * np.sin(self.zeit / 8 + 1) + np.random.normal(0, 0.05)
            spannung = max(0, min(10, spannung))
            strom = max(0, min(1.0, strom))
        else:
            # AC: Sinusförmige Werte, RMS berechnet
            phase = 2 * np.pi * self.frequency * (self.zeit / 1000)  # Zeit in Sekunden
            spannung_peak = self.base_spannung * np.sqrt(2)  # Spitzenwert für RMS = base_spannung
            strom_peak = self.base_strom * np.sqrt(2)
            spannung = spannung_peak * np.sin(phase) + np.random.normal(0, 0.1)
            strom = strom_peak * np.sin(phase + np.pi/4) + np.random.normal(0, 0.05)
            # RMS-Werte für Anzeige
            spannung = max(0, min(10, self.base_spannung + np.random.normal(0, 0.1)))
            strom = max(0, min(1.0, self.base_strom + np.random.normal(0, 0.05)))
        
        return {'zeit': self.zeit, 'spannung': spannung, 'strom': strom}

class DigitalMeterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.max_value = 10.0
        self.mode = "DC Spannung"
        self.unit = "V"
        self.ac_dc = "DC"
        self.color = QColor(0, 120, 255)  # Blau für Spannung
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #f0f0f0;")  # Heller Hintergrund

    def setMeasurement(self, value, max_value, mode, unit, ac_dc, color):
        self.value = value
        self.max_value = max_value
        self.mode = mode  # Direkt den vollständigen Modus-Text übernehmen (z.B. "AC Spannung")
        self.unit = unit
        self.ac_dc = ac_dc
        self.color = color
        self.update()

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Hintergrund (hell, passend zum Fenster)
        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0, QColor(240, 240, 240))
        gradient.setColorAt(1, QColor(230, 230, 230))
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(gradient))
        qp.drawRect(0, 0, width, height)

        # Titel
        qp.setFont(QFont("Arial", 18, QFont.Bold))
        qp.setPen(QColor(50, 50, 50))
        qp.drawText(QRectF(0, 10, width, 35), Qt.AlignCenter, "Digitales Multimeter")

        # Display-Bereich
        display_margin = width * 0.05
        display_rect = QRectF(display_margin, height * 0.15, 
                              width - 2 * display_margin, height * 0.55)
        shadow_rect = QRectF(display_margin + 3, height * 0.15 + 3, 
                             width - 2 * display_margin, height * 0.55)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(0, 0, 0, 60))  # Leichter Schatten
        qp.drawRoundedRect(shadow_rect, 12, 12)
        qp.setBrush(QColor(224, 224, 224))  # Weißerer Display-Hintergrund
        qp.setPen(QPen(QColor(150, 150, 150), 2))
        qp.drawRoundedRect(display_rect, 12, 12)

        # Modus-Anzeige (vergrößert, Schriftgröße 10pt)
        mode_rect = QRectF(display_rect.x() + 10, display_rect.y() + 10, 
                           display_rect.width() * 0.35, 35)  # Breiter und höher
        mode_color = self.color
        qp.setPen(QPen(mode_color, 1))
        qp.setBrush(QColor(255, 255, 255))  # Weißer Hintergrund
        qp.drawRoundedRect(mode_rect, 5, 5)
        qp.setFont(QFont("Arial", 10, QFont.Bold))  # Schriftgröße von 9pt auf 10pt
        qp.setPen(mode_color)
        qp.drawText(mode_rect, Qt.AlignCenter, self.mode)

        # Bereichsanzeige
        range_rect = QRectF(display_rect.right() - display_rect.width() * 0.35 - 10, 
                            display_rect.y() + 10, display_rect.width() * 0.35, 35)
        qp.setPen(QPen(QColor(50, 50, 50), 1))
        qp.setBrush(QColor(255, 255, 255))
        qp.drawRoundedRect(range_rect, 5, 5)
        qp.setFont(QFont("Arial", 10))
        qp.setPen(QColor(50, 50, 50))
        range_text = f"0-{self.max_value} {self.unit} {'RMS' if self.ac_dc == 'AC' else ''}"
        qp.drawText(range_rect, Qt.AlignCenter, range_text)

        # Digitale Wertanzeige
        value_str = f"{self.value:.2f}"
        symbol = "~" if self.ac_dc == "AC" else "⎓"
        qp.setFont(QFont("Arial", 36, QFont.Bold))
        qp.setPen(self.color)
        metrics = QFontMetrics(qp.font())
        value_width = metrics.width(value_str)
        value_height = metrics.height()
        symbol_width = metrics.width(symbol)
        qp.setFont(QFont("Arial", 16, QFont.Bold))
        unit_width = metrics.width(self.unit)
        unit_height = metrics.height()
        total_width = value_width + symbol_width + unit_width + 20
        total_height = max(value_height, unit_height)
        x_offset = display_rect.x() + (display_rect.width() - total_width) / 2
        y_offset = display_rect.y() + (display_rect.height() - total_height) / 2 + total_height / 2
        qp.setFont(QFont("Arial", 36, QFont.Bold))
        qp.drawText(QRectF(x_offset, y_offset - value_height / 2, value_width, value_height), 
                    Qt.AlignLeft | Qt.AlignVCenter, value_str)
        qp.drawText(QRectF(x_offset + value_width + 5, y_offset - value_height / 2, symbol_width, value_height), 
                    Qt.AlignLeft | Qt.AlignVCenter, symbol)
        qp.setFont(QFont("Arial", 16, QFont.Bold))
        qp.drawText(QRectF(x_offset + value_width + symbol_width + 15, y_offset - unit_height / 2, unit_width, unit_height), 
                    Qt.AlignLeft | Qt.AlignVCenter, self.unit)

        # Balkenanzeige
        bar_y = height * 0.75
        bar_rect = QRectF(display_margin, bar_y, width - 2 * display_margin, height * 0.15)
        qp.setPen(QPen(QColor(150, 150, 150), 2))
        qp.setBrush(QColor(180, 180, 180))
        qp.drawRoundedRect(bar_rect, 5, 5)
        
        scale_width = bar_rect.width() - 20
        scale_height = bar_rect.height() * 0.7
        scale_x = bar_rect.x() + 10
        scale_y = bar_y + (bar_rect.height() - scale_height) / 2
        normalized_value = min(self.value / self.max_value, 1.0)
        active_width = scale_width * normalized_value
        
        bar_gradient = QLinearGradient(scale_x, 0, scale_x + scale_width, 0)
        if "Spannung" in self.mode:
            bar_gradient.setColorAt(0, QColor(0, 120, 255))
            bar_gradient.setColorAt(1, QColor(70, 50, 255))
        else:
            bar_gradient.setColorAt(0, QColor(0, 200, 0))
            bar_gradient.setColorAt(1, QColor(100, 200, 0))
        
        qp.setPen(Qt.NoPen)
        qp.setBrush(bar_gradient)
        qp.drawRoundedRect(QRectF(scale_x, scale_y, active_width, scale_height), 3, 3)
        
        # Skalierungsmarkierungen
        qp.setPen(QPen(QColor(0, 0, 0), 1))
        for i in range(11):
            x = scale_x + (i / 10) * scale_width
            mark_height = scale_height / 3 if i % 5 == 0 else scale_height / 5
            qp.drawLine(QPointF(x, scale_y + scale_height - mark_height), 
                        QPointF(x, scale_y + scale_height))
            if i % 5 == 0:
                label = f"{(i / 10) * self.max_value:.1f}"
                qp.setFont(QFont("Arial", 8))
                qp.setPen(QColor(0, 0, 0))
                qp.drawText(QRectF(x - 15, scale_y + scale_height + 2, 30, 12), 
                            Qt.AlignCenter, label)

        # Überlast-Warnung
        if self.value > self.max_value:
            warning_rect = QRectF(0, bar_rect.bottom() + 10, width, 20)
            flash_opacity = 128 + 127 * math.sin(time.time() * 5)
            qp.setPen(QPen(Qt.red, 2))
            qp.setFont(QFont("Arial", 12, QFont.Bold))
            qp.drawText(warning_rect, Qt.AlignCenter, "⚠️ ÜBERLAST ⚠️")
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 0, 0, int(flash_opacity)))
            qp.drawRoundedRect(warning_rect.adjusted(-5, -2, 5, 2), 5, 5)

class MultimeterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OurDAQ Multimeter")
        self.setMinimumSize(800, 600)
        
        # Bereiche für AC und DC
        self.spannungsbereiche_dc = {'0-10V': 10, '0-50V': 50, '0-100V': 100, '0-500V': 500}
        self.spannungsbereiche_ac = {'0-10V RMS': 10, '0-50V RMS': 50, '0-100V RMS': 100, '0-500V RMS': 500}
        self.strombereiche_dc = {'0-1mA': 1, '0-10mA': 10, '0-100mA': 100, '0-500mA': 500}
        self.strombereiche_ac = {'0-1mA RMS': 1, '0-10mA RMS': 10, '0-100mA RMS': 100, '0-500mA RMS': 500}
        self.aktiver_modus = 'DC Spannung'
        self.aktueller_spannungsbereich = '0-10V'
        self.aktueller_strombereich = '0-1mA'
        self.ac_dc = 'DC'
        self.generator = DataGenerator()
        
        self.zeit = []
        self.spannungswerte = []
        self.stromwerte = []
        self.graph_visible = False
        self.graph_paused = False
        self.max_graph_points = 60  # 60-second window
        
        self.setup_ui()
        self.setup_timer()
        
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 10, 20, 20)
        main_layout.setSpacing(15)
        
        # Header mit Logo und Titel
        header_layout = QHBoxLayout()
        title_label = QLabel("Multimeter")
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setStyleSheet("color: #003366;")
        header_layout.addWidget(title_label, 7)
        
        logo = LogoWidget()
        logo.setMaximumSize(160, 80)
        header_layout.addWidget(logo, 3)
        main_layout.addLayout(header_layout)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #cccccc;")
        main_layout.addWidget(line)
        
        # Hauptbereich: Meter und Graph
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Meter-Bereich
        meter_layout = QVBoxLayout()
        self.meter = DigitalMeterWidget(self)
        self.meter.generator = self.generator
        meter_layout.addWidget(self.meter, alignment=Qt.AlignCenter)
        
        # Export-Feedback
        self.export_label = QLabel("")
        self.export_label.setFont(QFont("Arial", 10))
        self.export_label.setAlignment(Qt.AlignCenter)
        self.export_label.setStyleSheet("color: #333333;")
        meter_layout.addWidget(self.export_label)
        content_layout.addLayout(meter_layout, 1)
        
        # Graph
        self.graph_widget = pg.PlotWidget()
        self.graph_widget.setBackground('#ffffff')
        self.graph_widget.setTitle("Live-Graph", color='#333333', size='12pt')
        self.graph_widget.setLabel('left', 'Wert', units='V')
        self.graph_widget.setLabel('bottom', 'Zeit', units='s')
        self.graph_widget.showGrid(x=True, y=True)
        self.graph_widget.setVisible(False)
        self.plot_data = self.graph_widget.plot(pen=pg.mkPen(color='b', width=2))
        content_layout.addWidget(self.graph_widget, 1)
        
        main_layout.addLayout(content_layout)
        
        # Status-Label
        self.status_label = QLabel(f"Modus: {self.aktiver_modus}, Bereich: {self.aktueller_spannungsbereich}")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #003366; background-color: #f0f0f0; padding: 5px; border-radius: 3px;")
        main_layout.addWidget(self.status_label)
        
        # Steuerungsbereich
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        
        # AC/DC-Auswahl
        self.acdc_combo = QComboBox()
        self.acdc_combo.addItems(['DC', 'AC'])
        self.acdc_combo.setMinimumWidth(100)
        self.acdc_combo.setStyleSheet("""
            QComboBox {
                padding: 5px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: #ffffff;
                font: 12px Arial;
            }
            QComboBox:hover {
                border: 1px solid #999999;
            }
        """)
        self.acdc_combo.currentTextChanged.connect(self.acdc_aendern)
        controls_layout.addWidget(self.acdc_combo)
        
        # Modus-Button
        self.modus_button = QPushButton("Modus ändern")
        self.modus_button.setMinimumWidth(150)
        self.modus_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0055a4, stop:1 #003366);
                color: white;
                border-radius: 5px;
                padding: 8px;
                font: bold 12px Arial;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0066cc, stop:1 #004080);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #004080, stop:1 #002244);
            }
        """)
        self.modus_button.clicked.connect(self.modus_wechseln)
        controls_layout.addWidget(self.modus_button)
        
        # Modus-Anzeige
        self.modus_label = QLabel(self.aktiver_modus)
        self.modus_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.modus_label.setStyleSheet("color: #003366; padding: 5px;")
        controls_layout.addWidget(self.modus_label)
        
        # Bereichsauswahl
        self.bereich_combo = QComboBox()
        self.bereich_combo.addItems(self.spannungsbereiche_dc.keys())
        self.bereich_combo.setMinimumWidth(150)
        self.bereich_combo.setStyleSheet("""
            QComboBox {
                padding: 5px;
                border: 1px solid #cccccc;
                border-radius: 3px;
                background-color: #ffffff;
                font: 12px Arial;
            }
            QComboBox:hover {
                border: 1px solid #999999;
            }
        """)
        self.bereich_combo.currentTextChanged.connect(self.bereich_aendern)
        controls_layout.addWidget(self.bereich_combo)
        
        # Graph Toggle
        self.graph_button = QPushButton("Graph anzeigen")
        self.graph_button.setMinimumWidth(150)
        self.graph_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #66bb6a, stop:1 #4CAF50);
                color: white;
                border-radius: 5px;
                padding: 8px;
                font: bold 12px Arial;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #81c784, stop:1 #45a049);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #45a049, stop:1 #388e3c);
            }
        """)
        self.graph_button.clicked.connect(self.toggle_graph)
        controls_layout.addWidget(self.graph_button)
        
        # Export Button
        self.export_button = QPushButton("CSV exportieren")
        self.export_button.setMinimumWidth(150)
        self.export_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef5350, stop:1 #f44336);
                color: white;
                border-radius: 5px;
                padding: 8px;
                font: bold 12px Arial;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef5350, stop:1 #d32f2f);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #d32f2f, stop:1 #b71c1c);
            }
        """)
        self.export_button.clicked.connect(self.exportieren)
        controls_layout.addWidget(self.export_button)
        
        # Reset Button
        self.reset_button = QPushButton("Daten zurücksetzen")
        self.reset_button.setMinimumWidth(150)
        self.reset_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffa726, stop:1 #fb8c00);
                color: white;
                border-radius: 5px;
                padding: 8px;
                font: bold 12px Arial;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffb300, stop:1 #f57c00);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f57c00, stop:1 #ef6c00);
            }
        """)
        self.reset_button.clicked.connect(self.reset_data)
        controls_layout.addWidget(self.reset_button)
        
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)
        
    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)  # Update every 1000ms
    
    def acdc_aendern(self, text):
        self.ac_dc = text
        # Aktualisiere den aktiven Modus basierend auf AC/DC
        if "Spannung" in self.aktiver_modus:
            self.aktiver_modus = f"{self.ac_dc} Spannung"
        else:
            self.aktiver_modus = f"{self.ac_dc} Strom"
        self.update_modus_and_bereich()
        self.update_status_label()
        self.update_graph_label()
    
    def modus_wechseln(self):
        # Wechsel nur zwischen Spannung und Strom, behalte AC/DC bei
        if "Spannung" in self.aktiver_modus:
            self.aktiver_modus = f"{self.ac_dc} Strom"
        else:
            self.aktiver_modus = f"{self.ac_dc} Spannung"
        self.update_modus_and_bereich()
        self.update_status_label()
        self.update_graph_label()
    
    def update_modus_and_bereich(self):
        self.modus_label.setText(self.aktiver_modus)
        self.bereich_combo.clear()
        if "Spannung" in self.aktiver_modus:
            bereiche = self.spannungsbereiche_ac if self.ac_dc == "AC" else self.spannungsbereiche_dc
            self.bereich_combo.addItems(bereiche.keys())
            # Setze den aktuellen Bereich, falls verfügbar
            if self.aktueller_spannungsbereich in bereiche:
                self.bereich_combo.setCurrentText(self.aktueller_spannungsbereich)
            else:
                self.aktueller_spannungsbereich = list(bereiche.keys())[0]
                self.bereich_combo.setCurrentText(self.aktueller_spannungsbereich)
        else:
            bereiche = self.strombereiche_ac if self.ac_dc == "AC" else self.strombereiche_dc
            self.bereich_combo.addItems(bereiche.keys())
            if self.aktueller_strombereich in bereiche:
                self.bereich_combo.setCurrentText(self.aktueller_strombereich)
            else:
                self.aktueller_strombereich = list(bereiche.keys())[0]
                self.bereich_combo.setCurrentText(self.aktueller_strombereich)
    
    def bereich_aendern(self, text):
        if "Spannung" in self.aktiver_modus:
            self.aktueller_spannungsbereich = text
        else:
            self.aktueller_strombereich = text
        self.update_status_label()
    
    def toggle_graph(self):
        if not self.graph_visible:
            self.graph_visible = True
            self.graph_paused = False
            self.graph_button.setText("Graph pausieren")
            self.graph_widget.setVisible(True)
        else:
            self.graph_paused = not self.graph_paused
            self.graph_button.setText("Graph fortsetzen" if self.graph_paused else "Graph pausieren")
    
    def update_status_label(self):
        bereich = self.aktueller_spannungsbereich if "Spannung" in self.aktiver_modus else self.aktueller_strombereich
        self.status_label.setText(f"Modus: {self.aktiver_modus}, Bereich: {bereich}")
    
    def update_graph_label(self):
        unit = 'V' if "Spannung" in self.aktiver_modus else 'mA'
        color = '#0000FF' if "Spannung" in self.aktiver_modus else '#008000'
        self.graph_widget.setLabel('left', f"Wert ({self.ac_dc})", units=unit)
        self.plot_data.setPen(pg.mkPen(color=color, width=2))
    
    def exportieren(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = r"C:\Users\willm\Documents\Projekt_Raspi"
        os.makedirs(export_dir, exist_ok=True)
        filename = os.path.join(export_dir, f"messwerte_{timestamp}.csv")
        
        try:
            max_len = max(len(self.zeit), len(self.spannungswerte), len(self.stromwerte))
            zeit = self.zeit + [None] * (max_len - len(self.zeit))
            spannung = self.spannungswerte + [None] * (max_len - len(self.spannungswerte))
            strom = self.stromwerte + [None] * (max_len - len(self.stromwerte))
            
            data = []
            for i in range(max_len):
                data.append({
                    'Zeit (s)': zeit[i] if i < len(self.zeit) else None,
                    'Spannung (V)': spannung[i] if i < len(self.spannungswerte) else None,
                    'Strom (mA)': strom[i] if i < len(self.stromwerte) else None
                })
            
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False, sep=';', decimal=',')
            self.export_label.setText(f"Export OK: {os.path.basename(filename)}")
            self.export_label.setStyleSheet("color: #4CAF50;")
            print(f"✅ CSV gespeichert: {os.path.abspath(filename)}")
        except Exception as e:
            self.export_label.setText("Export FEHLER")
            self.export_label.setStyleSheet("color: #f44336;")
            print(f"❌ Export-Fehler: {str(e)}")
        QTimer.singleShot(3000, lambda: self.export_label.setText(""))
    
    def reset_data(self):
        self.zeit = []
        self.spannungswerte = []
        self.stromwerte = []
        self.plot_data.setData([], [])
        self.export_label.setText("Daten zurückgesetzt")
        self.export_label.setStyleSheet("color: #fb8c00;")
        QTimer.singleShot(3000, lambda: self.export_label.setText(""))
    
    def update(self):
        daten = self.generator.generiere_messdaten(self.aktiver_modus, self.ac_dc)
        self.zeit.append(daten['zeit'])
        if "Spannung" in self.aktiver_modus:
            wert = daten['spannung']
            max_wert = (self.spannungsbereiche_ac if self.ac_dc == "AC" else self.spannungsbereiche_dc)[self.aktueller_spannungsbereich]
            self.spannungswerte.append(wert)
            self.meter.setMeasurement(wert, max_wert, self.aktiver_modus, "V", self.ac_dc, QColor(0, 120, 255))
        else:
            wert = daten['strom'] * 1000
            max_wert = (self.strombereiche_ac if self.ac_dc == "AC" else self.strombereiche_dc)[self.aktueller_strombereich]
            self.stromwerte.append(wert)
            self.meter.setMeasurement(wert, max_wert, self.aktiver_modus, "mA", self.ac_dc, QColor(0, 200, 0))
        
        if len(self.zeit) > self.max_graph_points:
            self.zeit = self.zeit[-self.max_graph_points:]
            self.spannungswerte = self.spannungswerte[-self.max_graph_points:]
            self.stromwerte = self.stromwerte[-self.max_graph_points:]
        
        if self.graph_visible and not self.graph_paused:
            min_len = min(len(self.zeit), len(self.spannungswerte if "Spannung" in self.aktiver_modus else self.stromwerte))
            zeit_werte = np.array(self.zeit[-min_len:])
            werte = np.array((self.spannungswerte if "Spannung" in self.aktiver_modus else self.stromwerte)[-min_len:])
            self.plot_data.setData(zeit_werte, werte)
            self.graph_widget.setXRange(max(0, daten['zeit'] - self.max_graph_points), daten['zeit'])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultimeterApp()
    window.show()
    sys.exit(app.exec_())