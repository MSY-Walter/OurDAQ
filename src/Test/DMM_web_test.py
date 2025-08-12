#!/usr/bin/env python3
"""
Web-basierter Digitaler Multimeter mit erweiterter Wellenform-Auswahl
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
import math

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
        self.waveform = "Sinus"  # Standard-Wellenform für AC
        self.channel = 0
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
                if SIMULATION_MODE or not self.hat:
                    # Simulation mit Zufallswerten
                    wert = random.uniform(-5, 5)
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
                    clearable=False,
                    style={'marginBottom': '15px'}
                ),

                # Wellenform-Auswahl für AC
                html.Div(id='waveform-container', children=[
                    html.Label('Wellenform (nur AC):', style={'fontWeight': 'bold', 'display': 'block', 'marginTop': '10px'}),
                    dcc.Dropdown(
                        id='waveform-dropdown',
                        options=[
                            {'label': 'Sinus', 'value': 'Sinus'},
                            {'label': 'Dreieck', 'value': 'Dreieck'},
                            {'label': 'Rechteck (symmetrisch)', 'value': 'Rechteck (symmetrisch)'},
                            {'label': 'Rechteck (asymmetrisch)', 'value': 'Rechteck (asymmetrisch)'}
                        ],
                        value='Sinus',
                        clearable=False,
                        style={'marginBottom': '15px'}
                    )
                ], style={'display': 'none'}), # Standardmäßig versteckt
                
                # Kanal
                html.Label('Aktiver Kanal:', style={'fontWeight': 'bold', 'display': 'block', 'marginTop': '10px'}),
                dcc.Dropdown(
                    id='channel-dropdown',
                    options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                    value=0,
                    clearable=False,
                    style={'marginBottom': '15px'}
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
                        style={'backgroundColor': '#000', 'color': '#00ff00', 'padding': '30px',
                               'borderRadius': '8px', 'textAlign': 'center', 'minHeight': '40px',
                               'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'Courier New',
                               'marginBottom': '20px', 'border': '2px solid #00ff00'},
                        children='0.000000 V'),
            ]),
            
            # Diagramm
            dcc.Graph(id='measurement-chart', config={'displayModeBar': False}, style={'height': '400px', 'border': '1px solid #bdc3c7', 'borderRadius': '8px'}),
            
            # Status
            html.Div(id='status-display', style={'backgroundColor': '#34495e', 'color': 'white', 'padding': '10px', 'borderRadius': '5px', 'fontWeight': 'bold', 'marginTop': '15px'},
                    children=f"Status: Bereit - Keine Konfiguration{' (Simuliert)' if SIMULATION_MODE else ''}"),
        
        ], style={'marginLeft': '320px'}),
        
    ], style={'overflow': 'hidden'}),
    
    # Versteckte Komponenten
    dcc.Interval(id='display-interval', interval=100, n_intervals=0, disabled=True),
    dcc.Interval(id='chart-interval', interval=250, n_intervals=0, disabled=True),
    dcc.Download(id="download-csv"),
])

@app.callback(
    Output('waveform-container', 'style'),
    Input('mode-dropdown', 'value')
)
def toggle_waveform_selector(mode):
    """Zeigt das Wellenform-Dropdown nur für AC-Modi an."""
    if mode in ["AC Spannung", "AC Strom"]:
        return {'display': 'block'}
    else:
        return {'display': 'none'}

@app.callback(
    [Output('mode-dropdown', 'disabled'),
     Output('channel-dropdown', 'disabled'),
     Output('waveform-dropdown', 'disabled'),
     Output('config-button', 'children'),
     Output('config-button', 'style'),
     Output('start-button', 'disabled'),
     Output('display-interval', 'disabled'),
     Output('status-display', 'children')],
    [Input('config-button', 'n_clicks')],
    [State('mode-dropdown', 'value'),
     State('channel-dropdown', 'value'),
     State('waveform-dropdown', 'value')]
)
def handle_configuration(n_clicks, mode, channel, waveform):
    """Verwaltet die Konfiguration und Dekonfiguration des DMM."""
    if not n_clicks:
        return False, False, False, 'Konfigurieren', {'width': '100%', 'height': '40px', 'backgroundColor': '#3498db', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'}, True, True, f"Status: Bereit - Keine Konfiguration{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    # Toggle Konfiguration
    if dmm.configured:
        # Dekonfigurieren
        dmm.stop_measurement()
        return False, False, False, 'Konfigurieren', {'width': '100%', 'height': '40px', 'backgroundColor': '#3498db', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'}, True, True, f"Status: Bereit - Keine Konfiguration{' (Simuliert)' if SIMULATION_MODE else ''}"
    else:
        # Konfigurieren
        dmm.modus = mode
        dmm.channel = channel
        if mode in ["AC Spannung", "AC Strom"]:
            dmm.waveform = waveform
        dmm.start_measurement()

        status_text = f"Status: Konfiguriert - {mode} auf Kanal {channel}"
        if mode in ["AC Spannung", "AC Strom"]:
            status_text += f" ({waveform})"
        status_text += f"{' (Simuliert)' if SIMULATION_MODE else ''}"

        return True, True, True, 'Rekonfigurieren', {'width': '100%', 'height': '40px', 'backgroundColor': '#27ae60', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'fontSize': '14px', 'marginTop': '15px'}, False, False, status_text

@app.callback(
    Output('measurement-display', 'children'),
    Input('display-interval', 'n_intervals')
)
def update_display(n_intervals):
    """
    Aktualisiert die Messwertanzeige. Passt die Anzeige für verschiedene AC-Wellenformen an.
    """
    if not dmm.configured:
        return '0.000000 V'
    
    display_data = dmm.get_display_data()
    wert = display_data['wert']
    display_text = ""
    
    # --- DC Modi ---
    if "DC" in dmm.modus:
        display_value = wert
        if "Strom" in dmm.modus:
            display_value /= 1.0  # Annahme: A = V / 1Ω Shunt
        unit = dmm.mode_units[dmm.modus]
        display_text = f"{display_value:.6f} {unit}"

    # --- AC Modi ---
    elif "AC" in dmm.modus:
        peak_value = abs(wert)
        base_unit = "A" if "Strom" in dmm.modus else "V"
        unit = dmm.mode_units[dmm.modus]

        # Anzeige basierend auf der ausgewählten Wellenform
        if dmm.waveform == 'Rechteck (symmetrisch)':
            display_peak = peak_value
            if base_unit == "A":
                display_peak /= 1.0 # Annahme: Ipeak = Vpeak / 1Ω Shunt
            display_text = f"±{display_peak:.6f} {base_unit}"

        elif dmm.waveform == 'Rechteck (asymmetrisch)':
            display_peak = peak_value
            if base_unit == "A":
                display_peak /= 1.0 # Annahme: Ipeak = Vpeak / 1Ω Shunt
            
            # Zeigt den Bereich basierend auf dem Vorzeichen des aktuellen Werts an
            if wert >= 0:
                display_text = f"0 bis +{display_peak:.6f} {base_unit}"
            else:
                display_text = f"-{display_peak:.6f} bis 0 {base_unit}"
        
        # Standard RMS-Berechnung für Sinus und Dreieck
        else:
            display_value = 0.0
            strom_peak = peak_value / 1.0 # Annahme für Strom
            
            if dmm.waveform == 'Sinus':
                display_value = peak_value / math.sqrt(2)
                if "Strom" in dmm.modus:
                    display_value = strom_peak / math.sqrt(2)
            elif dmm.waveform == 'Dreieck':
                display_value = peak_value / math.sqrt(3)
                if "Strom" in dmm.modus:
                    display_value = strom_peak / math.sqrt(3)
            
            display_text = f"{display_value:.6f} {unit}"
            
    return display_text

def calculate_plot_value(wert, modus, waveform):
    """Hilfsfunktion zur Berechnung des Werts für das Diagramm (RMS oder Peak)."""
    # Für DC wird der Rohwert geplottet
    if "DC" in modus:
        if "Strom" in modus:
            return wert / 1.0  # Annahme: Shunt-Widerstand
        return wert

    # Für AC wird der Effektivwert (RMS) berechnet
    peak_value = abs(wert)
    if "Strom" in modus:
        peak_value /= 1.0  # Annahme: Shunt-Widerstand

    if waveform == 'Sinus':
        return peak_value / math.sqrt(2)
    elif waveform == 'Dreieck':
        return peak_value / math.sqrt(3)
    elif waveform == 'Rechteck (symmetrisch)':
        return peak_value  # RMS einer symmetrischen Rechteckwelle ist der Spitzenwert
    elif waveform == 'Rechteck (asymmetrisch)':
        # RMS einer 0-zu-Peak Rechteckwelle (50% Tastverhältnis) ist V_peak / sqrt(2)
        return peak_value / math.sqrt(2)
    
    return 0.0  # Fallback

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
    """Verwaltet Start, Pause und Stop der Datenaufzeichnung."""
    ctx = callback_context
    
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    status_text = f"Status: Aufzeichnung läuft - {dmm.modus} auf Kanal {dmm.channel}"
    if dmm.modus in ["AC Spannung", "AC Strom"]:
        status_text += f" ({dmm.waveform})"
    status_text += f"{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    if trigger_id == 'start-button' and start_clicks:
        dmm.start_recording()
        return True, False, False, True, 'Pause', False, status_text
    
    elif trigger_id == 'pause-button' and pause_clicks:
        if dmm.paused:
            dmm.resume_recording()
            return True, False, False, True, 'Pause', False, status_text.replace("läuft", "fortgesetzt")
        else:
            dmm.pause_recording()
            return True, False, False, True, 'Fortsetzen', False, status_text.replace("läuft", "pausiert")
    
    elif trigger_id == 'stop-button' and stop_clicks:
        dmm.stop_recording()
        count = len(dmm.messdaten)
        return False, True, True, False, 'Pause', True, f"Status: Aufzeichnung gestoppt - {count} Messpunkte aufgezeichnet{' (Simuliert)' if SIMULATION_MODE else ''}"
    
    return no_update, no_update, no_update, no_update, no_update, no_update, no_update

@app.callback(
    Output('measurement-chart', 'figure'),
    Input('chart-interval', 'n_intervals')
)
def update_chart(n):
    """Aktualisiert das Echtzeitdiagramm."""
    if not dmm.recording:
        # Leeres Chart
        fig = go.Figure()
        fig.update_layout(title='Messwerte', xaxis_title='Zeit (s)', yaxis_title='Wert', showlegend=False, plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=50, r=50, t=50, b=50))
        fig.add_annotation(text="Starten Sie die Aufzeichnung für Diagramm-Anzeige", xref="paper", yref="paper", x=0.5, y=0.5, xanchor='center', yanchor='middle', showarrow=False, font=dict(size=16, color="gray"))
        return fig
    
    x_data, y_data = dmm.get_chart_data()
    fig = go.Figure()
    
    y_axis_range = [-1, 1]
    
    if x_data and y_data:
        # Datenkonvertierung basierend auf Modus und Wellenform
        converted_y_data = [calculate_plot_value(wert, dmm.modus, dmm.waveform) for wert in y_data]
        
        fig.add_trace(go.Scatter(x=x_data, y=converted_y_data, mode='lines+markers', name=dmm.modus, line=dict(color='#00ff00', width=2), marker=dict(size=3)))
        
        # Y-Achsen-Skalierung
        if converted_y_data:
            y_min, y_max = min(converted_y_data), max(converted_y_data)
            y_range = y_max - y_min if y_max > y_min else 0.1
            margin = y_range * 0.1
            y_axis_range = [y_min - margin, y_max + margin]
    
    # Y-Achsen-Beschriftung je nach Modus
    y_title = "Strom (A)" if "Strom" in dmm.modus else "Spannung (V)"
    
    chart_title = f'{dmm.modus}-Verlauf (Kanal {dmm.channel})'
    if dmm.modus in ["AC Spannung", "AC Strom"]:
        chart_title += f" - {dmm.waveform}"

    fig.update_layout(title=chart_title, xaxis_title='Zeit (s)', yaxis_title=y_title, showlegend=False, plot_bgcolor='white', paper_bgcolor='white', margin=dict(l=50, r=50, t=50, b=50), yaxis=dict(range=y_axis_range))
    
    return fig

@app.callback(
    Output("download-csv", "data"),
    Input("csv-button", "n_clicks"),
    prevent_initial_call=True
)
def download_csv(n_clicks):
    """Ermöglicht den Download der aufgezeichneten Daten als CSV."""
    if n_clicks and dmm.messdaten:
        df = pd.DataFrame(dmm.messdaten)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"OurDAQ_DMM_Kanal{dmm.channel}_{timestamp}.csv"
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    return no_update

if __name__ == '__main__':
    print(f"Starting Digitalmultimeter in {'simulation' if SIMULATION_MODE else 'hardware'} mode")
    app.run(host=get_ip_address(), port=8050, debug=True)
