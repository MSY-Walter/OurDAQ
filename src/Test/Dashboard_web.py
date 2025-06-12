# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
"""
Verbesserte Version des OurDAQ Dashboards
Mit Onglet-basierter Navigation und integrierter Funktionalität
"""

import socket
import subprocess
import os
import time
import atexit
import threading
from datetime import datetime
import requests
from dash import Dash, dcc, html, Input, Output, callback, clientside_callback
from dash.exceptions import PreventUpdate
import plotly.graph_objs as go
import plotly.express as px

# =============================================================================
# DEBUG UND SIMULATION EINSTELLUNGEN
# =============================================================================

DEBUG_MODE = True
SIMULATION_MODE = False
CHECK_SCRIPTS_EXIST = True

# =============================================================================
# KONFIGURATION
# =============================================================================

MODULES = {
    'dmm': {
        'name': 'Digitalmultimeter',
        'script': 'DMM_web.py',
        'port': 8050,
        'color': '#3498db',
        'icon': '📊',
        'type': 'dash_app'
    },
    'funktionsgenerator': {
        'name': 'Funktionsgenerator',
        'script': 'Funktionsgenerator_web.py',
        'port': 8060,
        'color': '#e74c3c',
        'icon': '🌊',
        'type': 'dash_app'
    },
    'oszilloskop': {
        'name': 'Oszilloskop',
        'script': 'Oszilloskop_web.py',
        'port': 8080,
        'color': '#27ae60',
        'icon': '📈',
        'type': 'dash_app'
    },
    'netzteil': {
        'name': 'Netzteil',
        'script': 'Netzteil_web.py',
        'port': 8072,
        'color': '#f39c12',
        'icon': '⚡',
        'type': 'dash_app'
    },
    'kennlinie': {
        'name': 'Kennlinien',
        'color': '#9b59b6',
        'icon': '📋',
        'type': 'integrated'
    }
}

DASHBOARD_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'debug': False,
    'title': 'OurDAQ Datenerfassungssystem'
}

# =============================================================================
# DEBUG UND HILFSFUNKTIONEN
# =============================================================================

def debug_print(message):
    """Debug-Ausgabe nur wenn DEBUG_MODE aktiviert ist"""
    if DEBUG_MODE:
        timestamp = datetime.now().strftime('%H:%M:%S')
        safe_message = message.encode('ascii', 'replace').decode('ascii')
        print(f"[{timestamp}] DEBUG: {safe_message}")

def is_raspberry_pi():
    """Überprüft, ob das System ein Raspberry Pi ist"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        if 'Raspberry Pi' in cpuinfo:
            debug_print("Raspberry Pi hardware detected")
            return True
        else:
            debug_print("No Raspberry Pi hardware detected")
            return False
    except FileNotFoundError:
        debug_print("Cannot access /proc/cpuinfo, assuming not Raspberry Pi")
        return False
    except Exception as e:
        debug_print(f"Error checking for Raspberry Pi: {e}")
        return False

def set_simulation_mode():
    """Setzt SIMULATION_MODE basierend auf Raspberry Pi Erkennung"""
    global SIMULATION_MODE
    SIMULATION_MODE = not is_raspberry_pi()
    debug_print(f"Simulation Mode: {'AN' if SIMULATION_MODE else 'AUS'}")
    return SIMULATION_MODE

def get_ip_address():
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts"""
    ip_address = '127.0.0.1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.connect(('1.1.1.1', 1))
        ip_address = sock.getsockname()[0]
        debug_print(f"IP-Adresse ermittelt: {ip_address}")
    except Exception as e:
        debug_print(f"Fehler beim Ermitteln der IP-Adresse, verwende localhost: {e}")
    finally:
        sock.close()
    
    return ip_address

