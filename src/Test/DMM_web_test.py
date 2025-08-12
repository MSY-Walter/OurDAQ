#!/usr/bin/env python3
"""
Web-basierter Digitaler Multimeter mit erweiterter Simulation
"""

import os
import sys
import logging
import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import plotly.graph_objs as go
import pandas as pd
import time
from datetime import datetime
import threading
from collections import deque
import socket
import random

# Werkzeug und Flask Logging unterdrücken
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Simulation Mode
SIMULATION_MODE = '--simulate' in sys.argv

# Mock Hardware Imports
if not SIMULATION_MODE:
    try:
        from daqhats import mcc118, OptionFlags, HatError
    except ImportError as e:
        print(f"Fehler beim Importieren von daqhats: {e}. Wechsle zu Simulation.")
        SIMULATION_MODE = True

class DashDMM:
    def __init__(self):
        self.hat = None
        if not SIMULATION_MODE:
            self.init_mcc118()
        
        self.modus = "DC Spannung"  # Standardmodus
        self.channel = 0
        self.signal_type = 'symmetrisch' # NEU: Für Simulation
        self.sim_state = True # NEU: Zustand für Rechtecksignal-Generator
        
        self.configured = False  # Konfigurationsstatus
        self.recording = False  # Datenaufzeichnung für Chart
        self.paused = False
        self.messdaten = []
        
        # Einheiten für verschiedene Modi
        self.mode_units = {
            "DC Spannung": "V DC",
            "AC Spannung": "V AC", 
            "DC Strom": "A DC",
            "AC Strom": "A AC"
        }
        
        # Für Echtzeitdiagramm - optimiert für Pi 5
        self.max_punkte = 100  
        self.zeit_daten = deque(maxlen=self.max_punkte)
        self.wert_daten = deque(maxlen=self.max_punkte)
        self.start_zeit = time.time()
        
        # Cached Messwerte
        self.display_cache = {
            'wert': 0.0,
            'timestamp': time.time()
        }
        
        # Measurement Thread
        self.measurement_thread = None
        self.running = False
        self.lock = threading.Lock()
    
    def init_mcc118(self):
        """Initialisiert das MCC 118 DAQ HAT"""
        try:
            self.hat = mcc118(0)
        except HatError as e:
            print(f"Fehler beim Initialisieren des MCC 118: {str(e)}")
            self.hat = None
    
    def start_measurement(self):
        """Startet die kontinuierliche Messung für Display"""
        if not self.running:
            self.running = True
            self.configured = True
            self.measurement_thread = threading.Thread(target=self._measurement_loop)
            self.measurement_thread.daemon = True
            self.measurement_thread.start()
    
    def stop_measurement(self):
        """Stoppt alle Messungen"""
        self.running = False
        self.configured = False
        self.recording = False
        if self.measurement_thread:
            self.measurement_thread.join(timeout=1)
    
    def start_recording(self):
        """Startet die Datenaufzeichnung"""
        with self.lock:
            self.recording = True
            self.paused = False
            self.messdaten = []
            self.zeit_daten.clear()
            self.wert_daten.clear()
            self.start_zeit = time.time()
    
    def pause_recording(self):
        """Pausiert die Datenaufzeichnung"""
        self.paused = True
    
    def resume_recording(self):
        """Setzt die Datenaufzeichnung fort"""
        self.paused = False
    
    def stop_recording(self):
        """Stoppt die Datenaufzeichnung und resettet Timer"""
        self.recording = False
        self.paused = False
        # Reset für neue Aufzeichnung
        with self.lock:
            self.zeit_daten.clear()
            self.wert_daten.clear()
    
    def _measurement_loop(self):
        """Hauptschleife für kontinuierliche Messungen"""
        while self.running:
            try:
                wert = 0.0
                if SIMULATION_MODE or not self.hat:
                    # NEU: Simulation mit Rechtecksignal statt Zufallswerten
                    # Fügt eine kleine zufällige Abweichung hinzu, um realistischer zu wirken
                    noise = random.uniform(-0.05, 0.05)
                    if self.signal_type == 'symmetrisch':
                        wert = (5.0 if self.sim_state else -5.0) + noise
                    else:  # asymmetrisch
                        wert = (10.0 if self.sim_state else 0.0) + noise
                    
                    # Zustand für nächsten Durchlauf wechseln (ca. alle 200ms)
                    if int(time.time() * 5) % 2 == 0:
                        self.sim_state = True
                    else:
                        self.sim_state = False
                else:
                    wert = self.hat.a_in_read(self.channel, OptionFlags.DEFAULT)
                
                # Update Display Cache
                with self.lock:
                    self.display_cache.update({
                        'wert': wert,
                        'timestamp': time.time()
                    })
                
                # Datenaufzeichnung nur wenn aktiv und nicht pausiert
                if self.recording and not self.paused:
                    with self.lock:
                        aktuelle_zeit = time.time() - self.start_zeit
                        self.zeit_daten.append(aktuelle_zeit)
                        self.wert_daten.append(wert)
                        
                        zeit_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        self.messdaten.append({
                            'Zeit': zeit_str,
                            'Wert': wert,
                            'Modus': self.modus,
                            'Kanal': self.channel
                        })
                
                time.sleep(0.05)  # 20Hz für gute Responsivität
                
            except Exception as e:
                print(f"Fehler in Messschleife: {e}")
                time.sleep(0.1)
    
    def get_display_data(self):
        """Thread-safe Zugriff auf Display-Daten"""
        with self.lock:
            return self.display_cache.copy()
    
    def get_chart_data(self):
        """Thread-safe Zugriff auf Chart-Daten"""
        with self.lock:
            if self.recording and len(self.zeit_daten) > 0:
                return list(self.zeit_daten), list(self.wert_daten)
            return [], []

