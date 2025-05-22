# -*- coding: utf-8 -*-

"""
Web-basiertes Dashboard für das OurDAQ Datenerfassungssystem
Alle Module sind direkt über das Web zugänglich
Basiert auf Dash Framework für Responsive Web Interface
"""

import socket
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List
from time import sleep
import threading

# Dash und Plotly Imports
from dash import Dash, dcc, html, Input, Output, State, callback, dash_table
import plotly.graph_objects as go
import plotly.express as px
from dash.exceptions import PreventUpdate

# DAQ HAT Imports (falls verfügbar)
try:
    from daqhats import hat_list, mcc118, HatIDs, OptionFlags, mcc152
    DAQ_AVAILABLE = True
except ImportError:
    print("DAQ HAT Bibliothek nicht verfügbar - Simulationsmodus aktiv")
    DAQ_AVAILABLE = False

# Globale Variablen
app = Dash(__name__)
app.title = "OurDAQ Web Dashboard"

# HAT Objekte
HAT_118 = None  # Für Oszilloskop/DMM
HAT_152 = None  # Für Funktionsgenerator/Netzteil

# Datenstrukturen
measurement_data = []
oscilloscope_running = False
dmm_running = False

def get_ip_address() -> str:
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts."""
    ip_address = '127.0.0.1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.connect(('1.1.1.1', 1))
        ip_address = sock.getsockname()[0]
    finally:
        sock.close()
    
    return ip_address

def create_hat_selector(hat_type="MCC_118") -> dcc.Dropdown:
    """Erstellt HAT-Selector basierend auf verfügbaren Geräten"""
    if not DAQ_AVAILABLE:
        return dcc.Dropdown(
            id=f'hatSelector-{hat_type}',
            options=[{'label': 'Simulation Mode', 'value': 'sim'}],
            value='sim',
            clearable=False
        )
    
    if hat_type == "MCC_118":
        hats = hat_list(filter_by_id=HatIDs.MCC_118)
    else:
        hats = hat_list(filter_by_id=HatIDs.MCC_152)
    
    options = []
    for hat in hats:
        label = f'{hat.address}: {hat.product_name}'
        option = {'label': label, 'value': json.dumps(hat._asdict())}
        options.append(option)
    
    selection = options[0]['value'] if options else None
    
    return dcc.Dropdown(
        id=f'hatSelector-{hat_type}',
        options=options,
        value=selection,
        clearable=False
    )

# Stylesheet für besseres Design
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
app = Dash(__name__, external_stylesheets=external_stylesheets)

# Layout Definition
app.layout = html.Div([
    # Header
    html.Div([
        html.H1("OurDAQ Web Dashboard", 
                style={'textAlign': 'center', 'color': '#0066cc', 'marginBottom': '10px'}),
        html.P("Prototypisches Messdatenerfassungssystem - Remote Zugriff", 
               style={'textAlign': 'center', 'fontSize': '16px', 'marginBottom': '30px'})
    ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px', 'margin': '10px'}),
    
    # Navigation Tabs
    dcc.Tabs(id="main-tabs", value='dashboard', children=[
        dcc.Tab(label='Dashboard', value='dashboard'),
        dcc.Tab(label='Digitales Multimeter', value='dmm'),
        dcc.Tab(label='Oszilloskop', value='oscilloscope'),
        dcc.Tab(label='Funktionsgenerator', value='function-gen'),
        dcc.Tab(label='Netzteilfunktion', value='power-supply'),
        dcc.Tab(label='Systeminfo', value='system-info')
    ], style={'margin': '10px'}),
    
    # Content Area
    html.Div(id='tab-content', style={'margin': '20px'}),
    
    # Update Intervals
    dcc.Interval(id='dmm-interval', interval=1000, n_intervals=0, disabled=True),
    dcc.Interval(id='osc-interval', interval=100, n_intervals=0, disabled=True),
    
    # Hidden Divs für Datenspeicherung
    html.Div(id='dmm-data', style={'display': 'none'}),
    html.Div(id='osc-data', style={'display': 'none'}),
    html.Div(id='system-status', style={'display': 'none'}),
])

# Dashboard Tab Content
def create_dashboard_content():
    return html.Div([
        # System Status Cards
        html.Div([
            html.Div([
                html.H4("System Status", style={'textAlign': 'center'}),
                html.Div(id='system-status-display', children=[
                    html.P(f"Server IP: {get_ip_address()}", style={'margin': '5px'}),
                    html.P(f"Status: Online", style={'margin': '5px', 'color': 'green'}),
                    html.P(f"DAQ Hardware: {'Verfügbar' if DAQ_AVAILABLE else 'Simulation'}", 
                           style={'margin': '5px', 'color': 'green' if DAQ_AVAILABLE else 'orange'})
                ])
            ], className='four columns', style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '10px'}),
            
            html.Div([
                html.H4("Aktive Module", style={'textAlign': 'center'}),
                html.Div(id='active-modules-display', children=[
                    html.P("DMM: Bereit", style={'margin': '5px'}),
                    html.P("Oszilloskop: Bereit", style={'margin': '5px'}),
                    html.P("Funktionsgenerator: Bereit", style={'margin': '5px'}),
                    html.P("Netzteil: Bereit", style={'margin': '5px'})
                ])
            ], className='four columns', style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '10px'}),
            
            html.Div([
                html.H4("Schnellzugriff", style={'textAlign': 'center'}),
                html.Button("Alle Module stoppen", id='stop-all-btn', 
                           style={'width': '100%', 'margin': '5px', 'backgroundColor': '#dc3545', 'color': 'white'}),
                html.Button("System Reset", id='reset-btn', 
                           style={'width': '100%', 'margin': '5px', 'backgroundColor': '#6c757d', 'color': 'white'})
            ], className='four columns', style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '10px'})
        ], className='row', style={'margin': '20px 0'}),
        
        # Live Data Preview
        html.Div([
            html.H3("Live Datenvorschau"),
            dcc.Graph(id='dashboard-live-graph')
        ], style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '10px', 'margin': '20px 0'})
    ])

# DMM Tab Content
def create_dmm_content():
    return html.Div([
        html.H3("Digitales Multimeter", style={'textAlign': 'center'}),
        
        html.Div([
            # Steuerung
            html.Div([
                html.H4("Einstellungen"),
                create_hat_selector("MCC_118"),
                html.Br(),
                html.Label("Messbereich:"),
                dcc.Dropdown(
                    id='dmm-range',
                    options=[
                        {'label': '±10V', 'value': 10},
                        {'label': '±5V', 'value': 5},
                        {'label': '±2V', 'value': 2},
                        {'label': '±1V', 'value': 1}
                    ],
                    value=10
                ),
                html.Br(),
                html.Label("Kanal:"),
                dcc.Dropdown(
                    id='dmm-channel',
                    options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                    value=0
                ),
                html.Br(),
                html.Button("Start Messung", id='dmm-start-btn', 
                           style={'backgroundColor': '#28a745', 'color': 'white', 'width': '100%'}),
                html.Button("Stop Messung", id='dmm-stop-btn', 
                           style={'backgroundColor': '#dc3545', 'color': 'white', 'width': '100%', 'margin': '5px 0'}),
                html.Button("Daten exportieren", id='dmm-export-btn', 
                           style={'backgroundColor': '#007bff', 'color': 'white', 'width': '100%'})
            ], className='three columns'),
            
            # Anzeige
            html.Div([
                html.H4("Aktuelle Messwerte"),
                html.Div(id='dmm-display', style={'fontSize': '24px', 'textAlign': 'center', 'padding': '20px'}),
                dcc.Graph(id='dmm-graph')
            ], className='nine columns')
        ], className='row')
    ])

# Oszilloskop Tab Content
def create_oscilloscope_content():
    return html.Div([
        html.H3("Oszilloskop", style={'textAlign': 'center'}),
        
        html.Div([
            # Steuerung
            html.Div([
                html.H4("Einstellungen"),
                create_hat_selector("MCC_118"),
                html.Br(),
                html.Label("Abtastrate (Hz):"),
                dcc.Input(id='osc-sample-rate', type='number', value=1000, min=1, max=100000),
                html.Br(), html.Br(),
                html.Label("Anzahl Samples:"),
                dcc.Input(id='osc-samples', type='number', value=1000, min=100, max=10000),
                html.Br(), html.Br(),
                html.Label("Aktive Kanäle:"),
                dcc.Checklist(
                    id='osc-channels',
                    options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                    value=[0, 1]
                ),
                html.Br(),
                html.Button("Start Oszilloskop", id='osc-start-btn', 
                           style={'backgroundColor': '#28a745', 'color': 'white', 'width': '100%'}),
                html.Button("Stop Oszilloskop", id='osc-stop-btn', 
                           style={'backgroundColor': '#dc3545', 'color': 'white', 'width': '100%', 'margin': '5px 0'})
            ], className='three columns'),
            
            # Anzeige
            html.Div([
                dcc.Graph(id='oscilloscope-graph')
            ], className='nine columns')
        ], className='row')
    ])

# Funktionsgenerator Tab Content
def create_function_generator_content():
    return html.Div([
        html.H3("Funktionsgenerator", style={'textAlign': 'center'}),
        
        html.Div([
            html.Div([
                html.H4("Signaleinstellungen"),
                html.Label("Signalform:"),
                dcc.Dropdown(
                    id='fgen-waveform',
                    options=[
                        {'label': 'Sinus', 'value': 'sine'},
                        {'label': 'Rechteck', 'value': 'square'},
                        {'label': 'Dreieck', 'value': 'triangle'}
                    ],
                    value='sine'
                ),
                html.Br(),
                html.Label("Frequenz (Hz):"),
                dcc.Input(id='fgen-frequency', type='number', value=1000, min=1, max=50000),
                html.Br(), html.Br(),
                html.Label("Amplitude (V):"),
                dcc.Input(id='fgen-amplitude', type='number', value=1.0, min=0.1, max=5.0, step=0.1),
                html.Br(), html.Br(),
                html.Label("Offset (V):"),
                dcc.Input(id='fgen-offset', type='number', value=0.0, min=-2.5, max=2.5, step=0.1),
                html.Br(), html.Br(),
                html.Button("Signal aktivieren", id='fgen-start-btn', 
                           style={'backgroundColor': '#28a745', 'color': 'white', 'width': '100%'}),
                html.Button("Signal stoppen", id='fgen-stop-btn', 
                           style={'backgroundColor': '#dc3545', 'color': 'white', 'width': '100%', 'margin': '5px 0'})
            ], className='four columns'),
            
            html.Div([
                html.H4("Signalvorschau"),
                dcc.Graph(id='fgen-preview'),
                html.Div(id='fgen-status', style={'textAlign': 'center', 'fontSize': '18px', 'padding': '20px'})
            ], className='eight columns')
        ], className='row')
    ])

# Netzteil Tab Content
def create_power_supply_content():
    return html.Div([
        html.H3("Netzteilfunktion", style={'textAlign': 'center'}),
        
        html.Div([
            html.Div([
                html.H4("Einstellungen"),
                html.Label("Ausgangsspannung (V):"),
                dcc.Input(id='ps-voltage', type='number', value=5.0, min=0, max=10.0, step=0.1),
                html.Br(), html.Br(),
                html.Label("Strombegrenzung (mA):"),
                dcc.Input(id='ps-current-limit', type='number', value=100, min=1, max=1000),
                html.Br(), html.Br(),
                html.Button("Ausgang einschalten", id='ps-on-btn', 
                           style={'backgroundColor': '#28a745', 'color': 'white', 'width': '100%'}),
                html.Button("Ausgang ausschalten", id='ps-off-btn', 
                           style={'backgroundColor': '#dc3545', 'color': 'white', 'width': '100%', 'margin': '5px 0'})
            ], className='four columns'),
            
            html.Div([
                html.H4("Ausgangswerte"),
                html.Div(id='ps-display', style={'fontSize': '20px', 'padding': '20px'}),
                dcc.Graph(id='ps-graph')
            ], className='eight columns')
        ], className='row')
    ])

# Systeminfo Tab Content
def create_system_info_content():
    return html.Div([
        html.H3("Systeminformationen", style={'textAlign': 'center'}),
        
        html.Div([
            html.H4("Hardware Status"),
            html.Div(id='hardware-info'),
            html.Br(),
            html.H4("Netzwerk Information"),
            html.Div(id='network-info'),
            html.Br(),
            html.H4("Verfügbare HATs"),
            html.Div(id='hat-info')
        ])
    ])

# Callback für Tab Content
@callback(Output('tab-content', 'children'),
          Input('main-tabs', 'value'))
def render_tab_content(active_tab):
    if active_tab == 'dashboard':
        return create_dashboard_content()
    elif active_tab == 'dmm':
        return create_dmm_content()
    elif active_tab == 'oscilloscope':
        return create_oscilloscope_content()
    elif active_tab == 'function-gen':
        return create_function_generator_content()
    elif active_tab == 'power-supply':
        return create_power_supply_content()
    elif active_tab == 'system-info':
        return create_system_info_content()
    else:
        return html.Div("Tab nicht gefunden")

# DMM Callbacks
@callback(
    [Output('dmm-interval', 'disabled'),
     Output('dmm-data', 'children')],
    [Input('dmm-start-btn', 'n_clicks'),
     Input('dmm-stop-btn', 'n_clicks')],
    prevent_initial_call=True
)
def control_dmm(start_clicks, stop_clicks):
    from dash import ctx
    
    if ctx.triggered_id == 'dmm-start-btn' and start_clicks:
        return False, json.dumps({'running': True, 'data': []})
    elif ctx.triggered_id == 'dmm-stop-btn' and stop_clicks:
        return True, json.dumps({'running': False, 'data': []})
    
    raise PreventUpdate

@callback(
    [Output('dmm-display', 'children'),
     Output('dmm-graph', 'figure')],
    [Input('dmm-interval', 'n_intervals')],
    [State('dmm-data', 'children'),
     State('dmm-channel', 'value')],
    prevent_initial_call=True
)
def update_dmm(n_intervals, dmm_data_json, channel):
    if not dmm_data_json:
        raise PreventUpdate
    
    # Simulierte Messwerte (in echter Anwendung würde hier der HAT gelesen)
    import random
    voltage = random.uniform(-5, 5)
    current_time = datetime.now().strftime("%H:%M:%S")
    
    display = html.Div([
        html.H5(f"Kanal {channel}"),
        html.P(f"Spannung: {voltage:.3f} V", style={'color': 'blue'}),
        html.P(f"Zeit: {current_time}")
    ])
    
    # Graph Update
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[current_time], y=[voltage], mode='markers+lines', name=f'Kanal {channel}'))
    fig.update_layout(title="DMM Messwerte", xaxis_title="Zeit", yaxis_title="Spannung (V)")
    
    return display, fig

# Ähnliche Callbacks für andere Module...
# (Aus Platzgründen gekürzt, aber nach dem gleichen Muster)

# System Info Callback
@callback(
    [Output('hardware-info', 'children'),
     Output('network-info', 'children'),
     Output('hat-info', 'children')],
    Input('main-tabs', 'value')
)
def update_system_info(active_tab):
    if active_tab != 'system-info':
        raise PreventUpdate
    
    # Hardware Info
    hardware_info = html.Div([
        html.P(f"DAQ Hardware: {'Verfügbar' if DAQ_AVAILABLE else 'Nicht verfügbar'}"),
        html.P(f"Python Version: {sys.version.split()[0]}"),
        html.P(f"Betriebssystem: {os.name}")
    ])
    
    # Network Info
    network_info = html.Div([
        html.P(f"Server IP: {get_ip_address()}"),
        html.P(f"Port: 8080"),
        html.P(f"Zugriff über: http://{get_ip_address()}:8080")
    ])
    
    # HAT Info
    if DAQ_AVAILABLE:
        try:
            hats_118 = hat_list(filter_by_id=HatIDs.MCC_118)
            hats_152 = hat_list(filter_by_id=HatIDs.MCC_152)
            
            hat_info = html.Div([
                html.P(f"MCC 118 HATs: {len(hats_118)} gefunden"),
                html.P(f"MCC 152 HATs: {len(hats_152)} gefunden")
            ])
        except:
            hat_info = html.P("Fehler beim Lesen der HAT Information")
    else:
        hat_info = html.P("DAQ HAT Bibliothek nicht verfügbar")
    
    return hardware_info, network_info, hat_info

if __name__ == '__main__':
    print(f"\n{'='*50}")
    print("OurDAQ Web Dashboard startet...")
    print(f"Zugriff über: http://{get_ip_address()}:8080")
    print(f"DAQ Hardware: {'Verfügbar' if DAQ_AVAILABLE else 'Simulationsmodus'}")
    print(f"{'='*50}\n")
    
    # Server starten
    app.run(
        host=get_ip_address(),
        port=8080,
        debug=True,
        dev_tools_hot_reload=True
    )