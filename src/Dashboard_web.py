#!/usr/bin/env python3
"""
OurDAQ Dashboard
================

**ANLEITUNG ZUR VERWENDUNG DES JUPYTER-BUTTONS:**

Dieses Skript enthält nun einen Button "Jupyter Lab starten".
Wenn Sie darauf klicken, wird versucht, ein neues Terminalfenster auf Ihrem
Betriebssystem zu öffnen und darin Jupyter Lab zu starten.

Stellen Sie sicher, dass Jupyter Lab installiert ist:
`pip install jupyterlab`
"""

import sys
import socket
import subprocess
import os
import time
import atexit
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from pathlib import Path
import requests
from dash import Dash, dcc, html, Input, Output, State, callback_context
import webbrowser

# =============================================================================
# KONFIGURATION
# =============================================================================

@dataclass
class ModuleConfig:
    name: str
    script: Optional[str] = None
    port: Optional[int] = None
    color: str = '#3498db'
    type: str = 'dash_app'

@dataclass
class SystemConfig:
    debug: bool = True
    simulation: bool = False
    host: str = '0.0.0.0'
    port: int = 8000
    title: str = 'OurDAQ Datenerfassungssystem'

# --- MODIFIZIERTE MODUL-DEFINITIONEN ---
# Die Kennlinie-Module wurden entfernt, da sie über einen zentralen Button gesteuert werden.
MODULES = {
    'dmm': ModuleConfig('Digitalmultimeter', 'DMM_web.py', 8050, '#3498db'),
    'funktionsgenerator': ModuleConfig('Funktionsgenerator', 'Test/Funktionsgenerator_web.py', 8060, '#e74c3c'),
    'oszilloskop': ModuleConfig('Oszilloskop', 'Oszilloskop_web.py', 8080, '#27ae60'),
    'netzteil_plus': ModuleConfig('Netzteil positiv', 'Netzteil_plus_web.py', 8071, '#f39c12'),
    'netzteil_minus': ModuleConfig('Netzteil negativ', 'Netzteil_minus_web.py', 8072, '#f39c12'),
}

CONFIG = SystemConfig()

# =============================================================================
# UTILITIES & PROZESS-FUNKTIONEN
# =============================================================================

# (Die Klassen Logger und SystemUtils bleiben unverändert)
class Logger:
    @staticmethod
    def debug(message: str):
        if CONFIG.debug:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] {message}")
    @staticmethod
    def info(message: str): print(f"Info: {message}")
    @staticmethod
    def error(message: str): print(f"Error: {message}")

