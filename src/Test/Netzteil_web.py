#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Steuerprogramm für Labornetzteil als Dash Web-Anwendung.

Funktionen:
- Web-Interface zur Steuerung.
- Einmalige Spannungskalibrierung per Knopfdruck.
- Einstellen der Ausgangsspannung über ein Eingabefeld.
- Echtzeit-Anzeige von Strom und Spannung in Graphen.
- Dauerhafte Stromüberwachung mit linearem Korrekturfaktor.
- Überstromschutz: Setzt den DAC bei Überschreitung auf 0.
- Möglichkeit, die Stromkorrektur-Parameter im Web-Interface anzupassen.
"""

import dash
from dash import dcc, html, Input, Output, State, no_update
import plotly.graph_objs as go
from collections import deque
import time
import atexit
import socket
import numpy as np

# --- Hardware-spezifische Importe ---
# Wenn Sie auf einem System ohne die Hardware-Bibliotheken testen,
# können die folgenden Zeilen auskommentiert bleiben.
# Die "MOCK HARDWARE" Sektion weiter unten simuliert die Funktionen.
try:
    import spidev
    import lgpio
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    from daqhats_utils import select_hat_device, chan_list_to_mask
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    print("WARNUNG: Hardware-Bibliotheken (spidev, lgpio, daqhats) nicht gefunden. Starte im Simulationsmodus.")


# ----------------- Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin für DAC
READ_ALL_AVAILABLE = -1
MAX_STROM_MA = 500.0        # Schutzschwelle in mA
GRAPH_UPDATE_INTERVAL_MS = 500 # Update-Intervall für Graphen in Millisekunden

# ----------------- Globale Variablen & Datenstrukturen -----------------
# Deques für die Speicherung der Graphendaten (zeitlich begrenzt)
MAX_DATA_POINTS = 100
time_points = deque(maxlen=MAX_DATA_POINTS)
voltage_points = deque(maxlen=MAX_DATA_POINTS)
current_points = deque(maxlen=MAX_DATA_POINTS)

# Globale Handles für Hardware (werden bei Start initialisiert)
spi = None
gpio_handle = None
hat = None

# ----------------- Hardware Initialisierung & Steuerung -----------------
if HARDWARE_AVAILABLE:
    # Echte Hardware-Initialisierung
    try:
        # SPI für DAC
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00

        # GPIO für DAC Chip Select
        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN)
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

        # MCC 118 HAT
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        # Scan für Stromüberwachung vorbereiten
        scan_channels = [4] # Strommessung auf Channel 4
        scan_channel_mask = chan_list_to_mask(scan_channels)
        scan_rate = 1000.0
        scan_options = OptionFlags.CONTINUOUS
        hat.a_in_scan_start(scan_channel_mask, 0, scan_rate, scan_options)

    except Exception as e:
        print(f"FEHLER bei der Hardware-Initialisierung: {e}")
        HARDWARE_AVAILABLE = False

else:
    # MOCK HARDWARE (Simulationsmodus)
    # Diese Objekte simulieren die Hardware, wenn die Bibliotheken nicht verfügbar sind.
    class MockSPI:
        def xfer2(self, data): pass
        def close(self): pass

    class MockLGPIO:
        def gpiochip_open(self, dev): return 1
        def gpio_claim_output(self, handle, pin): pass
        def gpio_write(self, handle, pin, level): pass
        def gpiochip_close(self, handle): pass

    class MockHAT:
        _mock_voltage = 0.0
        _mock_dac_value = 0
        def a_in_read(self, channel):
            # Simuliert eine Spannung, die vom DAC-Wert abhängt
            return self._mock_dac_value / 4095 * 10.0 + np.random.rand() * 0.01

        def a_in_scan_read(self, num_samples, timeout):
            # Simuliert eine Strommessung (als Spannungswert)
            from types import SimpleNamespace
            # Simuliert einen leichten Stromfluss, der vom eingestellten Spannungswert abhängt
            mock_shunt_voltage = (self._mock_voltage / 10.0) * 0.05 + np.random.rand() * 0.001
            return SimpleNamespace(data=[mock_shunt_voltage])
        
        def a_in_scan_stop(self): pass

    spi = MockSPI()
    lgpio_mock = MockLGPIO()
    gpio_handle = lgpio_mock.gpiochip_open(0)
    hat = MockHAT()


def write_dac(value):
    """Schreibt einen 12-Bit-Wert (0-4095) an den DAC."""
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    
    if HARDWARE_AVAILABLE:
        control = 0b0011000000000000
        data = control | (value & 0xFFF)
        high_byte = (data >> 8) & 0xFF
        low_byte  = data & 0xFF
        lgpio.gpio_write(gpio_handle, CS_PIN, 0)
        spi.xfer2([high_byte, low_byte])
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)
    else: # Simulation
        hat._mock_dac_value = value
        hat._mock_voltage = value / 4095 * 10.0
    
    # Kurze Pause, damit die Spannung sich stabilisieren kann
    time.sleep(0.01)


def cleanup():
    """Wird bei Beendigung des Skripts aufgerufen, um die Hardware sicher zurückzusetzen."""
    print("\nAufräumen und Herunterfahren...")
    try:
        if HARDWARE_AVAILABLE and hat:
            hat.a_in_scan_stop()
        write_dac(0)
        if HARDWARE_AVAILABLE:
            spi.close()
            lgpio.gpiochip_close(gpio_handle)
        print("Hardware sicher heruntergefahren.")
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")

# Registriert die cleanup-Funktion, die bei Skript-Ende ausgeführt wird
atexit.register(cleanup)


def get_ip_address():
    """Ermittelt die lokale IP-Adresse des Rechners."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ----------------- Dash App Definition -----------------
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "Labornetzteil Steuerung"

