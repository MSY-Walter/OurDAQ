# -*- coding: utf-8 -*-
"""
Web-basierter Digitaler Multimeter für MCC 118 mit Dash
Ein LabVIEW-ähnlicher DMM als Webanwendung mit Dash/Plotly
Mit Überlastungswarnung, Echtzeitdiagramm und CSV-Download
Performance-optimiert für flüssige Bedienung
"""

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np
import time
import csv
import io
import base64
from datetime import datetime
import threading
from collections import deque
from daqhats import mcc118, OptionFlags, HatError

class DashDMM:
    def __init__(self):
        self.hat = None
        self.init_mcc118()
        
        self.modus = "Spannung DC"
        self.bereich = 10.0
        self.channel = 0
        self.datenerfassung_aktiv = False
        self.messdaten = []
        self.ueberlast_status = False
        
        # Für Echtzeitdiagramm - reduzierte Datenpunkte für bessere Performance
        self.max_punkte = 50  # Reduziert von 100
        self.zeit_daten = deque(maxlen=self.max_punkte)
        self.wert_daten = deque(maxlen=self.max_punkte)
        self.start_zeit = time.time()
        
        # Cached Messwerte für UI Updates
        self.display_cache = {
            'wert': 0.0,
            'ueberlast': False,
            'timestamp': time.time()
        }
        
        # Measurement Thread mit weniger häufigen Updates
        self.measurement_thread = None
        self.running = False
        self.lock = threading.Lock()
        
    def init_mcc118(self):
        """Initialisiert das MCC 118 DAQ HAT"""
        try:
            self.hat = mcc118(0)
            print("MCC 118 erfolgreich initialisiert")
        except HatError as e:
            print(f"Fehler beim Initialisieren des MCC 118: {str(e)}")
            self.hat = None
    
    def get_dezimalstellen(self, bereich):
        """Berechnet die Anzahl der Dezimalstellen basierend auf dem Messbereich"""
        if bereich >= 10.0:
            return 3
        elif bereich >= 1.0:
            return 4
        elif bereich >= 0.5:
            return 5
        else:  # 200mV Bereich
            return 6
    
    def start_measurement(self):
        """Startet die kontinuierliche Messung"""
        if not self.running:
            self.running = True
            self.measurement_thread = threading.Thread(target=self._measurement_loop)
            self.measurement_thread.daemon = True
            self.measurement_thread.start()
    
    def stop_measurement(self):
        """Stoppt die kontinuierliche Messung"""
        self.running = False
        if self.measurement_thread:
            self.measurement_thread.join(timeout=1)
    
    def _measurement_loop(self):
        """Hauptschleife für kontinuierliche Messungen - optimiert für Performance"""
        measurement_count = 0
        while self.running:
            try:
                if self.hat:
                    wert = self.hat.a_in_read(self.channel, OptionFlags.DEFAULT)
                else:
                    # Simulationsmodus für Tests ohne Hardware
                    import random
                    wert = random.uniform(-self.bereich, self.bereich) * 0.1
                
                ueberlast = abs(wert) > self.bereich
                
                # Update Cache für Display (weniger Lock-Verwendung)
                with self.lock:
                    self.display_cache.update({
                        'wert': wert,
                        'ueberlast': ueberlast,
                        'timestamp': time.time()
                    })
                    
                    # Überlast-Status nur bei Änderung aktualisieren
                    if ueberlast != self.ueberlast_status:
                        self.ueberlast_status = ueberlast
                
                # Datenerfassung nur alle 2. Messung für bessere Performance
                measurement_count += 1
                if self.datenerfassung_aktiv and measurement_count % 2 == 0:
                    with self.lock:
                        aktuelle_zeit = time.time() - self.start_zeit
                        self.zeit_daten.append(aktuelle_zeit)
                        self.wert_daten.append(wert)
                        
                        zeit_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        self.messdaten.append({
                            'Zeit': zeit_str,
                            'Wert': wert,
                            'Modus': self.modus,
                            'Kanal': self.channel,
                            'Bereich': self.bereich
                        })
                
                time.sleep(0.2)  # Erhöht von 0.1s auf 0.2s für bessere Performance
                
            except Exception as e:
                print(f"Fehler in Messschleife: {e}")
                time.sleep(0.2)
    
    def get_display_data(self):
        """Thread-safe Zugriff auf Display-Daten"""
        with self.lock:
            return self.display_cache.copy()
    
    def get_chart_data(self):
        """Thread-safe Zugriff auf Chart-Daten"""
        with self.lock:
            if self.datenerfassung_aktiv and len(self.zeit_daten) > 0:
                return list(self.zeit_daten), list(self.wert_daten)
            return [], []

