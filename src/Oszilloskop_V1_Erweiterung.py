import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
import time
import threading
from collections import deque
import datetime
import json

class SignalGenerator:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate

    def generate(self, signal_type, freq, amp, offset, noise, phase_deg, t):
        phase_rad = np.deg2rad(phase_deg)
        omega = 2 * np.pi * freq
        t_adj = t + phase_rad / omega

        if signal_type == 'Sinus':
            signal = amp * np.sin(omega * t_adj)
        elif signal_type == 'Rechteck':
            signal = amp * np.sign(np.sin(omega * t_adj))
        elif signal_type == 'Dreieck':
            signal = amp * (2 * np.abs(2 * (freq * t_adj % 1) - 1) - 1)
        elif signal_type == 'Sägezahn':
            signal = amp * (2 * (freq * t_adj % 1) - 1)
        elif signal_type == 'Rauschen':
            signal = amp * np.random.normal(size=1)[0]
        else:
            signal = 0

        return signal + offset + np.random.normal(0, noise * amp)

class TriggerSystem:
    def __init__(self):
        self.enabled = False
        self.channel = 0
        self.level = 0.0
        self.mode = "Steigend"  # Steigend, Fallend, Beides
        self.triggered = False
        self.holdoff = 0.0
        self.last_trigger_time = 0
        self.pre_trigger_buffer = None
        
    def check_trigger(self, buffer, current_time):
        if not self.enabled or len(buffer) < 2:
            return True
            
        if current_time - self.last_trigger_time < self.holdoff:
            return False
            
        if self.mode == "Steigend":
            for i in range(1, len(buffer)):
                if buffer[i-1] < self.level and buffer[i] >= self.level:
                    self.last_trigger_time = current_time
                    self.triggered = True
                    return True
        elif self.mode == "Fallend":
            for i in range(1, len(buffer)):
                if buffer[i-1] > self.level and buffer[i] <= self.level:
                    self.last_trigger_time = current_time
                    self.triggered = True
                    return True
        elif self.mode == "Beides":
            for i in range(1, len(buffer)):
                if (buffer[i-1] < self.level and buffer[i] >= self.level) or \
                   (buffer[i-1] > self.level and buffer[i] <= self.level):
                    self.last_trigger_time = current_time
                    self.triggered = True
                    return True
                    
        return False

class Cursor:
    def __init__(self, ax, orientation='vertical'):
        self.ax = ax
        self.orientation = orientation
        self.position = 0
        self.enabled = False
        self.color = 'yellow' if orientation == 'vertical' else 'orange'
        self.line = None
        self.create_line()
        
    def create_line(self):
        if self.orientation == 'vertical':
            self.line, = self.ax.plot([self.position, self.position], [-10, 10], 
                                     color=self.color, linestyle='--', alpha=0.7)
        else:
            self.line, = self.ax.plot([-1000, 1000], [self.position, self.position], 
                                     color=self.color, linestyle='--', alpha=0.7)
        self.line.set_visible(self.enabled)
        
    def update_position(self, position):
        self.position = position
        if self.orientation == 'vertical':
            self.line.set_xdata([position, position])
        else:
            self.line.set_ydata([position, position])
            
    def toggle(self):
        self.enabled = not self.enabled
        self.line.set_visible(self.enabled)