app.layout = html.Div(style={'padding': '20px'}, children=[
    # Titel
    html.H1("Labornetzteil Steuerung", style={'textAlign': 'center'}),
    
    # Store für Kalibrierdaten und Status
    dcc.Store(id='kalibrier-tabelle-store', storage_type='memory'),
    dcc.Store(id='strom-korrektur-store', storage_type='memory', data={'a': -0.1347, 'b': 0.0780}),
    dcc.Store(id='status-store', storage_type='memory', data={'output_on': False, 'overcurrent': False}),

    # Haupt-Layout in zwei Spalten
    html.Div(className='row', children=[
        # Linke Spalte: Steuerung
        html.Div(className='six columns', children=[
            html.Div(style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px'}, children=[
                html.H4("Steuerung & Kalibrierung"),
                
                # Spannungskalibrierung
                html.Button('1. Spannungskalibrierung starten', id='start-kalibrierung-button', n_clicks=0, style={'width': '100%', 'marginBottom': '10px'}),
                dcc.Loading(id="loading-kalibrierung", type="circle", children=html.Div(id='kalibrierung-status')),
                
                html.Hr(),
                
                # Spannungseinstellung
                html.Label("2. Zielsspannung (V):"),
                dcc.Input(id='spannung-input', type='number', min=0, max=10, step=0.01, value=0.0, style={'width': 'calc(100% - 20px)', 'marginBottom': '10px'}),
                html.Button('Spannung setzen & Ausgang AN', id='set-spannung-button', n_clicks=0, style={'width': '100%', 'backgroundColor': '#4CAF50', 'color': 'white'}),
                html.Button('AUSGANG AUS (Not-Aus)', id='stop-button', n_clicks=0, style={'width': '100%', 'marginTop': '10px', 'backgroundColor': '#f44336', 'color': 'white'}),
            ]),
            
            html.Div(style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginTop': '20px'}, children=[
                html.H4("Stromkorrektur anpassen"),
                html.P("I_true = a + b * I_mcc"),
                html.Div(className='row', children=[
                    html.Div(className='six columns', children=[
                        html.Label("Offset 'a' (mA):"),
                        dcc.Input(id='corr-a-input', type='number', value=-0.1347, step=0.0001, style={'width': 'calc(100% - 20px)'}),
                    ]),
                    html.Div(className='six columns', children=[
                        html.Label("Gain 'b':"),
                        dcc.Input(id='corr-b-input', type='number', value=0.0780, step=0.0001, style={'width': 'calc(100% - 20px)'}),
                    ]),
                ]),
                html.Button('Korrektur-Parameter übernehmen', id='set-korrektur-button', n_clicks=0, style={'width': '100%', 'marginTop': '10px'}),
            ]),
        ]),
        
        # Rechte Spalte: Anzeigen
        html.Div(className='six columns', children=[
            html.Div(id='status-anzeige', style={'border': '2px solid #ccc', 'padding': '15px', 'borderRadius': '5px', 'textAlign': 'center', 'marginBottom': '20px'}),
            
            dcc.Graph(id='spannung-graph'),
            dcc.Graph(id='strom-graph'),
        ]),
    ]),
    
    # Interval-Komponente für periodische Updates
    dcc.Interval(
        id='graph-update-interval',
        interval=GRAPH_UPDATE_INTERVAL_MS,
        n_intervals=0,
        disabled=True # Startet deaktiviert
    ),
])

