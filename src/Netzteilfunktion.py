# -*- coding: utf-8 -*-

"""
Netzteilfunktion für das OurDAQ-System
Simuliert ein einstellbares Netzteil mit variabler Spannung und Strombegrenzung
Mit Sicherheitsüberprüfungen und modernem Design
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
                           QGroupBox, QFrame, QDoubleSpinBox, QCheckBox, 
                           QSpacerItem, QSizePolicy, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor

class PowerSupplyWidget(QWidget):
    """Widget zur Anzeige der aktuellen Spannung und des Stroms"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMinimumWidth(400)
        
        self.voltage = 0.0
        self.current = 0.0
        self.overcurrent = False
        
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, Qt.black)
        self.setPalette(palette)
        
        self.normal_color = QColor(0, 210, 210)  # Cyan für normale Anzeige
        self.overcurrent_color = QColor(255, 50, 50)  # Rot für Überstrom
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Spannungsanzeige
        self.voltage_label = QLabel("0.00 V")
        self.voltage_label.setFont(QFont("Arial", 32, QFont.Bold))
        self.voltage_label.setStyleSheet("color: #00d2d2;")
        self.voltage_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.voltage_label)
        
        # Stromanzeige
        self.current_label = QLabel("0.00 A")
        self.current_label.setFont(QFont("Arial", 32, QFont.Bold))
        self.current_label.setStyleSheet("color: #00d2d2;")
        self.current_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.current_label)
    
    def update_values(self, voltage, current, overcurrent=False):
        self.voltage = voltage
        self.current = current
        self.overcurrent = overcurrent
        
        color = self.overcurrent_color if overcurrent else self.normal_color
        self.voltage_label.setStyleSheet(f"color: {color.name()};")
        self.current_label.setStyleSheet(f"color: {color.name()};")
        
        if overcurrent:
            self.voltage_label.setText("OVER!")
            self.current_label.setText("LIMIT!")
        else:
            self.voltage_label.setText(f"{voltage:.2f} V")
            self.current_label.setText(f"{current:.2f} A")

