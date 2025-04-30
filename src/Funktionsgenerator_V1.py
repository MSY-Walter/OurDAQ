# -*- coding: utf-8 -*-
import sys
import numpy as np
import threading
import time
import queue
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QLabel,
                             QVBoxLayout, QHBoxLayout, QComboBox, QFrame, QDoubleSpinBox,
                             QStatusBar)
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QLinearGradient, QBrush
from PyQt5.QtCore import Qt, QTimer
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

class Funktionsgenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OurDAQ Funktionsgenerator")
        self.setMinimumSize(800, 600)
        
        # Signalparameter
        self.signal_type = "Sinus"
        self.frequency = 1000.0
        self.amplitude = 1.0
        self.offset = 0.0
        self.duty_cycle = 50.0
        
        # Signal-Ausgabestatus
        self.is_running = False
        self.output_thread = None
        self.stop_event = threading.Event()
        self.oscilloscope_queue = queue.Queue()
        
        # Daten für Plot
        self.max_plot_points = 1000
        self.periods_to_show = 2
        self.time_data = np.linspace(0, 0.01, self.max_plot_points)
        self.signal_data = np.zeros(self.max_plot_points)
        
        self.setup_ui()
        self.update_plot()
        
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 10, 20, 20)
        main_layout.setSpacing(15)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Funktionsgenerator")
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
        
        # Hauptbereich
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # Steuerelemente
        control_frame = QFrame()
        control_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 5px;")
        control_layout = QVBoxLayout(control_frame)
        control_layout.setSpacing(10)
        
        # Signaltyp
        signal_layout = QHBoxLayout()
        signal_label = QLabel("Signalform:")
        signal_label.setFont(QFont("Arial", 12))
        signal_layout.addWidget(signal_label)
        
        self.signal_combo = QComboBox()
        self.signal_combo.addItems(["Sinus", "Rechteck", "Dreieck", "Sägezahn"])
        self.signal_combo.setCurrentText(self.signal_type)
        self.signal_combo.setStyleSheet("""
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
        self.signal_combo.currentTextChanged.connect(self.update_signal_type)
        signal_layout.addWidget(self.signal_combo)
        signal_layout.addStretch()
        control_layout.addLayout(signal_layout)
        
        # Frequenz
        freq_layout = QHBoxLayout()
        freq_label = QLabel("Frequenz (Hz):")
        freq_label.setFont(QFont("Arial", 12))
        freq_layout.addWidget(freq_label)
        
        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setRange(1.0, 20000.0)
        self.freq_spin.setValue(self.frequency)
        self.freq_spin.setDecimals(2)
        self.freq_spin.setSingleStep(10.0)
        self.freq_spin.setStyleSheet("padding: 3px; font: 12px Arial;")
        self.freq_spin.valueChanged.connect(self.update_frequency)
        freq_layout.addWidget(self.freq_spin)
        control_layout.addLayout(freq_layout)
        
        # Amplitude
        amp_layout = QHBoxLayout()
        amp_label = QLabel("Amplitude (V):")
        amp_label.setFont(QFont("Arial", 12))
        amp_layout.addWidget(amp_label)
        
        self.amp_spin = QDoubleSpinBox()
        self.amp_spin.setRange(0.01, 5.0)
        self.amp_spin.setValue(self.amplitude)
        self.amp_spin.setDecimals(2)
        self.amp_spin.setSingleStep(0.1)
        self.amp_spin.setStyleSheet("padding: 3px; font: 12px Arial;")
        self.amp_spin.valueChanged.connect(self.update_amplitude)
        amp_layout.addWidget(self.amp_spin)
        control_layout.addLayout(amp_layout)
        
        # Offset
        offset_layout = QHBoxLayout()
        offset_label = QLabel("Offset (V):")
        offset_label.setFont(QFont("Arial", 12))
        offset_layout.addWidget(offset_label)
        
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-5.0, 5.0)
        self.offset_spin.setValue(self.offset)
        self.offset_spin.setDecimals(2)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setStyleSheet("padding: 3px; font: 12px Arial;")
        self.offset_spin.valueChanged.connect(self.update_offset)
        offset_layout.addWidget(self.offset_spin)
        control_layout.addLayout(offset_layout)
        
        # Duty Cycle
        duty_layout = QHBoxLayout()
        duty_label = QLabel("Duty Cycle (%):")
        duty_label.setFont(QFont("Arial", 12))
        duty_layout.addWidget(duty_label)
        
        self.duty_spin = QDoubleSpinBox()
        self.duty_spin.setRange(1.0, 99.0)
        self.duty_spin.setValue(self.duty_cycle)
        self.duty_spin.setDecimals(1)
        self.duty_spin.setSingleStep(1.0)
        self.duty_spin.setStyleSheet("padding: 3px; font: 12px Arial;")
        self.duty_spin.valueChanged.connect(self.update_duty_cycle)
        self.duty_spin.setEnabled(self.signal_type == "Rechteck")
        duty_layout.addWidget(self.duty_spin)
        control_layout.addLayout(duty_layout)
        
        # Ausgabekontrolle
        output_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start")
        self.start_button.setStyleSheet("""
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
            QPushButton:disabled {
                background: #cccccc;
                color: #666666;
            }
        """)
        self.start_button.clicked.connect(self.start_output)
        output_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
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
            QPushButton:disabled {
                background: #cccccc;
                color: #666666;
            }
        """)
        self.stop_button.clicked.connect(self.stop_output)
        output_layout.addWidget(self.stop_button)
        
        reset_button = QPushButton("Zurücksetzen")
        reset_button.setStyleSheet("""
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
        reset_button.clicked.connect(self.reset_parameters)
        output_layout.addWidget(reset_button)
        
        output_layout.addStretch()
        control_layout.addLayout(output_layout)
        control_layout.addStretch()
        content_layout.addWidget(control_frame, 1)
        
        # Signalvorschau
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#ffffff')
        self.plot_widget.setTitle("Signalvorschau", color='#333333', size='12pt')
        self.plot_widget.setLabel('left', 'Amplitude', units='V')
        self.plot_widget.setLabel('bottom', 'Zeit', units='s')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_data = self.plot_widget.plot(pen=pg.mkPen(color='b', width=2))
        content_layout.addWidget(self.plot_widget, 2)
        
        main_layout.addLayout(content_layout)
        
        # Statusleiste
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("font: 12px Arial; color: #333333;")
        self.status_bar.showMessage("Bereit")
        self.setStatusBar(self.status_bar)
        
        # Verbindungshinweis
        self.connection_label = QLabel("Verbunden mit Oszilloskop")
        self.connection_label.setStyleSheet("color: #4CAF50; font: 10px Arial;")
        self.status_bar.addPermanentWidget(self.connection_label)
        
    def update_signal_type(self, text):
        self.signal_type = text
        self.duty_spin.setEnabled(text == "Rechteck")
        self.update_plot()
    
    def update_frequency(self, value):
        self.frequency = value
        self.update_plot()
    
    def update_amplitude(self, value):
        self.amplitude = value
        self.update_plot()
    
    def update_offset(self, value):
        self.offset = value
        self.update_plot()
    
    def update_duty_cycle(self, value):
        self.duty_cycle = value
        self.update_plot()
    
    def reset_parameters(self):
        self.signal_type = "Sinus"
        self.frequency = 1000.0
        self.amplitude = 1.0
        self.offset = 0.0
        self.duty_cycle = 50.0
        
        self.signal_combo.setCurrentText(self.signal_type)
        self.freq_spin.setValue(self.frequency)
        self.amp_spin.setValue(self.amplitude)
        self.offset_spin.setValue(self.offset)
        self.duty_spin.setValue(self.duty_cycle)
        self.duty_spin.setEnabled(self.signal_type == "Rechteck")
        
        self.status_bar.showMessage("Parameter zurückgesetzt", 3000)
        self.update_plot()
    
    def generate_signal(self, t):
        omega = 2 * np.pi * self.frequency
        duty = self.duty_cycle / 100.0
        
        if self.signal_type == "Sinus":
            return self.amplitude * np.sin(omega * t) + self.offset
        elif self.signal_type == "Rechteck":
            signal = np.zeros_like(t)
            mod_t = (t * self.frequency) % 1.0
            signal[mod_t < duty] = self.amplitude
            signal[mod_t >= duty] = -self.amplitude
            return signal + self.offset
        elif self.signal_type == "Dreieck":
            mod_t = (t * self.frequency) % 1.0
            signal = np.zeros_like(t)
            mask1 = mod_t < 0.5
            mask2 = mod_t >= 0.5
            signal[mask1] = self.amplitude * (4 * mod_t[mask1] - 1)
            signal[mask2] = self.amplitude * (3 - 4 * mod_t[mask2])
            return signal + self.offset
        elif self.signal_type == "Sägezahn":
            mod_t = (t * self.frequency) % 1.0
            return self.amplitude * (2 * mod_t - 1) + self.offset
    
    def update_plot(self):
        period = 1.0 / max(1.0, self.frequency)
        self.time_data = np.linspace(0, self.periods_to_show * period, self.max_plot_points)
        self.signal_data = self.generate_signal(self.time_data)
        
        self.plot_data.setData(self.time_data, self.signal_data)
        self.plot_widget.setTitle(f"{self.signal_type}-Signal, {self.frequency:.2f} Hz")
        
        y_max = max(abs(self.amplitude) + abs(self.offset), 0.1) * 1.2
        self.plot_widget.setYRange(-y_max, y_max)
        self.plot_widget.setXRange(0, self.periods_to_show * period)
    
    def start_output(self):
        if not self.is_running:
            self.is_running = True
            self.stop_event.clear()
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_bar.showMessage("Signal wird ausgegeben")
            
            self.output_thread = threading.Thread(target=self.output_signal_thread)
            self.output_thread.daemon = True
            self.output_thread.start()
    
    def stop_output(self):
        if self.is_running:
            self.stop_event.set()
            if self.output_thread:
                self.output_thread.join(timeout=1.0)
            self.is_running = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_bar.showMessage("Ausgabe gestoppt")
    
    def output_signal_thread(self):
        sample_rate = 44100
        buffer_size = 1024
        t_buffer = np.arange(buffer_size) / sample_rate
        time_counter = 0.0
        
        while not self.stop_event.is_set():
            # Thread-safe Parameterkopie
            signal_type = self.signal_type
            frequency = self.frequency
            amplitude = self.amplitude
            offset = self.offset
            duty_cycle = self.duty_cycle
            
            t = t_buffer + time_counter
            signal_buffer = self.generate_signal(t)
            
            try:
                signal_data = {
                    'signal': signal_buffer,
                    'time': t,
                    'type': signal_type,
                    'frequency': frequency,
                    'amplitude': amplitude,
                    'offset': offset,
                    'sample_rate': sample_rate
                }
                self.oscilloscope_queue.put(signal_data, block=False)
            except queue.Full:
                pass
            
            time_counter += buffer_size / sample_rate
            time.sleep(buffer_size / sample_rate)
    
    def closeEvent(self, event):
        if self.is_running:
            self.stop_output()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Funktionsgenerator()
    window.show()
    sys.exit(app.exec_())