# -*- coding: utf-8 -*-
"""
Web-basiertes Dashboard für das OurDAQ-System
Zentrale Übersicht mit Links zu allen verfügbaren Modulen
"""

import socket
import subprocess
import sys
import os
import webbrowser
import time
import atexit
from dash import Dash, dcc, html, Input, Output, callback

def get_ip_address():
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts"""
    ip_address = '127.0.0.1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.connect(('1.1.1.1', 1))
        ip_address = sock.getsockname()[0]
    finally:
        sock.close()
    
    return ip_address

# Dash App initialisieren
app = Dash(__name__)
app.title = "OurDAQ Datenerfassungssystem"

# Layout der App
app.layout = html.Div([
    # Header
    html.H1("OurDAQ Datenerfassungssystem", 
            style={'textAlign': 'center', 'color': 'white', 'backgroundColor': '#2c3e50',
                   'padding': '30px', 'margin': '0 0 40px 0', 'borderRadius': '8px',
                   'fontSize': '36px'}),
    
    # Beschreibung
    html.Div([
        html.P("Willkommen beim OurDAQ Datenerfassungssystem", 
               style={'textAlign': 'center', 'fontSize': '18px', 'color': '#34495e',
                      'marginBottom': '10px'}),
        html.P("Ein prototypisches Messdatenerfassungssystem basierend auf Raspberry Pi und Digilent MCC DAQ HAT 118", 
               style={'textAlign': 'center', 'fontSize': '14px', 'color': '#7f8c8d',
                      'marginBottom': '40px'}),
    ]),
    
    # Hauptinhalt Container
    html.Div([
        # Verfügbare Module
        html.H2("Verfügbare Module", 
                style={'color': '#2c3e50', 'marginBottom': '30px', 'textAlign': 'center'}),
        
        # Button-Container im Grid-Layout
        html.Div(id='module-buttons', children=[
            # Erste Reihe
            html.Div([
                html.Button(
                    'Digitalmultimeter',
                    id='dmm-button',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#3498db',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                html.Button(
                    'Funktionsgenerator',
                    id='funktionsgenerator-button',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#e74c3c',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                html.Button(
                    'Oszilloskop',
                    id='oszilloskop-button',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#27ae60',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
            ], style={'textAlign': 'center', 'marginBottom': '20px'}),
            
            # Zweite Reihe
            html.Div([
                html.Button(
                    'Diodenkennlinie',
                    id='diode-button',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#f39c12',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                html.Button(
                    'Filterkennlinie',
                    id='filter-button',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#9b59b6',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
            ], style={'textAlign': 'center', 'marginBottom': '20px'}),
        ]),
        
        # Status-Anzeige
        html.Div(id='status-output',
                style={'textAlign': 'center', 'marginTop': '30px', 'fontSize': '14px',
                       'color': '#34495e', 'backgroundColor': '#ecf0f1', 'padding': '15px',
                       'borderRadius': '5px'},
                children='Bereit - Wählen Sie ein Modul aus'),
        
    ], style={'maxWidth': '800px', 'margin': '0 auto', 'padding': '20px'}),
])

# Globale Variable zum Tracking der gestarteten Prozesse
gestartete_prozesse = {}

def ist_port_verfuegbar(port):
    """Überprüft, ob ein Port verfügbar ist"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('', port))
        sock.close()
        return True
    except:
        sock.close()
        return False