# Globale DMM-Instanz
dmm = DashDMM()

# Dash App initialisieren
app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "OurDAQ - Web Digitalmultimeter"

# Layout der App
app.layout = html.Div([
    # Header
    html.Div([
        html.H1("OurDAQ - Web Digitalmultimeter", 
                style={'textAlign': 'center', 'color': '#333', 'marginBottom': '20px'}),
        html.Div(id='connection-status', 
                style={'textAlign': 'center', 'padding': '5px', 'borderRadius': '3px',
                       'backgroundColor': '#4CAF50', 'color': 'white', 'fontWeight': 'bold',
                       'fontSize': '12px', 'marginBottom': '20px'},
                children='MCC 118 Verbunden' if dmm.hat else 'Simulation Modus')
    ], style={'marginBottom': '30px'}),
    
    # Messwert Display
    html.Div([
        html.Div(id='measurement-display',
                style={'backgroundColor': '#000', 'color': '#00d2d2', 'padding': '30px',
                       'borderRadius': '10px', 'textAlign': 'center', 'minHeight': '120px',
                       'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'Courier New',
                       'marginBottom': '20px'},
                children='0.000 V DC'),
        
        # Progress Bar
        html.Div([
            html.Div(id='progress-bar',
                    style={'width': '100%', 'height': '15px', 'backgroundColor': 'transparent',
                           'border': '1px solid #00d2d2', 'position': 'relative'}),
            html.Div('% FS', style={'textAlign': 'center', 'color': '#00d2d2', 'fontSize': '12px'})
        ], style={'marginBottom': '20px'})
    ]),
    
    # Steuerungsbereich
    html.Div([
        # Messmodus
        html.Div([
            html.H3("Messmodus", style={'fontWeight': 'bold', 'color': '#333'}),
            html.Div([
                html.Button('DC Spannung (V)', id='dc-voltage-btn', n_clicks=0,
                           style={'backgroundColor': '#c0e0ff', 'border': '2px solid #4080ff',
                                  'borderRadius': '5px', 'padding': '12px', 'fontWeight': 'bold',
                                  'margin': '5px', 'cursor': 'pointer'}),
                html.Button('AC Spannung (V)', id='ac-voltage-btn', n_clicks=0, disabled=True,
                           style={'backgroundColor': '#e0e0e0', 'border': '1px solid #a0a0a0',
                                  'borderRadius': '5px', 'padding': '12px', 'fontWeight': 'bold',
                                  'margin': '5px', 'cursor': 'not-allowed', 'color': '#999'}),
                html.Button('DC Strom (A)', id='dc-current-btn', n_clicks=0, disabled=True,
                           style={'backgroundColor': '#e0e0e0', 'border': '1px solid #a0a0a0',
                                  'borderRadius': '5px', 'padding': '12px', 'fontWeight': 'bold',
                                  'margin': '5px', 'cursor': 'not-allowed', 'color': '#999'}),
                html.Button('AC Strom (A)', id='ac-current-btn', n_clicks=0, disabled=True,
                           style={'backgroundColor': '#e0e0e0', 'border': '1px solid #a0a0a0',
                                  'borderRadius': '5px', 'padding': '12px', 'fontWeight': 'bold',
                                  'margin': '5px', 'cursor': 'not-allowed', 'color': '#999'})
            ], style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '10px'})
        ], style={'backgroundColor': '#f8f8f8', 'padding': '15px', 'borderRadius': '8px',
                  'border': '1px solid #ddd', 'marginBottom': '15px'}),
        
        # Messbereich und Kanal
        html.Div([
            html.Div([
                html.H3("Messbereich", style={'fontWeight': 'bold', 'color': '#333'}),
                dcc.Dropdown(
                    id='range-dropdown',
                    options=[
                        {'label': '±10V', 'value': '±10V'},
                        {'label': '±2V', 'value': '±2V'},
                        {'label': '±1V', 'value': '±1V'},
                        {'label': '±500mV', 'value': '±500mV'},
                        {'label': '±200mV', 'value': '±200mV'}
                    ],
                    value='±10V',
                    style={'marginBottom': '15px'}
                )
            ], style={'width': '48%', 'display': 'inline-block'}),
            
            html.Div([
                html.H3("Kanal", style={'fontWeight': 'bold', 'color': '#333'}),
                dcc.Dropdown(
                    id='channel-dropdown',
                    options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                    value=0,
                    style={'marginBottom': '15px'}
                )
            ], style={'width': '48%', 'float': 'right', 'display': 'inline-block'})
        ], style={'backgroundColor': '#f8f8f8', 'padding': '15px', 'borderRadius': '8px',
                  'border': '1px solid #ddd', 'marginBottom': '15px'}),
        
        # Banana Jacks Visualisierung
        html.Div([
            html.H3("Anschlüsse", style={'fontWeight': 'bold', 'color': '#333', 'textAlign': 'center'}),
            html.Div([
                html.Div([
                    html.Div(style={'width': '20px', 'height': '20px', 'borderRadius': '50%',
                                   'backgroundColor': '#ff0000', 'margin': '0 auto'}),
                    html.Div('V', style={'textAlign': 'center', 'fontWeight': 'bold'})
                ], style={'display': 'inline-block', 'margin': '0 20px'}),
                html.Div([
                    html.Div(style={'width': '20px', 'height': '20px', 'borderRadius': '50%',
                                   'backgroundColor': '#333', 'margin': '0 auto'}),
                    html.Div('COM', style={'textAlign': 'center', 'fontWeight': 'bold'})
                ], style={'display': 'inline-block', 'margin': '0 20px'}),
                html.Div([
                    html.Div(style={'width': '20px', 'height': '20px', 'borderRadius': '50%',
                                   'backgroundColor': '#ff0000', 'margin': '0 auto'}),
                    html.Div('A', style={'textAlign': 'center', 'fontWeight': 'bold'})
                ], style={'display': 'inline-block', 'margin': '0 20px'})
            ], style={'textAlign': 'center', 'padding': '20px'})
        ], style={'backgroundColor': '#f8f8f8', 'padding': '15px', 'borderRadius': '8px',
                  'border': '1px solid #ddd', 'marginBottom': '15px'})
    ], style={'display': 'grid', 'gridTemplateColumns': '2fr 1fr 1fr', 'gap': '20px', 'marginBottom': '20px'}),
    
    # Action Buttons
    html.Div([
        html.Button('Aufnahme starten', id='start-btn', n_clicks=0,
                   style={'backgroundColor': 'darkgreen', 'color': 'white', 'border': 'none',
                          'padding': '12px 24px', 'borderRadius': '5px', 'fontWeight': 'bold',
                          'cursor': 'pointer', 'fontSize': '14px', 'margin': '5px'}),
        html.Button('Aufnahme stoppen', id='stop-btn', n_clicks=0, disabled=True,
                   style={'backgroundColor': 'darkred', 'color': 'white', 'border': 'none',
                          'padding': '12px 24px', 'borderRadius': '5px', 'fontWeight': 'bold',
                          'cursor': 'pointer', 'fontSize': '14px', 'margin': '5px'}),
        html.Button('CSV speichern', id='csv-btn', n_clicks=0,
                   style={'backgroundColor': '#f0f0f0', 'color': '#333', 'border': '1px solid #a0a0a0',
                          'padding': '12px 24px', 'borderRadius': '5px', 'fontWeight': 'bold',
                          'cursor': 'pointer', 'fontSize': '14px', 'margin': '5px'}),
        html.Button('Hilfe', id='help-btn', n_clicks=0,
                   style={'backgroundColor': '#f0f0f0', 'color': '#333', 'border': '1px solid #a0a0a0',
                          'padding': '12px 24px', 'borderRadius': '5px', 'fontWeight': 'bold',
                          'cursor': 'pointer', 'fontSize': '14px', 'margin': '5px'})
    ], style={'display': 'flex', 'gap': '15px', 'marginBottom': '20px', 'flexWrap': 'wrap'}),
    
    # Diagramm
    html.Div([
        dcc.Graph(id='measurement-chart',
                 config={'displayModeBar': False},
                 style={'height': '400px', 'border': '1px solid #ddd', 'borderRadius': '8px'})
    ], style={'marginBottom': '20px'}),
    
    # Status Bar
    html.Div(id='status-bar',
            style={'backgroundColor': '#333', 'color': 'white', 'padding': '10px',
                   'borderRadius': '5px', 'fontWeight': 'bold'},
            children='Bereit - Keine Datenaufnahme aktiv'),
    
    # Hidden divs for data storage
    html.Div(id='hidden-div', style={'display': 'none'}),
    
    # Interval für Updates - weniger häufig für bessere Performance
    dcc.Interval(id='interval-component', interval=300, n_intervals=0),  # 300ms statt 100ms
    dcc.Interval(id='chart-interval', interval=500, n_intervals=0),      # Separates Intervall für Chart
    
    # Download component
    dcc.Download(id="download-csv")
])