class NetzteilFunktion(QMainWindow):
    """Hauptfenster für die Netzteilfunktion"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("OurDAQ - Netzteilfunktion")
        self.setGeometry(100, 100, 600, 500)
        
        self.is_power_on = False  # Zustand des Netzteils (ein/aus)
        self.set_voltage = 0.0  # Gewünschte Spannung
        self.set_current_limit = 1.0  # Strombegrenzung
        self.output_current = 0.0  # Simulierter Ausgangsstrom
        
        self.setup_ui()
    
    def setup_ui(self):
        # Haupt-Widget und Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Titel
        title_label = QLabel("Netzteilfunktion")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Anzeige für Spannung und Strom
        self.display = PowerSupplyWidget()
        main_layout.addWidget(self.display)
        
        # Einstellungen Gruppe
        settings_group = QGroupBox("Einstellungen")
        settings_group.setFont(QFont("Arial", 11, QFont.Bold))
        settings_layout = QGridLayout(settings_group)
        settings_layout.setSpacing(15)
        
        # Spannungseinstellung
        voltage_label = QLabel("Ausgangsspannung (V):")
        voltage_label.setFont(QFont("Arial", 10))
        settings_layout.addWidget(voltage_label, 0, 0)
        
        self.voltage_spinbox = QDoubleSpinBox()
        self.voltage_spinbox.setRange(0.0, 10.0)
        self.voltage_spinbox.setValue(0.0)
        self.voltage_spinbox.setSingleStep(0.1)
        self.voltage_spinbox.setDecimals(2)
        self.voltage_spinbox.setFixedWidth(100)
        self.voltage_spinbox.valueChanged.connect(self.update_output)
        settings_layout.addWidget(self.voltage_spinbox, 0, 1)
        
        # Strombegrenzung
        current_label = QLabel("Strombegrenzung (A):")
        current_label.setFont(QFont("Arial", 10))
        settings_layout.addWidget(current_label, 1, 0)
        
        self.current_spinbox = QDoubleSpinBox()
        self.current_spinbox.setRange(0.0, 3.0)
        self.current_spinbox.setValue(1.0)
        self.current_spinbox.setSingleStep(0.01)
        self.current_spinbox.setDecimals(2)
        self.current_spinbox.setFixedWidth(100)
        self.current_spinbox.valueChanged.connect(self.update_output)
        settings_layout.addWidget(self.current_spinbox, 1, 1)
        
        main_layout.addWidget(settings_group)
        
        # Steuerung Gruppe
        control_group = QGroupBox("Steuerung")
        control_group.setFont(QFont("Arial", 11, QFont.Bold))
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(15)
        
        # Ein/Aus-Schalter
        self.power_switch = QPushButton("Netzteil Einschalten")
        self.power_switch.setCheckable(True)
        self.power_switch.setChecked(False)
        self.power_switch.setFixedSize(200, 40)
        self.power_switch.setStyleSheet("""
            QPushButton {
                background-color: darkgreen;
                color: white;
                border-radius: 5px;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:checked {
                background-color: darkred;
                color: white;
            }
            QPushButton:hover {
                background-color: #00b300;
            }
            QPushButton:checked:hover {
                background-color: #cc0000;
            }
        """)
        self.power_switch.clicked.connect(self.toggle_power)
        control_layout.addWidget(self.power_switch)
        
        # Hilfe-Button
        help_button = QPushButton("Hilfe")
        help_button.setFixedSize(100, 40)
        help_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        help_button.clicked.connect(self.show_help)
        control_layout.addWidget(help_button)
        
        control_layout.addStretch()
        
        main_layout.addWidget(control_group)
        
        # Footer
        footer_label = QLabel("OurDAQ Netzteilfunktion - Technische Hochschule Nürnberg")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setFont(QFont("Arial", 9))
        main_layout.addWidget(footer_label)
        
        main_layout.addStretch()
    
    def toggle_power(self, checked):
        """Schaltet das Netzteil ein oder aus"""
        self.is_power_on = checked
        self.power_switch.setText("Netzteil Ausschalten" if checked else "Netzteil Einschalten")
        self.update_output()
    
    def update_output(self):
        """Aktualisiert die Anzeige basierend auf den Eingaben"""
        self.set_voltage = self.voltage_spinbox.value()
        self.set_current_limit = self.current_spinbox.value()
        
        if not self.is_power_on:
            # Netzteil ist ausgeschaltet
            self.display.update_values(0.0, 0.0)
            return
        
        # Simuliere einen Ausgangsstrom basierend auf der Spannung
        # Für die Simulation: Strom = Spannung / (konstanter Widerstand von 10 Ohm)
        # In einer echten Anwendung würde dies von der Last abhängen
        simulated_resistance = 10.0  # Simulierter Lastwiderstand in Ohm
        self.output_current = self.set_voltage / simulated_resistance if simulated_resistance != 0 else 0.0
        
        # Überstromprüfung
        overcurrent = self.output_current > self.set_current_limit
        
        if overcurrent:
            # Überstrom erkannt: Spannung auf 0 setzen und Warnung anzeigen
            self.display.update_values(0.0, 0.0, overcurrent=True)
            QMessageBox.warning(self, "Überstrom", "Strombegrenzung überschritten! Ausgang wurde deaktiviert.")
            self.power_switch.setChecked(False)
            self.is_power_on = False
            self.power_switch.setText("Netzteil Einschalten")
        else:
            self.display.update_values(self.set_voltage, self.output_current)
    
    def show_help(self):
        """Zeigt Hilfeinformationen an"""
        help_text = """
        OurDAQ Netzteilfunktion - Hilfe
        
        Dieses Modul simuliert ein einstellbares Netzteil mit den folgenden Funktionen:
        
        1. **Ausgangsspannung einstellen**:
           - Wählen Sie eine Spannung zwischen 0 und 30 V.
           - Verwenden Sie das Eingabefeld "Ausgangsspannung".
        
        2. **Strombegrenzung einstellen**:
           - Stellen Sie eine Strombegrenzung zwischen 0 und 3 A ein.
           - Verwenden Sie das Eingabefeld "Strombegrenzung".
        
        3. **Netzteil ein-/ausschalten**:
           - Klicken Sie auf "Netzteil Einschalten", um den Ausgang zu aktivieren.
           - Klicken Sie auf "Netzteil Ausschalten", um den Ausgang zu deaktivieren.
        
        4. **Sicherheitsfunktionen**:
           - Wenn der Strom die eingestellte Strombegrenzung überschreitet, wird der Ausgang deaktiviert und eine Warnung angezeigt.
        
        Hinweis:
        - Dies ist eine Simulation. Der simulierte Strom wird basierend auf einem festen Lastwiderstand (10 Ohm) berechnet.
        - In einer echten Anwendung würde der Strom von der tatsächlichen Last abhängen.
        
        Bei Fragen wenden Sie sich bitte an die Projektbetreuer.
        """
        QMessageBox.information(self, "Netzteilfunktion - Hilfe", help_text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = NetzteilFunktion()
    window.show()
    sys.exit(app.exec_())