def get_ip_address():
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts."""
    ip_address = '127.0.0.1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.connect(('1.1.1.1', 1))
        ip_address = sock.getsockname()[0]
    finally:
        sock.close()
    
    return ip_address

# Globale DMM-Instanz
dmm = DashDMM()

# Dash App initialisieren
app = dash.Dash(__name__)
app.title = "OurDAQ - Digitalmultimeter"

# Layout der App
app.layout = html.Div([
    # Header
    html.H1("OurDAQ - Digitalmultimeter", 
            style={'textAlign': 'center', 'color': 'white', 'backgroundColor': '#2c3e50',
                   'padding': '20px', 'margin': '0 0 20px 0', 'borderRadius': '8px'}),
    
    # Hauptinhalt Container
    html.Div([
        # Linke Spalte - Steuerung
        html.Div([
            # Konfigurationsbereich
            html.Div([
                html.H3("Konfiguration", style={'color': '#2c3e50', 'marginBottom': '15px'}),
                
                # Messmodus
                html.Label('Messmodus:', style={'fontWeight': 'bold', 'display': 'block', 'marginTop': '10px'}),
                dcc.Dropdown(
                    id='mode-dropdown',
                    options=[
                        {'label': 'DC Spannung', 'value': 'DC Spannung'},
                        {'label': 'AC Spannung', 'value': 'AC Spannung'},
                        {'label': 'DC Strom', 'value': 'DC Strom'},
                        {'label': 'AC Strom', 'value': 'AC Strom'}
                    ],
                    value='DC Spannung',
                    style={'marginBottom': '15px'}
                ),
                
                # Kanal
                html.Label('Aktiver Kanal:', style={'fontWeight': 'bold', 'display': 'block', 'marginTop': '10px'}),
                dcc.Dropdown(
                    id='channel-dropdown',
                    options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                    value=0,
                    style={'marginBottom': '15px'}
                ),
                
                # NEU: Signalart für Simulation
                html.Label('Signalart (Simulation):', style={'fontWeight': 'bold', 'display': 'block', 'marginTop': '10px'}),
                dcc.RadioItems(
                    id='signal-type-radio',
                    options=[
                        {'label': 'Symmetrisch (+/- 5V)', 'value': 'symmetrisch'},
                        {'label': 'Asymmetrisch (0-10V)', 'value': 'asymmetrisch'},
                    ],
                    value='symmetrisch',
                    style={'marginBottom': '15px'},
                    inputStyle={"margin-right": "5px"},
                    labelStyle={'display': 'inline-block', 'margin-right': '20px'}
                ),
                
                # Konfigurationsbutton
                html.Button(
                    'Konfigurieren',
                    id='config-button',
                    style={'width': '100%', 'height': '40px', 'backgroundColor': '#3498db',
                           'color': 'white', 'border': 'none', 'borderRadius': '5px',
                           'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'}
                ),
            ], style={'backgroundColor': '#ecf0f1', 'padding': '20px', 'borderRadius': '8px',
                      'marginBottom': '20px'}),
            
            # Aufzeichnungssteuerung
            html.Div([
                html.H3("Datenaufzeichnung", style={'color': '#2c3e50', 'marginBottom': '15px'}),
                
                html.Button('Start', id='start-button', disabled=True, style={'width': '100%', 'height': '35px', 'backgroundColor': '#27ae60', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'marginBottom': '10px'}),
                html.Button('Pause', id='pause-button', disabled=True, style={'width': '100%', 'height': '35px', 'backgroundColor': '#f39c12', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'marginBottom': '10px'}),
                html.Button('Stop', id='stop-button', disabled=True, style={'width': '100%', 'height': '35px', 'backgroundColor': '#e74c3c', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'marginBottom': '15px'}),
                html.Button('CSV Export', id='csv-button', disabled=True, style={'width': '100%', 'height': '35px', 'backgroundColor': '#95a5a6', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold'}),
            ], style={'backgroundColor': '#ecf0f1', 'padding': '20px', 'borderRadius': '8px'}),
            
        ], style={'width': '300px', 'float': 'left', 'marginRight': '20px'}),
        
        # Rechte Spalte - Anzeige
        html.Div([
            # Messwert Display
            html.Div([
                html.Div(id='measurement-display',
                        style={'backgroundColor': '#000', 'color': '#00ff00', 'padding': '30px', 'borderRadius': '8px', 'textAlign': 'center', 'minHeight': '40px', 'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'Courier New', 'marginBottom': '20px', 'border': '2px solid #00ff00'},
                        children='0.000000 V DC'),
            ]),
            
            # Diagramm
            dcc.Graph(id='measurement-chart', config={'displayModeBar': False}, style={'height': '400px', 'border': '1px solid #bdc3c7', 'borderRadius': '8px'}),
            
            # Status
            html.Div(id='status-display',
                    style={'backgroundColor': '#34495e', 'color': 'white', 'padding': '10px', 'borderRadius': '5px', 'fontWeight': 'bold', 'marginTop': '15px'},
                    children=f"Status: Bereit - Keine Konfiguration{' (Simuliert)' if SIMULATION_MODE else ''}"),
        
        ], style={'marginLeft': '320px'}),
        
    ], style={'overflow': 'hidden'}),
    
    # Versteckte Komponenten
    dcc.Interval(id='display-interval', interval=100, n_intervals=0, disabled=True),
    dcc.Interval(id='chart-interval', interval=250, n_intervals=0, disabled=True),
    dcc.Download(id="download-csv"),
])

@app.callback(
    [Output('mode-dropdown', 'disabled'),
     Output('channel-dropdown', 'disabled'),
     Output('signal-type-radio', 'disabled'), # NEU
     Output('config-button', 'children'),
     Output('config-button', 'style'),
     Output('start-button', 'disabled'),
     Output('display-interval', 'disabled'),
     Output('status-display', 'children')],
    [Input('config-button', 'n_clicks')],
    [State('mode-dropdown', 'value'),
     State('channel-dropdown', 'value'),
     State('signal-type-radio', 'value')] # NEU
)
def handle_configuration(n_clicks, mode, channel, signal_type): # NEU
    if not n_clicks:
        return False, False, False, 'Konfigurieren', {
            'width': '100%', 'height': '40px', 'backgroundColor': '#3498db',
            'color': 'white', 'border': 'none', 'borderRadius': '5px',
            'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'
        }, True, True, f"Status: Bereit - Keine Konfiguration{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    # Toggle Konfiguration
    if dmm.configured:
        # Dekonfigurieren
        dmm.stop_measurement()
        return False, False, False, 'Konfigurieren', {
            'width': '100%', 'height': '40px', 'backgroundColor': '#3498db',
            'color': 'white', 'border': 'none', 'borderRadius': '5px',
            'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'
        }, True, True, f"Status: Bereit - Keine Konfiguration{' (Simuliert)' if SIMULATION_MODE else ''}"
    else:
        # Konfigurieren
        dmm.modus = mode
        dmm.channel = channel
        dmm.signal_type = signal_type # NEU
        dmm.start_measurement()
        return True, True, True, 'Rekonfigurieren', {
            'width': '100%', 'height': '40px', 'backgroundColor': '#27ae60',
            'color': 'white', 'border': 'none', 'borderRadius': '5px',
            'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'
        }, False, False, f"Status: Konfiguriert - {mode} auf Kanal {channel}{' (Simuliert)' if SIMULATION_MODE else ''}"

@app.callback(
    [Output('measurement-display', 'children')],
    [Input('display-interval', 'n_intervals')]
)
def update_display(n_intervals):
    if not dmm.configured:
        return ['0.000000 V DC']
    
    display_data = dmm.get_display_data()
    wert = display_data['wert']
    
    # Einheitenberechnung je nach Modus
    if dmm.modus == "DC Spannung":
        display_value = wert
    elif dmm.modus == "AC Spannung":
        display_value = abs(wert) * 0.707  # RMS approximation
    elif dmm.modus == "DC Strom":
        display_value = wert / 1.0  # A = V / 1Ω Shunt
    elif dmm.modus == "AC Strom":
        display_value = abs(wert) * 0.707 / 1.0  # RMS current
    
    unit = dmm.mode_units[dmm.modus]
    display_text = f"{display_value:.6f} {unit}"
    
    return [display_text]

@app.callback(
    [Output('start-button', 'disabled', allow_duplicate=True),
     Output('pause-button', 'disabled'),
     Output('stop-button', 'disabled'),
     Output('csv-button', 'disabled'),
     Output('pause-button', 'children'),
     Output('chart-interval', 'disabled'),
     Output('status-display', 'children', allow_duplicate=True)],
    [Input('start-button', 'n_clicks'),
     Input('pause-button', 'n_clicks'),
     Input('stop-button', 'n_clicks')],
    prevent_initial_call=True
)
def handle_recording(start_clicks, pause_clicks, stop_clicks):
    ctx = callback_context
    
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'start-button' and start_clicks:
        dmm.start_recording()
        return True, False, False, True, 'Pause', False, f"Status: Aufzeichnung läuft - {dmm.modus} auf Kanal {dmm.channel}{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    elif trigger_id == 'pause-button' and pause_clicks:
        if dmm.paused:
            dmm.resume_recording()
            return True, False, False, True, 'Pause', False, f"Status: Aufzeichnung fortgesetzt - {dmm.modus} auf Kanal {dmm.channel}{' (Simuliert)' if SIMULATION_MODE else ''}"
        else:
            dmm.pause_recording()
            return True, False, False, True, 'Fortsetzen', False, f"Status: Aufzeichnung pausiert - {dmm.modus} auf Kanal {dmm.channel}{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    elif trigger_id == 'stop-button' and stop_clicks:
        dmm.stop_recording()
        count = len(dmm.messdaten)
        return False, True, True, False, 'Pause', True, f"Status: Aufzeichnung gestoppt - {count} Messpunkte aufgezeichnet{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    return no_update, no_update, no_update, no_update, no_update, no_update, no_update

@app.callback(
    [Output('measurement-chart', 'figure')],
    [Input('chart-interval', 'n_intervals')]
)
def update_chart(n):
    if not dmm.recording:
        # Leeres Chart
        fig = go.Figure()
        fig.update_layout(
            title='Messwerte',
            xaxis_title='Zeit (s)',
            yaxis_title='Spannung (V)',
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=50, r=50, t=50, b=50)
        )
        fig.add_annotation(
            text="Starten Sie die Aufzeichnung für Diagramm-Anzeige",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False,
            font=dict(size=16, color="gray")
        )
        return [fig]
    
    x_data, y_data = dmm.get_chart_data()
    
    fig = go.Figure()
    
    if x_data and y_data:
        # Datenkonvertierung je nach Modus
        converted_y_data = []
        for wert in y_data:
            if dmm.modus == "DC Spannung":
                converted_y_data.append(wert)
            elif dmm.modus == "AC Spannung":
                converted_y_data.append(abs(wert) * 0.707)
            elif dmm.modus == "DC Strom":
                converted_y_data.append(wert / 1.0)
            elif dmm.modus == "AC Strom":
                converted_y_data.append(abs(wert) * 0.707 / 1.0)
        
        fig.add_trace(go.Scatter(
            x=x_data,
            y=converted_y_data,
            mode='lines', # 'lines+markers' kann bei vielen Punkten langsam werden
            name=dmm.modus,
            line=dict(color='#00ff00', width=2)
        ))
        
        # Y-Achsen-Skalierung
        y_min = min(converted_y_data)
        y_max = max(converted_y_data)
        y_range_val = y_max - y_min
        
        if y_range_val < 0.1:
            y_range_val = 0.1
        
        margin = y_range_val * 0.1
        y_axis_range = [y_min - margin, y_max + margin]
    else:
        # Standardbereich, wenn keine Daten vorhanden sind
        y_axis_range = [-11, 11] if dmm.signal_type == 'symmetrisch' else [-1, 11]

    
    # Y-Achsen-Beschriftung je nach Modus
    if "Spannung" in dmm.modus:
        y_title = "Spannung (V)"
    else:
        y_title = "Strom (A)"
    
    fig.update_layout(
        title=f'{dmm.modus}-Verlauf (Kanal {dmm.channel})',
        xaxis_title='Zeit (s)',
        yaxis_title=y_title,
        showlegend=False,
        plot_bgcolor='black',
        paper_bgcolor='white',
        font=dict(color='black'),
        xaxis=dict(gridcolor='lightgrey'),
        yaxis=dict(gridcolor='lightgrey', range=y_axis_range),
        margin=dict(l=50, r=50, t=50, b=50),
    )
    
    return [fig]

@app.callback(
    Output("download-csv", "data"),
    [Input("csv-button", "n_clicks")],
    prevent_initial_call=True
)
def download_csv(n_clicks):
    if n_clicks and dmm.messdaten:
        df = pd.DataFrame(dmm.messdaten)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"OurDAQ_DMM_Kanal{dmm.channel}_{timestamp}.csv"
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    return no_update

if __name__ == '__main__':
    print(f"Starting Digitalmultimeter in {'simulation' if SIMULATION_MODE else 'hardware'} mode")
    app.run(host=get_ip_address(), port=8050, debug=True)
