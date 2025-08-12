#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dash Web-Anwendung zur Steuerung eines Zweikanal-Labornetzteils.
- Kombiniert die Logik für positive und negative Spannungsausgänge.
- Bietet eine Web-Oberfläche zur Einstellung der Spannung und Überwachung des Stroms.
- Führt kontinuierliche Stromüberwachung und Überstromschutz im Hintergrund aus.
- Zeigt Spannungs- und Stromwerte sowie eine Live-Grafik des Stromverlaufs an.
"""

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
from collections import deque
import time
import threading
import atexit
import socket
import numpy as np

# Versuche, die Hardware-Bibliotheken zu importieren.
# Wenn dies fehlschlägt, wird ein "Dummy-Modus" aktiviert.
try:
    import spidev
    import lgpio
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    from daqhats_utils import select_hat_device, chan_list_to_mask
    HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError) as e:
    print(f"WARNUNG: Hardware-Bibliotheken nicht gefunden oder konnten nicht geladen werden: {e}")
    print("Die Anwendung wird im Dummy-Modus ohne echte Hardware-Steuerung ausgeführt.")
    HARDWARE_AVAILABLE = False

# ----------------- Globale Konfiguration -----------------
# Konstanten für beide Kanäle
CS_PIN = 22
READ_ALL_AVAILABLE = -1
MAX_DATA_POINTS = 100 # Anzahl der Punkte in der Grafik

# Konfiguration für den positiven Kanal (+)
POS_CONFIG = {
    "channel_name": "Positiv",
    "dac_control_byte": 0b0011000000000000,
    "mcc_voltage_channel": 0,
    "mcc_current_channel": 4,
    "shunt_resistance_ohm": 0.1,
    "amplifier_gain": 69.0,
    "max_current_mA": 500.0,
    "corr_a": -0.1347, # Offset-Korrektur für Strom
    "corr_b": 0.0780,  # Gain-Korrektur für Strom
    "max_voltage": 10.0,
}

# Konfiguration für den negativen Kanal (-)
NEG_CONFIG = {
    "channel_name": "Negativ",
    "dac_control_byte": 0b1011000000000000,
    "mcc_voltage_channel": 0, # Annahme: Spannung wird am selben Punkt gemessen
    "mcc_current_channel": 5,
    "shunt_resistance_ohm": 0.1,
    "amplifier_gain": 69.0,
    "max_current_mA": 500.0,
    "corr_a": -0.2793, # Offset-Korrektur für Strom
    "corr_b": 1.7828,  # Gain-Korrektur für Strom
    "max_voltage": -10.0,
}


class PowerSupplyController:
    """Klasse zur Kapselung der gesamten Hardware-Logik."""
    def __init__(self):
        self.spi = None
        self.gpio_handle = None
        self.hat = None
        self.monitoring_thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        # Kalibrier- und Statusdaten
        self.calibration_tables = {'plus': [], 'minus': []}
        self.current_values_mA = {'plus': 0.0, 'minus': 0.0}
        self.voltage_values_V = {'plus': 0.0, 'minus': 0.0}
        self.dac_values = {'plus': 0, 'minus': 0}
        self.overcurrent_flags = {'plus': False, 'minus': False}
        self.status_message = "Initialisierung..."

        if HARDWARE_AVAILABLE:
            try:
                self._init_hardware()
                self.status_message = "Hardware initialisiert. Starte Kalibrierung..."
            except Exception as e:
                self.status_message = f"Hardware-Fehler: {e}"
                print(self.status_message)
        else:
            self.status_message = "Dummy-Modus aktiv."

    def _init_hardware(self):
        # SPI
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 1000000
        self.spi.mode = 0b00
        # GPIO
        self.gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.gpio_handle, CS_PIN)
        lgpio.gpio_write(self.gpio_handle, CS_PIN, 1)
        # MCC118 HAT
        address = select_hat_device(HatIDs.MCC_118)
        self.hat = mcc118(address)

    def write_dac(self, channel_key, value):
        if not HARDWARE_AVAILABLE: return
        if not (0 <= value <= 4095):
            raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")

        config = POS_CONFIG if channel_key == 'plus' else NEG_CONFIG
        control = config["dac_control_byte"]
        data = control | (value & 0xFFF)
        high_byte = (data >> 8) & 0xFF
        low_byte = data & 0xFF

        with self.lock:
            lgpio.gpio_write(self.gpio_handle, CS_PIN, 0)
            self.spi.xfer2([high_byte, low_byte])
            lgpio.gpio_write(self.gpio_handle, CS_PIN, 1)
            self.dac_values[channel_key] = value

    def calibrate(self, channel_key):
        """Führt die Spannungskalibrierung für einen Kanal durch."""
        if not HARDWARE_AVAILABLE:
            # Dummy-Kalibrierung für den Offline-Betrieb
            self.status_message = f"Dummy-Kalibrierung für Kanal '{channel_key}'."
            print(self.status_message)
            if channel_key == 'plus':
                self.calibration_tables['plus'] = [(0.0, 0), (10.0, 4095)]
            else:
                self.calibration_tables['minus'] = [(-10.0, 4095), (0.0, 0)]
            time.sleep(0.5)
            return

        self.status_message = f"Kalibriere Kanal '{channel_key}'..."
        print(self.status_message)
        table = []
        config = POS_CONFIG if channel_key == 'plus' else NEG_CONFIG
        mcc_channel = config["mcc_voltage_channel"]

        try:
            for dac_wert in range(0, 4096, 64):
                self.write_dac(channel_key, dac_wert)
                time.sleep(0.05)
                spannung = self.hat.a_in_read(mcc_channel)
                
                is_valid = (spannung >= 0) if channel_key == 'plus' else (spannung <= 0)
                if is_valid:
                    table.append((spannung, dac_wert))
            
            # Endpunkt sicherstellen
            self.write_dac(channel_key, 4095)
            time.sleep(0.05)
            spannung = self.hat.a_in_read(mcc_channel)
            is_valid = (spannung >= 0) if channel_key == 'plus' else (spannung <= 0)
            if is_valid:
                table.append((spannung, 4095))

            self.write_dac(channel_key, 0) # Sicherer Zustand
            table.sort(key=lambda x: x[0])
            self.calibration_tables[channel_key] = table
            self.status_message = f"Kalibrierung für '{channel_key}' abgeschlossen."
            print(self.status_message)
        except HatError as e:
            self.status_message = f"Hardware-Fehler bei Kalibrierung von '{channel_key}': {e}"
            print(self.status_message)


    def set_voltage(self, channel_key, target_voltage):
        """Stellt die Spannung basierend auf Kalibrierdaten ein."""
        table = self.calibration_tables[channel_key]
        if not table:
            self.status_message = f"Fehler: Kanal '{channel_key}' nicht kalibriert."
            return

        # Randbehandlung und Validierung
        min_v, max_v = table[0][0], table[-1][0]
        if not (min_v <= target_voltage <= max_v):
             self.status_message = f"Spannung für '{channel_key}' ({target_voltage}V) außerhalb des Bereichs ({min_v:.2f}V bis {max_v:.2f}V)."
             return

        # Interpolation
        u_vals = [p[0] for p in table]
        dac_vals = [p[1] for p in table]
        dac_wert = int(round(np.interp(target_voltage, u_vals, dac_vals)))

        self.write_dac(channel_key, dac_wert)
        self.voltage_values_V[channel_key] = target_voltage
        self.overcurrent_flags[channel_key] = False # Reset flag on new set
        self.status_message = f"Spannung '{channel_key}' auf {target_voltage:.3f} V gesetzt (DAC={dac_wert})."

    def _monitoring_loop(self):
        """Hintergrund-Thread zur kontinuierlichen Überwachung."""
        if not HARDWARE_AVAILABLE:
            # Dummy-Schleife
            while not self.stop_event.is_set():
                with self.lock:
                    # Simuliere kleine Schwankungen
                    self.current_values_mA['plus'] = max(0, 50 + np.random.randn() * 2) if self.dac_values['plus'] > 0 else 0
                    self.current_values_mA['minus'] = max(0, 30 + np.random.randn() * 2) if self.dac_values['minus'] > 0 else 0
                time.sleep(0.2)
            return

        # Echte Hardware-Schleife
        scan_rate = 1000.0
        options = OptionFlags.CONTINUOUS
        channels = [POS_CONFIG['mcc_current_channel'], NEG_CONFIG['mcc_current_channel']]
        channel_mask = chan_list_to_mask(channels)
        
        try:
            self.hat.a_in_scan_start(channel_mask, 0, scan_rate, options)
            
            while not self.stop_event.is_set():
                read_result = self.hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.1)
                
                if read_result.hardware_overrun or read_result.buffer_overrun:
                    self.status_message = "WARNUNG: MCC Hardware/Buffer Overrun."
                    continue

                if len(read_result.data) > 0:
                    with self.lock:
                        # Positive channel
                        pos_v_samples = read_result.data[::2]
                        if pos_v_samples:
                            pos_v = pos_v_samples[-1]
                            pos_conf = POS_CONFIG
                            i_raw_mA = (pos_v / (pos_conf['amplifier_gain'] * pos_conf['shunt_resistance_ohm'])) * 1000.0
                            self.current_values_mA['plus'] = pos_conf['corr_a'] + pos_conf['corr_b'] * i_raw_mA

                        # Negative channel
                        neg_v_samples = read_result.data[1::2]
                        if neg_v_samples:
                            neg_v = neg_v_samples[-1]
                            neg_conf = NEG_CONFIG
                            i_raw_mA = (neg_v / (neg_conf['amplifier_gain'] * neg_conf['shunt_resistance_ohm'])) * 1000.0
                            self.current_values_mA['minus'] = neg_conf['corr_a'] + neg_conf['corr_b'] * i_raw_mA

                        # Überstromschutz prüfen
                        if self.current_values_mA['plus'] > pos_conf['max_current_mA'] and not self.overcurrent_flags['plus']:
                            self.write_dac('plus', 0)
                            self.overcurrent_flags['plus'] = True
                            self.status_message = f"ÜBERSTROM auf Kanal 'Positiv'! Netzteil deaktiviert."
                        
                        if self.current_values_mA['minus'] > neg_conf['max_current_mA'] and not self.overcurrent_flags['minus']:
                            self.write_dac('minus', 0)
                            self.overcurrent_flags['minus'] = True
                            self.status_message = f"ÜBERSTROM auf Kanal 'Negativ'! Netzteil deaktiviert."
                
                time.sleep(0.05) # Kurze Pause

        except Exception as e:
            self.status_message = f"Fehler im Monitoring: {e}"
            print(self.status_message)
        finally:
            if HARDWARE_AVAILABLE and self.hat:
                self.hat.a_in_scan_stop()

    def start_monitoring(self):
        if self.monitoring_thread is None:
            self.stop_event.clear()
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()
            self.status_message = "Stromüberwachung gestartet."
            print(self.status_message)

    def cleanup(self):
        print("Räume auf und beende Anwendung...")
        self.stop_event.set()
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=2)
        
        if HARDWARE_AVAILABLE and self.spi:
            try:
                self.write_dac('plus', 0)
                self.write_dac('minus', 0)
                self.spi.close()
                lgpio.gpiochip_close(self.gpio_handle)
                print("Hardware-Ressourcen freigegeben.")
            except Exception as e:
                print(f"Fehler beim Aufräumen: {e}")

# ----------------- Globale Instanz und App-Setup -----------------
controller = PowerSupplyController()
atexit.register(controller.cleanup)

# Starte Kalibrierung und Überwachung SEQUENZIELL
def startup_sequence():
    controller.calibrate('plus')
    controller.calibrate('minus')
    controller.status_message = "Bereit."
    controller.start_monitoring()

threading.Thread(target=startup_sequence).start()


# Daten-Deques für die Graphen
time_deque = deque(maxlen=MAX_DATA_POINTS)
current_plus_deque = deque(maxlen=MAX_DATA_POINTS)
current_minus_deque = deque(maxlen=MAX_DATA_POINTS)

# Dash App
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "Labornetzteil Steuerung"

# ----------------- Dash Layout -----------------
def create_channel_layout(channel_key, config):
    """Erzeugt das Layout für einen einzelnen Kanal."""
    return html.Div([
        html.H3(f"Kanal: {config['channel_name']}"),
        html.Div([
            dcc.Input(
                id=f'input-voltage-{channel_key}',
                type='number',
                placeholder=f"Spannung V",
                step=0.01,
                style={'width': '60%'}
            ),
            html.Button('Einstellen', id=f'button-set-voltage-{channel_key}', n_clicks=0, style={'width': '38%', 'marginLeft': '2%'}),
        ], className='row'),
        html.Div([
            html.B("Akt. Spannung: "),
            html.Span("0.000 V", id=f'display-voltage-{channel_key}')
        ], style={'marginTop': '10px'}),
        html.Div([
            html.B("Akt. Strom: "),
            html.Span("0.0 mA", id=f'display-current-{channel_key}')
        ]),
        html.Div([
            html.B("Status: "),
            html.Span("OK", id=f'display-status-{channel_key}', style={'color': 'green', 'fontWeight': 'bold'})
        ]),
    ], className='six columns', style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px'})

app.layout = html.Div([
    html.H1("Labornetzteil Steuerung"),
    html.Div(id='status-bar', style={'padding': '10px', 'backgroundColor': '#f0f0f0', 'marginBottom': '10px'}),
    
    html.Div([
        create_channel_layout('plus', POS_CONFIG),
        create_channel_layout('minus', NEG_CONFIG),
    ], className='row'),

    html.Div([
        dcc.Graph(id='live-current-graph'),
    ], style={'marginTop': '20px'}),

    dcc.Interval(
        id='interval-component',
        interval=200,  # in Millisekunden
        n_intervals=0
    )
], style={'padding': '20px'})


# ----------------- Dash Callbacks -----------------
@app.callback(
    Output('status-bar', 'children'),
    [Input('interval-component', 'n_intervals')]
)
def update_status_bar(n):
    return f"System-Status: {controller.status_message}"

def create_set_voltage_callback(channel_key):
    def set_voltage_callback(n_clicks, voltage):
        if n_clicks > 0 and voltage is not None:
            controller.set_voltage(channel_key, float(voltage))
        return dash.no_update
    return set_voltage_callback

app.callback(
    Output(f'button-set-voltage-plus', 'n_clicks_timestamp'), # Dummy output
    [Input('button-set-voltage-plus', 'n_clicks')],
    [State('input-voltage-plus', 'value')]
)(create_set_voltage_callback('plus'))

app.callback(
    Output(f'button-set-voltage-minus', 'n_clicks_timestamp'), # Dummy output
    [Input('button-set-voltage-minus', 'n_clicks')],
    [State('input-voltage-minus', 'value')]
)(create_set_voltage_callback('minus'))


@app.callback(
    [Output('live-current-graph', 'figure'),
     Output('display-voltage-plus', 'children'),
     Output('display-current-plus', 'children'),
     Output('display-status-plus', 'children'),
     Output('display-status-plus', 'style'),
     Output('display-voltage-minus', 'children'),
     Output('display-current-minus', 'children'),
     Output('display-status-minus', 'children'),
     Output('display-status-minus', 'style')],
    [Input('interval-component', 'n_intervals')]
)
def update_live_data(n):
    # Daten aus dem Controller holen
    with controller.lock:
        current_plus = controller.current_values_mA['plus']
        current_minus = controller.current_values_mA['minus']
        voltage_plus = controller.voltage_values_V['plus']
        voltage_minus = controller.voltage_values_V['minus']
        overcurrent_plus = controller.overcurrent_flags['plus']
        overcurrent_minus = controller.overcurrent_flags['minus']

    # Daten für Graphen aktualisieren
    time_deque.append(time.time())
    current_plus_deque.append(current_plus)
    current_minus_deque.append(current_minus)

    # Graph erstellen
    trace_plus = go.Scatter(
        x=list(time_deque),
        y=list(current_plus_deque),
        name='Strom (+)',
        mode='lines'
    )
    trace_minus = go.Scatter(
        x=list(time_deque),
        y=list(current_minus_deque),
        name='Strom (-)',
        mode='lines'
    )
    
    y_axis_range = [
        min(list(current_plus_deque) + list(current_minus_deque) + [-10]),
        max(list(current_plus_deque) + list(current_minus_deque) + [10, POS_CONFIG['max_current_mA'] * 1.1])
    ]

    figure = {
        'data': [trace_plus, trace_minus],
        'layout': go.Layout(
            title='Live Strommessung',
            xaxis={'title': 'Zeit'},
            yaxis={'title': 'Strom (mA)', 'range': y_axis_range},
            showlegend=True
        )
    }

    # Statusanzeigen aktualisieren
    status_plus_text = "ÜBERSTROM!" if overcurrent_plus else "OK"
    status_plus_style = {'color': 'red', 'fontWeight': 'bold'} if overcurrent_plus else {'color': 'green', 'fontWeight': 'bold'}
    
    status_minus_text = "ÜBERSTROM!" if overcurrent_minus else "OK"
    status_minus_style = {'color': 'red', 'fontWeight': 'bold'} if overcurrent_minus else {'color': 'green', 'fontWeight': 'bold'}

    # Formatierte Strings für die Anzeige
    voltage_plus_str = f"{voltage_plus:.3f} V"
    current_plus_str = f"{current_plus:.2f} mA"
    voltage_minus_str = f"{voltage_minus:.3f} V"
    current_minus_str = f"{current_minus:.2f} mA"

    return (figure, 
            voltage_plus_str, current_plus_str, status_plus_text, status_plus_style,
            voltage_minus_str, current_minus_str, status_minus_text, status_minus_style)

# ----------------- Server Start -----------------
def get_ip_address():
    """Ermittelt die lokale IP-Adresse des Hosts."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

if __name__ == '__main__':
    host_ip = get_ip_address()
    print(f"Starte Dash Server auf http://{host_ip}:8070")
    # KORREKTUR: app.run() statt app.run_server() verwenden
    app.run(host=host_ip, port=8070, debug=True)
