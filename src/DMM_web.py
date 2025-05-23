# -*- coding: utf-8 -*-
"""
Web-basierter Digitaler Multimeter für MCC 118 mit Dash
Ein LabVIEW-ähnlicher DMM als Webanwendung mit Dash/Plotly
Mit Echtzeitdiagramm und CSV-Download
Performance-optimiert für Raspberry Pi 5
Optimiert für automatische Bildschirmanpassung mit aktueller Wert-Anzeige
"""

import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import plotly.graph_objs as go
import pandas as pd
import time
from datetime import datetime
import threading
from collections import deque
import os
from daqhats import mcc118, OptionFlags, HatError

class DashDMM:
    def __init__(self):
        self.hat = None
        self.init_mcc118()
        
        self.modus = "DC Spannung"  # Standardmodus
        self.bereich = 10.0  # MCC 118 fester Bereich ±10V
        self.channel = 0
        self.measuring = False  # Kontinuierliche Messung für Display
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
        self.max_punkte = 50  # Erhöht für bessere Darstellung
        self.zeit_daten = deque(maxlen=self.max_punkte)
        self.wert_daten = deque(maxlen=self.max_punkte)
        self.start_zeit = time.time()
        
        # Cached Messwerte
        self.display_cache = {
            'wert': 0.0,
            'timestamp': time.time()
        }
        
        # Aktueller Wert für Chart-Anzeige
        self.current_value = 0.0
        
        # Measurement Thread
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
    
    def start_measurement(self):
        """Startet die kontinuierliche Messung für Display"""
        if not self.running:
            self.running = True
            self.measuring = True
            self.measurement_thread = threading.Thread(target=self._measurement_loop)
            self.measurement_thread.daemon = True
            self.measurement_thread.start()
    
    def stop_measurement(self):
        """Stoppt alle Messungen"""
        self.running = False
        self.measuring = False
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
        """Stoppt die Datenaufzeichnung"""
        self.recording = False
        self.paused = False
    
    def _measurement_loop(self):
        """Hauptschleife für kontinuierliche Messungen"""
        while self.running:
            try:
                if self.hat:
                    wert = self.hat.a_in_read(self.channel, OptionFlags.DEFAULT)
                else:
                    # Simulation für Tests
                    import random
                    wert = random.uniform(-5, 5)
                
                # Update Display Cache und aktueller Wert
                with self.lock:
                    self.display_cache.update({
                        'wert': wert,
                        'timestamp': time.time()
                    })
                    self.current_value = wert
                
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
                
                time.sleep(0.1)  # 10Hz für gute Responsivität
                
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
    
    def get_current_converted_value(self):
        """Gibt den aktuellen konvertierten Wert zurück"""
        with self.lock:
            wert = self.current_value
            
        # Einheitenberechnung je nach Modus
        if self.modus == "DC Spannung":
            return wert
        elif self.modus == "AC Spannung":
            return abs(wert) * 0.707  # RMS approximation
        elif self.modus == "DC Strom":
            return wert / 1.0  # A = V / 1Ω
        elif self.modus == "AC Strom":
            return abs(wert) * 0.707 / 1.0  # RMS current
        return wert

# Globale DMM-Instanz
dmm = DashDMM()

# Dash App initialisieren
app = dash.Dash(__name__)
app.title = "OurDAQ - Web Digitalmultimeter"

