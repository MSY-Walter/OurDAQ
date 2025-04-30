import sys
import os
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, 
                            QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, 
                            QStackedWidget, QFrame)
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QPolygonF
from PyQt5.QtCore import Qt, QSize, QRectF, QPointF, pyqtSignal

# Placeholder imports for external modules (not provided)
try:
    from DMM_V1 import MultimeterApp
except ImportError:
    print("MultimeterApp module not found")
    MultimeterApp = None

try:
    from Oszilloskop_V1 import MyDAQOszilloskop
except ImportError:
    print("OscilloscopeApp module not found")
    OscilloscopeApp = None

try:
    from Funktionsgenerator_V1 import Funktionsgenerator
except ImportError:
    print("MyDAQFunktionsgenerator module not found")
    MyDAQFunktionsgenerator = None
    
try:
    from Diodenkennlinie_V1 import DiodeKennlinieApp
except ImportError:
    print("DiodeKennlinieApp module not found")
    DiodeKennlinieApp = None    
try:
    from Filterkennlinie_V1 import FilterKennlinieApp
except ImportError:
    print("FilterKennlinieApp module not found")
    FilterKennlinieApp = None    

class DeviceButton(QFrame):
    """Spezialisierter Button für Geräteauswahl mit Icon und Text"""
    clicked = pyqtSignal()
    
    def __init__(self, title, color, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = self._get_qt_color(color)
        self.light_color = self._get_qt_color(color, alpha=50)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setMinimumSize(180, 180)
        
        # Layout für Button
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Icon-Bereich 
        self.icon_area = IconWidget(title, self.color)
        self.icon_area.setMinimumHeight(100)
        layout.addWidget(self.icon_area)
        
        # Text-Label
        self.label = QLabel(title)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(self.label)
        
        # Styling
        self.setStyleSheet(f"""
            DeviceButton {{
                background-color: #f8f8f8;
                border: 2px solid {self.color.name()};
                border-radius: 10px;
            }}
            DeviceButton:hover {{
                background-color: {self.light_color.name()};
            }}
        """)
    
    def _get_qt_color(self, color_name, alpha=255):
        """Konvertiert Farbnamen in QColor-Objekte"""
        color_map = {
            'blue': QColor(0, 102, 204, alpha),
            'green': QColor(0, 153, 51, alpha),
            'red': QColor(204, 51, 0, alpha),
            'purple': QColor(153, 51, 153, alpha)
        }
        return color_map.get(color_name, QColor(100, 100, 100, alpha))
    
    def mousePressEvent(self, event):
        """Emit clicked signal on left mouse click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

class IconWidget(QWidget):
    def __init__(self, title, color, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = color

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)

        if self.title == "Multimeter":
            self._draw_multimeter_icon(qp)
        elif self.title == "Funktionsgenerator":
            self._draw_funcgen_icon(qp)
        elif self.title == "Oszilloskop":
            self._draw_oscilloscope_icon(qp)
        elif self.title == "Kennlinie":
            self._draw_kennlinie_icon(qp)
        elif self.title == "Diodenkennlinie":
            self._draw_diode_icon(qp)
        elif self.title == "Filterkennlinie":
            self._draw_filter_icon(qp)
            
    def _draw_multimeter_icon(self, qp):
        """Zeichnet ein Multimeter-Symbol"""
        width = self.width()
        height = self.height()
        
        # Gerätekörper
        qp.setPen(QPen(self.color, 2))
        qp.setBrush(QColor(250, 250, 250))
        qp.drawRect(QRectF(width*0.2, height*0.1, width*0.6, height*0.8))
        
        # Display
        qp.setPen(QPen(Qt.black, 1))
        qp.setBrush(QColor(220, 255, 220))
        qp.drawRect(QRectF(width*0.3, height*0.2, width*0.4, height*0.3))
        
        # Messwert
        qp.setFont(QFont("Arial", 12))
        qp.drawText(QRectF(width*0.3, height*0.2, width*0.4, height*0.3), 
                   Qt.AlignCenter, "8.88")
        
        # Drehschalter
        qp.setPen(QPen(Qt.black, 1))
        qp.setBrush(QColor(220, 220, 220))
        qp.drawEllipse(QPointF(width*0.5, height*0.65), width*0.1, height*0.1)
        
        # Zeiger
        qp.setPen(QPen(Qt.black, 2))
        qp.drawLine(QPointF(width*0.5, height*0.65), QPointF(width*0.57, height*0.6))
    
    def _draw_funcgen_icon(self, qp):
        """Zeichnet ein Funktionsgenerator-Symbol"""
        width = self.width()
        height = self.height()
        
        # Gerätekörper
        qp.setPen(QPen(self.color, 2))
        qp.setBrush(QColor(250, 250, 250))
        qp.drawRect(QRectF(width*0.2, height*0.1, width*0.6, height*0.8))
        
        # Display
        qp.setPen(QPen(Qt.black, 1))
        qp.setBrush(QColor(220, 220, 255))
        qp.drawRect(QRectF(width*0.3, height*0.2, width*0.4, height*0.3))
        
        # Sinuskurve zeichnen
        path = QPainterPath()
        path.moveTo(width*0.3, height*0.35)
        
        # Sinuskurve berechnen
        for i in range(51):
            x = width * (0.3 + i * 0.4 / 50)
            y = height * (0.35 + 0.1 * np.sin(i * np.pi / 8))
            path.lineTo(x, y)
            
        qp.setPen(QPen(QColor(0, 0, 200), 2))
        qp.drawPath(path)
        
        # Drehregler zeichnen
        for i in range(3):
            qp.setPen(QPen(Qt.black, 1))
            qp.setBrush(QColor(220, 220, 220))
            qp.drawEllipse(QPointF(width*(0.3 + i*0.15), height*0.65), width*0.05, height*0.05)
    
    def _draw_oscilloscope_icon(self, qp):
        """Zeichnet ein Oszilloskop-Symbol"""
        width = self.width()
        height = self.height()
        
        # Gerätekörper
        qp.setPen(QPen(self.color, 2))
        qp.setBrush(QColor(250, 250, 250))
        qp.drawRect(QRectF(width*0.2, height*0.1, width*0.6, height*0.8))
        
        # Display
        qp.setPen(QPen(Qt.black, 1))
        qp.setBrush(QColor(200, 255, 200))
        qp.drawRect(QRectF(width*0.3, height*0.2, width*0.4, height*0.5))
        
        # Horizontale und vertikale Hilfslinien
        qp.setPen(QPen(QColor(0, 0, 0, 100), 1, Qt.DashLine))
        qp.drawLine(QPointF(width*0.3, height*0.45), QPointF(width*0.7, height*0.45))
        qp.drawLine(QPointF(width*0.5, height*0.2), QPointF(width*0.5, height*0.7))
        
        # Signal zeichnen
        path = QPainterPath()
        path.moveTo(width*0.3, height*0.45)
        
        # Signal berechnen (gedämpfte Schwingung)
        for i in range(51):
            x = width * (0.3 + i * 0.4 / 50)
            y = height * (0.45 + 0.15 * np.sin(i * np.pi / 4) * np.exp(-i/50))
            path.lineTo(x, y)
            
        qp.setPen(QPen(QColor(0, 180, 0), 2))
        qp.drawPath(path)
    
    def _draw_kennlinie_icon(self, qp):
        """Zeichnet ein Kennlinien-Symbol"""
        width = self.width()
        height = self.height()
        
        # Gerätekörper
        qp.setPen(QPen(self.color, 2))
        qp.setBrush(QColor(250, 250, 250))
        qp.drawRect(QRectF(width*0.2, height*0.1, width*0.6, height*0.8))
        
        # Display
        qp.setPen(QPen(Qt.black, 1))
        qp.setBrush(QColor(255, 240, 240))
        qp.drawRect(QRectF(width*0.3, height*0.2, width*0.4, height*0.5))
        
        # Achsen
        qp.setPen(QPen(Qt.black, 1))
        qp.drawLine(QPointF(width*0.35, height*0.6), QPointF(width*0.65, height*0.6))  # x-Achse
        qp.drawLine(QPointF(width*0.35, height*0.6), QPointF(width*0.35, height*0.3))  # y-Achse
        
        # Diodenkennlinie
        path = QPainterPath()
        path.moveTo(width*0.35, height*0.6)  # Ursprung
        path.lineTo(width*0.5, height*0.6)   # Horizontaler Teil
        
        # Ansteigender Teil (Diodenkennlinie)
        for i in range(31):
            x = width * (0.5 + i * 0.15 / 30)
            y = height * (0.6 - 0.3 * (1 - np.exp(-i/5)) * i/30)
            path.lineTo(x, y)
            
        qp.setPen(QPen(self.color, 2))
        qp.drawPath(path)
    
    def _draw_diode_icon(self, qp):
        """Zeichnet ein Dioden-Symbol mit Kennlinie"""
        width = self.width()
        height = self.height()
        
        # Diodensymbol
        qp.setPen(QPen(self.color, 2))
        # Dreieck
        points = [QPointF(width*0.3, height*0.3), 
                  QPointF(width*0.7, height*0.3),
                  QPointF(width*0.5, height*0.5)]
        polygon = QPolygonF(points)
        qp.setBrush(Qt.white)
        qp.drawPolygon(polygon)
        
        # Linie
        qp.drawLine(QPointF(width*0.5, height*0.5), QPointF(width*0.5, height*0.6))
        qp.drawLine(QPointF(width*0.3, height*0.6), QPointF(width*0.7, height*0.6))
        
        # Kennlinie
        path = QPainterPath()
        path.moveTo(width*0.2, height*0.8)
        
        # Diodenkennlinie: flach bis Schwellspannung, dann ansteigend
        path.lineTo(width*0.5, height*0.8)  # Flacher Teil
        
        # Ansteigender Teil
        for i in range(21):
            x = width * (0.5 + i * 0.3 / 20)
            y = height * (0.8 - 0.3 * i/20)
            path.lineTo(x, y)
            
        qp.drawPath(path)
    
    def _draw_filter_icon(self, qp):
        """Zeichnet ein Filter-Symbol mit Bode-Diagramm"""
        width = self.width()
        height = self.height()
        
        # Schaltungselemente
        qp.setPen(QPen(self.color, 2))
        qp.setBrush(Qt.white)
        
        # Widerstand
        qp.drawRect(QRectF(width*0.25, height*0.3, width*0.2, height*0.1))
        
        # Kondensator (zwei Linien)
        qp.drawLine(QPointF(width*0.55, height*0.25), QPointF(width*0.55, height*0.35))
        qp.drawLine(QPointF(width*0.65, height*0.25), QPointF(width*0.65, height*0.35))
        
        # Verbindungslinien
        qp.drawLine(QPointF(width*0.2, height*0.35), QPointF(width*0.25, height*0.35))
        qp.drawLine(QPointF(width*0.45, height*0.35), QPointF(width*0.55, height*0.35))
        qp.drawLine(QPointF(width*0.65, height*0.35), QPointF(width*0.8, height*0.35))
        
        # Filterkennlinie (Tiefpass)
        path = QPainterPath()
        path.moveTo(width*0.2, height*0.6)
        
        # Zunächst konstant, dann abfallend
        path.lineTo(width*0.4, height*0.6)
        
        # Abknickende Kurve (Tiefpass-Charakteristik)
        for i in range(31):
            x = width * (0.4 + i * 0.4 / 30)
            y = height * (0.6 + 0.2 * (1 - 1/(1 + (i/15)**2)**0.5))
            path.lineTo(x, y)
            
        qp.drawPath(path)

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

class OurDAQApp(QMainWindow):
    """Hauptanwendung für OurDAQ"""
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("OurDAQ - Datenerfassungstool")
        self.setMinimumSize(900, 600)
        
        # Stacked Widget für verschiedene Seiten
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # Verschiedene Seiten erstellen
        self.create_start_screen()
        self.create_device_selection_screen()
        self.create_kennlinie_screen()
        
        # Mit Startbildschirm beginnen
        self.stacked_widget.setCurrentIndex(0)
        
        # Fenster anzeigen
        self.show()
    
    def create_start_screen(self):
        """Erstellt den Startbildschirm"""
        start_screen = QWidget()
        layout = QVBoxLayout(start_screen)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Logo
        logo_widget = LogoWidget()
        logo_widget.setMinimumSize(300, 150)
        layout.addWidget(logo_widget, alignment=Qt.AlignCenter)
        
        # Willkommenstext
        welcome_label = QLabel("Willkommen bei OurDAQ")
        welcome_label.setFont(QFont("Arial", 24, QFont.Bold))
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setStyleSheet("color: #003366;")
        layout.addWidget(welcome_label)
        
        subtitle_label = QLabel("Ihr Tool für professionelle Messdatenerfassung")
        subtitle_label.setFont(QFont("Arial", 16))
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #003366;")
        layout.addWidget(subtitle_label)
        
        # Spacer
        layout.addStretch()
        
        # Start-Button
        start_button = QPushButton("Geräteauswahl öffnen")
        start_button.setMinimumHeight(40)
        start_button.setFont(QFont("Arial", 14))
        start_button.setStyleSheet("""
            QPushButton {
                background-color: #003366;
                color: white;
                border-radius: 5px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #004080;
            }
        """)
        start_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(start_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Spacer am Ende
        layout.addStretch()
        
        self.stacked_widget.addWidget(start_screen)
    
    def create_device_selection_screen(self):
        """Erstellt den Geräteauswahlbildschirm"""
        device_screen = QWidget()
        layout = QVBoxLayout(device_screen)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Oberer Bereich mit Logo und Titel
        header_layout = QHBoxLayout()
        
        # Titel links
        title_widget = QWidget()
        title_layout = QVBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("Wählen Sie bitte ein Messgerät aus")
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setStyleSheet("color: #003366;")
        title_layout.addWidget(title_label)
        
        header_layout.addWidget(title_widget, 7)
        
        # Logo rechts
        logo = LogoWidget()
        logo.setMaximumSize(160, 80)
        header_layout.addWidget(logo, 3)
        
        layout.addLayout(header_layout)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #cccccc;")
        layout.addWidget(line)
        
        # Buttons für Geräte in Grid-Layout
        device_layout = QGridLayout()
        device_layout.setSpacing(20)
        
        # Multimeter Button
        multimeter_button = DeviceButton("Multimeter", "blue")
        multimeter_button.clicked.connect(self.open_multimeter)
        device_layout.addWidget(multimeter_button, 0, 0)
        
        # Funktionsgenerator Button
        funcgen_button = DeviceButton("Funktionsgenerator", "green")
        funcgen_button.clicked.connect(self.open_function_generator)
        device_layout.addWidget(funcgen_button, 0, 1)
        
        # Oszilloskop Button
        oscilloscope_button = DeviceButton("Oszilloskop", "red")
        oscilloscope_button.clicked.connect(self.open_oscilloscope)
        device_layout.addWidget(oscilloscope_button, 0, 2)
        
        # Kennlinie Button
        kennlinie_button = DeviceButton("Kennlinie", "purple")
        kennlinie_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(2))
        device_layout.addWidget(kennlinie_button, 0, 3)
        
        # Spacer hinzufügen für vertikalen Platz
        device_layout.setRowStretch(1, 1)
        
        device_widget = QWidget()
        device_widget.setLayout(device_layout)
        layout.addWidget(device_widget)
        
        # Buttons am unteren Bildschirmrand
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        back_button = QPushButton("Zurück zum Startbildschirm")
        back_button.setMinimumWidth(200)
        back_button.setMinimumHeight(30)
        back_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        button_layout.addWidget(back_button)
        
        exit_button = QPushButton("Beenden")
        exit_button.setMinimumWidth(100)
        exit_button.setMinimumHeight(30)
        exit_button.clicked.connect(self.close)
        exit_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        button_layout.addWidget(exit_button)
        
        layout.addLayout(button_layout)
        
        self.stacked_widget.addWidget(device_screen)
    
    def create_kennlinie_screen(self):
        """Erstellt den Kennlinie-Bildschirm mit Diodenkennlinie und Filterkennlinie"""
        kennlinie_screen = QWidget()
        layout = QVBoxLayout(kennlinie_screen)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Titel
        title_label = QLabel("Kennlinien-Messung")
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setStyleSheet("color: #003366;")
        layout.addWidget(title_label, alignment=Qt.AlignCenter)
        
        # Untertitel
        subtitle_label = QLabel("Wählen Sie eine Kennlinie aus")
        subtitle_label.setFont(QFont("Arial", 16))
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #003366;")
        layout.addWidget(subtitle_label)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #cccccc;")
        layout.addWidget(line)
        
        # Buttons für Kennlinien in Grid-Layout
        kennlinie_layout = QGridLayout()
        kennlinie_layout.setSpacing(20)
        
        # Diodenkennlinie Button
        diode_button = DeviceButton("Diodenkennlinie", "blue")
        diode_button.clicked.connect(self.open_diode_kennlinie)
        kennlinie_layout.addWidget(diode_button, 0, 0)
        
        # Filterkennlinie Button
        filter_button = DeviceButton("Filterkennlinie", "green")
        filter_button.clicked.connect(self.open_filter_kennlinie)
        kennlinie_layout.addWidget(filter_button, 0, 1)
        
        # Spacer hinzufügen für vertikalen Platz
        kennlinie_layout.setRowStretch(1, 1)
        
        kennlinie_widget = QWidget()
        kennlinie_widget.setLayout(kennlinie_layout)
        layout.addWidget(kennlinie_widget)
        
        # Zurück-Button
        back_button = QPushButton("Zurück zur Geräteauswahl")
        back_button.setMinimumWidth(200)
        back_button.setMinimumHeight(30)
        back_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(back_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        layout.addStretch()
        
        self.stacked_widget.addWidget(kennlinie_screen)
    
    def open_multimeter(self):
        """Öffnet das Multimeter (Placeholder-Funktion)"""
        if MultimeterApp is None:
            print("MultimeterApp is not available")
            return
        print("Multimeter wird geöffnet")
        self.multimeter_app = MultimeterApp()
        self.multimeter_app.show()
    
    def open_function_generator(self):
        """Öffnet den Funktionsgenerator (Placeholder-Funktion)"""
        if Funktionsgenerator is None:
            print("MyDAQFunktionsgenerator is not available")
            return
        print("Funktionsgenerator wird geöffnet")
        self.function_generator = Funktionsgenerator()
        self.function_generator.show()
    
    def open_oscilloscope(self):
        """Öffnet das Oszilloskop (Placeholder-Funktion)"""
        if MyDAQOszilloskop is None:
            print("OscilloscopeApp is not available")
            return
        print("Oszilloskop wird geöffnet")
        self.oscilloscope_app = MyDAQOszilloskop()
        self.oscilloscope_app.show()
    
    def open_diode_kennlinie(self):
       """Öffnet die Diodenkennlinie-Anwendung"""
       if DiodeKennlinieApp is None:
           print("DiodeKennlinieApp is not available")
           return
       print("Diodenkennlinie wird geöffnet")
       self.diode_app = DiodeKennlinieApp(self)
       self.diode_app.show()
    
    def open_filter_kennlinie(self):
        if FilterKennlinieApp is None:
            print("FilterKennlinieApp is not available")
            return
        print("Filterkennlinie wird geöffnet")
        self.filter_app = FilterKennlinieApp(self)
        self.filter_app.show()
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OurDAQApp()
    sys.exit(app.exec_())