# ----------------- Callbacks -----------------

@app.callback(
    Output('kalibrier-tabelle-store', 'data'),
    Output('kalibrierung-status', 'children'),
    Input('start-kalibrierung-button', 'n_clicks'),
    prevent_initial_call=True
)
def kalibrieren_spannung(n_clicks):
    """Führt die Spannungskalibrierung durch."""
    print("Starte Spannungskalibrierung...")
    kalibrier_tabelle = []
    sp_step = 64  # Kleinere Schritte für schnellere Kalibrierung
    settle_time = 0.05

    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert)
        time.sleep(settle_time)
        spannung = hat.a_in_read(0)
        kalibrier_tabelle.append((spannung, dac_wert))

    # Letzten Punkt (4095) sicherstellen
    write_dac(4095)
    time.sleep(settle_time)
    spannung = hat.a_in_read(0) # Read from channel 0
    kalibrier_tabelle.append((spannung, 4095))
    
    # DAC sicher zurücksetzen
    write_dac(0)
    
    # Nach Spannung sortieren
    kalibrier_tabelle.sort(key=lambda x: x[0])
    
    status_text = f"Kalibrierung abgeschlossen. {len(kalibrier_tabelle)} Punkte erfasst."
    print(status_text)
    return {'tabelle': kalibrier_tabelle}, html.P(status_text, style={'color': 'green'})