# Optimierte Callbacks - getrennte Intervalle für bessere Performance

@app.callback(
    [Output('measurement-display', 'children'),
     Output('measurement-display', 'style'),
     Output('progress-bar', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_display(n):
    # Verwendung der Cache-Funktion statt direktem Lock-Zugriff
    display_data = dmm.get_display_data()
    wert = display_data['wert']
    ueberlast = display_data['ueberlast']
    bereich = dmm.bereich
    
    dezimalstellen = dmm.get_dezimalstellen(bereich)
    
    if ueberlast:
        display_text = "ÜBERLAST!"
        display_style = {
            'backgroundColor': '#000', 'color': '#ff3232', 'padding': '30px',
            'borderRadius': '10px', 'textAlign': 'center', 'minHeight': '120px',
            'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'Courier New',
            'marginBottom': '20px', 'animation': 'blink 1s infinite'
        }
        progress_percent = 100
        progress_color = '#ff3232'
    else:
        einheit = 'V DC' if 'Spannung' in dmm.modus else 'A DC'
        format_string = f"{{:.{dezimalstellen}f}} {einheit}"
        display_text = format_string.format(wert)
        display_style = {
            'backgroundColor': '#000', 'color': '#00d2d2', 'padding': '30px',
            'borderRadius': '10px', 'textAlign': 'center', 'minHeight': '120px',
            'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'Courier New',
            'marginBottom': '20px'
        }
        progress_percent = min(max(0, abs(wert) / bereich), 1.0) * 100
        progress_color = '#00d2d2'
    
    progress_bar = html.Div(
        style={'width': f'{progress_percent}%', 'height': '100%', 
               'backgroundColor': progress_color, 'transition': 'width 0.2s'}
    )
    
    return display_text, display_style, progress_bar

@app.callback(
    Output('measurement-chart', 'figure'),
    [Input('chart-interval', 'n_intervals')]  # Separates Intervall für Chart
)
def update_chart(n):
    # Verwendung der Cache-Funktion für bessere Performance
    x_data, y_data = dmm.get_chart_data()
    
    einheit = 'Spannung (V)' if 'Spannung' in dmm.modus else 'Strom (A)'
    
    fig = go.Figure()
    
    if x_data and y_data:
        fig.add_trace(go.Scatter(
            x=x_data,
            y=y_data,
            mode='lines',
            name=einheit,
            line=dict(color='#00d2d2', width=3)
        ))
    
    fig.update_layout(
        title='Messwert-Verlauf',
        xaxis_title='Zeit (s)',
        yaxis_title=einheit,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    if not dmm.datenerfassung_aktiv:
        fig.add_annotation(
            text="Diagramm wird angezeigt, wenn Datenaufnahme aktiviert ist",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False,
            font=dict(size=16, color="gray")
        )
    
    return fig

# Callback für Steuerung - weniger häufige Triggerung
@app.callback(
    [Output('start-btn', 'disabled'),
     Output('stop-btn', 'disabled'),
     Output('status-bar', 'children')],
    [Input('start-btn', 'n_clicks'),
     Input('stop-btn', 'n_clicks'),
     Input('range-dropdown', 'value'),
     Input('channel-dropdown', 'value')],
    prevent_initial_call=False
)
def update_recording_state(start_clicks, stop_clicks, range_val, channel_val):
    ctx = callback_context
    
    if not ctx.triggered:
        return False, True, 'Bereit - Keine Datenaufnahme aktiv'
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Bereich oder Kanal geändert
    if trigger_id in ['range-dropdown', 'channel-dropdown']:
        # Bereich parsen
        bereich_text = range_val.replace("±", "")
        if "mV" in bereich_text:
            dmm.bereich = float(bereich_text.replace("mV", "")) / 1000.0
        else:
            dmm.bereich = float(bereich_text.replace("V", ""))
        
        dmm.channel = channel_val
        
        # Daten zurücksetzen
        with dmm.lock:
            dmm.zeit_daten.clear()
            dmm.wert_daten.clear()
            dmm.messdaten = []
            dmm.start_zeit = time.time()
        
        if dmm.datenerfassung_aktiv:
            return True, False, f'Datenaufnahme für {dmm.modus} aktiv - Bereich/Kanal geändert'
        else:
            return False, True, 'Bereit - Keine Datenaufnahme aktiv'
    
    # Start Button
    if trigger_id == 'start-btn' and start_clicks > 0:
        dmm.datenerfassung_aktiv = True
        with dmm.lock:
            dmm.messdaten = []
            dmm.zeit_daten.clear()
            dmm.wert_daten.clear()
            dmm.start_zeit = time.time()
        return True, False, f'Datenaufnahme für {dmm.modus} gestartet'
    
    # Stop Button
    if trigger_id == 'stop-btn' and stop_clicks > 0:
        dmm.datenerfassung_aktiv = False
        count = len(dmm.messdaten)
        return False, True, f'Datenaufnahme gestoppt - {count} Messpunkte aufgezeichnet'
    
    # Default state
    if dmm.datenerfassung_aktiv:
        return True, False, f'Datenaufnahme für {dmm.modus} aktiv'
    else:
        return False, True, 'Bereit - Keine Datenaufnahme aktiv'

@app.callback(
    Output("download-csv", "data"),
    [Input("csv-btn", "n_clicks")],
    prevent_initial_call=True
)
def download_csv(n_clicks):
    if n_clicks and dmm.messdaten:
        df = pd.DataFrame(dmm.messdaten)
        
        filename = f"Messdaten_{dmm.modus.replace(' ', '_')}_Kanal{dmm.channel}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    
    return None

@app.callback(
    Output('hidden-div', 'children'),
    [Input('help-btn', 'n_clicks')],
    prevent_initial_call=True
)
def show_help(n_clicks):
    if n_clicks:
        print("""
        Digitaler Multimeter für MCC 118

        Bedienung:
        1. Wählen Sie den Messmodus (derzeit nur DC Spannung)
        2. Wählen Sie den Messbereich (±10V, ±2V, ±1V, ±500mV, ±200mV)
        3. Wählen Sie den Kanal (Kanal 0 bis Kanal 7)
        4. Klicken Sie 'Aufnahme starten', um Messwerte aufzuzeichnen
        5. Klicken Sie 'Aufnahme stoppen', um die Aufzeichnung zu beenden

        Performance-Optimierungen:
        - Display-Updates alle 300ms für flüssige Bedienung
        - Chart-Updates alle 500ms für bessere Performance
        - Reduzierte Datenpunkte für schnellere Darstellung

        Hinweise:
        - Überlast wird angezeigt, wenn die Spannung den Messbereich überschreitet
        - Der MCC 118 misst Spannungen bis ±10 V
        - Die Anzeige aktualisiert sich in Echtzeit
        """)
    
    return ""

# Server starten
if __name__ == '__main__':
    # Messung starten
    dmm.start_measurement()
    
    try:
        app.run(debug=False, host='0.0.0.0', port=8050)  # Debug=False für bessere Performance
    finally:
        dmm.stop_measurement()