# Responsive CSS für automatische Bildschirmanpassung
responsive_styles = {
    'container': {
        'maxWidth': '1400px',
        'margin': '0 auto',
        'padding': '10px',
        'fontFamily': 'Arial, sans-serif'
    },
    'header': {
        'textAlign': 'center',
        'marginBottom': '20px'
    },
    'display_container': {
        'marginBottom': '20px',
        'display': 'flex',
        'flexDirection': 'column',
        'alignItems': 'center'
    },
    'measurement_display': {
        'backgroundColor': '#000',
        'color': '#00d2d2',
        'padding': '30px',
        'borderRadius': '10px',
        'textAlign': 'center',
        'minHeight': '100px',
        'fontSize': 'clamp(32px, 5vw, 56px)',  # Responsive Schriftgröße
        'fontWeight': 'bold',
        'fontFamily': 'Courier New',
        'marginBottom': '15px',
        'border': '2px solid #00d2d2',
        'width': '100%',
        'maxWidth': '600px',
        'boxSizing': 'border-box'
    },
    'controls_container': {
        'display': 'grid',
        'gridTemplateColumns': 'repeat(auto-fit, minmax(300px, 1fr))',
        'gap': '15px',
        'marginBottom': '20px'
    },
    'control_panel': {
        'backgroundColor': '#f8f8f8',
        'padding': '15px',
        'borderRadius': '8px',
        'border': '1px solid #ddd'
    },
    'button_container': {
        'display': 'flex',
        'flexWrap': 'wrap',
        'gap': '10px',
        'marginBottom': '20px',
        'justifyContent': 'center'
    },
    'button': {
        'border': 'none',
        'padding': '12px 20px',
        'borderRadius': '5px',
        'fontWeight': 'bold',
        'cursor': 'pointer',
        'fontSize': '14px',
        'minWidth': '140px',
        'transition': 'all 0.3s ease'
    },
    'chart_container': {
        'marginBottom': '20px',
        'border': '1px solid #ddd',
        'borderRadius': '8px',
        'padding': '10px'
    },
    'status_bar': {
        'backgroundColor': '#333',
        'color': 'white',
        'padding': '15px',
        'borderRadius': '5px',
        'fontWeight': 'bold',
        'textAlign': 'center'
    }
}

# Layout der App mit responsivem Design
app.layout = html.Div([
    # Header
    html.Div([
        html.H1("OurDAQ - Web Digitalmultimeter", 
                style={'color': '#333', 'fontSize': 'clamp(24px, 4vw, 36px)'}),
        html.Div(id='connection-status', 
                style={'padding': '8px', 'borderRadius': '3px',
                       'backgroundColor': '#4CAF50' if dmm.hat else '#FF9800', 
                       'color': 'white', 'fontWeight': 'bold',
                       'fontSize': 'clamp(12px, 2vw, 14px)', 'marginTop': '10px'},
                children='MCC 118 Verbunden' if dmm.hat else 'Simulation Modus')
    ], style=responsive_styles['header']),
    
    # Messwert Display
    html.Div([
        html.Div(id='measurement-display',
                style=responsive_styles['measurement_display'],
                children='0.000000 V DC'),
        html.Div('Messbereich: ±10V (MCC 118 Maximum)', 
                style={'textAlign': 'center', 'color': '#666', 'fontSize': 'clamp(12px, 2vw, 14px)',
                       'marginBottom': '10px'})
    ], style=responsive_styles['display_container']),
    
    # Steuerungsbereich - Responsive Grid
    html.Div([
        # Messmodus-Auswahl
        html.Div([
            html.H3("Messmodus", style={'fontWeight': 'bold', 'color': '#333', 
                                      'fontSize': 'clamp(16px, 3vw, 20px)'}),
            dcc.RadioItems(
                id='mode-selector',
                options=[
                    {'label': 'DC Spannung', 'value': 'DC Spannung'},
                    {'label': 'AC Spannung', 'value': 'AC Spannung'},
                    {'label': 'DC Strom', 'value': 'DC Strom'},
                    {'label': 'AC Strom', 'value': 'AC Strom'}
                ],
                value='DC Spannung',
                style={'marginBottom': '15px'},
                labelStyle={'display': 'block', 'marginBottom': '8px', 
                          'fontSize': 'clamp(14px, 2.5vw, 16px)'}
            )
        ], style=responsive_styles['control_panel']),
        
        # Kanal-Auswahl
        html.Div([
            html.H3("Kanal", style={'fontWeight': 'bold', 'color': '#333',
                                  'fontSize': 'clamp(16px, 3vw, 20px)'}),
            dcc.Dropdown(
                id='channel-dropdown',
                options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                value=0,
                style={'marginBottom': '15px', 'fontSize': 'clamp(12px, 2vw, 14px)'}
            ),
            # Hinweise für verschiedene Modi
            html.Div(id='mode-info', 
                    style={'fontSize': 'clamp(11px, 2vw, 13px)', 'color': '#666', 'marginTop': '10px'})
        ], style=responsive_styles['control_panel'])
    ], style=responsive_styles['controls_container']),
    
    # Action Buttons - Responsive Layout
    html.Div([
        html.Button('Messung konfigurieren', id='config-btn', n_clicks=0,
                   style={**responsive_styles['button'], 'backgroundColor': '#2196F3', 'color': 'white'}),
        html.Button('Aufzeichnung starten', id='start-record-btn', n_clicks=0, disabled=True,
                   style={**responsive_styles['button'], 'backgroundColor': '#4CAF50', 'color': 'white'}),
        html.Button('Pausieren', id='pause-btn', n_clicks=0, disabled=True,
                   style={**responsive_styles['button'], 'backgroundColor': '#FF9800', 'color': 'white'}),
        html.Button('Stoppen', id='stop-record-btn', n_clicks=0, disabled=True,
                   style={**responsive_styles['button'], 'backgroundColor': '#F44336', 'color': 'white'}),
        html.Button('CSV speichern', id='csv-btn', n_clicks=0, disabled=True,
                   style={**responsive_styles['button'], 'backgroundColor': '#607D8B', 'color': 'white'})
    ], style=responsive_styles['button_container']),
    
    # Diagramm mit verbesserter Responsivität
    html.Div([
        dcc.Graph(id='measurement-chart',
                 config={'displayModeBar': True, 'responsive': True},
                 style={'height': 'clamp(300px, 50vh, 500px)', 'width': '100%'})
    ], style=responsive_styles['chart_container']),
    
    # Status Bar
    html.Div(id='status-bar',
            style=responsive_styles['status_bar'],
            children='Bereit - Klicken Sie "Messung konfigurieren" zum Starten'),
    
    # Speicher-Dialog
    html.Div(id='save-dialog', style={'display': 'none'}),
    
    # Interval für Updates - optimiert für Pi 5
    dcc.Interval(id='display-interval', interval=200, n_intervals=0, disabled=True),  # 5Hz Display
    dcc.Interval(id='chart-interval', interval=500, n_intervals=0, disabled=True),    # 2Hz Chart
    
    # Download component
    dcc.Download(id="download-csv")
], style=responsive_styles['container'])

