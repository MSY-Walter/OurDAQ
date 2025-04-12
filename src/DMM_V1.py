import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
import math
import matplotlib.patches as patches
from matplotlib.widgets import Button, RadioButtons
from matplotlib.animation import FuncAnimation
from datetime import datetime
import pandas as pd
import os


class DataGenerator:
    def __init__(self):
        self.zeit = 0
        self.base_spannung = 5.0
        self.base_strom = 0.5

    def generiere_messdaten(self):
        self.zeit += 1
        spannung = self.base_spannung + 0.5 * np.sin(self.zeit / 10) + np.random.normal(0, 0.1)
        strom = self.base_strom + 0.1 * np.sin(self.zeit / 8 + 1) + np.random.normal(0, 0.05)
        spannung = max(0, min(10, spannung))
        strom = max(0, min(1.0, strom))
        return {'zeit': self.zeit, 'spannung': spannung, 'strom': strom}

class MultimeterApp:
    def __init__(self):
        self.spannungsbereiche = {'0-10V': 10, '0-50V': 50, '0-100V': 100, '0-500V': 500}
        self.strombereiche = {'0-1mA': 1, '0-10mA': 10, '0-100mA': 100, '0-500mA': 500}
        self.aktiver_modus = 'Spannung'
        self.aktueller_spannungsbereich = '0-10V'
        self.aktueller_strombereich = '0-1mA'
        self.generator = DataGenerator()

        self.zeit = []
        self.spannungswerte = []
        self.stromwerte = []
        self.graph_visible = False
        self.graph_paused = False
        self.battery_level = 1.0

        self.fig = plt.figure(figsize=(10, 6))
        self.fig.set_facecolor('#f5f5f5')
        self.fig.canvas.manager.set_window_title('Analoges Multimeter')

        self.ax_meter = plt.subplot2grid((4, 4), (0, 0), colspan=2, rowspan=3)
        self.ax_graph = plt.subplot2grid((4, 4), (0, 2), colspan=2, rowspan=3)
        self.ax_controls = plt.subplot2grid((4, 4), (3, 0), colspan=4)

        self.ax_modus = plt.axes([0.05, 0.05, 0.15, 0.05])
        self.ax_toggle_graph = plt.axes([0.25, 0.05, 0.2, 0.05])
        self.ax_export = plt.axes([0.5, 0.05, 0.2, 0.05])

        self.ax_dropdown_spannung = plt.axes([0.05, 0.15, 0.15, 0.12])
        self.ax_dropdown_strom = plt.axes([0.05, 0.15, 0.15, 0.12])

        self.modus_button = Button(self.ax_modus, 'Modus wechseln')
        self.modus_button.on_clicked(self.modus_wechseln)

        self.toggle_graph_button = Button(self.ax_toggle_graph, 'Graph anzeigen')
        self.toggle_graph_button.on_clicked(self.toggle_graph)

        self.export_button = Button(self.ax_export, 'Exportieren')
        self.export_button.on_clicked(self.exportieren)

        self.spannung_radio = RadioButtons(self.ax_dropdown_spannung, list(self.spannungsbereiche.keys()))
        self.spannung_radio.on_clicked(self.spannungsbereich_ändern)

        self.strom_radio = RadioButtons(self.ax_dropdown_strom, list(self.strombereiche.keys()))
        self.strom_radio.on_clicked(self.strombereich_ändern)
        self.ax_dropdown_strom.set_visible(False)

        self.setup_controls()
        self.animation = FuncAnimation(self.fig, self.update, interval=1000, blit=False)
        plt.tight_layout(rect=[0, 0.12, 1, 0.95])
        plt.show()

    def setup_controls(self):
        self.ax_controls.clear()
        self.ax_controls.set_facecolor('#eeeeee')
        self.ax_controls.axis('off')
        self.battery_rect = patches.Rectangle((0.9, 0.3), 0.08, 0.4, linewidth=1, edgecolor='black', facecolor='white')
        self.ax_controls.add_patch(self.battery_rect)
        self.battery_fill = patches.Rectangle((0.91, 0.32), 0.06, 0.36, facecolor='#4CAF50')
        self.ax_controls.add_patch(self.battery_fill)
        self.battery_text = self.ax_controls.text(0.93, 0.5, '100%', ha='center', va='center', fontsize=10)

    def update_battery(self):
        self.battery_level = max(0, 1 - (self.generator.zeit % 300) / 500)
        color = '#4CAF50' if self.battery_level > 0.3 else ('#FFC107' if self.battery_level > 0.1 else '#F44336')
        self.battery_fill.set_width(0.06 * self.battery_level)
        self.battery_fill.set_facecolor(color)
        self.battery_text.set_text(f"{int(self.battery_level * 100)}%")
        self.battery_text.set_color('red' if self.battery_level < 0.15 else 'black')

    def modus_wechseln(self, event):
        self.aktiver_modus = 'Strom' if self.aktiver_modus == 'Spannung' else 'Spannung'
        self.ax_dropdown_spannung.set_visible(self.aktiver_modus == 'Spannung')
        self.ax_dropdown_strom.set_visible(self.aktiver_modus == 'Strom')
        self.fig.canvas.draw_idle()

    def toggle_graph(self, event):
        if not self.graph_visible:
            self.graph_visible = True
            self.graph_paused = False
            self.toggle_graph_button.label.set_text("Graph pausieren")
        else:
            self.graph_paused = not self.graph_paused
            self.toggle_graph_button.label.set_text("Graph fortsetzen" if self.graph_paused else "Graph pausieren")
        self.ax_graph.set_visible(True)
        self.fig.canvas.draw_idle()

    def spannungsbereich_ändern(self, label):
        self.aktueller_spannungsbereich = label

    def strombereich_ändern(self, label):
        self.aktueller_strombereich = label

    def exportieren(self, event):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = "export"
        os.makedirs(export_dir, exist_ok=True)

        filename_img = os.path.join(export_dir, f"screenshot_{timestamp}.png")
        filename_xlsx = os.path.join(export_dir, f"messwerte_{timestamp}.xlsx")

        try:
            # Screenshot
            self.fig.savefig(filename_img, dpi=300, bbox_inches='tight', facecolor=self.fig.get_facecolor())
            print(f"✅ Screenshot gespeichert: {os.path.abspath(filename_img)}")

            # Excel
            df = pd.DataFrame({
                'Zeit (s)': self.zeit,
                'Spannung (V)': self.spannungswerte + [None] * (len(self.zeit) - len(self.spannungswerte)),
                'Strom (mA)': self.stromwerte + [None] * (len(self.zeit) - len(self.stromwerte))
            })
            df.to_excel(filename_xlsx, index=False)
            print(f"✅ Excel gespeichert: {os.path.abspath(filename_xlsx)}")

            self.battery_text.set_text("Export OK")
        except Exception as e:
            print(f"❌ Export-Fehler: {str(e)}")
            self.battery_text.set_text("Export FEHLER")
        finally:
            plt.pause(1.5)

    def draw_analog_meter(self, value, max_value, title, unit, color):
        self.ax_meter.clear()
        self.ax_meter.set_facecolor('white')
        self.ax_meter.text(0, 1.2, "Analoges Multimeter", ha='center', fontsize=16, fontweight='bold', color='#333')
        self.ax_meter.set_title(title.upper(), fontsize=14, fontweight='bold', color=color)

        center = (0, 0)
        radius = 1.0
        self.ax_meter.add_patch(patches.Circle(center, radius + 0.05, facecolor='#f8f8f8', edgecolor='gray', linewidth=2))

        for i in range(11):
            angle = 180 - i * 18
            rad = math.radians(angle)
            x0 = radius * math.cos(rad)
            y0 = radius * math.sin(rad)
            x1 = 0.85 * radius * math.cos(rad)
            y1 = 0.85 * radius * math.sin(rad)
            self.ax_meter.plot([x0, x1], [y0, y1], 'black')
            if i % 2 == 0:
                val = i * max_value / 10
                xt = 0.7 * radius * math.cos(rad)
                yt = 0.7 * radius * math.sin(rad)
                self.ax_meter.text(xt, yt, f"{val:.0f}", ha='center', va='center')

        percentage = min(value / max_value, 1.0)
        angle = 180 - percentage * 180
        rad = math.radians(angle)
        x_end = 0.75 * radius * math.cos(rad)
        y_end = 0.75 * radius * math.sin(rad)
        self.ax_meter.plot([0, x_end], [0, y_end], color=color, linewidth=2)
        self.ax_meter.add_patch(patches.Circle(center, 0.03, facecolor='black'))

        self.ax_meter.text(0, -0.5, f"{value:.2f} {unit}", ha='center', fontsize=14, fontweight='bold')
        self.ax_meter.text(0, -0.7, f"Messbereich: {max_value} {unit}", ha='center', fontsize=10, color='#555')

        if value > max_value:
            self.ax_meter.text(0, -0.9, "WARNUNG: ÜBERLAST!", ha='center', fontsize=12, color='red', fontweight='bold')

        self.ax_meter.set_xlim(-1.2, 1.2)
        self.ax_meter.set_ylim(-1, 1.4)
        self.ax_meter.axis('off')

    def draw_graph(self):
        if not self.graph_visible:
            return
        self.ax_graph.clear()
        if self.aktiver_modus == 'Spannung':
            werte = self.spannungswerte
            unit = 'V'
            color = 'blue'
        else:
            werte = self.stromwerte
            unit = 'mA'
            color = 'green'
        min_len = min(len(self.zeit), len(werte))
        if min_len == 0:
            return
        zeit_werte = self.zeit[-min_len:]
        werte = werte[-min_len:]
        self.ax_graph.set_title("Live-Graph")
        self.ax_graph.set_xlabel("Zeit (s)")
        self.ax_graph.set_ylabel(f"Wert ({unit})")
        self.ax_graph.grid(True)
        self.ax_graph.plot(zeit_werte, werte, color=color)

    def update(self, frame):
        daten = self.generator.generiere_messdaten()
        self.zeit.append(daten['zeit'])

        if self.aktiver_modus == 'Spannung':
            wert = daten['spannung']
            max_wert = self.spannungsbereiche[self.aktueller_spannungsbereich]
            self.spannungswerte.append(wert)
            self.draw_analog_meter(wert, max_wert, "Spannung", "V", 'blue')
        else:
            wert = daten['strom'] * 1000
            max_wert = self.strombereiche[self.aktueller_strombereich]
            self.stromwerte.append(wert)
            self.draw_analog_meter(wert, max_wert, "Strom", "mA", 'green')

        if self.graph_visible and not self.graph_paused:
            self.draw_graph()

        self.update_battery()

if __name__ == "__main__":
    MultimeterApp()