class SystemUtils:
    @staticmethod
    def is_raspberry_pi() -> bool:
        try:
            return 'Raspberry Pi' in Path('/proc/cpuinfo').read_text()
        except FileNotFoundError: return False
    @staticmethod
    def get_ip_address() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(('1.1.1.1', 1)); return sock.getsockname()[0]
        except Exception: return '127.0.0.1'
    @staticmethod
    def is_port_available(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(('', port)); return True
        except socket.error: return False

def open_jupyter_in_new_terminal() -> (bool, str):
    """
    Öffnet Jupyter Lab in einem neuen Terminalfenster.
    Gibt (Erfolg, Nachricht) zurück.
    """
    project_dir = Path(__file__).parent.resolve()
    # Startet Jupyter Lab im Verzeichnis des Projekts
    jupyter_command = f"jupyter lab --notebook-dir='{project_dir}'"

    command_to_run = []
    platform = sys.platform

    if platform.startswith("linux"):
        # Priorisiert lxterminal für Raspberry Pi, mit Fallbacks
        terminals = ["lxterminal", "gnome-terminal", "xterm"]
        for term in terminals:
            # Überprüfen, ob der Terminal-Emulator existiert
            if subprocess.run(["which", term], capture_output=True).returncode == 0:
                command_to_run = [term, "-e", jupyter_command]
                break
        if not command_to_run:
            return False, "Kein unterstützter Terminal-Emulator (lxterminal, gnome-terminal, xterm) gefunden."

    elif platform == "darwin":  # macOS
        command_to_run = [
            "osascript",
            "-e", f'tell app "Terminal" to do script "{jupyter_command}"'
        ]
    elif platform == "win32":  # Windows
        # start cmd /k führt den Befehl aus und lässt das Fenster offen
        command_to_run = ["start", "cmd", "/k", jupyter_command]
    else:
        return False, f"Nicht unterstütztes Betriebssystem: {platform}"

    try:
        # Führe den Befehl als separaten Prozess aus, ohne auf ihn zu warten
        subprocess.Popen(command_to_run, shell=(platform == "win32")) # shell=True wird für 'start' unter Windows benötigt
        return True, "Jupyter Lab wird in einem neuen Terminal gestartet..."
    except Exception as e:
        Logger.error(f"Fehler beim Öffnen des Terminals: {e}")
        return False, f"Fehler beim Ausführen des Befehls: {e}"

# =============================================================================
# PROCESS MANAGER
# =============================================================================

# (ProcessManager Klasse bleibt größtenteils unverändert)
@dataclass
class ProcessInfo:
    process: subprocess.Popen
    port: int
    started_at: datetime = field(default_factory=datetime.now)
    restart_count: int = 0

class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, ProcessInfo] = {}
        self.ip_address = SystemUtils.get_ip_address()
        CONFIG.simulation = not SystemUtils.is_raspberry_pi()
        self.system_log = []
        self.start_time = datetime.now()
        Logger.info(f"Simulation Mode: {'AN' if CONFIG.simulation else 'AUS'}")
        self.log_message("System gestartet", "info")

    def start_module(self, module_id: str) -> bool:
        if module_id not in MODULES:
            error_msg = f"Modul {module_id} nicht gefunden"; Logger.error(error_msg); self.log_message(error_msg, "error"); return False
        config = MODULES[module_id]
        if config.type != 'dash_app' or not config.script or not config.port: return False
        if not SystemUtils.is_port_available(config.port):
            error_msg = f"Port {config.port} bereits belegt für {config.name}"; Logger.error(error_msg); self.log_message(error_msg, "error"); return False
        script_path = Path(__file__).parent / config.script
        if not script_path.exists():
            error_msg = f"Script nicht gefunden: {script_path}"; Logger.error(error_msg); self.log_message(error_msg, "error"); return False
        try:
            command = [sys.executable, str(script_path)]
            if CONFIG.simulation: command.append('--simulate')
            env = os.environ.copy()
            env['PYTHONPATH'] = str(Path(__file__).parent)
            env['DASH_HOST'] = '0.0.0.0'
            env['DASH_PORT'] = str(config.port)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=str(Path(__file__).parent))
            time.sleep(3)
            if process.poll() is not None:
                stderr_output = process.stderr.read()
                error_msg = f"Prozess {module_id} sofort beendet. Fehler: {stderr_output}"; Logger.error(error_msg); self.log_message(error_msg, "error"); return False
            self.processes[module_id] = ProcessInfo(process, config.port)
            success_msg = f"{config.name} gestartet auf Port {config.port}"; Logger.info(success_msg); self.log_message(success_msg, "success"); return True
        except Exception as e:
            error_msg = f"Fehler beim Starten von {module_id}: {e}"; Logger.error(error_msg); self.log_message(error_msg, "error"); return False

    def stop_module(self, module_id: str) -> bool:
        if module_id not in self.processes: return False
        try:
            process_info = self.processes[module_id]; process_info.process.terminate(); process_info.process.wait(timeout=2); del self.processes[module_id]
            success_msg = f"{MODULES[module_id].name} gestoppt"; Logger.info(success_msg); self.log_message(success_msg, "success"); return True
        except Exception as e:
            error_msg = f"Fehler beim Stoppen von {module_id}: {e}"; Logger.error(error_msg); self.log_message(error_msg, "error"); return False

    def get_system_info(self) -> Dict:
        uptime = datetime.now() - self.start_time
        return {'ip_address': self.ip_address, 'mode': 'Simulation' if CONFIG.simulation else 'Hardware', 'hardware_available': not CONFIG.simulation, 'uptime': str(uptime).split('.')[0], 'dashboard_port': CONFIG.port, 'debug_mode': CONFIG.debug, 'system_time': datetime.now().strftime('%H:%M:%S'), 'raspberry_pi': SystemUtils.is_raspberry_pi()}
    def log_message(self, message: str, level: str = "info"):
        timestamp = datetime.now().strftime('%H:%M:%S'); self.system_log.append({'timestamp': timestamp, 'message': message, 'level': level})
        if len(self.system_log) > 50: self.system_log = self.system_log[-50:]
    def stop_all_modules(self) -> int:
        stopped_count = 0
        for module_id in list(self.processes.keys()):
            if self.stop_module(module_id): stopped_count += 1
        self.log_message(f"{stopped_count} Module gestoppt", "info"); return stopped_count
    def cleanup(self):
        Logger.info("Cleanup gestartet..."); self.stop_all_modules()