@app.callback(
    [Output('measurement-display', 'children'),
     Output('display-interval', 'disabled'),
     Output('mode-info', 'children')],
    [Input('config-btn', 'n_clicks'),
     Input('display-interval', 'n_intervals'),
     Input('channel-dropdown', 'value'),
     Input('mode-selector', 'value')]
)
def update_display(config_clicks, n_intervals, channel, mode):
    ctx = callback_context
    
    if not ctx.triggered:
        return no_update, True, no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Hinweis für verschiedene Modi
    mode_info = ""
    if mode == "DC Spannung":
        mode_info = "Direkte Spannungsmessung mit MCC 118"
    elif mode == "AC Spannung":
        mode_info = "AC Spannung: Benötigt AC-DC Wandler oder RMS-Berechnung"
    elif mode == "DC Strom":
        mode_info = "DC Strom: Benötigt Shunt-Widerstand (V = I × R)"
    elif mode == "AC Strom":
        mode_info = "AC Strom: Benötigt Stromwandler oder Shunt + RMS"
    
    # Konfiguration gestartet
    if trigger_id == 'config-btn' and config_clicks > 0:
        dmm.channel = channel
        dmm.modus = mode
        dmm.start_measurement()
        unit = dmm.mode_units[mode]
        return f'0.000000 {unit}', False, mode_info
    
    # Modus oder Kanal geändert
    if trigger_id in ['channel-dropdown', 'mode-selector']:
        dmm.channel = channel
        dmm.modus = mode
        if dmm.measuring:
            return no_update, False, mode_info
        return no_update, True, mode_info
    
    # Display Update
    if trigger_id == 'display-interval' and dmm.measuring:
        display_data = dmm.get_display_data()
        wert = display_data['wert']
        
        # Einheitenberechnung je nach Modus
        if dmm.modus == "DC Spannung":
            display_value = wert
        elif dmm.modus == "AC Spannung":
            # Vereinfachte AC-Berechnung (RMS für Sinussignal)
            display_value = abs(wert) * 0.707  # RMS approximation
        elif dmm.modus == "DC Strom":
            # Annahme: 1Ω Shunt-Widerstand, I = V/R
            display_value = wert / 1.0  # A = V / 1Ω
        elif dmm.modus == "AC Strom":
            # AC Strom mit RMS
            display_value = abs(wert) * 0.707 / 1.0  # RMS current
        
        unit = dmm.mode_units[dmm.modus]
        
        # Dezimalstellen je nach Messgröße
        if "Strom" in dmm.modus:
            display_text = f"{display_value:.6f} {unit}"
        else:
            display_text = f"{display_value:.6f} {unit}"
        
        return display_text, False, mode_info
    
    return no_update, no_update, mode_info