class MeasurementSystem:
    def __init__(self, channels):
        self.channels = channels
        self.selected_channel = 0
        self.available_measurements = [
            "Frequenz", "Periode", "Spitze-Spitze", "Mittelwert", 
            "RMS", "Min", "Max", "Anstiegszeit", "Fallzeit"
        ]
        self.active_measurements = []
        
    def calculate(self, data, sample_rate):
        results = {}
        if not data or len(data) < 2:
            return results
            
        # Grundlegende Messungen
        results["Min"] = np.min(data)
        results["Max"] = np.max(data)
        results["Spitze-Spitze"] = results["Max"] - results["Min"]
        results["Mittelwert"] = np.mean(data)
        results["RMS"] = np.sqrt(np.mean(np.array(data)**2))
        
        # Frequenz und Periode berechnen (durch Nulldurchgänge)
        zero_crossings = np.where(np.diff(np.signbit(np.array(data) - np.mean(data))))[0]
        if len(zero_crossings) > 1:
            avg_period_samples = np.mean(np.diff(zero_crossings)) * 2  # Vollständige Periode
            results["Periode"] = avg_period_samples / sample_rate
            results["Frequenz"] = 1.0 / results["Periode"] if results["Periode"] > 0 else 0
        else:
            results["Periode"] = 0
            results["Frequenz"] = 0
            
        # Anstiegs- und Fallzeit (10% bis 90%)
        if results["Spitze-Spitze"] > 0:
            low_threshold = results["Min"] + 0.1 * results["Spitze-Spitze"]
            high_threshold = results["Min"] + 0.9 * results["Spitze-Spitze"]
            
            # Vereinfachte Berechnung
            data_arr = np.array(data)
            rising_edges = []
            falling_edges = []
            
            for i in range(1, len(data_arr)):
                if data_arr[i-1] < low_threshold and data_arr[i] > low_threshold:
                    rising_edges.append(i)
                if data_arr[i-1] < high_threshold and data_arr[i] > high_threshold:
                    for j in range(len(rising_edges)):
                        if rising_edges[j] > 0:
                            results["Anstiegszeit"] = (i - rising_edges[j]) / sample_rate
                            rising_edges[j] = -1  # Markieren als verwendet
                            break
                            
                if data_arr[i-1] > high_threshold and data_arr[i] < high_threshold:
                    falling_edges.append(i)
                if data_arr[i-1] > low_threshold and data_arr[i] < low_threshold:
                    for j in range(len(falling_edges)):
                        if falling_edges[j] > 0:
                            results["Fallzeit"] = (i - falling_edges[j]) / sample_rate
                            falling_edges[j] = -1  # Markieren als verwendet
                            break
        
        if "Anstiegszeit" not in results:
            results["Anstiegszeit"] = 0
        if "Fallzeit" not in results:
            results["Fallzeit"] = 0
            
        return results

class OscilloscopeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Erweitertes Oszilloskop")
        self.root.geometry("1280x720")
        self.root.configure(bg='#f0f0f0')
        
        # Style konfigurieren - hier ändern wir nur die Kontrollpanel-Farben
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background='#f0f0f0', foreground='black')
        self.style.configure('TButton', background='#e0e0e0', foreground='black')
        self.style.configure('TCheckbutton', background='#f0f0f0', foreground='black')
        self.style.configure('TLabel', background='#f0f0f0', foreground='black')
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabelframe', background='#f0f0f0', foreground='black')
        self.style.configure('TLabelframe.Label', background='#f0f0f0', foreground='black')
        self.style.configure('TScale', background='#f0f0f0', troughcolor='#d0d0d0')
        
        self.sample_rate = 5000  # Hz
        self.channels = []
        self.running = True
        self.paused = False
        self.generator = SignalGenerator(self.sample_rate)
        self.timebase = 0.002  # seconds/division
        self.divisions = 10
        self.buffer_size = 5000
        self.display_size = 1000  # Anzahl der Punkte auf dem Display
        
        # Zoom und Navigation
        self.zoom_level = 1.0
        self.x_offset = 0.0
        self.y_scale = 1.0
        
        # Trigger-System
        self.trigger = TriggerSystem()
        
        # Cursor-System
        self.cursors = []
        
        # Messungen
        self.show_measurements = False
        
        self.init_ui()
        self.init_plot()
        self.start_data_thread()
        self.start_animation()

    def init_ui(self):
        # Main container
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)
        
        # Linke Seite (Kontrollpanel)
        left_frame = ttk.Frame(main_paned)
        
        # Rechte Seite (Plot + Messungen)
        right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(left_frame, weight=1)
        main_paned.add(right_paned, weight=3)
        
        # Oberer Teil (Plot)
        self.plot_frame = ttk.Frame(right_paned)
        
        # Unterer Teil (Messungen)
        self.measurement_frame = ttk.LabelFrame(right_paned, text="Messungen")
        right_paned.add(self.plot_frame, weight=3)
        right_paned.add(self.measurement_frame, weight=1)
        
        # Erstellen des ScrollCanvas für die Kontrollpanel-Elemente
        self.control_canvas = tk.Canvas(left_frame, bg='#212121', highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.control_canvas.yview)
        scrollable_frame = ttk.Frame(self.control_canvas)
        scrollable_frame.bind("<Configure>", lambda e: self.control_canvas.configure(scrollregion=self.control_canvas.bbox("all")))
        self.control_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self.control_canvas.configure(yscrollcommand=scrollbar.set)
        self.control_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Kanaleinstellungen
        for i in range(3):
            ch = {
                'enabled': tk.BooleanVar(value=(i == 0)),
                'freq': tk.DoubleVar(value=50.0),
                'amp': tk.DoubleVar(value=1.0),
                'offset': tk.DoubleVar(value=0.0),
                'noise': tk.DoubleVar(value=0.05),
                'phase': tk.DoubleVar(value=0.0),
                'type': tk.StringVar(value='Sinus'),
                'buffer': deque(maxlen=self.buffer_size),
                'display_buffer': deque(maxlen=self.display_size),
                'color': ['cyan', 'magenta', 'lime'][i]
            }
            self.channels.append(ch)

            ch_frame = ttk.LabelFrame(scrollable_frame, text=f"Kanal {i+1}")
            ch_frame.pack(fill=tk.X, padx=5, pady=5)

            ttk.Checkbutton(ch_frame, text="Aktiv", variable=ch['enabled']).pack(anchor='w')
            ttk.Label(ch_frame, text=f"Frequenz (Hz): {ch['freq'].get():.1f}").pack(anchor='w')
            freq_scale = ttk.Scale(ch_frame, from_=1, to=1000, variable=ch['freq'])
            freq_scale.pack(fill=tk.X)
            freq_scale.bind("<Motion>", lambda e, lbl=ch_frame.winfo_children()[2], var=ch['freq']: 
                           lbl.config(text=f"Frequenz (Hz): {var.get():.1f}"))
            
            ttk.Label(ch_frame, text=f"Amplitude (V): {ch['amp'].get():.2f}").pack(anchor='w')
            amp_scale = ttk.Scale(ch_frame, from_=0.1, to=5, variable=ch['amp'])
            amp_scale.pack(fill=tk.X)
            amp_scale.bind("<Motion>", lambda e, lbl=ch_frame.winfo_children()[4], var=ch['amp']: 
                          lbl.config(text=f"Amplitude (V): {var.get():.2f}"))
            
            ttk.Label(ch_frame, text=f"Offset (V): {ch['offset'].get():.2f}").pack(anchor='w')
            offset_scale = ttk.Scale(ch_frame, from_=-5, to=5, variable=ch['offset'])
            offset_scale.pack(fill=tk.X)
            offset_scale.bind("<Motion>", lambda e, lbl=ch_frame.winfo_children()[6], var=ch['offset']: 
                             lbl.config(text=f"Offset (V): {var.get():.2f}"))
            
            ttk.Label(ch_frame, text=f"Rauschen: {ch['noise'].get():.2f}").pack(anchor='w')
            noise_scale = ttk.Scale(ch_frame, from_=0, to=1, variable=ch['noise'])
            noise_scale.pack(fill=tk.X)
            noise_scale.bind("<Motion>", lambda e, lbl=ch_frame.winfo_children()[8], var=ch['noise']: 
                            lbl.config(text=f"Rauschen: {var.get():.2f}"))
            
            ttk.Label(ch_frame, text=f"Phase (Grad): {ch['phase'].get():.1f}").pack(anchor='w')
            phase_scale = ttk.Scale(ch_frame, from_=0, to=360, variable=ch['phase'])
            phase_scale.pack(fill=tk.X)
            phase_scale.bind("<Motion>", lambda e, lbl=ch_frame.winfo_children()[10], var=ch['phase']: 
                            lbl.config(text=f"Phase (Grad): {var.get():.1f}"))
            
            ttk.Label(ch_frame, text="Signaltyp").pack(anchor='w')
            signaltype_combo = ttk.Combobox(ch_frame, values=['Sinus', 'Rechteck', 'Dreieck', 'Sägezahn', 'Rauschen'], 
                                         textvariable=ch['type'])
            signaltype_combo.pack(fill=tk.X)
            
        # Zeitbasis-Frame
        timebase_frame = ttk.LabelFrame(scrollable_frame, text="Zeitbasis")
        timebase_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.timebase_label = ttk.Label(timebase_frame, text=f"Zeit/Division: {self.timebase*1000:.2f} ms")
        self.timebase_label.pack(anchor='w')
        timebase_scale = ttk.Scale(timebase_frame, from_=0.1, to=100, command=self.update_timebase)
        timebase_scale.set(self.timebase * 1000)  # In Millisekunden umrechnen
        timebase_scale.pack(fill=tk.X)
        
        # Trigger-Frame
        trigger_frame = ttk.LabelFrame(scrollable_frame, text="Trigger")
        trigger_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.trigger_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(trigger_frame, text="Trigger aktivieren", variable=self.trigger_enabled, 
                      command=self.update_trigger).pack(anchor='w')
        
        ttk.Label(trigger_frame, text="Trigger-Kanal").pack(anchor='w')
        self.trigger_channel = tk.IntVar(value=0)
        for i in range(3):
            ttk.Radiobutton(trigger_frame, text=f"Kanal {i+1}", variable=self.trigger_channel, 
                          value=i, command=self.update_trigger).pack(anchor='w', padx=15)
        
        ttk.Label(trigger_frame, text="Trigger-Level (V)").pack(anchor='w')
        self.trigger_level = tk.DoubleVar(value=0.0)
        trigger_level_scale = ttk.Scale(trigger_frame, from_=-5, to=5, variable=self.trigger_level, 
                                      command=lambda x: self.update_trigger())
        trigger_level_scale.pack(fill=tk.X)
        
        ttk.Label(trigger_frame, text="Trigger-Modus").pack(anchor='w')
        self.trigger_mode = tk.StringVar(value="Steigend")
        ttk.Radiobutton(trigger_frame, text="Steigend", variable=self.trigger_mode, 
                      value="Steigend", command=self.update_trigger).pack(anchor='w', padx=15)
        ttk.Radiobutton(trigger_frame, text="Fallend", variable=self.trigger_mode, 
                      value="Fallend", command=self.update_trigger).pack(anchor='w', padx=15)
        ttk.Radiobutton(trigger_frame, text="Beides", variable=self.trigger_mode, 
                      value="Beides", command=self.update_trigger).pack(anchor='w', padx=15)
        
        ttk.Label(trigger_frame, text="Holdoff (ms)").pack(anchor='w')
        self.trigger_holdoff = tk.DoubleVar(value=0.0)
        trigger_holdoff_scale = ttk.Scale(trigger_frame, from_=0, to=500, variable=self.trigger_holdoff, 
                                        command=lambda x: self.update_trigger())
        trigger_holdoff_scale.pack(fill=tk.X)
        
        # Cursor-Frame
        cursor_frame = ttk.LabelFrame(scrollable_frame, text="Cursor")
        cursor_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.cursor_x1_enabled = tk.BooleanVar(value=False)
        self.cursor_x2_enabled = tk.BooleanVar(value=False)
        self.cursor_y1_enabled = tk.BooleanVar(value=False)
        self.cursor_y2_enabled = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(cursor_frame, text="X-Cursor 1", variable=self.cursor_x1_enabled, 
                      command=lambda: self.toggle_cursor(0)).pack(anchor='w')
        ttk.Checkbutton(cursor_frame, text="X-Cursor 2", variable=self.cursor_x2_enabled, 
                      command=lambda: self.toggle_cursor(1)).pack(anchor='w')
        ttk.Checkbutton(cursor_frame, text="Y-Cursor 1", variable=self.cursor_y1_enabled, 
                      command=lambda: self.toggle_cursor(2)).pack(anchor='w')
        ttk.Checkbutton(cursor_frame, text="Y-Cursor 2", variable=self.cursor_y2_enabled, 
                      command=lambda: self.toggle_cursor(3)).pack(anchor='w')
        
        # Messung-Frame
        measurement_control_frame = ttk.LabelFrame(scrollable_frame, text="Messungen")
        measurement_control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.measurement_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(measurement_control_frame, text="Messungen anzeigen", 
                      variable=self.measurement_enabled,
                      command=self.toggle_measurements).pack(anchor='w')
        
        self.measurement_channel = tk.IntVar(value=0)
        for i in range(3):
            ttk.Radiobutton(measurement_control_frame, text=f"Kanal {i+1}", 
                          variable=self.measurement_channel, value=i).pack(anchor='w', padx=15)
        
        # Button-Frame
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        ttk.Button(button_frame, text="Start/Pause", command=self.toggle_pause).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Screenshot", command=self.save_screenshot).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Daten speichern", command=self.save_data).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Daten laden", command=self.load_data).pack(side="left", padx=5)
        
        # Messungs-Panel initialisieren
        self.measurement_system = MeasurementSystem(self.channels)
        self.init_measurement_panel()

    def init_measurement_panel(self):
        # Messungs-GUI erstellen
        self.measurement_results_frame = ttk.Frame(self.measurement_frame)
        self.measurement_results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.measurement_labels = {}
        measurements = self.measurement_system.available_measurements
        
        # Messungen in Spalten aufteilen
        col_count = min(3, len(measurements))
        row_count = (len(measurements) + col_count - 1) // col_count
        
        for i, measurement in enumerate(measurements):
            row = i // col_count
            col = i % col_count
            
            measurement_frame = ttk.LabelFrame(self.measurement_results_frame, text=measurement)
            measurement_frame.grid(row=row, column=col, padx=5, pady=5, sticky="ew")
            
            value_label = ttk.Label(measurement_frame, text="---")
            value_label.pack(padx=5, pady=2)
            
            self.measurement_labels[measurement] = value_label
            
        # Gewichtung der Spalten anpassen
        for col in range(col_count):
            self.measurement_results_frame.columnconfigure(col, weight=1)

    def init_plot(self):
        self.fig, self.ax = plt.subplots(figsize=(10, 6), facecolor='#222222')
        self.ax.set_facecolor('#111111')
        self.ax.set_title("Oszilloskop", color='white', fontsize=14)
        self.ax.set_xlabel("Zeit (ms)", color='white')
        self.ax.set_ylabel("Spannung (V)", color='white')
        self.ax.tick_params(colors='white')
        self.ax.grid(True, color='#444444', linestyle='--', linewidth=0.5)
        
        # Grid für 10 Divisionen erstellen
        self.ax.set_xticks(np.linspace(-self.divisions/2, self.divisions/2, self.divisions+1))
        self.ax.set_yticks(np.linspace(-5, 5, 11))
        
        self.lines = []
        for ch in self.channels:
            line, = self.ax.plot([], [], color=ch['color'], lw=1.5)
            self.lines.append(line)
        
        # Cursor erstellen
        self.cursors = [
            Cursor(self.ax, orientation='vertical'),   # X1
            Cursor(self.ax, orientation='vertical'),   # X2
            Cursor(self.ax, orientation='horizontal'), # Y1
            Cursor(self.ax, orientation='horizontal')  # Y2
        ]
        
        # Cursor-Info-Text
        self.cursor_info = self.ax.text(0.02, 0.02, "", transform=self.ax.transAxes, 
                                      color='white', fontsize=9, backgroundcolor='black')
        
        # Trigger-Level-Linie
        self.trigger_line, = self.ax.plot([-100, 100], [0, 0], 'r--', lw=1, alpha=0.7)
        self.trigger_line.set_visible(False)
        
        # Matplotlib-Toolbar für Zoom, Pan, etc.
        self.toolbar_frame = ttk.Frame(self.plot_frame)
        self.toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.toolbar_frame)
        self.toolbar.update()
        
        # Mausevents verbinden
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.canvas.mpl_connect('button_press_event', self.on_mouse_click)
        self.canvas.mpl_connect('key_press_event', self.on_key_press)
        
        # Status-Zeile
        self.status_frame = ttk.Frame(self.plot_frame)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.coords_label = ttk.Label(self.status_frame, text="X: --- ms, Y: --- V")
        self.coords_label.pack(side=tk.LEFT, padx=10)
        
        self.trigger_status_label = ttk.Label(self.status_frame, text="Trigger: Inaktiv")
        self.trigger_status_label.pack(side=tk.RIGHT, padx=10)

    def update_timebase(self, value):
        # Wert in Millisekunden wird in Sekunden umgewandelt
        self.timebase = float(value) / 1000.0
        self.timebase_label.config(text=f"Zeit/Division: {float(value):.2f} ms")
        
    def update_trigger(self):
        self.trigger.enabled = self.trigger_enabled.get()
        self.trigger.channel = self.trigger_channel.get()
        self.trigger.level = self.trigger_level.get()
        self.trigger.mode = self.trigger_mode.get()
        self.trigger.holdoff = self.trigger_holdoff.get() / 1000.0  # ms zu s
        
        self.trigger_line.set_ydata([self.trigger.level, self.trigger.level])
        self.trigger_line.set_visible(self.trigger.enabled)
        
        if self.trigger.enabled:
            self.trigger_status_label.config(text=f"Trigger: Aktiv ({self.trigger.mode})")
        else:
            self.trigger_status_label.config(text="Trigger: Inaktiv")
            
    def toggle_cursor(self, cursor_idx):
        if cursor_idx == 0:
            self.cursors[0].toggle()
        elif cursor_idx == 1:
            self.cursors[1].toggle()
        elif cursor_idx == 2:
            self.cursors[2].toggle()
        elif cursor_idx == 3:
            self.cursors[3].toggle()
        
        self.update_cursor_info()
            
    def update_cursor_info(self):
        info_text = ""
        
        # X-Cursor-Differenz
        if self.cursors[0].enabled and self.cursors[1].enabled:
            time_diff = abs(self.cursors[1].position - self.cursors[0].position)
            freq = 1000.0 / time_diff if time_diff > 0 else 0
            info_text += f"ΔX: {time_diff:.2f} ms ({freq:.1f} Hz)\n"
            
        # Y-Cursor-Differenz
        if self.cursors[2].enabled and self.cursors[3].enabled:
            volt_diff = abs(self.cursors[3].position - self.cursors[2].position)
            info_text += f"ΔY: {volt_diff:.2f} V\n"
            
        # Cursor-Positionen
        for i, cursor in enumerate(self.cursors):
            if cursor.enabled:
                prefix = "X" if cursor.orientation == 'vertical' else "Y"
                suffix = " ms" if cursor.orientation == 'vertical' else " V"
                info_text += f"{prefix}{i%2+1}: {cursor.position:.2f}{suffix}\n"
                
        self.cursor_info.set_text(info_text)
            
    def toggle_measurements(self):
        self.show_measurements = self.measurement_enabled.get()
        
    def update_measurements(self):
        if not self.show_measurements:
            return
            
        selected_channel = self.measurement_channel.get()
        if not self.channels[selected_channel]['enabled'].get() or len(self.channels[selected_channel]['display_buffer']) < 2:
            # Reset measurement displays if channel is disabled or has insufficient data
            for key in self.measurement_labels:
                self.measurement_labels[key].config(text="---")
            return
            
        # Calculate measurements
        data = list(self.channels[selected_channel]['display_buffer'])
        results = self.measurement_system.calculate(data, self.sample_rate)
        
        # Update labels
        for measurement, value in results.items():
            if measurement in self.measurement_labels:
                if measurement == "Frequenz":
                    self.measurement_labels[measurement].config(text=f"{value:.2f} Hz")
                elif measurement == "Periode":
                    self.measurement_labels[measurement].config(text=f"{value*1000:.2f} ms")
                elif measurement in ["Anstiegszeit", "Fallzeit"]:
                    self.measurement_labels[measurement].config(text=f"{value*1000:.2f} ms")
                else:
                    self.measurement_labels[measurement].config(text=f"{value:.3f} V")

    def on_mouse_move(self, event):
        if event.inaxes:
            # Update coordinates display
            x_coord = event.xdata
            y_coord = event.ydata
            self.coords_label.config(text=f"X: {x_coord:.2f} ms, Y: {y_coord:.2f} V")
            
            # Update any active cursor being dragged
            if hasattr(self, 'dragging_cursor') and self.dragging_cursor is not None:
                self.cursors[self.dragging_cursor].update_position(
                    x_coord if self.cursors[self.dragging_cursor].orientation == 'vertical' else y_coord
                )
                self.update_cursor_info()
                self.canvas.draw_idle()

    def on_mouse_click(self, event):
        if event.inaxes and event.button == 1:  # Left click
            x, y = event.xdata, event.ydata
            
            # Check if a cursor is being clicked
            for i, cursor in enumerate(self.cursors):
                if cursor.enabled:
                    if cursor.orientation == 'vertical':
                        if abs(x - cursor.position) < 0.02 * self.divisions:
                            self.dragging_cursor = i
                            return
                    else:  # horizontal
                        if abs(y - cursor.position) < 0.1:
                            self.dragging_cursor = i
                            return
                            
            # If not clicking on a cursor, set the dragging_cursor to None
            self.dragging_cursor = None

    def on_key_press(self, event):
        # Keyboard controls for cursors and other functions
        if event.key == 'escape':
            self.dragging_cursor = None
        elif event.key == ' ':  # Space key
            self.toggle_pause()
        elif event.key == 't':
            # Toggle trigger
            self.trigger_enabled.set(not self.trigger_enabled.get())
            self.update_trigger()
        
    def toggle_pause(self):
        self.paused = not self.paused
        
    def start_data_thread(self):
        # Create a thread for data generation
        self.data_thread = threading.Thread(target=self.generate_data, daemon=True)
        self.data_thread.start()
        
    def generate_data(self):
        t = 0.0
        dt = 1.0 / self.sample_rate
        
        while self.running:
            if not self.paused:
                # Generate data for each channel
                current_time = time.time()
                
                for i, ch in enumerate(self.channels):
                    if ch['enabled'].get():
                        # Generate a sample
                        value = self.generator.generate(
                            ch['type'].get(), 
                            ch['freq'].get(), 
                            ch['amp'].get(), 
                            ch['offset'].get(),
                            ch['noise'].get(),
                            ch['phase'].get(),
                            t
                        )
                        ch['buffer'].append(value)
                
                # Check trigger condition
                trigger_ch = self.channels[self.trigger.channel]
                if (not self.trigger.enabled) or (len(trigger_ch['buffer']) >= 2 and 
                    self.trigger.check_trigger(list(trigger_ch['buffer'])[-2:], current_time)):
                    # If triggered or no trigger, update display buffers
                    for ch in self.channels:
                        if len(ch['buffer']) > 0:
                            # Convert buffer to display buffer based on timebase
                            display_points = min(len(ch['buffer']), self.display_size)
                            ch['display_buffer'] = deque(list(ch['buffer'])[-display_points:], maxlen=self.display_size)
                
                t += dt
            time.sleep(dt)
            
    def start_animation(self):
        self.anim_running = True
        self.update_plot()
        
    def update_plot(self):
        if not self.anim_running:
            return
            
        # Calculate x-axis (time) values based on timebase
        time_per_sample = 1.0 / self.sample_rate
        
        for i, ch in enumerate(self.channels):
            if ch['enabled'].get():
                y_data = list(ch['display_buffer'])
                if len(y_data) > 0:
                    x_data = [(j - len(y_data)/2) * time_per_sample * 1000 for j in range(len(y_data))]
                    self.lines[i].set_data(x_data, y_data)
                    
        # Set axis limits based on timebase
        half_width = self.divisions * self.timebase * 1000 / 2  # half width in ms
        self.ax.set_xlim(-half_width, half_width)
        self.ax.set_ylim(-5, 5)  # Fixed vertical range
        
        # Update measurements
        self.update_measurements()
        
        self.canvas.draw_idle()
        self.root.after(33, self.update_plot)  # ~30 fps
        
    def save_screenshot(self):
        filetypes = [('PNG Image', '*.png'), ('All Files', '*.*')]
        filename = filedialog.asksaveasfilename(defaultextension=".png", filetypes=filetypes)
        if filename:
            self.fig.savefig(filename, facecolor=self.fig.get_facecolor())
            messagebox.showinfo("Screenshot gespeichert", f"Screenshot wurde gespeichert als: {filename}")
            
    def save_data(self):
        filetypes = [('JSON Files', '*.json'), ('All Files', '*.*')]
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=filetypes)
        if filename:
            data = {
                'timestamp': datetime.datetime.now().isoformat(),
                'timebase': self.timebase,
                'sample_rate': self.sample_rate,
                'channels': []
            }
            
            for i, ch in enumerate(self.channels):
                if ch['enabled'].get():
                    channel_data = {
                        'channel': i+1,
                        'type': ch['type'].get(),
                        'freq': ch['freq'].get(),
                        'amp': ch['amp'].get(),
                        'offset': ch['offset'].get(),
                        'noise': ch['noise'].get(),
                        'phase': ch['phase'].get(),
                        'samples': list(ch['display_buffer'])
                    }
                    data['channels'].append(channel_data)
                    
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
                
            messagebox.showinfo("Daten gespeichert", f"Daten wurden gespeichert als: {filename}")
            
    def load_data(self):
        filetypes = [('JSON Files', '*.json'), ('All Files', '*.*')]
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    
                # Set timebase
                if 'timebase' in data:
                    self.timebase = data['timebase']
                    self.timebase_label.config(text=f"Zeit/Division: {self.timebase*1000:.2f} ms")
                
                # Load channel data
                for ch_data in data['channels']:
                    ch_idx = ch_data['channel'] - 1
                    if 0 <= ch_idx < len(self.channels):
                        ch = self.channels[ch_idx]
                        ch['enabled'].set(True)
                        ch['type'].set(ch_data['type'])
                        ch['freq'].set(ch_data['freq'])
                        ch['amp'].set(ch_data['amp'])
                        ch['offset'].set(ch_data['offset'])
                        ch['noise'].set(ch_data['noise'])
                        ch['phase'].set(ch_data['phase'])
                        
                        # Load samples
                        if 'samples' in ch_data:
                            ch['display_buffer'] = deque(ch_data['samples'], maxlen=self.display_size)
                            ch['buffer'] = deque(ch_data['samples'], maxlen=self.buffer_size)
                
                messagebox.showinfo("Daten geladen", f"Daten wurden geladen aus: {filename}")
            except Exception as e:
                messagebox.showerror("Fehler beim Laden", f"Fehler beim Laden der Daten: {str(e)}")
    
    def __del__(self):
        self.running = False
        self.anim_running = False
        if hasattr(self, 'data_thread') and self.data_thread.is_alive():
            self.data_thread.join(timeout=1.0)

# Main application
if __name__ == "__main__":
    root = tk.Tk()
    app = OscilloscopeApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, 'running', False), 
                                             setattr(app, 'anim_running', False), 
                                             root.destroy()))
    root.mainloop()