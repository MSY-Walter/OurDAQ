import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import time
import threading
from collections import deque

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
            signal = amp * np.random.normal()
        else:
            signal = 0

        return signal + offset + np.random.normal(0, noise * amp)

class OscilloscopeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Oszilloskop - Basisversion")
        self.sample_rate = 5000  # Hz
        self.channels = []
        self.running = True
        self.paused = False
        self.generator = SignalGenerator(self.sample_rate)
        self.timebase = 0.002  # seconds/division
        self.divisions = 10
        self.buffer_size = 1000

        self.init_ui()
        self.init_plot()
        self.start_data_thread()
        self.start_animation()

    def init_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.control_canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.control_canvas.yview)
        scrollable_frame = ttk.Frame(self.control_canvas)

        scrollable_frame.bind("<Configure>", lambda e: self.control_canvas.configure(scrollregion=self.control_canvas.bbox("all")))

        self.control_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self.control_canvas.configure(yscrollcommand=scrollbar.set)

        self.control_canvas.pack(side="left", fill="y")
        scrollbar.pack(side="left", fill="y")

        self.plot_frame = ttk.Frame(main_frame)
        self.plot_frame.pack(side="left", fill=tk.BOTH, expand=True)

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
                'color': ['cyan', 'magenta', 'lime'][i]
            }
            self.channels.append(ch)

            ch_frame = ttk.LabelFrame(scrollable_frame, text=f"Kanal {i+1}")
            ch_frame.pack(fill=tk.X, padx=5, pady=5)

            ttk.Checkbutton(ch_frame, text="Aktiv", variable=ch['enabled']).pack(anchor='w')
            ttk.Label(ch_frame, text="Frequenz (Hz)").pack(anchor='w')
            ttk.Scale(ch_frame, from_=1, to=1000, variable=ch['freq']).pack(fill=tk.X)
            ttk.Label(ch_frame, text="Amplitude (V)").pack(anchor='w')
            ttk.Scale(ch_frame, from_=0.1, to=5, variable=ch['amp']).pack(fill=tk.X)
            ttk.Label(ch_frame, text="Offset (V)").pack(anchor='w')
            ttk.Scale(ch_frame, from_=-2, to=2, variable=ch['offset']).pack(fill=tk.X)
            ttk.Label(ch_frame, text="Rauschen").pack(anchor='w')
            tk.Scale(ch_frame, from_=0, to=1, resolution=0.01, variable=ch['noise'], orient=tk.HORIZONTAL).pack(fill=tk.X)
            ttk.Label(ch_frame, text="Phase (Grad)").pack(anchor='w')
            ttk.Scale(ch_frame, from_=0, to=360, variable=ch['phase']).pack(fill=tk.X)
            ttk.Label(ch_frame, text="Signaltyp").pack(anchor='w')
            ttk.Combobox(ch_frame, values=['Sinus', 'Rechteck', 'Dreieck', 'Sägezahn', 'Rauschen'], textvariable=ch['type']).pack(fill=tk.X)

        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Pause/Weiter", command=self.toggle_pause).pack(side="left", padx=5)

    def init_plot(self):
        self.fig, self.ax = plt.subplots(figsize=(8, 4), facecolor='#222222')
        self.ax.set_facecolor('#111111')
        self.ax.set_title("Live-Daten", color='white')
        self.ax.set_xlabel("Zeit (ms)", color='white')
        self.ax.set_ylabel("Spannung (V)", color='white')
        self.ax.tick_params(colors='white')
        self.ax.grid(True, color='gray', linestyle='--', linewidth=0.5)
        self.lines = []

        for ch in self.channels:
            line, = self.ax.plot([], [], color=ch['color'], lw=1.5)
            self.lines.append(line)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def toggle_pause(self):
        self.paused = not self.paused

    def start_data_thread(self):
        def data_loop():
            t = 0
            dt = 1 / self.sample_rate
            while self.running:
                if not self.paused:
                    for ch in self.channels:
                        if ch['enabled'].get():
                            value = self.generator.generate(
                                ch['type'].get(), ch['freq'].get(), ch['amp'].get(),
                                ch['offset'].get(), ch['noise'].get(), ch['phase'].get(), t
                            )
                            ch['buffer'].append(value)
                        else:
                            ch['buffer'].append(0)
                    t += dt
                time.sleep(dt)

        threading.Thread(target=data_loop, daemon=True).start()

    def start_animation(self):
        def update(frame):
            time_axis = np.linspace(-self.divisions*self.timebase/2, self.divisions*self.timebase/2, self.buffer_size) * 1000
            for i, ch in enumerate(self.channels):
                data = list(ch['buffer'])
                if data:
                    self.lines[i].set_data(time_axis[-len(data):], data)
                    self.lines[i].set_visible(ch['enabled'].get())
            self.ax.set_xlim(time_axis[0], time_axis[-1])
            self.ax.set_ylim(-5, 5)
            return self.lines

        import matplotlib.animation as animation
        self.ani = animation.FuncAnimation(self.fig, update, interval=50, blit=False)

    def stop(self):
        self.running = False

if __name__ == '__main__':
    root = tk.Tk()
    app = OscilloscopeApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop(), root.destroy()))
    root.mainloop()