@app.callback(
    [Output('measurement-chart', 'figure')],
    [Input('chart-interval', 'n_intervals')]
)
def update_chart(n):
    if not dmm.recording:
        # Leeres Chart wenn keine Aufzeichnung
        fig = go.Figure()
        fig.update_layout(
            title={
                'text': 'Messwert-Verlauf',
                'font': {'size': 18}
            },
            xaxis_title='Zeit (s)',
            yaxis_title='Spannung (V)',
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=60, r=60, t=60, b=60),
            font=dict(size=12),
            # Responsive Konfiguration
            autosize=True
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
                converted_y_data.append(wert / 1.0)  # 1Ω Shunt
            elif dmm.modus == "AC Strom":
                converted_y_data.append(abs(wert) * 0.707 / 1.0)
        
        fig.add_trace(go.Scatter(
            x=x_data,
            y=converted_y_data,
            mode='lines+markers',
            name=dmm.modus,
            line=dict(color='#00d2d2', width=3),
            marker=dict(size=6, color='#00d2d2'),
            hovertemplate='Zeit: %{x:.2f}s<br>Wert: %{y:.6f}<extra></extra>'
        ))
        
        # Aktueller Wert am letzten Punkt anzeigen
        if x_data and converted_y_data:
            last_x = x_data[-1]
            last_y = converted_y_data[-1]
            current_value = dmm.get_current_converted_value()
            unit = dmm.mode_units[dmm.modus]
            
            # Annotation für aktuellen Wert am rechten Rand
            fig.add_annotation(
                x=last_x,
                y=last_y,
                text=f"Aktuell: {current_value:.6f} {unit}",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="#ff6600",
                ax=60,  # Pfeil-Offset
                ay=0,
                bgcolor="rgba(255, 255, 255, 0.9)",
                bordercolor="#ff6600",
                borderwidth=2,
                font=dict(size=12, color="#333")
            )
            
            # Markierung des aktuellen Punktes
            fig.add_trace(go.Scatter(
                x=[last_x],
                y=[last_y],
                mode='markers',
                marker=dict(size=12, color='#ff6600', symbol='circle'),
                name='Aktueller Wert',
                showlegend=False,
                hovertemplate=f'Aktueller Wert: {current_value:.6f} {unit}<extra></extra>'
            ))
        
        # Automatische Y-Achsen-Skalierung
        if converted_y_data:
            y_min = min(converted_y_data)
            y_max = max(converted_y_data)
            y_range = y_max - y_min
            
            if y_range < 0.1:
                y_range = 0.1
            
            margin = y_range * 0.15  # Größerer Rand für Annotation
            y_axis_range = [y_min - margin, y_max + margin]
            
            # Begrenzung je nach Messmodus
            if "Spannung" in dmm.modus:
                y_axis_range[0] = max(y_axis_range[0], -10.5)
                y_axis_range[1] = min(y_axis_range[1], 10.5)
            else:  # Strom
                y_axis_range[0] = max(y_axis_range[0], -10.5)  # 10A max bei 1Ω Shunt
                y_axis_range[1] = min(y_axis_range[1], 10.5)
        else:
            y_axis_range = [-1, 1]
    else:
        y_axis_range = [-1, 1]
    
    # Y-Achsen-Beschriftung je nach Modus
    if "Spannung" in dmm.modus:
        y_title = "Spannung (V)"
    else:
        y_title = "Strom (A)"
    
    fig.update_layout(
        title={
            'text': f'{dmm.modus}-Verlauf (Kanal {dmm.channel})',
            'font': {'size': 18}
        },
        xaxis_title='Zeit (s)',
        yaxis_title=y_title,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=60, r=120, t=60, b=60),  # Rechter Rand vergrößert für Annotation
        font=dict(size=12),
        # Responsive Konfiguration
        autosize=True,
        # Grid und Achsen-Konfiguration
        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='LightGray'),
        yaxis=dict(range=y_axis_range, showgrid=True, gridwidth=1, gridcolor='LightGray')
    )
    
    return [fig]