@app.callback(
    Output('graph-update-interval', 'disabled'),
    Output('status-store', 'data'),
    Input('set-spannung-button', 'n_clicks'),
    Input('stop-button', 'n_clicks'),
    State('spannung-input', 'value'),
    State('kalibrier-tabelle-store', 'data'),
    State('status-store', 'data'),
    prevent_initial_call=True
)
def steuere_ausgang(set_n_clicks, stop_n_clicks, ziel_spannung, kalibrier_data, status_data):
    """Schaltet den Ausgang AN/AUS und setzt die Spannung."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update, no_update

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'set-spannung-button':
        if not kalibrier_data or not kalibrier_data.get('tabelle'):
            print("FEHLER: Bitte zuerst die Spannung kalibrieren.")
            return no_update, no_update # Nichts tun, wenn keine Kalibrierung vorhanden ist
        
        kalibrier_tabelle = kalibrier_data['tabelle']
        
        # Lineare Interpolation
        if ziel_spannung <= kalibrier_tabelle[0][0]:
            dac_wert = kalibrier_tabelle[0][1]
        elif ziel_spannung >= kalibrier_tabelle[-1][0]:
            dac_wert = kalibrier_tabelle[-1][1]
        else:
            dac_wert = np.interp(ziel_spannung, [p[0] for p in kalibrier_tabelle], [p[1] for p in kalibrier_tabelle])

        dac_wert = int(round(dac_wert))
        write_dac(dac_wert)
        print(f"Spannung gesetzt auf {ziel_spannung:.3f} V (DAC={dac_wert})")
        
        # Status aktualisieren und Interval aktivieren
        status_data['output_on'] = True
        status_data['overcurrent'] = False
        return False, status_data

    elif button_id == 'stop-button':
        write_dac(0)
        print("Ausgang manuell deaktiviert (Not-Aus).")
        
        # Status aktualisieren und Interval deaktivieren
        status_data['output_on'] = False
        return True, status_data

    return no_update, no_update


@app.callback(
    Output('strom-korrektur-store', 'data'),
    Input('set-korrektur-button', 'n_clicks'),
    State('corr-a-input', 'value'),
    State('corr-b-input', 'value'),
    prevent_initial_call=True
)
def update_strom_korrektur(n_clicks, a, b):
    """Aktualisiert die Korrekturparameter im Store."""
    print(f"Neue Stromkorrektur-Parameter: a={a}, b={b}")
    return {'a': a, 'b': b}


@app.callback(
    Output('spannung-graph', 'figure'),
    Output('strom-graph', 'figure'),
    Output('status-anzeige', 'children'),
    Output('graph-update-interval', 'disabled', allow_duplicate=True),
    Output('status-store', 'data', allow_duplicate=True),
    Input('graph-update-interval', 'n_intervals'),
    State('strom-korrektur-store', 'data'),
    State('status-store', 'data'),
    prevent_initial_call=True
)
def update_graphs_and_status(n, korrektur_data, status_data):
    """Liest periodisch Sensordaten, aktualisiert Graphen und prüft auf Überstrom."""
    # Aktuelle Spannung lesen (Kanal 0)
    gemessene_spannung = hat.a_in_read(0) if HARDWARE_AVAILABLE else hat._mock_voltage + np.random.rand() * 0.02
    
    # Aktuellen Strom lesen (Kanal 4)
    if HARDWARE_AVAILABLE:
        read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.1)
        if not read_result.data:
            return no_update, no_update, no_update, no_update, no_update
        shunt_v = read_result.data[-1]
        # Umrechnung von Shunt-Spannung zu Strom in mA
        current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
    else: # Simulation
        read_result = hat.a_in_scan_read(0, 0)
        shunt_v = read_result.data[-1]
        current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0

    # Korrektur anwenden
    corr_a = korrektur_data['a']
    corr_b = korrektur_data['b']
    current_true_mA = corr_a + corr_b * current_mcc_mA

    # Daten für Graphen hinzufügen
    current_time = time.time()
    time_points.append(current_time)
    voltage_points.append(gemessene_spannung)
    current_points.append(current_true_mA)

    # Überstromprüfung
    if current_true_mA > MAX_STROM_MA:
        write_dac(0)
        print(f"!!! ÜBERSTROM DETEKTIERT: {current_true_mA:.1f} mA > {MAX_STROM_MA:.1f} mA !!!")
        status_data['output_on'] = False
        status_data['overcurrent'] = True
        disable_interval = True
    else:
        disable_interval = False

    # Graphen erstellen
    voltage_fig = go.Figure(
        data=[go.Scatter(x=list(time_points), y=list(voltage_points), mode='lines', name='Spannung')],
        layout=go.Layout(
            title='Gemessene Ausgangsspannung',
            yaxis={'title': 'Spannung (V)', 'range': [min(voltage_points)-0.5, max(voltage_points)+0.5] if voltage_points else [0, 12]},
            xaxis={'title': 'Zeit'},
            showlegend=True
        )
    )
    current_fig = go.Figure(
        data=[go.Scatter(x=list(time_points), y=list(current_points), mode='lines', name='Strom', line={'color': 'orange'})],
        layout=go.Layout(
            title='Korrigierter Ausgangsstrom',
            yaxis={'title': 'Strom (mA)', 'range': [min(current_points)-10, max(current_points)+10] if current_points else [0, MAX_STROM_MA + 50]},
            xaxis={'title': 'Zeit'},
            shapes=[{ # Linie für Überstromschwelle
                'type': 'line', 'x0': time_points[0] if time_points else 0, 'y0': MAX_STROM_MA,
                'x1': time_points[-1] if time_points else 1, 'y1': MAX_STROM_MA,
                'line': {'color': 'red', 'width': 2, 'dash': 'dash'}
            }],
            showlegend=True
        )
    )
    
    # Statusanzeige aktualisieren
    if status_data['overcurrent']:
        status_text = f"ÜBERSTROM! ({current_true_mA:.1f} mA)"
        status_color = '#f44336' # Rot
    elif status_data['output_on']:
        status_text = "Ausgang AN"
        status_color = '#4CAF50' # Grün
    else:
        status_text = "Ausgang AUS"
        status_color = '#888888' # Grau

    status_div = html.Div([
        html.H3("STATUS", style={'margin': '0 0 10px 0'}),
        html.H4(status_text, style={'margin': '0'})
    ], style={'backgroundColor': status_color, 'color': 'white', 'padding': '15px', 'borderRadius': '5px'})

    return voltage_fig, current_fig, status_div, disable_interval, status_data


# ----------------- Server starten -----------------
if __name__ == '__main__':
    host_ip = get_ip_address()
    print(f"Dash-Server wird gestartet. Zugriff unter http://{host_ip}:8070")
    # KORRIGIERTE ZEILE: app.run_server() wurde zu app.run() geändert.
    app.run(host=host_ip, port=8070, debug=True)
