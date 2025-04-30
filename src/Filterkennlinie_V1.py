import sys
import numpy as np
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QFrame
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath
from PyQt5.QtCore import QTimer, Qt
import pyqtgraph as pg

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
        qp.drawText(0, 0, width, height, Qt.AlignCenter, "OurDAQ")

class FilterKennlinieApp(QMainWindow):
    """Anwendung zur Messung und Darstellung der Filterkennlinie"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filterkennlinie - OurDAQ")
        self.setMinimumSize(800, 600)

        # Haupt-Widget und Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(20, 10, 20, 20)
        self.layout.setSpacing(15)

        # Header-Layout für Titel und Logo
        header_layout = QHBoxLayout()
        
        # Titel links
        title_label = QLabel("Filterkennlinie-Messung")
        title_label.setFont(QFont("Arial", 20, QFont.Bold))
        title_label.setStyleSheet("color: #003366;")
        header_layout.addWidget(title_label, 7)
        
        # Logo rechts
        logo = LogoWidget()
        logo.setMaximumSize(160, 80)
        header_layout.addWidget(logo, 3)
        
        self.layout.addLayout(header_layout)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #cccccc;")
        self.layout.addWidget(line)

        # Untertitel
        subtitle_label = QLabel("Frequenzbereich einstellen und Amplitudengang messen")
        subtitle_label.setFont(QFont("Arial", 14))
        subtitle_label.setStyleSheet("color: #003366;")
        self.layout.addWidget(subtitle_label, alignment=Qt.AlignCenter)

        # Plot-Widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.setTitle("Amplitudengang", color="k", size="14pt")
        self.plot_widget.setLabel("left", "Verstärkung (dB)", color="k", size="12pt")
        self.plot_widget.setLabel("bottom", "Frequenz (Hz)", color="k", size="12pt")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setLogMode(x=True, y=False)  # Logarithmische Frequenzskala
        self.plot_widget.setXRange(np.log10(10), np.log10(20000))
        self.plot_widget.setYRange(-60, 0)
        self.layout.addWidget(self.plot_widget, stretch=1)

        # Plot-Daten
        self.frequencies = []
        self.gains = []
        self.plot_line = self.plot_widget.plot(self.frequencies, self.gains, pen=pg.mkPen(color=(0, 102, 204), width=2))

        # Eingabefelder für Frequenzbereich
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Frequenz (Hz):"))
        self.freq_min = QLineEdit("10")
        self.freq_max = QLineEdit("20000")
        self.freq_step = QLineEdit("100")
        control_layout.addWidget(self.freq_min)
        control_layout.addWidget(QLabel("bis"))
        control_layout.addWidget(self.freq_max)
        control_layout.addWidget(QLabel("Schritt"))
        control_layout.addWidget(self.freq_step)
        control_layout.addStretch()
        self.layout.addLayout(control_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Messung starten")
        self.start_button.setMinimumHeight(30)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #003366;
                color: white;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #004080;
            }
        """)
        self.start_button.clicked.connect(self.start_measurement)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Messung stoppen")
        self.stop_button.setMinimumHeight(30)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_measurement)
        button_layout.addWidget(self.stop_button)

        self.back_button = QPushButton("Zurück")
        self.back_button.setMinimumHeight(30)
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.back_button.clicked.connect(self.close)
        button_layout.addWidget(self.back_button)

        button_layout.addStretch()
        self.layout.addLayout(button_layout)

        # Statusanzeige
        self.status_label = QLabel("Bereit")
        self.status_label.setFont(QFont("Arial", 12))
        self.status_label.setStyleSheet("color: #003366;")
        self.layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Timer für Messungen
        self.timer = QTimer()
        self.timer.timeout.connect(self.perform_measurement)

        # Messvariablen
        self.current_frequency = 0
        self.is_measuring = False

    def start_measurement(self):
        """Startet die Messung der Filterkennlinie"""
        try:
            f_min = float(self.freq_min.text())
            f_max = float(self.freq_max.text())
            f_step = float(self.freq_step.text())
            if f_min <= 0 or f_min >= f_max or f_step <= 0 or f_step > (f_max - f_min):
                self.status_label.setText("Ungültige Eingabewerte!")
                return
        except ValueError:
            self.status_label.setText("Bitte gültige Zahlen eingeben!")
            return

        self.frequencies = []
        self.gains = []
        self.current_frequency = f_min
        self.f_max = f_max
        self.f_step = f_step
        self.is_measuring = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Messung läuft...")
        self.timer.start(200)  # 200 ms pro Messung

    def stop_measurement(self):
        """Stoppt die Messung"""
        if self.is_measuring:
            self.is_measuring = False
            self.timer.stop()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_label.setText("Messung gestoppt")

    def perform_measurement(self):
        """Führt eine einzelne Messung durch (simuliert)"""
        if not self.is_measuring or self.current_frequency > self.f_max:
            self.stop_measurement()
            return

        # Simulierter Tiefpassfilter: H(f) = 1 / sqrt(1 + (f/f_c)^2)
        f_c = 1000  # Grenzfrequenz (Hz)
        gain_linear = 1 / np.sqrt(1 + (self.current_frequency / f_c) ** 2)
        gain_db = 20 * np.log10(gain_linear)  # Verstärkung in dB

        # Platzhalter für Hardware-Interaktion
        # self.set_frequency(self.current_frequency)
        # gain_db = self.measure_gain()

        self.frequencies.append(self.current_frequency)
        self.gains.append(gain_db)
        self.plot_line.setData(np.log10(self.frequencies), self.gains)

        self.current_frequency += self.f_step

    def resizeEvent(self, event):
        """Behandelt Größenänderungen des Fensters"""
        if self.is_measuring:
            self.stop_measurement()  # Stoppe Messung bei Größenänderung
        super().resizeEvent(event)

    def closeEvent(self, event):
        """Behandelt das Schließen des Fensters"""
        self.stop_measurement()
        event.accept()