# =============================================================================
# UI COMPONENTS
# =============================================================================

class UIComponents:
    @staticmethod
    def create_header(ip_address: str) -> html.Div:
        return html.Div([
            html.H1(CONFIG.title, style={'textAlign': 'center', 'color': 'white', 'margin': '0', 'fontSize': '32px', 'fontWeight': '300'}),
            html.Div(id='header-status', style={'textAlign': 'center', 'color': 'white', 'fontSize': '14px', 'marginTop': '10px', 'opacity': '0.9'})
        ], style={'background': 'linear-gradient(135deg, #2c3e50 0%, #34495e 100%)', 'padding': '30px 20px', 'marginBottom': '0', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'})

    @staticmethod
    def create_system_overview(system_info: Dict) -> html.Div:
        hardware_color = '#27ae60' if system_info['hardware_available'] else '#e74c3c'
        hardware_text = 'Hardware verfügbar' if system_info['hardware_available'] else 'Simulation aktiv'
        raspberry_pi_text = 'Raspberry Pi erkannt' if system_info['raspberry_pi'] else 'Kein Raspberry Pi'
        return html.Div([
            html.H2("Systemübersicht", style={'color': '#2c3e50', 'marginBottom': '20px', 'textAlign': 'center'}),
            html.Div([
                html.Div([html.H4("Netzwerk", style={'color': '#3498db', 'margin': '0 0 10px 0'}), html.P(f"IP-Adresse: {system_info['ip_address']}", style={'margin': '5px 0'}), html.P(f"Laufzeit: {system_info['uptime']}", style={'margin': '5px 0'})], style={'flex': '1', 'margin': '10px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px', 'border': '2px solid #3498db'}),
                html.Div([html.H4("Hardware", style={'color': hardware_color, 'margin': '0 0 10px 0'}), html.P(hardware_text, style={'margin': '5px 0', 'fontWeight': 'bold', 'color': hardware_color}), html.P(f"Raspberry Pi: {raspberry_pi_text}", style={'margin': '5px 0', 'color': hardware_color}), html.P(f"Dashboard Port: {system_info['dashboard_port']}", style={'margin': '5px 0'})], style={'flex': '1', 'margin': '10px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px', 'border': f'2px solid {hardware_color}'})
            ], style={'display': 'flex', 'flexWrap': 'wrap'})
        ], style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '12px', 'marginBottom': '25px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)'})

    @staticmethod
    def create_navigation_buttons(ip_address: str) -> html.Div:
        buttons = []
        base_style = {'padding': '25px 50px', 'borderRadius': '15px', 'cursor': 'pointer', 'fontSize': '20px', 'margin': '15px', 'textAlign': 'center', 'boxShadow': '0 4px 8px rgba(0,0,0,0.1)', 'transition': 'all 0.3s ease', 'border': 'none', 'color': 'white'}
        link_style = {**base_style, 'display': 'inline-block', 'textDecoration': 'none'}
        button_style = {**base_style, 'display': 'inline-block'}

        for module_id, config in MODULES.items():
            if config.type == 'dash_app' and config.port:
                buttons.append(html.A(config.name, href=f"http://{ip_address}:{config.port}", target="_blank", style={**link_style, 'backgroundColor': config.color}))

        # Hinzufügen des neuen, zentralen Jupyter-Buttons
        jupyter_button = html.Button(
            "Jupyter Lab starten",
            id='open-jupyter-button',
            n_clicks=0,
            style={**button_style, 'backgroundColor': '#5D6D7E', 'width': '100%', 'marginTop': '20px'}
        )

        return html.Div([
            html.H2("Module & Funktionen", style={'color': '#2c3e50', 'marginBottom': '25px', 'textAlign': 'center'}),
            html.Div(buttons, style={'textAlign': 'center'}),
            html.Div(jupyter_button, style={'textAlign': 'center', 'padding': '0 15px'}) # Um den Button zu zentrieren
        ], style={'backgroundColor': 'white', 'padding': '25px', 'borderRadius': '15px', 'marginBottom': '30px', 'boxShadow': '0 4px 15px rgba(0,0,0,0.1)'})

# =============================================================================
# DASH APP
# =============================================================================
process_manager = ProcessManager()
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = CONFIG.title
app.index_string = """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}<style>a:hover, button:hover { transform: scale(1.05); opacity: 0.9; }</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

app.layout = html.Div([
    UIComponents.create_header(process_manager.ip_address),
    html.Div([
        html.Div(id='system-overview'),
        html.Div(id='navigation-buttons'),
        html.Div(id='main-content')
    ], style={'maxWidth': '1200px', 'margin': '0 auto', 'padding': '20px', 'backgroundColor': '#f5f7fa', 'minHeight': '80vh'}),
    dcc.Interval(id='status-interval', interval=5000, n_intervals=0)
], style={'height': '100vh'})

# =============================================================================
# CALLBACKS
# =============================================================================
@app.callback(Output('header-status', 'children'), Input('status-interval', 'n_intervals'))
def update_header_status(n_intervals):
    system_info = process_manager.get_system_info()
    active_modules = len(process_manager.processes)
    return f"{active_modules} Module aktiv | IP: {system_info['ip_address']} | Zeit: {system_info['system_time']}"

@app.callback([Output('system-overview', 'children'), Output('navigation-buttons', 'children')], [Input('status-interval', 'n_intervals')])
def update_system_display(n_intervals):
    system_info = process_manager.get_system_info()
    overview = UIComponents.create_system_overview(system_info)
    buttons = UIComponents.create_navigation_buttons(process_manager.ip_address)
    return overview, buttons

# --- NEUER CALLBACK FÜR DEN JUPYTER-BUTTON ---
@app.callback(
    Output('main-content', 'children'),
    Input('open-jupyter-button', 'n_clicks'),
    prevent_initial_call=True
)
def handle_jupyter_button(n_clicks):
    success, message = open_jupyter_in_new_terminal()
    
    if success:
        style = {'color': '#27ae60', 'fontWeight': 'bold', 'padding': '10px', 'backgroundColor': '#d5f4e6', 'borderRadius': '5px', 'textAlign': 'center', 'marginTop': '20px'}
    else:
        style = {'color': '#e74c3c', 'fontWeight': 'bold', 'padding': '10px', 'backgroundColor': '#fadbd8', 'borderRadius': '5px', 'textAlign': 'center', 'marginTop': '20px'}
        
    return html.Div(message, style=style)

# =============================================================================
# INITIALIZATION & MAIN
# =============================================================================
def initialize_system():
    Logger.info("System wird initialisiert...")
    for module_id, config in MODULES.items():
        if config.type == 'dash_app':
            process_manager.start_module(module_id)
    dashboard_url = f"http://{process_manager.ip_address}:{CONFIG.port}"
    Logger.info(f"Dashboard wird geöffnet: {dashboard_url}")
    webbrowser.open(dashboard_url)

if __name__ == '__main__':
    atexit.register(process_manager.cleanup)
    initialize_system()
    try:
        Logger.info(f"Starte Dashboard auf http://{process_manager.ip_address}:{CONFIG.port}")
        app.run(host=CONFIG.host, port=CONFIG.port, debug=CONFIG.debug, use_reloader=False)
    except Exception as e:
        Logger.error(f"Fehler beim Starten des Dashboards: {e}"); process_manager.cleanup()