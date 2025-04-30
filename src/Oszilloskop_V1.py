# -*- coding: utf-8 -*-
import sys
import os
import time
import numpy as np
from datetime import datetime
import queue
import threading
from collections import deque
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QLabel,
                             QVBoxLayout, QHBoxLayout, QFrame, QDoubleSpinBox, QStatusBar,
                             QCheckBox, QGridLayout, QRadioButton, QTabWidget, QMessageBox,
                             QScrollArea)
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QLinearGradient, QBrush
from PyQt5.QtCore import Qt, QTimer
import pyqtgraph as pg
import pandas as pd

class LogoWidget(QWidget):
    """Widget zum Zeichnen des OurDAQ-Logos"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(100, 60)
    
    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0, QColor(0, 51, 102, 200))
        gradient.setColorAt(1, QColor(0, 102, 204, 200))
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(gradient))
        qp.drawRoundedRect(0, 0, width, height, 10, 10)
        path = QPainterPath()
        path.moveTo(width*0.1, center_y)
        for i in range(100):
            x = width * (0.1 + i * 0.8 / 99)
            y = center_y + height * 0.2 * np.sin(i * np.pi / 15)
            path.lineTo(x, y)
        qp.setPen(QPen(QColor(255, 255, 255, 220), 3))
        qp.drawPath(path)
        qp.setFont(QFont("Segoe UI", int(height/3), QFont.Bold))
        qp.setPen(QPen(QColor(255, 255, 255), 1))
        qp.drawText(0, 0, width, height, Qt.AlignCenter, "OurDAQ")

class TriggerSystem:
    def __init__(self):
        self.enabled = False
        self.level = 0.0
        self.mode = "Steigend"
    
    def check_trigger(self, buffer, current_time):
        if not self.enabled or len(buffer) < 2:
            return True
        if self.mode == "Steigend":
            for i in range(1, len(buffer)):
                if buffer[i-1] < self.level and buffer[i] >= self.level:
                    return True
        elif self.mode == "Fallend":
            for i in range(1, len(buffer)):
                if buffer[i-1] > self.level and buffer[i] <= self.level:
                    return True
        return False

class MeasurementSystem:
    def __init__(self):
        self.available_measurements = ["Frequenz", "Periode", "Spitze-Spitze", "Mittelwert", "RMS", "Min", "Max"]
    
    def calculate(self, data, sample_rate):
        results = {}
        if not data or len(data) < 2:
            return results
        data = np.array(data)
        results["Min"] = np.min(data)
        results["Max"] = np.max(data)
        results["Spitze-Spitze"] = results["Max"] - results["Min"]
        results["Mittelwert"] = np.mean(data)
        results["RMS"] = np.sqrt(np.mean(data**2))
        zero_crossings = np.where(np.diff(np.signbit(data - np.mean(data))))[0]
        if len(zero_crossings) > 1:
            avg_period_samples = np.mean(np.diff(zero_crossings)) * 2
            results["Periode"] = avg_period_samples / sample_rate
            results["Frequenz"] = 1.0 / results["Periode"] if results["Periode"] > 0 else 0
        else:
            results["Periode"] = 0
            results["Frequenz"] = 0
        return results

class MyDAQOszilloskop(QMainWindow):
    def __init__(self, oscilloscope_queue=None):
        super().__init__()
        self.setWindowTitle("OurDAQ Oszilloskop")
        self.setMinimumSize(800, 600)
        self.oscilloscope_queue = oscilloscope_queue or queue.Queue()
        self.sample_rate = 44100
        self.buffer_size = 1024
        self.display_size = 1000
        self.timebase = 0.002  # s/div
        self.divisions = 10
        self.running = True
        self.paused = False
        self.single_shot = False
        self.x_range = [-0.01, 0.01]  # ms
        self.y_range = [-5, 5]  # V
        self.last_meas_update = [0, 0]  # Für jeden Kanal
        self.meas_update_interval = 0.5  # 500 ms
        self.zoom_level = 1.0  # Zoom-Stufe für Statusleiste
        
        # Kanäle
        self.channels = [
            {'enabled': True, 'buffer': deque(maxlen=self.buffer_size),
             'display_buffer': deque(maxlen=self.display_size), 'color': '#00ffff', 'volt_per_div': 1.0,
             'trigger': TriggerSystem(), 'meas_enabled': False},
            {'enabled': False, 'buffer': deque(maxlen=self.buffer_size),
             'display_buffer': deque(maxlen=self.display_size), 'color': '#ff00ff', 'volt_per_div': 1.0,
             'trigger': TriggerSystem(), 'meas_enabled': False}
        ]
        
        self.measurement_system = MeasurementSystem()
        self.cursor_positions = [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]]  # X1, X2, Y1, Y2 pro Kanal
        self.cursor_enabled = [[False] * 4, [False] * 4]  # Pro Kanal
        self.setup_ui()
        self.setup_data_thread()
    
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Stil für die gesamte UI
        self.setStyleSheet("""
    QMainWindow, QWidget { background-color: #f0f0f0; color: #333333; }
    QLabel { font: 12px 'Segoe UI'; color: #333333; }
    QPushButton { 
        background-color: #d0d0d0; 
        color: #333333; 
        border: 1px solid #888888; 
        padding: 5px; 
        border-radius: 3px; 
    }
    QPushButton:hover { background-color: #e0e0e0; }
    QDoubleSpinBox, QCheckBox, QRadioButton { 
        background-color: #ffffff; 
        color: #333333; 
        border: 1px solid #888888; 
        padding: 3px; 
    }
    QTabWidget::pane { border: 1px solid #888888; background: #ffffff; }
    QTabBar::tab { 
        background: #d0d0d0; 
        color: #333333; 
        padding: 5px; 
        border: 1px solid #888888; 
    }
    QTabBar::tab:selected { background: #e0e0e0; }
""")
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Oszilloskop")
        title_label.setStyleSheet("font: 18px 'Segoe UI' bold; color: #00aaff;")
        header_layout.addWidget(title_label, 7)
        logo = LogoWidget()
        logo.setMaximumSize(160, 80)
        header_layout.addWidget(logo, 3)
        main_layout.addLayout(header_layout)
        
        # Inhalt
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        
        # Steuerpanel
        control_frame = QFrame()
        control_frame.setStyleSheet("border: 1px solid #555555; border-radius: 5px;")
        control_layout = QVBoxLayout(control_frame)
        control_layout.setContentsMargins(10, 10, 10, 10)
        
        # Zeitbasis
        timebase_layout = QHBoxLayout()
        timebase_label = QLabel("Zeit/Div (ms):")
        timebase_layout.addWidget(timebase_label)
        self.timebase_spin = QDoubleSpinBox()
        self.timebase_spin.setRange(0.1, 100)
        self.timebase_spin.setValue(self.timebase * 1000)
        self.timebase_spin.valueChanged.connect(self.update_timebase)
        timebase_layout.addWidget(self.timebase_spin)
        control_layout.addLayout(timebase_layout)
        
        # Zoom-Steuerung
        zoom_layout = QHBoxLayout()
        zoom_in_button = QPushButton("Hineinzoomen")
        zooming_out_button = QPushButton("Herauszoomen")
        zoom_reset_button = QPushButton("Zoom zurücksetzen")
        zoom_in_button.clicked.connect(self.zoom_in)
        zooming_out_button.clicked.connect(self.zoom_out)
        zoom_reset_button.clicked.connect(self.zoom_reset)
        zoom_layout.addWidget(zoom_in_button)
        zoom_layout.addWidget(zooming_out_button)
        zoom_layout.addWidget(zoom_reset_button)
        control_layout.addLayout(zoom_layout)
        
        # Kanal-Tabs
        channel_tabs = QTabWidget()
        self.channel_checks = []
        self.volt_spins = []
        self.trigger_checks = []
        self.trigger_level_spins = []
        self.trigger_modes = []
        self.meas_checks = []
        self.cursor_checks = []
        self.cursor_pos_labels = []
        self.meas_labels = []
        
        # Scrollbares Widget für Tabs
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(channel_tabs)
        scroll_area.setStyleSheet("border: none;")
        
        for i in range(2):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(5, 5, 5, 5)
            tab_layout.setSpacing(5)
            
            # Kanal aktivieren
            chk = QCheckBox(f"Kanal {i+1} aktivieren")
            chk.setChecked(self.channels[i]['enabled'])
            chk.stateChanged.connect(lambda state, idx=i: self.toggle_channel(idx, state))
            tab_layout.addWidget(chk)
            self.channel_checks.append(chk)
            
            # Volt pro Division
            volt_layout = QHBoxLayout()
            volt_label = QLabel("Volt/Div (V):")
            volt_layout.addWidget(volt_label)
            volt_spin = QDoubleSpinBox()
            volt_spin.setRange(0.1, 5.0)
            volt_spin.setValue(self.channels[i]['volt_per_div'])
            volt_spin.valueChanged.connect(lambda value, idx=i: self.update_volt_per_div(idx, value))
            volt_layout.addWidget(volt_spin)
            self.volt_spins.append(volt_spin)
            tab_layout.addLayout(volt_layout)
            
            # Trigger
            trigger_frame = QFrame()
            trigger_layout = QVBoxLayout(trigger_frame)
            trigger_check = QCheckBox("Trigger aktivieren")
            trigger_check.stateChanged.connect(lambda state, idx=i: self.update_trigger(idx))
            trigger_layout.addWidget(trigger_check)
            self.trigger_checks.append(trigger_check)
            
            trigger_level_layout = QHBoxLayout()
            trigger_level_label = QLabel("Level (V):")
            trigger_level_layout.addWidget(trigger_level_label)
            trigger_level_spin = QDoubleSpinBox()
            trigger_level_spin.setRange(-5, 5)
            trigger_level_spin.valueChanged.connect(lambda value, idx=i: self.update_trigger(idx))
            trigger_level_layout.addWidget(trigger_level_spin)
            self.trigger_level_spins.append(trigger_level_spin)
            trigger_layout.addLayout(trigger_level_layout)
            
            trigger_mode_layout = QHBoxLayout()
            modes = []
            for mode in ["Steigend", "Fallend"]:
                rb = QRadioButton(mode)
                rb.setChecked(mode == "Steigend")
                rb.toggled.connect(lambda state, idx=i: self.update_trigger(idx))
                trigger_mode_layout.addWidget(rb)
                modes.append(rb)
            self.trigger_modes.append(modes)
            trigger_layout.addLayout(trigger_mode_layout)
            tab_layout.addWidget(trigger_frame)
            
            # Messungen
            meas_frame = QFrame()
            meas_layout = QVBoxLayout(meas_frame)
            meas_check = QCheckBox("Messungen anzeigen")
            meas_check.stateChanged.connect(lambda state, idx=i: self.toggle_measurements(idx, state))
            meas_layout.addWidget(meas_check)
            self.meas_checks.append(meas_check)
            
            meas_grid = QGridLayout()
            labels = {}
            for j, meas in enumerate(self.measurement_system.available_measurements):
                frame = QFrame()
                frame_layout = QHBoxLayout(frame)
                title = QLabel(meas + ":")
                frame_layout.addWidget(title)
                value = QLabel("---")
                frame_layout.addWidget(value)
                meas_grid.addWidget(frame, j//3, j%3)
                labels[meas] = value
            self.meas_labels.append(labels)
            meas_layout.addLayout(meas_grid)
            tab_layout.addWidget(meas_frame)
            
            # Cursor
            cursor_frame = QFrame()
            cursor_layout = QVBoxLayout(cursor_frame)
            cursor_title = QLabel("Cursor:")
            cursor_layout.addWidget(cursor_title)
            cursor_check_layout = QHBoxLayout()
            checks = []
            for j, label in enumerate(["X1", "X2", "Y1", "Y2"]):
                check = QCheckBox(label)
                check.stateChanged.connect(lambda state, idx=i, jdx=j: self.toggle_cursor(idx, jdx, state))
                cursor_check_layout.addWidget(check)
                checks.append(check)
            self.cursor_checks.append(checks)
            cursor_layout.addLayout(cursor_check_layout)
            
            cursor_pos_layout = QGridLayout()
            pos_labels = []
            for j, label in enumerate(["X1 (ms):", "X2 (ms):", "Y1 (V):", "Y2 (V):"]):
                lbl = QLabel(label)
                cursor_pos_layout.addWidget(lbl, j, 0)
                val = QLabel(f"{self.cursor_positions[i][j]:.2f}")
                cursor_pos_layout.addWidget(val, j, 1)
                pos_labels.append(val)
            self.cursor_pos_labels.append(pos_labels)
            cursor_layout.addLayout(cursor_pos_layout)
            tab_layout.addWidget(cursor_frame)
            
            tab_layout.addStretch()
            channel_tabs.addTab(tab, f"CH{i+1}")
        
        control_layout.addWidget(scroll_area)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)
        self.start_button = QPushButton("Start/Pause")
        self.start_button.clicked.connect(self.toggle_pause)
        button_layout.addWidget(self.start_button)
        single_button = QPushButton("Einzelaufnahme")
        single_button.clicked.connect(self.single_shot_capture)
        button_layout.addWidget(single_button)
        screenshot_button = QPushButton("Screenshot")
        screenshot_button.clicked.connect(self.save_screenshot)
        button_layout.addWidget(screenshot_button)
        save_button = QPushButton("Daten speichern")
        save_button.clicked.connect(self.save_data)
        button_layout.addWidget(save_button)
        self.save_raw_check = QCheckBox("Rohdaten speichern")
        button_layout.addWidget(self.save_raw_check)
        load_button = QPushButton("Daten laden")
        load_button.clicked.connect(self.load_data)
        button_layout.addWidget(load_button)
        help_button = QPushButton("Hilfe")
        help_button.clicked.connect(self.show_help)
        button_layout.addWidget(help_button)
        control_layout.addLayout(button_layout)
        content_layout.addWidget(control_frame, 1)
        
        # Plot
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.setLabel('left', 'Spannung (V)', color='#e0e0e0', size='12pt')
        self.plot_widget.setLabel('bottom', 'Zeit (ms)', color='#e0e0e0', size='12pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getViewBox().setMouseEnabled(x=True, y=True)
        self.plot_widget.getViewBox().wheelEvent = self.wheelEvent
        # Legende hinzufügen
        self.plot_widget.addLegend(offset=(10, 10))
        self.ch_plots = []
        for i, ch in enumerate(self.channels):
            plot = self.plot_widget.plot(pen=pg.mkPen(color=ch['color'], width=2), name=f"Kanal {i+1}")
            self.ch_plots.append(plot)
        
        self.cursor_lines = [
            [  # CH1
                pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen(color='#00ff00', style=Qt.DashLine), movable=True),
                pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen(color='#ff0000', style=Qt.DashLine), movable=True),
                pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen(color='#00ffff', style=Qt.DashLine), movable=True),
                pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen(color='#ff00ff', style=Qt.DashLine), movable=True)
            ],
            [  # CH2
                pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen(color='#00cc00', style=Qt.DashLine), movable=True),
                pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen(color='#cc0000', style=Qt.DashLine), movable=True),
                pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen(color='#00cccc', style=Qt.DashLine), movable=True),
                pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen(color='#cc00cc', style=Qt.DashLine), movable=True)
            ]
        ]
        for i in range(2):
            for j, line in enumerate(self.cursor_lines[i]):
                self.plot_widget.addItem(line)
                line.setVisible(False)
                line.sigPositionChanged.connect(lambda line, idx=i, jdx=j: self.update_cursor_position(idx, jdx, line))
        
        self.trigger_lines = [
            pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color='#ff0000', style=Qt.DashLine)),
            pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(color='#ff0000', style=Qt.DashLine))
        ]
        for line in self.trigger_lines:
            self.plot_widget.addItem(line)
            line.setVisible(False)
        
        content_layout.addWidget(self.plot_widget, 2)
        main_layout.addLayout(content_layout)
        
        # Statusleiste
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("color: #e0e0e0; background-color: #333333;")
        self.status_bar.showMessage("Bereit")
        self.setStatusBar(self.status_bar)
    
    def toggle_channel(self, idx, state):
        self.channels[idx]['enabled'] = state == Qt.Checked
        self.update_plot()
        self.status_bar.showMessage(f"Kanal {idx+1} {'aktiviert' if self.channels[idx]['enabled'] else 'deaktiviert'}", 3000)
        print(f"Kanal {idx+1} {'aktiviert' if self.channels[idx]['enabled'] else 'deaktiviert'}")
    
    def update_volt_per_div(self, idx, value):
        self.channels[idx]['volt_per_div'] = value
        self.update_plot()
        self.status_bar.showMessage(f"Kanal {idx+1} Volt/Div: {value} V", 3000)
        print(f"Kanal {idx+1} Volt/Div: {value} V")
    
    def update_timebase(self, value):
        self.timebase = value / 1000.0
        self.x_range = [-self.divisions * self.timebase * 1000 / 2, self.divisions * self.timebase * 1000 / 2]
        self.update_plot()
        self.status_bar.showMessage(f"Zeitbasis: {self.timebase*1000} ms/Div", 3000)
        print(f"Zeitbasis: {self.timebase*1000} ms")
    
    def update_trigger(self, idx):
        trigger = self.channels[idx]['trigger']
        trigger.enabled = self.trigger_checks[idx].isChecked()
        trigger.level = self.trigger_level_spins[idx].value()
        for rb in self.trigger_modes[idx]:
            if rb.isChecked():
                trigger.mode = rb.text()
        self.trigger_lines[idx].setPos(trigger.level)
        self.trigger_lines[idx].setVisible(trigger.enabled and self.channels[idx]['enabled'])
        self.status_bar.showMessage(f"Trigger Kanal {idx+1}: {'Aktiv' if trigger.enabled else 'Inaktiv'}", 3000)
        print(f"Trigger Kanal {idx+1} aktualisiert: enabled={trigger.enabled}, level={trigger.level}, mode={trigger.mode}")
    
    def toggle_cursor(self, ch_idx, cursor_idx, state):
        self.cursor_enabled[ch_idx][cursor_idx] = state == Qt.Checked
        self.cursor_positions[ch_idx][cursor_idx] = 0.0
        if cursor_idx < 2:
            self.cursor_positions[ch_idx][cursor_idx] = max(self.x_range[0], min(self.x_range[1], self.cursor_positions[ch_idx][cursor_idx]))
        else:
            self.cursor_positions[ch_idx][cursor_idx] = max(self.y_range[0], min(self.y_range[1], self.cursor_positions[ch_idx][cursor_idx]))
        self.cursor_lines[ch_idx][cursor_idx].setPos(self.cursor_positions[ch_idx][cursor_idx])
        self.cursor_lines[ch_idx][cursor_idx].setVisible(self.cursor_enabled[ch_idx][cursor_idx])
        self.update_cursor_position(ch_idx, cursor_idx, self.cursor_lines[ch_idx][cursor_idx])
        self.status_bar.showMessage(f"Cursor Kanal {ch_idx+1} {'aktiviert' if self.cursor_enabled[ch_idx][cursor_idx] else 'deaktiviert'}", 3000)
        print(f"Cursor Kanal {ch_idx+1} {cursor_idx} {'aktiviert' if self.cursor_enabled[ch_idx][cursor_idx] else 'deaktiviert'}, pos={self.cursor_positions[ch_idx][cursor_idx]:.2f}")
    
    def update_cursor_position(self, ch_idx, cursor_idx, line):
        pos = line.pos()[0] if cursor_idx < 2 else line.pos()[1]
        self.cursor_positions[ch_idx][cursor_idx] = pos
        if cursor_idx < 2:  # X1, X2 (Zeit)
            time_data = np.linspace(self.x_range[0], self.x_range[1], self.display_size)
            idx = np.searchsorted(time_data, pos)
            if 0 < idx < len(time_data):
                frac = (pos - time_data[idx-1]) / (time_data[idx] - time_data[idx-1])
                self.cursor_positions[ch_idx][cursor_idx] = time_data[idx-1] + frac * (time_data[idx] - time_data[idx-1])
        else:  # Y1, Y2 (Spannung)
            if len(self.channels[ch_idx]['display_buffer']) > 0:
                y_data = np.array(list(self.channels[ch_idx]['display_buffer'])) * self.channels[ch_idx]['volt_per_div']
                self.cursor_positions[ch_idx][cursor_idx] = max(self.y_range[0], min(self.y_range[1], pos))
        self.cursor_pos_labels[ch_idx][cursor_idx].setText(f"{self.cursor_positions[ch_idx][cursor_idx]:.3f}")
        self.status_bar.showMessage(f"Cursor Kanal {ch_idx+1} Position: {self.cursor_positions[ch_idx][cursor_idx]:.3f}", 3000)
        print(f"Cursor Kanal {ch_idx+1} {cursor_idx} Position: {self.cursor_positions[ch_idx][cursor_idx]:.3f}")
    
    def toggle_measurements(self, idx, state):
        self.channels[idx]['meas_enabled'] = state == Qt.Checked
        self.update_measurements(idx)
        self.status_bar.showMessage(f"Messungen Kanal {idx+1} {'aktiviert' if self.channels[idx]['meas_enabled'] else 'deaktiviert'}", 3000)
        print(f"Messungen Kanal {idx+1} {'aktiviert' if self.channels[idx]['meas_enabled'] else 'deaktiviert'}")
    
    def update_measurements(self, idx):
        current_time = time.time()
        if current_time - self.last_meas_update[idx] < self.meas_update_interval:
            return
        self.last_meas_update[idx] = current_time
        
        if not self.channels[idx]['meas_enabled']:
            for key in self.meas_labels[idx]:
                self.meas_labels[idx][key].setText("---")
            print(f"Messungen Kanal {idx+1} deaktiviert")
            return
        ch = self.channels[idx]
        if ch['enabled'] and len(ch['display_buffer']) >= 2:
            data = list(ch['display_buffer'])
            results = self.measurement_system.calculate(data, self.sample_rate)
            for meas, value in results.items():
                if meas in self.meas_labels[idx]:
                    if meas == "Frequenz":
                        self.meas_labels[idx][meas].setText(f"{value:.2f} Hz")
                    elif meas == "Periode":
                        self.meas_labels[idx][meas].setText(f"{value*1000:.2f} ms")
                    else:
                        self.meas_labels[idx][meas].setText(f"{value:.3f} V")
            print(f"Messungen Kanal {idx+1} aktualisiert: {results}")
        else:
            for key in self.meas_labels[idx]:
                self.meas_labels[idx][key].setText("---")
            print(f"Keine Messungen Kanal {idx+1}: enabled={ch['enabled']}, buffer_len={len(ch['display_buffer'])}")
        self.status_bar.showMessage(f"Messungen für Kanal {idx+1} aktualisiert", 3000)
    
    def update_all_measurements(self):
        for i in range(2):
            self.update_measurements(i)
    
    def toggle_pause(self):
        self.paused = not self.paused
        self.single_shot = False
        self.status_bar.showMessage("Pausiert" if self.paused else "Läuft")
        self.start_button.setText("Start" if self.paused else "Pause")
        print("Pause umgeschaltet")
    
    def single_shot_capture(self):
        self.single_shot = True
        self.paused = False
        self.status_bar.showMessage("Einzelaufnahme gestartet")
        self.start_button.setText("Start")
        print("Einzelaufnahme gestartet")
    
    def save_screenshot(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = "export"
        os.makedirs(export_dir, exist_ok=True)
        filename = os.path.join(export_dir, f"oszilloskop_screenshot_{timestamp}.png")
        try:
            image = self.plot_widget.grab().toImage()
            image.save(filename)
            self.status_bar.showMessage(f"Screenshot gespeichert: {filename}", 3000)
            print(f"Screenshot gespeichert: {filename}")
        except Exception as e:
            self.status_bar.showMessage("Fehler beim Speichern des Screenshots", 3000)
            print(f"Fehler beim Speichern des Screenshots: {e}")
    
    def save_data(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = "export"
        os.makedirs(export_dir, exist_ok=True)
        filename = os.path.join(export_dir, f"oszilloskop_daten_{timestamp}.csv")
        try:
            time_data = np.linspace(self.x_range[0], self.x_range[1], self.display_size)
            data = {'Zeit_ms': time_data}
            for i, ch in enumerate(self.channels):
                if ch['enabled'] and len(ch['display_buffer']) > 0:
                    data_values = np.array(list(ch['display_buffer']))
                    if not self.save_raw_check.isChecked():
                        data_values *= ch['volt_per_div']
                    data[f'Kanal{i+1}_V'] = data_values[:len(time_data)]
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False, float_format='%.6f')
            self.status_bar.showMessage(f"Daten gespeichert: {filename}", 3000)
            print(f"Daten gespeichert: {filename}")
        except Exception as e:
            self.status_bar.showMessage("Fehler beim Speichern der Daten", 3000)
            print(f"Fehler beim Speichern der Daten: {e}")
    
    def load_data(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = "export"
        filename = os.path.join(export_dir, f"oszilloskop_daten_{timestamp}.csv")
        try:
            if os.path.exists(filename):
                df = pd.read_csv(filename)
                for i, ch in enumerate(self.channels):
                    if ch['enabled'] and f'Kanal{i+1}_V' in df.columns:
                        ch['display_buffer'].clear()
                        data = df[f'Kanal{i+1}_V'].dropna().values
                        if not self.save_raw_check.isChecked():
                            data /= ch['volt_per_div']
                        ch['display_buffer'].extend(data)
                self.update_plot()
                self.status_bar.showMessage(f"Daten geladen: {filename}", 3000)
                print(f"Daten geladen: {filename}")
            else:
                self.status_bar.showMessage("Keine Daten zum Laden gefunden", 3000)
                print("Keine Daten zum Laden gefunden")
        except Exception as e:
            self.status_bar.showMessage("Fehler beim Laden der Daten", 3000)
            print(f"Fehler beim Laden der Daten: {e}")
    
    def show_help(self):
        QMessageBox.information(self, "Hilfe", "Anleitung:\n"
                                "- Tabs: Konfigurieren Sie Kanal 1/2 (Aktivierung, Volt/Div, Trigger, Messungen, Cursor).\n"
                                "- Zeitbasis: Stellen Sie Zeit/Division (ms) ein.\n"
                                "- Trigger: Aktivieren und konfigurieren Sie Level und Modus pro Kanal.\n"
                                "- Messungen: Aktivieren Sie die Anzeige von Messungen pro Kanal.\n"
                                "- Cursor: Aktivieren und bewegen Sie X1/X2 (Zeit), Y1Ascertainments:\n"
                                "- Zoom: Verwenden Sie das Mausrad (Strg für Y-Zoom) oder die Zoom-Buttons.\n"
                                "- Speichern: Aktivieren Sie 'Rohdaten speichern' für unskalierte Daten.\n"
                                "- Buttons: Start/Pause, Einzelaufnahme, Screenshot, Daten speichern/laden.")
        print("Hilfedialog angezeigt")
    
    def wheelEvent(self, event):
        factor = 1.05 if event.delta() > 0 else 1 / 1.05
        view_box = self.plot_widget.getViewBox()
        x_range = view_box.viewRange()[0]
        y_range = view_box.viewRange()[1]
        x_center = (x_range[0] + x_range[1]) / 2
        y_center = (y_range[0] + y_range[1]) / 2
        new_x_width = (x_range[1] - x_range[0]) * factor
        new_y_width = (y_range[1] - y_range[0]) * factor
        if event.modifiers() & Qt.ControlModifier:
            self.plot_widget.setYRange(y_center - new_y_width / 2, y_center + new_y_width / 2, padding=0)
        else:
            self.plot_widget.setXRange(x_center - new_x_width / 2, x_center + new_x_width / 2, padding=0)
        self.zoom_level *= factor if event.delta() > 0 else 1 / factor
        self.status_bar.showMessage(f"Zoom-Stufe: {self.zoom_level:.2f}x", 3000)
        event.accept()
    
    def zoom_in(self):
        view_box = self.plot_widget.getViewBox()
        view_box.scaleBy((0.95, 0.95))
        self.zoom_level /= 0.95
        self.status_bar.showMessage(f"Zoom-Stufe: {self.zoom_level:.2f}x", 3000)
        print("Hineingezoomt")
    
    def zoom_out(self):
        view_box = self.plot_widget.getViewBox()
        view_box.scaleBy((1.05, 1.05))
        self.zoom_level *= 1.05
        self.status_bar.showMessage(f"Zoom-Stufe: {self.zoom_level:.2f}x", 3000)
        print("Herausgezoomt")
    
    def zoom_reset(self):
        self.plot_widget.setXRange(self.x_range[0], self.x_range[1], padding=0)
        self.plot_widget.setYRange(self.y_range[0], self.y_range[1], padding=0)
        self.zoom_level = 1.0
        self.status_bar.showMessage("Zoom zurückgesetzt", 3000)
        print("Zoom zurückgesetzt")
    
    def setup_data_thread(self):
        self.data_thread = threading.Thread(target=self.generate_data, daemon=True)
        self.data_thread.start()
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plot)
        self.plot_timer.start(33)
        self.meas_timer = QTimer()
        self.meas_timer.timeout.connect(self.update_all_measurements)
        self.meas_timer.start(500)
        print("Daten-Thread, Plot-Timer und Mess-Timer gestartet")
    
    def generate_data(self):
        t = 0.0
        dt = 1.0 / self.sample_rate
        while self.running:
            if not self.paused:
                try:
                    signal_data = self.oscilloscope_queue.get_nowait()
                    signal = signal_data['signal']
                    for i, ch in enumerate(self.channels):
                        if ch['enabled']:
                            ch['buffer'].extend(signal if i == 0 else np.zeros_like(signal))
                    self.oscilloscope_queue.task_done()
                    print(f"Daten aus Queue empfangen: {len(signal)} Samples")
                except queue.Empty:
                    for i, ch in enumerate(self.channels):
                        if ch['enabled']:
                            freq = 1000 if i == 0 else 2000
                            value = np.sin(2 * np.pi * freq * t)
                            ch['buffer'].append(value)
                            print(f"Daten für Kanal {i+1} generiert: {value:.2f}, buffer_len={len(ch['buffer'])}")
                    t += dt
                current_time = time.time()
                for i, ch in enumerate(self.channels):
                    if ch['enabled'] and len(ch['buffer']) > 0:
                        if not ch['trigger'].enabled or ch['trigger'].check_trigger(list(ch['buffer'])[-2:], current_time):
                            display_points = min(len(ch['buffer']), self.display_size)
                            ch['display_buffer'].clear()
                            ch['display_buffer'].extend(list(ch['buffer'])[-display_points:])
                            print(f"Kanal {i+1} display_buffer aktualisiert: {len(ch['display_buffer'])} Punkte")
                            if self.single_shot:
                                self.paused = True
                                self.single_shot = False
                                self.status_bar.showMessage("Einzelaufnahme abgeschlossen")
                                print("Einzelaufnahme abgeschlossen")
                                break
            time.sleep(dt)
    
    def update_plot(self):
        time_data = np.linspace(self.x_range[0], self.x_range[1], self.display_size)
        for i, ch in enumerate(self.channels):
            if ch['enabled'] and len(ch['display_buffer']) > 0:
                y_data = np.array(list(ch['display_buffer'])) * ch['volt_per_div']
                self.ch_plots[i].setData(time_data[:len(y_data)], y_data)
                print(f"Plot Kanal {i+1}: {len(y_data)} Punkte, min={np.min(y_data):.2f}, max={np.max(y_data):.2f}")
            else:
                self.ch_plots[i].setData([], [])
                print(f"Kanal {i+1}: Kein Plot (enabled={ch['enabled']}, buffer_len={len(ch['display_buffer'])})")
        print("Plot aktualisiert")
    
    def closeEvent(self, event):
        self.running = False
        self.plot_timer.stop()
        self.meas_timer.stop()
        if hasattr(self, 'data_thread') and self.data_thread.is_alive():
            self.data_thread.join(timeout=1.0)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyDAQOszilloskop()
    window.show()
    sys.exit(app.exec_())