def ist_port_verfuegbar(port):
    """Überprüft, ob ein Port verfügbar ist"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('', port))
        debug_print(f"Port {port} ist verfügbar")
        return True
    except socket.error as e:
        debug_print(f"Port {port} nicht verfügbar: {e}")
        return False
    finally:
        sock.close()

# =============================================================================
# PROZESS MANAGER
# =============================================================================

class AdvancedProcessManager:
    def __init__(self):
        self.processes = {}
        self.monitoring = True
        self.ip_address = get_ip_address()
        self.active_modules = set()
        set_simulation_mode()
        
    def start_process(self, name, command, port, service_type='unknown'):
        """Startet einen Prozess"""
        debug_print(f"Versuche {name} zu starten...")
        
        if not ist_port_verfuegbar(port):
            debug_print(f"Port {port} für {name} bereits belegt")
            return False
        
        try:
            prozess = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            time.sleep(1)
            poll_result = prozess.poll()
            
            if poll_result is not None:
                debug_print(f"Prozess {name} sofort beendet")
                return False
            
            self.processes[name] = {
                'process': prozess,
                'port': port,
                'command': command,
                'service_type': service_type,
                'started_at': datetime.now(),
                'restart_count': 0
            }
            
            self.active_modules.add(name)
            debug_print(f"✅ {name} erfolgreich gestartet auf Port {port}")
            return True
            
        except Exception as e:
            debug_print(f"❌ Fehler beim Starten von {name}: {e}")
            return False
    
    def stop_process(self, name):
        """Stoppt einen spezifischen Prozess"""
        if name in self.processes:
            try:
                self.processes[name]['process'].terminate()
                del self.processes[name]
                self.active_modules.discard(name)
                debug_print(f"✅ {name} gestoppt")
                return True
            except Exception as e:
                debug_print(f"❌ Fehler beim Stoppen von {name}: {e}")
                return False
        return False
    
    def start_module(self, module_id):
        """Startet ein spezifisches Modul"""
        if module_id not in MODULES:
            return False
            
        config = MODULES[module_id]
        if config['type'] != 'dash_app':
            return False
            
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, config['script'])
        
        if not os.path.exists(script_path):
            debug_print(f"Script nicht gefunden: {script_path}")
            return False
        
        command = [sys.executable, script_path]
        if SIMULATION_MODE:
            command.append('--simulate')
        
        return self.start_process(module_id, command, config['port'], 'dash_app')
    
    def get_module_status(self):
        """Liefert Status aller Module"""
        status = {}
        
        for module_id, config in MODULES.items():
            if config['type'] == 'integrated':
                status[module_id] = {
                    'name': config['name'],
                    'status': 'integrated',
                    'active': True,
                    'type': 'integrated'
                }
            else:
                is_running = module_id in self.processes
                service_online = False
                
                if is_running:
                    try:
                        response = requests.get(f'http://{self.ip_address}:{config["port"]}', timeout=2)
                        service_online = response.status_code == 200
                    except:
                        pass
                
                status[module_id] = {
                    'name': config['name'],
                    'port': config.get('port', 0),
                    'status': 'online' if service_online else ('starting' if is_running else 'offline'),
                    'active': is_running,
                    'type': config['type']
                }
        
        return status
    
    def cleanup_all(self):
        """Cleanup aller Prozesse"""
        debug_print("🧹 Starte Cleanup...")
        self.monitoring = False
        
        for name, prozess_info in self.processes.items():
            try:
                if prozess_info['process'].poll() is None:
                    prozess_info['process'].terminate()
                    debug_print(f"✅ Prozess {name} beendet")
            except Exception as e:
                debug_print(f"❌ Fehler beim Beenden von {name}: {e}")

# =============================================================================
# DASH APP
# =============================================================================

process_manager = AdvancedProcessManager()

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = DASHBOARD_CONFIG['title']

# CSS Styles
tab_style = {
    'borderBottom': '1px solid #d6d6d6',
    'padding': '10px 20px',
    'fontWeight': 'bold',
    'fontSize': '16px',
    'backgroundColor': '#f8f9fa'
}

tab_selected_style = {
    'borderTop': '3px solid #2c3e50',
    'borderBottom': '1px solid #d6d6d6',
    'backgroundColor': '#ffffff',
    'color': '#2c3e50',
    'padding': '10px 20px',
    'fontWeight': 'bold',
    'fontSize': '16px'
}

# Layout
app.layout = html.Div([
    # Header
    html.Div([
        html.H1([
            html.Span("🔬 ", style={'fontSize': '40px'}),
            DASHBOARD_CONFIG['title']
        ], style={
            'textAlign': 'center', 
            'color': 'white', 
            'margin': '0',
            'fontSize': '32px',
            'fontWeight': '300'
        }),
        
        # Status Bar
        html.Div(id='header-status', style={
            'textAlign': 'center',
            'color': 'white',
            'fontSize': '14px',
            'marginTop': '10px',
            'opacity': '0.9'
        })
    ], style={
        'background': 'linear-gradient(135deg, #2c3e50 0%, #34495e 100%)',
        'padding': '30px 20px',
        'marginBottom': '0',
        'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'
    }),
    
    # Main Content
    html.Div([
        # Tabs
        dcc.Tabs(
            id="main-tabs",
            value='overview',
            children=[
                dcc.Tab(
                    label=f"📊 Übersicht",
                    value='overview',
                    style=tab_style,
                    selected_style=tab_selected_style
                ),
                dcc.Tab(
                    label=f"📊 DMM",
                    value='dmm',
                    style=tab_style,
                    selected_style=tab_selected_style
                ),
                dcc.Tab(
                    label=f"🌊 Funktionsgenerator",
                    value='funktionsgenerator',
                    style=tab_style,
                    selected_style=tab_selected_style
                ),
                dcc.Tab(
                    label=f"📈 Oszilloskop",
                    value='oszilloskop',
                    style=tab_style,
                    selected_style=tab_selected_style
                ),
                dcc.Tab(
                    label=f"⚡ Netzteil",
                    value='netzteil',
                    style=tab_style,
                    selected_style=tab_selected_style
                ),
                dcc.Tab(
                    label=f"📋 Kennlinien",
                    value='kennlinie',
                    style=tab_style,
                    selected_style=tab_selected_style
                )
            ],
            style={'marginBottom': '30px'}
        ),
        
        # Tab Content
        html.Div(id='tab-content')
        
    ], style={
        'maxWidth': '1200px',
        'margin': '0 auto',
        'padding': '20px',
        'backgroundColor': 'white',
        'minHeight': '80vh'
    }),
    
    # Update Intervals
    dcc.Interval(
        id='status-interval',
        interval=5*1000,  # 5 seconds
        n_intervals=0
    ),
    
    dcc.Interval(
        id='data-interval',
        interval=1*1000,  # 1 second for data updates
        n_intervals=0
    )
], style={'backgroundColor': '#f5f7fa', 'minHeight': '100vh'})

# =============================================================================
# CALLBACKS
# =============================================================================

@app.callback(
    Output('header-status', 'children'),
    Input('status-interval', 'n_intervals')
)
def update_header_status(n_intervals):
    status = process_manager.get_module_status()
    active_count = sum(1 for s in status.values() if s['active'])
    total_count = len([s for s in status.values() if s['type'] != 'integrated'])+1
    
    return f"🟢 {active_count}/{total_count} Module aktiv | 🌐 {process_manager.ip_address} | ⏰ {datetime.now().strftime('%H:%M:%S')}"

@app.callback(
    Output('tab-content', 'children'),
    [Input('main-tabs', 'value'),
     Input('status-interval', 'n_intervals')]
)
def render_tab_content(active_tab, n_intervals):
    if active_tab == 'overview':
        return create_overview_content()
    elif active_tab == 'kennlinie':
        return create_kennlinie_content()
    elif active_tab in MODULES:
        return create_module_content(active_tab)
    else:
        return html.Div("Tab nicht gefunden")

def create_overview_content():
    """Erstellt Übersichts-Content"""
    status = process_manager.get_module_status()
    
    # Status Cards
    status_cards = []
    for module_id, module_status in status.items():
        if module_status['type'] == 'integrated':
            continue
            
        config = MODULES[module_id]
        
        if module_status['status'] == 'online':
            status_color = '#27ae60'
            status_icon = '🟢'
            status_text = 'Online'
        elif module_status['status'] == 'starting':
            status_color = '#f39c12'
            status_icon = '🟡'
            status_text = 'Startet...'
        else:
            status_color = '#e74c3c'
            status_icon = '🔴'
            status_text = 'Offline'
        
        # Control Buttons
        if module_status['active']:
            control_button = html.Button(
                '⏹️ Stoppen',
                id=f'stop-{module_id}',
                className='control-button stop-button',
                style={
                    'backgroundColor': '#e74c3c',
                    'color': 'white',
                    'border': 'none',
                    'padding': '8px 15px',
                    'borderRadius': '5px',
                    'cursor': 'pointer',
                    'marginTop': '10px'
                }
            )
        else:
            control_button = html.Button(
                '▶️ Starten',
                id=f'start-{module_id}',
                className='control-button start-button',
                style={
                    'backgroundColor': '#27ae60',
                    'color': 'white',
                    'border': 'none',
                    'padding': '8px 15px',
                    'borderRadius': '5px',
                    'cursor': 'pointer',
                    'marginTop': '10px'
                }
            )
        
        card = html.Div([
            html.Div([
                html.H3([
                    config['icon'], ' ', config['name']
                ], style={'margin': '0 0 10px 0', 'color': config['color']}),
                
                html.Div([
                    html.Span(status_icon, style={'fontSize': '20px', 'marginRight':'10px'}),
                    html.Span(status_text, style={'fontWeight': 'bold', 'color': status_color})
                ], style={'marginBottom': '10px'}),
                
                html.P(f"Port: {module_status.get('port', 'N/A')}", 
                      style={'margin': '5px 0', 'fontSize': '14px', 'color': '#7f8c8d'}),
                
                control_button
            ])
        ], style={
            'border': f'2px solid {status_color}',
            'borderRadius': '10px',
            'padding': '20px',
            'margin': '10px',
            'width': '250px',
            'display': 'inline-block',
            'verticalAlign': 'top',
            'backgroundColor': 'white',
            'boxShadow': '0 2px 5px rgba(0,0,0,0.1)'
        })
        
        status_cards.append(card)
    
    return html.Div([
        html.H2("📊 System Übersicht", style={'color': '#2c3e50', 'marginBottom': '30px'}),
        
        # System Info
        html.Div([
            html.Div([
                html.H4("🖥️ System Information", style={'color': '#34495e', 'marginBottom': '15px'}),
                html.P(f"🔧 Debug Mode: {'AN' if DEBUG_MODE else 'AUS'}"),
                html.P(f"🎭 Simulation Mode: {'AN' if SIMULATION_MODE else 'AUS'}"),
                html.P(f"🌐 IP-Adresse: {process_manager.ip_address}"),
                html.P(f"⏰ Letzte Aktualisierung: {datetime.now().strftime('%H:%M:%S')}")
            ], style={
                'backgroundColor': '#ecf0f1',
                'padding': '20px',
                'borderRadius': '10px',
                'marginBottom': '30px'
            })
        ]),
        
        # Module Status
        html.H3("📱 Module Status", style={'color': '#2c3e50', 'marginBottom': '20px'}),
        html.Div(status_cards, style={'textAlign': 'center'})
    ])

def create_module_content(module_id):
    """Erstellt Content für ein spezifisches Modul"""
    config = MODULES[module_id]
    status = process_manager.get_module_status()[module_id]
    
    if not status['active']:
        return html.Div([
            html.Div([
                html.H2([config['icon'], ' ', config['name']], 
                       style={'color': config['color'], 'textAlign': 'center'}),
                html.Div([
                    html.P("🔴 Modul ist nicht aktiv", 
                          style={'fontSize': '18px', 'textAlign': 'center', 'color': '#e74c3c'}),
                    html.Button(
                        '▶️ Modul starten',
                        id=f'start-{module_id}-inline',
                        style={
                            'backgroundColor': '#27ae60',
                            'color': 'white',
                            'border': 'none',
                            'padding': '15px 30px',
                            'borderRadius': '8px',
                            'cursor': 'pointer',
                            'fontSize': '16px',
                            'margin': '20px'
                        }
                    )
                ], style={'textAlign': 'center'})
            ], style={
                'backgroundColor': '#f8f9fa',
                'padding': '40px',
                'borderRadius': '10px',
                'textAlign': 'center'
            })
        ])
    
    # Module is active - show iframe
    module_url = f"http://{process_manager.ip_address}:{config['port']}"
    
    return html.Div([
        html.Div([
            html.H3([config['icon'], ' ', config['name']], 
                   style={'color': config['color'], 'margin': '0', 'display': 'inline-block'}),
            html.Div([
                html.Span("🟢 Online", style={'color': '#27ae60', 'marginRight': '20px'}),
                html.A("🔗 In neuem Tab öffnen", href=module_url, target="_blank",
                      style={'color': '#3498db', 'textDecoration': 'none'})
            ], style={'float': 'right', 'fontSize': '14px'})
        ], style={'marginBottom': '20px', 'overflow': 'hidden'}),
        
        html.Iframe(
            src=module_url,
            style={
                'width': '100%',
                'height': '800px',
                'border': '1px solid #ddd',
                'borderRadius': '8px'
            }
        )
    ])

def create_kennlinie_content():
    """Erstellt Content für Kennlinien-Tab"""
    return html.Div([
        html.H2("📋 Kennlinien Messungen", style={'color': '#9b59b6', 'marginBottom': '30px'}),
        
        html.Div([
            html.Div([
                html.H3("📊 Diodenkennlinie", style={'color': '#e74c3c'}),
                html.P("Messung der Strom-Spannungs-Charakteristik von Dioden"),
                html.Button(
                    "🔬 Diodenkennlinie starten",
                    id="start-diode-kennlinie",
                    style={
                        'backgroundColor': '#e74c3c',
                        'color': 'white',
                        'border': 'none',
                        'padding': '15px 25px',
                        'borderRadius': '8px',
                        'cursor': 'pointer',
                        'fontSize': '16px',
                        'margin': '10px 0'
                    }
                )
            ], style={
                'backgroundColor': 'white',
                'padding': '30px',
                'borderRadius': '10px',
                'margin': '10px',
                'width': '45%',
                'display': 'inline-block',
                'verticalAlign': 'top',
                'boxShadow': '0 2px 5px rgba(0,0,0,0.1)',
                'border': '2px solid #e74c3c'
            }),
            
            html.Div([
                html.H3("🌊 Filterkennlinie", style={'color': '#3498db'}),
                html.P("Frequenzgang-Messung von elektronischen Filtern"),
                html.Button(
                    "🔬 Filterkennlinie starten",
                    id="start-filter-kennlinie",
                    style={
                        'backgroundColor': '#3498db',
                        'color': 'white',
                        'border': 'none',
                        'padding': '15px 25px',
                        'borderRadius': '8px',
                        'cursor': 'pointer',
                        'fontSize': '16px',
                        'margin': '10px 0'
                    }
                )
            ], style={
                'backgroundColor': 'white',
                'padding': '30px',
                'borderRadius': '10px',
                'margin': '10px',
                'width': '45%',
                'display': 'inline-block',
                'verticalAlign': 'top',
                'boxShadow': '0 2px 5px rgba(0,0,0,0.1)',
                'border': '2px solid #3498db'
            })
        ], style={'textAlign': 'center'}),
        
        # Results Area
        html.Div(id='kennlinie-results', style={'marginTop': '30px'})
    ])

# Module Control Callbacks
for module_id in MODULES:
    if MODULES[module_id]['type'] == 'dash_app':
        # Start button callback
        @app.callback(
            Output(f'start-{module_id}', 'children'),
            Input(f'start-{module_id}', 'n_clicks'),
            prevent_initial_call=True
        )
        def start_module_callback(n_clicks, module_id=module_id):
            if n_clicks:
                success = process_manager.start_module(module_id)
                if success:
                    return '✅ Gestartet'
                else:
                    return '❌ Fehler'
            return '▶️ Starten'
        
        # Stop button callback
        @app.callback(
            Output(f'stop-{module_id}', 'children'),
            Input(f'stop-{module_id}', 'n_clicks'),
            prevent_initial_call=True
        )
        def stop_module_callback(n_clicks, module_id=module_id):
            if n_clicks:
                success = process_manager.stop_process(module_id)
                if success:
                    return '✅ Gestoppt'
                else:
                    return '❌ Fehler'
            return '⏹️ Stoppen'

# Kennlinie Callbacks
@app.callback(
    Output('kennlinie-results', 'children'),
    [Input('start-diode-kennlinie', 'n_clicks'),
     Input('start-filter-kennlinie', 'n_clicks')],
    prevent_initial_call=True
)
def handle_kennlinie_buttons(diode_clicks, filter_clicks):
    ctx = callback_context
    if not ctx.triggered:
        return ""
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'start-diode-kennlinie':
        return html.Div([
            html.H4("🔬 Diodenkennlinie Messung gestartet", style={'color': '#e74c3c'}),
            html.P("Die Messung läuft... Ergebnisse werden hier angezeigt."),
            # Hier würden Sie die tatsächliche Diodenkennlinie-Logik implementieren
        ], style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '8px'})
    
    elif button_id == 'start-filter-kennlinie':
        return html.Div([
            html.H4("🔬 Filterkennlinie Messung gestartet", style={'color': '#3498db'}),
            html.P("Die Messung läuft... Ergebnisse werden hier angezeigt."),
            # Hier würden Sie die tatsächliche Filterkennlinie-Logik implementieren
        ], style={'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '8px'})
    
    return ""

# Cleanup
atexit.register(process_manager.cleanup_all)

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 OurDAQ Dashboard - Verbesserte Version")
    print("=" * 60)
    print(f"🔧 Debug Mode: {'AN' if DEBUG_MODE else 'AUS'}")
    print(f"🎭 Simulation Mode: {'AN' if SIMULATION_MODE else 'AUS'}")
    print(f"🌐 IP-Adresse: {process_manager.ip_address}")
    print(f"🌐 Dashboard URL: http://{process_manager.ip_address}:{DASHBOARD_CONFIG['port']}")
    print("=" * 60)
    
    try:
        app.run(
            host=DASHBOARD_CONFIG['host'], 
            port=DASHBOARD_CONFIG['port'], 
            debug=DASHBOARD_CONFIG['debug']
        )
    except KeyboardInterrupt:
        print("\n🛑 Dashboard wird beendet...")
        process_manager.cleanup_all()
    except Exception as e:
        print(f"❌ Fehler: {e}")
        process_manager.cleanup_all()