@app.callback(
    [Output('status-output', 'children'),
     Output('module-buttons', 'children')],
    [Input('dmm-button', 'n_clicks'),
     Input('funktionsgenerator-button', 'n_clicks'),
     Input('oszilloskop-button', 'n_clicks'),
     Input('diode-button', 'n_clicks'),
     Input('filter-button', 'n_clicks')]
)
def handle_button_clicks(dmm_clicks, funktionsgenerator_clicks, oszilloskop_clicks, 
                        diode_clicks, filter_clicks):
    """
    Behandelt Button-Klicks und erstellt direkte Links
    """
    from dash import callback_context
    import time
    
    ip_address = get_ip_address()
    
    # Standard Button-Layout
    default_buttons = [
        # Erste Reihe
        html.Div([
            html.A(
                html.Button(
                    'Digitalmultimeter',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#3498db',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                id='dmm-button',
                href=f'http://{ip_address}:8050',
                target='_blank',
                style={'textDecoration': 'none'}
            ),
            html.A(
                html.Button(
                    'Funktionsgenerator',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#e74c3c',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                id='funktionsgenerator-button',
                href=f'http://{ip_address}:8060',
                target='_blank',
                style={'textDecoration': 'none'}
            ),
            html.A(
                html.Button(
                    'Oszilloskop',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#27ae60',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                id='oszilloskop-button',
                href=f'http://{ip_address}:8080',
                target='_blank',
                style={'textDecoration': 'none'}
            ),
        ], style={'textAlign': 'center', 'marginBottom': '20px'}),
        
        # Zweite Reihe
        html.Div([
            html.A(
                html.Button(
                    'Diodenkennlinie',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#f39c12',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                id='diode-button',
                href=f'http://{ip_address}:8888',
                target='_blank',
                style={'textDecoration': 'none'}
            ),
            html.A(
                html.Button(
                    'Filterkennlinie',
                    style={'width': '200px', 'height': '80px', 'backgroundColor': '#9b59b6',
                           'color': 'white', 'border': 'none', 'borderRadius': '8px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer',
                           'margin': '10px'}
                ),
                id='filter-button',
                href=f'http://{ip_address}:8889',
                target='_blank',
                style={'textDecoration': 'none'}
            ),
        ], style={'textAlign': 'center', 'marginBottom': '20px'}),
    ]
    
    if not callback_context.triggered:
        # Starte alle Services im Hintergrund beim ersten Laden
        try:
            # Starte DMM
            dmm_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DMM_web.py")
            if os.path.exists(dmm_pfad) and ist_port_verfuegbar(8050):
                prozess = subprocess.Popen([sys.executable, dmm_pfad], 
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                gestartete_prozesse['dmm'] = prozess
            
            # Starte Funktionsgenerator
            funktionsgenerator_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Funktionsgenerator_web.py")
            if os.path.exists(funktionsgenerator_pfad) and ist_port_verfuegbar(8060):
                prozess = subprocess.Popen([sys.executable, funktionsgenerator_pfad],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                gestartete_prozesse['funktionsgenerator'] = prozess
            
            # Starte Oszilloskop
            oszilloskop_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Oszilloskop_web.py")
            if os.path.exists(oszilloskop_pfad) and ist_port_verfuegbar(8080):
                prozess = subprocess.Popen([sys.executable, oszilloskop_pfad],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                gestartete_prozesse['oszilloskop'] = prozess
            
            # Starte Jupyter Notebooks mit deaktivierter Token-Authentifizierung
            diode_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Diodenkennlinie.ipynb")
            if os.path.exists(diode_pfad) and ist_port_verfuegbar(8888):
                try:
                    # Wichtige Änderung: --NotebookApp.token='' deaktiviert die Token-Authentifizierung
                    prozess = subprocess.Popen([
                        'jupyter', 'notebook', diode_pfad, 
                        '--ip=0.0.0.0', 
                        '--port=8888', 
                        '--no-browser',
                        '--NotebookApp.token=',
                        '--NotebookApp.password=',
                        '--NotebookApp.disable_check_xsrf=True'
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    gestartete_prozesse['diode_notebook'] = prozess
                except:
                    pass
            
            filter_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Filterkennlinie.ipynb")
            if os.path.exists(filter_pfad) and ist_port_verfuegbar(8889):
                try:
                    # Wichtige Änderung: --NotebookApp.token='' deaktiviert die Token-Authentifizierung
                    prozess = subprocess.Popen([
                        'jupyter', 'notebook', filter_pfad, 
                        '--ip=0.0.0.0', 
                        '--port=8889', 
                        '--no-browser',
                        '--NotebookApp.token=',
                        '--NotebookApp.password=',
                        '--NotebookApp.disable_check_xsrf=True'
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    gestartete_prozesse['filter_notebook'] = prozess
                except:
                    pass
        except:
            pass
        
        return 'Alle Services werden gestartet... Die Links sind in wenigen Sekunden verfügbar', default_buttons
    
    return 'Bereit - Klicken Sie direkt auf die Module', default_buttons

def cleanup_prozesse():
    """Beendet alle gestarteten Prozesse beim Beenden des Dashboards"""
    for name, prozess in gestartete_prozesse.items():
        try:
            if prozess.poll() is None:  # Prozess läuft noch
                prozess.terminate()
                print(f"Prozess {name} beendet")
        except:
            pass

# Cleanup beim Beenden registrieren
atexit.register(cleanup_prozesse)

if __name__ == '__main__':
    ip_address = get_ip_address()
    app.run(host=ip_address, port=8000, debug=False)