# -*- coding: utf-8 -*-

"""
Web-basiertes Dashboard für das OurDAQ Datenerfassungssystem
Alle Module sind direkt über das Web zugänglich
Mit Logos, Icons und erweiterten Funktionen
"""

import socket
import json
import os
import sys
import csv
import io
import base64
from datetime import datetime
from typing import Dict, Any, List
from time import sleep
import threading
import numpy as np
import pandas as pd

# Dash und Plotly Imports
from dash import Dash, dcc, html, Input, Output, State, callback, dash_table
import plotly.graph_objects as go
import plotly.express as px
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

# DAQ HAT Imports (falls verfügbar)
try:
    from daqhats import hat_list, mcc118, HatIDs, OptionFlags, mcc152
    DAQ_AVAILABLE = True
except ImportError:
    print("DAQ HAT Bibliothek nicht verfügbar - Simulationsmodus aktiv")
    DAQ_AVAILABLE = False

# Globale Variablen
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(APP_ROOT, "assets")
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
ICONS_DIR = os.path.join(ASSETS_DIR, "icons")

app = Dash(__name__, assets_folder=ASSETS_DIR, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "OurDAQ Web Dashboard"

# HAT Objekte
HAT_118 = None
HAT_152 = None

# Datenstrukturen
measurement_data = {
    'dmm': [],
    'osc': [],
    'fgen': [],
    'ps': []
}
oscilloscope_running = False
dmm_running = False
fgen_running = False
ps_running = False
dmm_mode = "simulation"  # "simulation", "realtime_demo", oder HAT-Adresse
dmm_measurement_type = "DC_VOLTAGE"  # DC_VOLTAGE, AC_VOLTAGE, DC_CURRENT, AC_CURRENT

def erstelle_ressourcen_verzeichnisse():
    """Erstellt die Ressourcenverzeichnisse, falls sie noch nicht existieren"""
    for directory in [ASSETS_DIR, IMAGES_DIR, ICONS_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)

def get_ip_address() -> str:
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts."""
    ip_address = '127.0.0.1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('1.1.1.1', 1))
        ip_address = sock.getsockname()[0]
    except Exception:
        pass
    finally:
        sock.close()
    return ip_address

def create_svg_logo():
    """Erstellt das OurDAQ Logo als SVG"""
    return """
    <svg width="200" height="80" viewBox="0 0 200 80" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#0066cc;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#0099ff;stop-opacity:1" />
            </linearGradient>
        </defs>
        <rect width="200" height="80" rx="10" fill="url(#logoGradient)"/>
        <text x="100" y="30" font-family="Arial, sans-serif" font-size="24" font-weight="bold" 
              text-anchor="middle" fill="white">OurDAQ</text>
        <text x="100" y="50" font-family="Arial, sans-serif" font-size="12" 
              text-anchor="middle" fill="white">Data Acquisition System</text>
        <circle cx="20" cy="60" r="3" fill="white"/>
        <circle cx="30" cy="60" r="3" fill="white"/>
        <circle cx="40" cy="60" r="3" fill="white"/>
        <line x1="50" y1="60" x2="150" y2="60" stroke="white" stroke-width="2"/>
        <circle cx="160" cy="60" r="3" fill="white"/>
        <circle cx="170" cy="60" r="3" fill="white"/>
        <circle cx="180" cy="60" r="3" fill="white"/>
    </svg>
    """

def create_module_icon(module_type):
    """Erstellt SVG-Icons für verschiedene Module"""
    icons = {
        'dmm': """
        <svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="8" width="56" height="48" rx="4" fill="#2c3e50" stroke="#34495e" stroke-width="2"/>
            <rect x="8" y="12" width="48" height="20" rx="2" fill="#1abc9c"/>
            <text x="32" y="26" font-family="monospace" font-size="12" text-anchor="middle" fill="white">8.888</text>
            <circle cx="16" cy="44" r="3" fill="#e74c3c"/>
            <circle cx="48" cy="44" r="3" fill="#000"/>
            <rect x="12" y="48" width="8" height="8" fill="#95a5a6"/>
            <rect x="44" y="48" width="8" height="8" fill="#95a5a6"/>
        </svg>
        """,
        'oscilloscope': """
        <svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="8" width="56" height="48" rx="4" fill="#2c3e50" stroke="#34495e" stroke-width="2"/>
            <rect x="8" y="12" width="48" height="32" rx="2" fill="#0f3460"/>
            <polyline points="12,28 20,20 28,36 36,16 44,32 52,24" 
                      stroke="#00ff00" stroke-width="2" fill="none"/>
            <line x1="8" y1="28" x2="56" y2="28" stroke="#333" stroke-width="1"/>
            <line x1="32" y1="12" x2="32" y2="44" stroke="#333" stroke-width="1"/>
            <circle cx="16" cy="52" r="2" fill="#e74c3c"/>
            <circle cx="48" cy="52" r="2" fill="#e74c3c"/>
        </svg>
        """,
        'function_gen': """
        <svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="8" width="56" height="48" rx="4" fill="#2c3e50" stroke="#34495e" stroke-width="2"/>
            <rect x="8" y="12" width="48" height="20" rx="2" fill="#8e44ad"/>
            <path d="M12,22 Q20,16 28,22 T44,22 Q48,16 52,22" 
                  stroke="#fff" stroke-width="2" fill="none"/>
            <rect x="12" y="36" width="12" height="8" fill="#e74c3c"/>
            <rect x="26" y="36" width="12" height="8" fill="#f39c12"/>
            <rect x="40" y="36" width="12" height="8" fill="#27ae60"/>
            <text x="32" y="52" font-family="Arial" font-size="8" text-anchor="middle" fill="white">FGEN</text>
        </svg>
        """,
        'power_supply': """
        <svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="8" width="56" height="48" rx="4" fill="#2c3e50" stroke="#34495e" stroke-width="2"/>
            <rect x="8" y="12" width="24" height="16" rx="2" fill="#e74c3c"/>
            <rect x="32" y="12" width="24" height="16" rx="2" fill="#27ae60"/>
            <text x="20" y="22" font-family="monospace" font-size="8" text-anchor="middle" fill="white">12.0V</text>
            <text x="44" y="22" font-family="monospace" font-size="8" text-anchor="middle" fill="white">0.5A</text>
            <circle cx="20" cy="40" r="8" fill="#f39c12"/>
            <text x="20" y="44" font-family="Arial" font-size="12" text-anchor="middle" fill="white">+</text>
            <circle cx="44" cy="40" r="8" fill="#95a5a6"/>
            <text x="44" y="44" font-family="Arial" font-size="12" text-anchor="middle" fill="white">-</text>
        </svg>
        """
    }
    return icons.get(module_type, "")

def create_hat_selector(hat_type="MCC_118") -> dcc.Dropdown:
    """Erstellt HAT-Selector mit Simulation und Echtzeit-Modi"""
    options = [
        {'label': '🔄 Simulation Mode', 'value': 'simulation'},
        {'label': '⚡ Echtzeit Mode (Demo)', 'value': 'realtime_demo'}
    ]
    
    if DAQ_AVAILABLE:
        if hat_type == "MCC_118":
            hats = hat_list(filter_by_id=HatIDs.MCC_118)
        else:
            hats = hat_list(filter_by_id=HatIDs.MCC_152)
        
        for hat in hats:
            label = f'🔧 {hat.address}: {hat.product_name}'
            option = {'label': label, 'value': json.dumps(hat._asdict())}
            options.append(option)
    
    return dcc.Dropdown(
        id=f'hatSelector-{hat_type}',
        options=options,
        value='simulation',
        clearable=False
    )

# Layout Definition mit verbessertem Design
app.layout = dbc.Container([
    # Header mit Logo
    dbc.Row([
        dbc.Col([
            html.Div([
                html.Img(
                    src="/assets/images/OurDAQ_logo.png",
                    style={'height': '80px', 'margin-right': '20px'},
                    alt="OurDAQ Logo"
                ) if os.path.exists(os.path.join(IMAGES_DIR, "OurDAQ_logo.png")) else
                html.Div(
                    create_svg_logo(),
                    style={'display': 'inline-block', 'margin-right': '20px'}
                ),
                html.Div([
                    html.H1("OurDAQ Web Dashboard",
                           style={'color': '#0066cc', 'marginBottom': '5px'}),
                    html.P("Prototypisches Messdatenerfassungssystem - Remote Zugriff",
                          style={'fontSize': '16px', 'color': '#666'})
                ], style={'display': 'inline-block', 'vertical-align': 'middle'}),
                html.Img(
                    src="/assets/images/OHM_logo.png",
                    style={'height': '80px', 'margin-left': '20px'},
                    alt="OHM Logo"
                ) if os.path.exists(os.path.join(IMAGES_DIR, "OHM_logo.png")) else
                html.Span(
                    "TH Nürnberg",
                    style={'fontSize': '16px', 'color': '#0066cc', 'margin-left': '20px'}
                )
            ], style={
                'textAlign': 'center',
                'padding': '20px',
                'backgroundColor': '#f8f9fa',
                'borderRadius': '15px',
                'margin': '10px',
                'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'center'
            })
        ])
    ]),
    
    # Navigation Tabs mit Icons
    dbc.Row([
        dbc.Col([
            dbc.Tabs(id="main-tabs", active_tab='dashboard', children=[
                dbc.Tab(label='📊 Dashboard', tab_id='dashboard'),
                dbc.Tab(label='🔌 Multimeter', tab_id='dmm'),
                dbc.Tab(label='📺 Oszilloskop', tab_id='oscilloscope'),
                dbc.Tab(label='🌊 Funktionsgenerator', tab_id='function-gen'),
                dbc.Tab(label='⚡ Netzteil', tab_id='power-supply'),
                dbc.Tab(label='⚙️ System', tab_id='system-info')
            ], style={'margin': '10px'})
        ])
    ]),
    
    # Content Area
    dbc.Row([
        dbc.Col([
            html.Div(id='tab-content', style={'margin': '20px'})
        ])
    ]),
    
    # Update Intervals
    dcc.Interval(id='dmm-interval', interval=1000, n_intervals=0, disabled=True),
    dcc.Interval(id='osc-interval', interval=100, n_intervals=0, disabled=True),
    dcc.Interval(id='fgen-interval', interval=1000, n_intervals=0, disabled=True),
    dcc.Interval(id='ps-interval', interval=1000, n_intervals=0, disabled=True),
    
    # Hidden Divs für Datenspeicherung
    html.Div(id='dmm-data', style={'display': 'none'}),
    html.Div(id='osc-data', style={'display': 'none'}),
    html.Div(id='fgen-data', style={'display': 'none'}),
    html.Div(id='ps-data', style={'display': 'none'}),
    html.Div(id='system-status', style={'display': 'none'}),
    
    # Download Component
    dcc.Download(id="download-csv")
], fluid=True)

# Dashboard Tab Content mit Icons
def create_dashboard_content():
    return html.Div([
        # System Status Cards mit Icons
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("🖥️ System Status", className="card-title"),
                        html.Hr(),
                        html.P(f"📡 Server IP: {get_ip_address()}", className="card-text"),
                        html.P("🟢 Status: Online", className="card-text", style={'color': 'green'}),
                        html.P(f"🔧 DAQ Hardware: {'✅ Verfügbar' if DAQ_AVAILABLE else '🔄 Simulation'}",
                               className="card-text", style={'color': 'green' if DAQ_AVAILABLE else 'orange'})
                    ])
                ], color="light", outline=True)
            ], width=4),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("📋 Aktive Module", className="card-title"),
                        html.Hr(),
                        html.Div(id='active-modules-display', children=[
                            html.P(f"🔌 DMM: {'Aktiv' if dmm_running else 'Bereit'}", className="card-text"),
                            html.P(f"📺 Oszilloskop: {'Aktiv' if oscilloscope_running else 'Bereit'}", className="card-text"),
                            html.P(f"🌊 Funktionsgenerator: {'Aktiv' if fgen_running else 'Bereit'}", className="card-text"),
                            html.P(f"⚡ Netzteil: {'Aktiv' if ps_running else 'Bereit'}", className="card-text")
                        ])
                    ])
                ], color="light", outline=True)
            ], width=4),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("🚀 Schnellzugriff", className="card-title"),
                        html.Hr(),
                        dbc.Button("🛑 Alle Module stoppen", id='stop-all-btn',
                                  color="danger", className="mb-2", style={'width': '100%'}),
                        dbc.Button("🔄 System Reset", id='reset-btn',
                                  color="secondary", style={'width': '100%'})
                    ])
                ], color="light", outline=True)
            ], width=4)
        ], className="mb-4"),
        
        # Live Data Preview
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H3("📈 Live Datenvorschau"),
                        dcc.Graph(id='dashboard-live-graph')
                    ])
                ], color="light", outline=True)
            ])
        ])
    ])

# DMM Tab Content mit erweiterten Funktionen
def create_dmm_content():
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Img(src="/assets/icons/dmm_icon.png", style={'height': '64px'})
                    if os.path.exists(os.path.join(ICONS_DIR, "dmm_icon.png"))
                    else create_module_icon('dmm'),
                    html.H3("🔌 Digitales Multimeter", style={'display': 'inline-block', 'margin-left': '10px'})
                ], style={'textAlign': 'center', 'marginBottom': '20px'})
            ])
        ]),
        
        dbc.Row([
            # Steuerung
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("⚙️ Einstellungen"),
                        html.Hr(),
                        
                        html.Label("🔧 Hardware Mode:"),
                        create_hat_selector("MCC_118"),
                        html.Br(),
                        
                        html.Label("📏 Messart:"),
                        dcc.Dropdown(
                            id='dmm-measurement-type',
                            options=[
                                {'label': '⚡ DC Spannung', 'value': 'DC_VOLTAGE'},
                                {'label': '🌊 AC Spannung', 'value': 'AC_VOLTAGE'},
                                {'label': '⚡ DC Strom', 'value': 'DC_CURRENT'},
                                {'label': '🌊 AC Strom', 'value': 'AC_CURRENT'}
                            ],
                            value='DC_VOLTAGE'
                        ),
                        html.Br(),
                        
                        html.Label("📊 Messbereich:"),
                        dcc.Dropdown(
                            id='dmm-range',
                            options=[
                                {'label': '±10V / 1A', 'value': 10},
                                {'label': '±5V / 500mA', 'value': 5},
                                {'label': '±2V / 200mA', 'value': 2},
                                {'label': '±1V / 100mA', 'value': 1}
                            ],
                            value=10
                        ),
                        html.Br(),
                        
                        html.Label("🔌 Kanal:"),
                        dcc.Dropdown(
                            id='dmm-channel',
                            options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                            value=0
                        ),
                        html.Br(),
                        
                        html.Label("⏱️ Messintervall (ms):"),
                        dcc.Input(id='dmm-interval-time', type='number', value=1000,
                                 min=100, max=10000, step=100),
                        html.Br(), html.Br(),
                        
                        dbc.ButtonGroup([
                            dbc.Button("▶️ Start", id='dmm-start-btn', color="success"),
                            dbc.Button("⏹️ Stop", id='dmm-stop-btn', color="danger"),
                            dbc.Button("💾 Export CSV", id='dmm-export-btn', color="primary")
                        ], vertical=True, style={'width': '100%'})
                    ])
                ])
            ], width=4),
            
            # Anzeige
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("📊 Aktuelle Messwerte"),
                        html.Div(id='dmm-display', style={'fontSize': '24px', 'textAlign': 'center', 'padding': '20px'}),
                        html.Hr(),
                        dcc.Graph(id='dmm-graph'),
                        html.Hr(),
                        html.H5("📋 Messdaten Tabelle"),
                        html.Div(id='dmm-table', style={'maxHeight': '300px', 'overflowY': 'auto'})
                    ])
                ])
            ], width=8)
        ])
    ])

# Oszilloskop Tab Content
def create_oscilloscope_content():
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Img(src="/assets/icons/osc_icon.png", style={'height': '64px'})
                    if os.path.exists(os.path.join(ICONS_DIR, "osc_icon.png"))
                    else create_module_icon('oscilloscope'),
                    html.H3("📺 Oszilloskop", style={'display': 'inline-block', 'margin-left': '10px'})
                ], style={'textAlign': 'center', 'marginBottom': '20px'})
            ])
        ]),
        
        dbc.Row([
            # Steuerung
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("⚙️ Einstellungen"),
                        html.Hr(),
                        create_hat_selector("MCC_118"),
                        html.Br(),
                        html.Label("📊 Abtastrate (Hz):"),
                        dcc.Input(id='osc-sample-rate', type='number', value=1000, min=1, max=100000),
                        html.Br(), html.Br(),
                        html.Label("📈 Anzahl Samples:"),
                        dcc.Input(id='osc-samples', type='number', value=1000, min=100, max=10000),
                        html.Br(), html.Br(),
                        html.Label("🔌 Aktive Kanäle:"),
                        dcc.Checklist(
                            id='osc-channels',
                            options=[{'label': f'Kanal {i}', 'value': i} for i in range(8)],
                            value=[0, 1],
                            style={'marginBottom': '10px'}
                        ),
                        html.Label("📏 Spannungsbereich (V):"),
                        dcc.Dropdown(
                            id='osc-range',
                            options=[
                                {'label': '±10V', 'value': 10},
                                {'label': '±5V', 'value': 5},
                                {'label': '±2V', 'value': 2},
                                {'label': '±1V', 'value': 1}
                            ],
                            value=10
                        ),
                        html.Br(), html.Br(),
                        dbc.ButtonGroup([
                            dbc.Button("▶️ Start", id='osc-start-btn', color="success"),
                            dbc.Button("⏹️ Stop", id='osc-stop-btn', color="danger"),
                            dbc.Button("💾 Export CSV", id='osc-export-btn', color="primary")
                        ], vertical=True, style={'width': '100%'})
                    ])
                ])
            ], width=3),
            
            # Anzeige
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dcc.Graph(id='oscilloscope-graph', style={'height': '500px'})
                    ])
                ])
            ], width=9)
        ])
    ])

# Funktionsgenerator Tab Content
def create_function_generator_content():
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Img(src="/assets/icons/fgen_icon.png", style={'height': '64px'})
                    if os.path.exists(os.path.join(ICONS_DIR, "fgen_icon.png"))
                    else create_module_icon('function_gen'),
                    html.H3("🌊 Funktionsgenerator", style={'display': 'inline-block', 'margin-left': '10px'})
                ], style={'textAlign': 'center', 'marginBottom': '20px'})
            ])
        ]),
        
        dbc.Row([
            # Steuerung
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("⚙️ Einstellungen"),
                        html.Hr(),
                        create_hat_selector("MCC_152"),
                        html.Br(),
                        html.Label("📊 Signalform:"),
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
                        html.Label("📈 Frequenz (Hz):"),
                        dcc.Input(id='fgen-frequency', type='number', value=1000, min=1, max=10000),
                        html.Br(), html.Br(),
                        html.Label("📏 Amplitude (V):"),
                        dcc.Input(id='fgen-amplitude', type='number', value=1.0, min=0.1, max=5.0, step=0.1),
                        html.Br(), html.Br(),
                        html.Label("🔧 Offset (V):"),
                        dcc.Input(id='fgen-offset', type='number', value=0.0, min=-5.0, max=5.0, step=0.1),
                        html.Br(), html.Br(),
                        html.Label("⏱️ Aktualisierungsintervall (ms):"),
                        dcc.Input(id='fgen-interval-time', type='number', value=1000, min=100, max=10000, step=100),
                        html.Br(), html.Br(),
                        dbc.ButtonGroup([
                            dbc.Button("▶️ Start", id='fgen-start-btn', color="success"),
                            dbc.Button("⏹️ Stop", id='fgen-stop-btn', color="danger"),
                            dbc.Button("💾 Export CSV", id='fgen-export-btn', color="primary")
                        ], vertical=True, style={'width': '100%'})
                    ])
                ])
            ], width=4),
            
            # Anzeige
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("📊 Signalvorschau"),
                        dcc.Graph(id='fgen-preview', style={'height': '400px'}),
                        html.Hr(),
                        html.H5("📋 Signalparameter"),
                        html.Div(id='fgen-status', style={'textAlign': 'center', 'padding': '10px'})
                    ])
                ])
            ], width=8)
        ])
    ])

# Netzteil Tab Content
def create_power_supply_content():
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Img(src="/assets/icons/ps_icon.png", style={'height': '64px'})
                    if os.path.exists(os.path.join(ICONS_DIR, "ps_icon.png"))
                    else create_module_icon('power_supply'),
                    html.H3("⚡ Netzteilfunktion", style={'display': 'inline-block', 'margin-left': '10px'})
                ], style={'textAlign': 'center', 'marginBottom': '20px'})
            ])
        ]),
        
        dbc.Row([
            # Steuerung
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("⚙️ Einstellungen"),
                        html.Hr(),
                        create_hat_selector("MCC_152"),
                        html.Br(),
                        html.Label("📏 Ausgangsspannung (V):"),
                        dcc.Input(id='ps-voltage', type='number', value=5.0, min=0, max=10.0, step=0.1),
                        html.Br(), html.Br(),
                        html.Label("🔧 Strombegrenzung (mA):"),
                        dcc.Input(id='ps-current-limit', type='number', value=500, min=10, max=1000, step=10),
                        html.Br(), html.Br(),
                        html.Label("⏱️ Aktualisierungsintervall (ms):"),
                        dcc.Input(id='ps-interval-time', type='number', value=1000, min=100, max=10000, step=100),
                        html.Br(), html.Br(),
                        dbc.ButtonGroup([
                            dbc.Button("▶️ Start", id='ps-start-btn', color="success"),
                            dbc.Button("⏹️ Stop", id='ps-stop-btn', color="danger"),
                            dbc.Button("💾 Export CSV", id='ps-export-btn', color="primary")
                        ], vertical=True, style={'width': '100%'})
                    ])
                ])
            ], width=4),
            
            # Anzeige
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("📊 Aktuelle Werte"),
                        html.Div(id='ps-display', style={'fontSize': '24px', 'textAlign': 'center', 'padding': '20px'}),
                        html.Hr(),
                        dcc.Graph(id='ps-graph', style={'height': '400px'})
                    ])
                ])
            ], width=8)
        ])
    ])

# Systeminfo Tab Content
def create_system_info_content():
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.H3("⚙️ Systeminformationen", style={'textAlign': 'center', 'marginBottom': '20px'})
            ])
        ]),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("🖥️ System Status"),
                        html.Hr(),
                        html.Div(id='system-info-display')
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("🔧 Hardware Info"),
                        html.Hr(),
                        html.Div(id='hardware-info-display')
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("📡 Netzwerk Info"),
                        html.Hr(),
                        html.Div(id='network-info-display')
                    ])
                ])
            ], width=4)
        ])
    ])

# Callback für Tab Content
@callback(
    Output('tab-content', 'children'),
    Input('main-tabs', 'active_tab')
)
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
    return html.Div("Tab nicht gefunden")

# DMM Callbacks
@callback(
    [Output('dmm-interval', 'disabled'),
     Output('dmm-interval', 'interval'),
     Output('dmm-data', 'children')],
    [Input('dmm-start-btn', 'n_clicks'),
     Input('dmm-stop-btn', 'n_clicks')],
    [State('dmm-interval-time', 'value'),
     State('dmm-measurement-type', 'value'),
     State('hatSelector-MCC_118', 'value')],
    prevent_initial_call=True
)
def control_dmm(start_clicks, stop_clicks, interval_time, measurement_type, hat_mode):
    global dmm_running, dmm_mode, dmm_measurement_type
    from dash import ctx
    
    if ctx.triggered_id == 'dmm-start-btn' and start_clicks:
        dmm_running = True
        dmm_mode = hat_mode
        dmm_measurement_type = measurement_type
        return False, interval_time, json.dumps({
            'running': True,
            'data': [],
            'mode': hat_mode,
            'measurement_type': measurement_type
        })
    elif ctx.triggered_id == 'dmm-stop-btn' and stop_clicks:
        dmm_running = False
        return True, 1000, json.dumps({'running': False, 'data': measurement_data['dmm']})
    
    raise PreventUpdate

@callback(
    [Output('dmm-display', 'children'),
     Output('dmm-graph', 'figure'),
     Output('dmm-table', 'children')],
    [Input('dmm-interval', 'n_intervals')],
    [State('dmm-data', 'children'),
     State('dmm-channel', 'value'),
     State('dmm-measurement-type', 'value'),
     State('dmm-range', 'value'),
     State('hatSelector-MCC_118', 'value')],
    prevent_initial_call=True
)
def update_dmm(n_intervals, dmm_data_json, channel, measurement_type, range_val, hat_mode):
    global measurement_data
    if not dmm_data_json:
        raise PreventUpdate
    
    dmm_data = json.loads(dmm_data_json)
    if not dmm_data.get('running', False):
        raise PreventUpdate
    
    current_time = datetime.now()
    time_str = current_time.strftime("%H:%M:%S.%f")[:-3]
    
    if hat_mode == 'simulation':
        if measurement_type == 'DC_VOLTAGE':
            value = np.random.uniform(-range_val, range_val)
            unit = 'V'
            symbol = '⚡'
        elif measurement_type == 'AC_VOLTAGE':
            value = abs(np.random.uniform(0, range_val)) * np.sin(np.random.uniform(0, 2*np.pi))
            unit = 'V~'
            symbol = '🌊'
        elif measurement_type == 'DC_CURRENT':
            value = np.random.uniform(-range_val/10, range_val/10)
            unit = 'A'
            symbol = '⚡'
        else:  # AC_CURRENT
            value = abs(np.random.uniform(0, range_val/10)) * np.sin(np.random.uniform(0, 2*np.pi))
            unit = 'A~'
            symbol = '🌊'
    elif hat_mode == 'realtime_demo':
        t = n_intervals * 0.1
        if measurement_type == 'DC_VOLTAGE':
            value = 5.0 + 0.5 * np.sin(t) + 0.1 * np.random.randn()
            unit = 'V'
            symbol = '⚡'
        elif measurement_type == 'AC_VOLTAGE':
            value = abs(3.3 * np.sin(2*np.pi*50*t) + 0.1 * np.random.randn())
            unit = 'V~'
            symbol = '🌊'
        elif measurement_type == 'DC_CURRENT':
            value = 0.1 + 0.02 * np.sin(t) + 0.005 * np.random.randn()
            unit = 'A'
            symbol = '⚡'
        else:  # AC_CURRENT
            value = abs(0.05 * np.sin(2*np.pi*50*t) + 0.005 * np.random.randn())
            unit = 'A~'
            symbol = '🌊'
    else:
        try:
            hat_info = json.loads(hat_mode)
            global HAT_118
            if HAT_118 is None:
                HAT_118 = mcc118(hat_info['address'])
            samples = [HAT_118.a_in_read(channel, OptionFlags.DEFAULT) for _ in range(100)]
            if measurement_type == 'DC_VOLTAGE':
                value = np.mean(samples)
                unit = 'V'
                symbol = '⚡'
            elif measurement_type == 'AC_VOLTAGE':
                value = np.sqrt(np.mean(np.square(samples)))
                unit = 'V~'
                symbol = '🌊'
            elif measurement_type == 'DC_CURRENT':
                value = np.mean(samples) / 0.1  # Annahme: 100 mOhm Shunt
                unit = 'A'
                symbol = '⚡'
            else:  # AC_CURRENT
                value = np.sqrt(np.mean(np.square(samples))) / 0.1
                unit = 'A~'
                symbol = '🌊'
        except Exception as e:
            print(f"Fehler bei MCC 118: {e}")
            value = 0.0
            unit = 'V' if 'VOLTAGE' in measurement_type else 'A'
            symbol = '🔧'
    
    data_point = {
        'time': time_str,
        'timestamp': current_time.timestamp(),
        'value': value,
        'channel': channel,
        'type': measurement_type,
        'unit': unit
    }
    
    measurement_data['dmm'].append(data_point)
    if len(measurement_data['dmm']) > 1000:
        measurement_data['dmm'] = measurement_data['dmm'][-1000:]
    
    display = dbc.Card([
        dbc.CardBody([
            html.H3(f"{symbol} Kanal {channel}", style={'textAlign': 'center'}),
            html.H2(f"{value:.4f} {unit}",
                   style={'textAlign': 'center', 'color': 'blue', 'fontSize': '36px'}),
            html.P(f"📊 {measurement_type.replace('_', ' ')}", style={'textAlign': 'center'}),
            html.P(f"⏰ {time_str}", style={'textAlign': 'center', 'fontSize': '14px'})
        ])
    ], color="primary", outline=True)
    
    if measurement_data['dmm']:
        times = [d['time'] for d in measurement_data['dmm'][-100:]]
        values = [d['value'] for d in measurement_data['dmm'][-100:]]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times,
            y=values,
            mode='lines+markers',
            name=f'{measurement_type} - Kanal {channel}',
            line=dict(color='blue', width=2),
            marker=dict(size=4)
        ))
        fig.update_layout(
            title=f"{symbol} {measurement_type.replace('_', ' ')} - Kanal {channel}",
            xaxis_title="Zeit",
            yaxis_title=f"Wert ({unit})",
            height=400,
            showlegend=False
        )
    else:
        fig = go.Figure()
    
    if measurement_data['dmm']:
        recent_data = measurement_data['dmm'][-20:]
        table = dash_table.DataTable(
            data=[{
                'Zeit': d['time'],
                'Wert': f"{d['value']:.4f}",
                'Einheit': d['unit'],
                'Kanal': d['channel']
            } for d in reversed(recent_data)],
            columns=[
                {'name': 'Zeit', 'id': 'Zeit'},
                {'name': 'Wert', 'id': 'Wert'},
                {'name': 'Einheit', 'id': 'Einheit'},
                {'name': 'Kanal', 'id': 'Kanal'}
            ],
            style_cell={'textAlign': 'center', 'fontSize': '12px'},
            style_header={'backgroundColor': '#0066cc', 'color': 'white', 'fontWeight': 'bold'},
            page_size=10
        )
    else:
        table = html.P("Keine Daten verfügbar")
    
    return display, fig, table

# Oszilloskop Callbacks
@callback(
    [Output('osc-interval', 'disabled'),
     Output('osc-interval', 'interval'),
     Output('osc-data', 'children')],
    [Input('osc-start-btn', 'n_clicks'),
     Input('osc-stop-btn', 'n_clicks')],
    [State('osc-sample-rate', 'value'),
     State('osc-samples', 'value'),
     State('osc-channels', 'value'),
     State('osc-range', 'value'),
     State('hatSelector-MCC_118', 'value')],
    prevent_initial_call=True
)
def control_oscilloscope(start_clicks, stop_clicks, sample_rate, samples, channels, range_val, hat_mode):
    global oscilloscope_running
    from dash import ctx
    
    if ctx.triggered_id == 'osc-start-btn' and start_clicks:
        oscilloscope_running = True
        return False, 1000/sample_rate*1000, json.dumps({
            'running': True,
            'data': [],
            'mode': hat_mode,
            'sample_rate': sample_rate,
            'samples': samples,
            'channels': channels,
            'range': range_val
        })
    elif ctx.triggered_id == 'osc-stop-btn' and stop_clicks:
        oscilloscope_running = False
        return True, 100, json.dumps({'running': False, 'data': measurement_data['osc']})
    
    raise PreventUpdate

@callback(
    Output('oscilloscope-graph', 'figure'),
    Input('osc-interval', 'n_intervals'),
    [State('osc-data', 'children'),
     State('osc-sample-rate', 'value'),
     State('osc-samples', 'value'),
     State('osc-channels', 'value'),
     State('osc-range', 'value'),
     State('hatSelector-MCC_118', 'value')],
    prevent_initial_call=True
)
def update_oscilloscope(n_intervals, osc_data_json, sample_rate, samples, channels, range_val, hat_mode):
    global measurement_data
    if not osc_data_json:
        raise PreventUpdate
    
    osc_data = json.loads(osc_data_json)
    if not osc_data.get('running', False):
        raise PreventUpdate
    
    time_step = 1.0 / sample_rate
    times = np.linspace(0, samples * time_step, samples)
    fig = go.Figure()
    
    if hat_mode == 'simulation':
        for ch in channels:
            values = np.random.uniform(-range_val, range_val, samples)
            measurement_data['osc'].append({
                'time': datetime.now().strftime("%H:%M:%S.%f")[:-3],
                'channel': ch,
                'values': values.tolist()
            })
            fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines',
                name=f'Kanal {ch}',
                line=dict(width=2)
            ))
    elif hat_mode == 'realtime_demo':
        t = np.linspace(0, samples/sample_rate, samples)
        for ch in channels:
            values = 2.0 * np.sin(2 * np.pi * (50 + ch * 10) * t) + 0.1 * np.random.randn(samples)
            measurement_data['osc'].append({
                'time': datetime.now().strftime("%H:%M:%S.%f")[:-3],
                'channel': ch,
                'values': values.tolist()
            })
            fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines',
                name=f'Kanal {ch}',
                line=dict(width=2)
            ))
    else:
        try:
            hat_info = json.loads(hat_mode)
            global HAT_118
            if HAT_118 is None:
                HAT_118 = mcc118(hat_info['address'])
            for ch in channels:
                values = [HAT_118.a_in_read(ch, OptionFlags.DEFAULT) for _ in range(samples)]
                measurement_data['osc'].append({
                    'time': datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    'channel': ch,
                    'values': values
                })
                fig.add_trace(go.Scatter(
                    x=times,
                    y=values,
                    mode='lines',
                    name=f'Kanal {ch}',
                    line=dict(width=2)
                ))
        except Exception as e:
            print(f"Fehler bei MCC 118: {e}")
    
    if len(measurement_data['osc']) > 1000:
        measurement_data['osc'] = measurement_data['osc'][-1000:]
    
    fig.update_layout(
        title="Oszilloskop Signal",
        xaxis_title="Zeit (s)",
        yaxis_title="Spannung (V)",
        height=500,
        showlegend=True
    )
    
    return fig

# Funktionsgenerator Callbacks
@callback(
    [Output('fgen-interval', 'disabled'),
     Output('fgen-interval', 'interval'),
     Output('fgen-data', 'children')],
    [Input('fgen-start-btn', 'n_clicks'),
     Input('fgen-stop-btn', 'n_clicks')],
    [State('fgen-interval-time', 'value'),
     State('fgen-waveform', 'value'),
     State('fgen-frequency', 'value'),
     State('fgen-amplitude', 'value'),
     State('fgen-offset', 'value'),
     State('hatSelector-MCC_152', 'value')],
    prevent_initial_call=True
)
def control_fgen(start_clicks, stop_clicks, interval_time, waveform, frequency, amplitude, offset, hat_mode):
    global fgen_running
    from dash import ctx
    
    if ctx.triggered_id == 'fgen-start-btn' and start_clicks:
        fgen_running = True
        return False, interval_time, json.dumps({
            'running': True,
            'data': [],
            'mode': hat_mode,
            'waveform': waveform,
            'frequency': frequency,
            'amplitude': amplitude,
            'offset': offset
        })
    elif ctx.triggered_id == 'fgen-stop-btn' and stop_clicks:
        fgen_running = False
        return True, 1000, json.dumps({'running': False, 'data': measurement_data['fgen']})
    
    raise PreventUpdate

@callback(
    [Output('fgen-preview', 'figure'),
     Output('fgen-status', 'children')],
    Input('fgen-interval', 'n_intervals'),
    [State('fgen-data', 'children'),
     State('fgen-waveform', 'value'),
     State('fgen-frequency', 'value'),
     State('fgen-amplitude', 'value'),
     State('fgen-offset', 'value'),
     State('hatSelector-MCC_152', 'value')],
    prevent_initial_call=True
)
def update_fgen(n_intervals, fgen_data_json, waveform, frequency, amplitude, offset, hat_mode):
    global measurement_data
    if not fgen_data_json:
        raise PreventUpdate
    
    fgen_data = json.loads(fgen_data_json)
    if not fgen_data.get('running', False):
        raise PreventUpdate
    
    t = np.linspace(0, 1/frequency, 1000)
    if waveform == 'sine':
        signal = amplitude * np.sin(2 * np.pi * frequency * t) + offset
    elif waveform == 'square':
        signal = amplitude * np.sign(np.sin(2 * np.pi * frequency * t)) + offset
    else:  # triangle
        signal = amplitude * (2 * np.abs(2 * (t * frequency - np.floor(t * frequency + 0.5))) - 1) + offset
    
    if hat_mode not in ['simulation', 'realtime_demo']:
        try:
            hat_info = json.loads(hat_mode)
            global HAT_152
            if HAT_152 is None:
                HAT_152 = mcc152(hat_info['address'])
            # Hier würde MCC 152 DAC-Ausgabe implementiert werden
        except Exception as e:
            print(f"Fehler bei MCC 152: {e}")
    
    data_point = {
        'time': datetime.now().strftime("%H:%M:%S.%f")[:-3],
        'waveform': waveform,
        'frequency': frequency,
        'amplitude': amplitude,
        'offset': offset,
        'signal': signal.tolist()[:100]
    }
    
    measurement_data['fgen'].append(data_point)
    if len(measurement_data['fgen']) > 1000:
        measurement_data['fgen'] = measurement_data['fgen'][-1000:]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t[:100],
        y=signal[:100],
        mode='lines',
        name=waveform,
        line=dict(color='blue')
    ))
    fig.update_layout(
        title=f"{waveform.capitalize()} Signal",
        xaxis_title="Zeit (s)",
        yaxis_title="Spannung (V)",
        height=400,
        showlegend=True
    )
    
    status = html.Div([
        html.P(f"Signalform: {waveform.capitalize()}"),
        html.P(f"Frequenz: {frequency} Hz"),
        html.P(f"Amplitude: {amplitude} V"),
        html.P(f"Offset: {offset} V")
    ])
    
    return fig, status

# Netzteil Callbacks
@callback(
    [Output('ps-interval', 'disabled'),
     Output('ps-interval', 'interval'),
     Output('ps-data', 'children')],
    [Input('ps-start-btn', 'n_clicks'),
     Input('ps-stop-btn', 'n_clicks')],
    [State('ps-interval-time', 'value'),
     State('ps-voltage', 'value'),
     State('ps-current-limit', 'value'),
     State('hatSelector-MCC_152', 'value')],
    prevent_initial_call=True
)
def control_power_supply(start_clicks, stop_clicks, interval_time, voltage, current_limit, hat_mode):
    global ps_running
    from dash import ctx
    
    if ctx.triggered_id == 'ps-start-btn' and start_clicks:
        ps_running = True
        return False, interval_time, json.dumps({
            'running': True,
            'data': [],
            'mode': hat_mode,
            'voltage': voltage,
            'current_limit': current_limit
        })
    elif ctx.triggered_id == 'ps-stop-btn' and stop_clicks:
        ps_running = False
        return True, 1000, json.dumps({'running': False, 'data': measurement_data['ps']})
    
    raise PreventUpdate

@callback(
    [Output('ps-display', 'children'),
     Output('ps-graph', 'figure')],
    Input('ps-interval', 'n_intervals'),
    [State('ps-data', 'children'),
     State('ps-voltage', 'value'),
     State('ps-current-limit', 'value'),
     State('hatSelector-MCC_152', 'value')],
    prevent_initial_call=True
)
def update_power_supply(n_intervals, ps_data_json, voltage, current_limit, hat_mode):
    global measurement_data
    if not ps_data_json:
        raise PreventUpdate
    
    ps_data = json.loads(ps_data_json)
    if not ps_data.get('running', False):
        raise PreventUpdate
    
    current_time = datetime.now()
    time_str = current_time.strftime("%H:%M:%S.%f")[:-3]
    
    if hat_mode == 'simulation':
        actual_voltage = voltage + np.random.uniform(-0.05, 0.05)
        actual_current = np.random.uniform(0, current_limit/1000)
    elif hat_mode == 'realtime_demo':
        actual_voltage = voltage + 0.05 * np.sin(n_intervals * 0.1)
        actual_current = np.random.uniform(0, current_limit/1000)
    else:
        try:
            hat_info = json.loads(hat_mode)
            global HAT_152
            if HAT_152 is None:
                HAT_152 = mcc152(hat_info['address'])
            # Hier würde MCC 152 DAC-Ausgabe implementiert werden
            actual_voltage = voltage
            actual_current = np.random.uniform(0, current_limit/1000)
        except Exception as e:
            print(f"Fehler bei MCC 152: {e}")
            actual_voltage = 0.0
            actual_current = 0.0
    
    data_point = {
        'time': time_str,
        'timestamp': current_time.timestamp(),
        'voltage': actual_voltage,
        'current': actual_current
    }
    
    measurement_data['ps'].append(data_point)
    if len(measurement_data['ps']) > 1000:
        measurement_data['ps'] = measurement_data['ps'][-1000:]
    
    display = dbc.Card([
        dbc.CardBody([
            html.H3("⚡ Netzteil Status", style={'textAlign': 'center'}),
            html.H2(f"{actual_voltage:.2f} V",
                   style={'textAlign': 'center', 'color': 'blue', 'fontSize': '36px'}),
            html.P(f"Strom: {actual_current*1000:.2f} mA", style={'textAlign': 'center'}),
            html.P(f"Zeit: {time_str}", style={'textAlign': 'center', 'fontSize': '14px'})
        ])
    ], color="primary", outline=True)
    
    if measurement_data['ps']:
        times = [d['time'] for d in measurement_data['ps'][-100:]]
        voltages = [d['voltage'] for d in measurement_data['ps'][-100:]]
        currents = [d['current']*1000 for d in measurement_data['ps'][-100:]]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times,
            y=voltages,
            mode='lines+markers',
            name='Spannung',
            line=dict(color='blue')
        ))
        fig.add_trace(go.Scatter(
            x=times,
            y=currents,
            mode='lines+markers',
            name='Strom',
            line=dict(color='red')
        ))
        fig.update_layout(
            title="Netzteil Werte",
            xaxis_title="Zeit",
            yaxis_title="Wert (V/mA)",
            height=400,
            showlegend=True
        )
    else:
        fig = go.Figure()
    
    return display, fig

# System Info Callback
@callback(
    [Output('system-info-display', 'children'),
     Output('hardware-info-display', 'children'),
     Output('network-info-display', 'children')],
    Input('main-tabs', 'active_tab')
)
def update_system_info(active_tab):
    if active_tab != 'system-info':
        raise PreventUpdate
    
    system_info = [
        html.P(f"🖥️ Server IP: {get_ip_address()}"),
        html.P(f"🟢 Status: {'Online' if get_ip_address() != '127.0.0.1' else 'Offline'}"),
        html.P(f"🔧 DAQ: {'Verfügbar' if DAQ_AVAILABLE else 'Simulation'}")
    ]
    
    hardware_info = []
    if DAQ_AVAILABLE:
        hats_118 = hat_list(filter_by_id=HatIDs.MCC_118)
        hats_152 = hat_list(filter_by_id=HatIDs.MCC_152)
        for hat in hats_118:
            hardware_info.append(html.P(f"🔌 MCC 118 @ Adresse {hat.address}: {hat.product_name}"))
        for hat in hats_152:
            hardware_info.append(html.P(f"🔌 MCC 152 @ Adresse {hat.address}: {hat.product_name}"))
    else:
        hardware_info.append(html.P("🔴 Keine DAQ Hardware erkannt"))
    
    network_info = [
        html.P(f"📡 Host: {socket.gethostname()}"),
        html.P(f"🌐 IP: {get_ip_address()}")
    ]
    
    return system_info, hardware_info, network_info

# Dashboard Graph Callback
@callback(
    Output('dashboard-live-graph', 'figure'),
    [Input('dmm-interval', 'n_intervals'),
     Input('osc-interval', 'n_intervals'),
     Input('fgen-interval', 'n_intervals'),
     Input('ps-interval', 'n_intervals')],
    [State('dmm-data', 'children'),
     State('osc-data', 'children'),
     State('fgen-data', 'children'),
     State('ps-data', 'children')]
)
def update_dashboard_graph(dmm_n, osc_n, fgen_n, ps_n, dmm_data_json, osc_data_json, fgen_data_json, ps_data_json):
    fig = go.Figure()
    
    if dmm_data_json:
        dmm_data = json.loads(dmm_data_json)
        if dmm_data.get('data'):
            times = [d['time'] for d in dmm_data['data'][-50:]]
            values = [d['value'] for d in dmm_data['data'][-50:]]
            fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines+markers',
                name='Multimeter',
                line=dict(color='blue')
            ))
    
    if osc_data_json:
        osc_data = json.loads(osc_data_json)
        if osc_data.get('data'):
            last_record = osc_data['data'][-1]
            sample_rate = osc_data.get('sample_rate', 1000)
            times = np.linspace(0, 50/sample_rate, 50)
            values = last_record['values'][:50]
            fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines',
                name=f"Oszilloskop Kanal {last_record['channel']}",
                line=dict(color='green')
            ))
    
    if fgen_data_json:
        fgen_data = json.loads(fgen_data_json)
        if fgen_data.get('data'):
            last_record = fgen_data['data'][-1]
            frequency = last_record['frequency']
            times = np.linspace(0, 1/frequency, 50)
            values = last_record['signal'][:50]
            fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines',
                name='Funktionsgenerator',
                line=dict(color='purple')
            ))
    
    if ps_data_json:
        ps_data = json.loads(ps_data_json)
        if ps_data.get('data'):
            times = [d['time'] for d in ps_data['data'][-50:]]
            voltages = [d['voltage'] for d in ps_data['data'][-50:]]
            fig.add_trace(go.Scatter(
                x=times,
                y=voltages,
                mode='lines+markers',
                name='Netzteil Spannung',
                line=dict(color='orange')
            ))
    
    fig.update_layout(
        title="Live Datenübersicht",
        xaxis_title="Zeit",
        yaxis_title="Wert",
        height=400,
        showlegend=True
    )
    
    return fig

# Stop All und Reset Callbacks
@callback(
    [Output('dmm-interval', 'disabled', allow_duplicate=True),
     Output('osc-interval', 'disabled', allow_duplicate=True),
     Output('fgen-interval', 'disabled', allow_duplicate=True),
     Output('ps-interval', 'disabled', allow_duplicate=True),
     Output('dmm-data', 'children', allow_duplicate=True),
     Output('osc-data', 'children', allow_duplicate=True),
     Output('fgen-data', 'children', allow_duplicate=True),
     Output('ps-data', 'children', allow_duplicate=True)],
    [Input('stop-all-btn', 'n_clicks')],
    prevent_initial_call=True
)
def stop_all_modules(n_clicks):
    global dmm_running, oscilloscope_running, fgen_running, ps_running, measurement_data
    if not n_clicks:
        raise PreventUpdate
    
    dmm_running = False
    oscilloscope_running = False
    fgen_running = False
    ps_running = False
    
    return (
        True, True, True, True,
        json.dumps({'running': False, 'data': measurement_data['dmm']}),
        json.dumps({'running': False, 'data': measurement_data['osc']}),
        json.dumps({'running': False, 'data': measurement_data['fgen']}),
        json.dumps({'running': False, 'data': measurement_data['ps']})
    )

@callback(
    [Output('dmm-interval', 'disabled', allow_duplicate=True),
     Output('osc-interval', 'disabled', allow_duplicate=True),
     Output('fgen-interval', 'disabled', allow_duplicate=True),
     Output('ps-interval', 'disabled', allow_duplicate=True),
     Output('dmm-data', 'children', allow_duplicate=True),
     Output('osc-data', 'children', allow_duplicate=True),
     Output('fgen-data', 'children', allow_duplicate=True),
     Output('ps-data', 'children', allow_duplicate=True)],
    [Input('reset-btn', 'n_clicks')],
    prevent_initial_call=True
)
def reset_system(n_clicks):
    global dmm_running, oscilloscope_running, fgen_running, ps_running, measurement_data
    if not n_clicks:
        raise PreventUpdate
    
    dmm_running = False
    oscilloscope_running = False
    fgen_running = False
    ps_running = False
    measurement_data = {'dmm': [], 'osc': [], 'fgen': [], 'ps': []}
    
    return (
        True, True, True, True,
        json.dumps({'running': False, 'data': []}),
        json.dumps({'running': False, 'data': []}),
        json.dumps({'running': False, 'data': []}),
        json.dumps({'running': False, 'data': []})
    )

# Export Callbacks
@callback(
    Output('download-csv', 'data'),
    [Input('dmm-export-btn', 'n_clicks'),
     Input('osc-export-btn', 'n_clicks'),
     Input('fgen-export-btn', 'n_clicks'),
     Input('ps-export-btn', 'n_clicks')],
    [State('dmm-data', 'children'),
     State('osc-data', 'children'),
     State('fgen-data', 'children'),
     State('ps-data', 'children')],
    prevent_initial_call=True
)
def export_data(dmm_n, osc_n, fgen_n, ps_n, dmm_data_json, osc_data_json, fgen_data_json, ps_data_json):
    from dash import ctx
    triggered_id = ctx.triggered_id
    
    if triggered_id == 'dmm-export-btn' and dmm_n:
        dmm_data = json.loads(dmm_data_json)
        if not dmm_data.get('data'):
            raise PreventUpdate
        df = pd.DataFrame(dmm_data['data'])
        return dcc.send_data_frame(
            df.to_csv,
            f"dmm_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    
    elif triggered_id == 'osc-export-btn' and osc_n:
        osc_data = json.loads(osc_data_json)
        if not osc_data.get('data'):
            raise PreventUpdate
        records = []
        for record in osc_data['data']:
            for i, val in enumerate(record['values']):
                records.append({
                    'time': record['time'],
                    'channel': record['channel'],
                    'sample': i,
                    'value': val
                })
        df = pd.DataFrame(records)
        return dcc.send_data_frame(
            df.to_csv,
            f"osc_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    
    elif triggered_id == 'fgen-export-btn' and fgen_n:
        fgen_data = json.loads(fgen_data_json)
        if not fgen_data.get('data'):
            raise PreventUpdate
        records = []
        for record in fgen_data['data']:
            for i, val in enumerate(record['signal']):
                records.append({
                    'time': record['time'],
                    'waveform': record['waveform'],
                    'frequency': record['frequency'],
                    'amplitude': record['amplitude'],
                    'offset': record['offset'],
                    'sample': i,
                    'value': val
                })
        df = pd.DataFrame(records)
        return dcc.send_data_frame(
            df.to_csv,
            f"fgen_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    
    elif triggered_id == 'ps-export-btn' and ps_n:
        ps_data = json.loads(ps_data_json)
        if not ps_data.get('data'):
            raise PreventUpdate
        df = pd.DataFrame(ps_data['data'])
        return dcc.send_data_frame(
            df.to_csv,
            f"ps_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    
    raise PreventUpdate

if __name__ == '__main__':
    erstelle_ressourcen_verzeichnisse()
    app.run(debug=True, host='0.0.0.0', port=8050)