@app.callback(
    [Output('start-record-btn', 'disabled'),
     Output('pause-btn', 'disabled'),
     Output('stop-record-btn', 'disabled'),
     Output('csv-btn', 'disabled'),
     Output('pause-btn', 'children'),
     Output('status-bar', 'children'),
     Output('chart-interval', 'disabled')],
    [Input('config-btn', 'n_clicks'),
     Input('start-record-btn', 'n_clicks'),
     Input('pause-btn', 'n_clicks'),
     Input('stop-record-btn', 'n_clicks')]
)
def update_controls(config_clicks, start_clicks, pause_clicks, stop_clicks):
    ctx = callback_context
    
    if not ctx.triggered:
        return True, True, True, True, 'Pausieren', 'Bereit - Klicken Sie "Messung konfigurieren" zum Starten', True
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Konfiguration
    if trigger_id == 'config-btn' and config_clicks > 0:
        return False, True, True, True, 'Pausieren', f'Messung aktiv - Kanal {dmm.channel} - Bereit für Aufzeichnung', True
    
    # Aufzeichnung starten
    if trigger_id == 'start-record-btn' and start_clicks > 0:
        dmm.start_recording()
        return True, False, False, True, 'Pausieren', f'Aufzeichnung läuft - Kanal {dmm.channel}', False
    
    # Pausieren/Fortsetzen
    if trigger_id == 'pause-btn' and pause_clicks > 0:
        if dmm.paused:
            dmm.resume_recording()
            return True, False, False, True, 'Pausieren', f'Aufzeichnung fortgesetzt - Kanal {dmm.channel}', False
        else:
            dmm.pause_recording()
            return True, False, False, True, 'Fortsetzen', f'Aufzeichnung pausiert - Kanal {dmm.channel}', False
    
    # Stoppen
    if trigger_id == 'stop-record-btn' and stop_clicks > 0:
        dmm.stop_recording()
        count = len(dmm.messdaten)
        return False, True, True, False, 'Pausieren', f'Aufzeichnung gestoppt - {count} Messpunkte - Bereit zum Speichern', True
    
    return no_update, no_update, no_update, no_update, no_update, no_update, no_update

@app.callback(
    Output("download-csv", "data"),
    [Input("csv-btn", "n_clicks")],
    prevent_initial_call=True
)
def download_csv(n_clicks):
    if n_clicks and dmm.messdaten:
        df = pd.DataFrame(dmm.messdaten)
        
        # Standardpfad für Downloads
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"OurDAQ_Messdaten_Kanal{dmm.channel}_{timestamp}.csv"
        
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    
    return no_update

# Server starten
if __name__ == '__main__':
    try:
        # Für Dash 2.x verwenden wir run() ohne run_server()
        app.run(debug=False, host='0.0.0.0', port=8050, 
                dev_tools_hot_reload=False,  # Deaktiviert für bessere Performance
                threaded=True)
    finally:
        dmm.stop_measurement()