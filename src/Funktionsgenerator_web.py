#!/usr/bin/env python3
"""
Web-basierter Funktionsgenerator mit AD9833
Dieses Modul stellt eine webbasierte Benutzeroberfläche für den AD9833 Funktionsgenerator bereit.
"""

import socket
import sys
from typing import Optional, Dict, Any
import time

# Dash-Importierungen
from dash import Dash, dcc, html, Input, Output, State, callback
import plotly.graph_objects as go

# Simulation Mode überprüfen
SIMULATION_MODE = '--simulate' in sys.argv

# Mock Hardware Imports für Simulation
if not SIMULATION_MODE:
    try:
        import lgpio
        import spidev
    except ImportError as e:
        print(f"Hardware-Bibliotheken nicht verfügbar: {e}. Wechsle zu Simulation.")
        SIMULATION_MODE = True

# AD9833 Register-Konstanten
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
# CONTROL_REG = 0x2000 # Diese Konstante ist die Quelle des Fehlers und wird entfernt.

# KORRIGIERTE Wellenform-Konstanten
# Der Abschlussbefehl zum Aktivieren der Wellenform darf das B28-Bit (0x2000) NICHT enthalten.
SINE_WAVE = 0x0000      # Sinuswelle (RESET=0, B28=0)
TRIANGLE_WAVE = 0x0002  # Dreieckswelle (RESET=0, B28=0, MODE=1)
SQUARE_WAVE = 0x0028    # Rechteckwelle (RESET=0, B28=0, OPBITEN=1, DIV2=1)

# Dieser Reset-Befehl ist KORREKT, da er B28=1 und RESET=1 setzt, um die Frequenzübertragung zu starten.
RESET = 0x2100

# SPI Einstellungen
SPI_BUS = 0
SPI_DEVICE = 0
SPI_FREQUENCY = 1000000  # 1 MHz

# FSYNC Pin (Chip Select)
FSYNC_PIN = 25  # GPIO-Pin für FSYNC

# Frequenz-Konstanten
FMCLK = 25000000  # 25 MHz Standardtaktfrequenz
MAX_FREQUENCY = 20000  # Maximale Ausgangsfrequenz: 20 kHz
MIN_FREQUENCY = 0.1    # Minimale Ausgangsfrequenz: 0.1 Hz

# Globale Variablen für Hardware
gpio_handle = None
spi = None
current_status = "Nicht initialisiert"

# Dash App initialisieren
app = Dash(__name__)
app.css.config.serve_locally = True
app.scripts.config.serve_locally = True
app.title = "AD9833 Funktionsgenerator"

def get_ip_address() -> str:
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts"""
    ip_address = '127.0.0.1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.connect(('1.1.1.1', 1))
        ip_address = sock.getsockname()[0]
    finally:
        sock.close()
    
    return ip_address

def init_AD9833() -> bool:
    """Initialisiert GPIO und SPI für AD9833"""
    global gpio_handle, spi, current_status
    
    if SIMULATION_MODE:
        current_status = "Simulation - Hardware emuliert"
        return True
    
    try:
        # lgpio initialisieren - öffnet GPIO-Chip
        gpio_handle = lgpio.gpiochip_open(4)  # gpiochip4 für Raspberry Pi 5

        # FSYNC Pin als Ausgang konfigurieren (initial HIGH)
        lgpio.gpio_claim_output(gpio_handle, FSYNC_PIN, lgpio.SET)

        # SPI initialisieren
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_DEVICE)
        spi.max_speed_hz = SPI_FREQUENCY
        spi.mode = 0b10  # SPI Modus 2 (CPOL=1, CPHA=0)

        # Initiales Reset des AD9833
        reset_success = write_to_AD9833(RESET)
        if not reset_success:
            current_status = "Initiales Reset fehlgeschlagen"
            return False
            
        time.sleep(0.1)  # Warten bis Reset abgeschlossen
        current_status = "Hardware erfolgreich initialisiert"
        return True
        
    except Exception as e:
        current_status = f"Initialisierungsfehler: {e}"
        cleanup_AD9833()
        return False

def write_to_AD9833(data: int) -> bool:
    """Sendet 16-Bit Daten an AD9833"""
    if SIMULATION_MODE:
        # Im Simulationsmodus loggen wir, was gesendet würde
        # print(f"SIM: Sende 0x{data:04X} an AD9833")
        return True
        
    if gpio_handle is None or spi is None:
        return False
    
    try:
        # FSYNC auf LOW setzen (Übertragung startet)
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, lgpio.CLEAR)
        
        # 16-Bit Daten in zwei 8-Bit Bytes aufteilen und senden
        high_byte = (data >> 8) & 0xFF
        low_byte = data & 0xFF
        spi.xfer2([high_byte, low_byte])
        
        # FSYNC auf HIGH setzen (Übertragung beendet)
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, lgpio.SET)
        
        return True
        
    except Exception as e:
        current_status = f"SPI Schreibfehler: {e}"
        return False

def configure_AD9833(freq_hz: float, waveform: int) -> bool:
    """Komplette Konfiguration des AD9833 mit korrekter Sequenz"""
    global current_status
    
    try:
        # Frequenz validieren
        if not (MIN_FREQUENCY <= freq_hz <= MAX_FREQUENCY):
            current_status = f"Frequenz {freq_hz} Hz außerhalb des gültigen Bereichs"
            return False

        # Frequenzwort berechnen (28-Bit)
        freq_word = int((freq_hz * (2**28)) / FMCLK)
        
        # KRITISCHE ÜBERTRAGUNGSSEQUENZ
        # 1. Reset aktivieren UND B28-Bit setzen
        if not write_to_AD9833(RESET): # RESET = 0x2100
            current_status = "Reset-Befehl fehlgeschlagen"
            return False
        
        # 2. Lower 14 Bits schreiben
        if not write_to_AD9833(FREQ0_REG | (freq_word & 0x3FFF)):
            current_status = "Lower Bits Übertragung fehlgeschlagen"
            return False
        
        # 3. Upper 14 Bits schreiben  
        if not write_to_AD9833(FREQ0_REG | ((freq_word >> 14) & 0x3FFF)):
            current_status = "Upper Bits Übertragung fehlgeschlagen"
            return False
            
        # 4. Wellenform aktivieren UND Reset beenden (B28-Bit ist hier 0!)
        if not write_to_AD9833(waveform):
            current_status = "Wellenform-Aktivierung fehlgeschlagen"
            return False

        current_status = f"Konfiguration erfolgreich abgeschlossen"
        return True
        
    except Exception as e:
        current_status = f"Konfigurationsfehler: {e}"
        return False

def combined_init_and_configure(freq_hz: float, waveform: int) -> bool:
    """Kombinierte Initialisierung und Konfiguration in einem Schritt"""
    global current_status
    
    # Schritt 1: Hardware initialisieren falls noch nicht geschehen
    if not SIMULATION_MODE and (gpio_handle is None or spi is None):
        if not init_AD9833():
            return False
    
    # Schritt 2: Signal konfigurieren
    return configure_AD9833(freq_hz, waveform)

def cleanup_AD9833():
    """Räumt GPIO und SPI Ressourcen auf"""
    global gpio_handle, spi, current_status
    
    if SIMULATION_MODE:
        return
    
    try:
        if gpio_handle is not None and spi is not None:
            write_to_AD9833(RESET)
            time.sleep(0.01)
        
        if gpio_handle is not None:
            lgpio.gpio_free(gpio_handle, FSYNC_PIN)
            lgpio.gpiochip_close(gpio_handle)
            gpio_handle = None
        
        if spi is not None:
            spi.close()
            spi = None
            
        current_status = "Ressourcen freigegeben"
            
    except Exception as e:
        current_status = f"Cleanup-Fehler: {e}"

# Layout der Dash-Anwendung
app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '800px', 'margin': 'auto'}, children=[
    html.H1("AD9833 Funktionsgenerator", 
            style={'textAlign': 'center', 'color': 'white', 'backgroundColor': '#007BFF',
                   'padding': '20px', 'borderRadius': '8px'}),
    
    html.Div(id='control-panel', style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px', 'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)'}, children=[
        html.H3("Status"),
        html.Div(id='status-display', style={'padding': '10px', 'backgroundColor': '#e9ecef', 'borderRadius': '5px', 'marginBottom': '20px', 'fontWeight': 'bold'}),
        
        html.H3("Einstellungen"),
        html.Label(f"Frequenz ({MIN_FREQUENCY} - {MAX_FREQUENCY} Hz):"),
        dcc.Input(
            id='frequency-input',
            type='text',
            inputMode='numeric',
            pattern='[0-9]*\.?[0-9]+',
            value='1000',
            style={'width': '100%', 'padding': '8px', 'marginBottom': '20px'}
        ),
        
        html.Label("Wellenform:"),
        dcc.RadioItems(
            id='waveform-selector',
            options=[
                {'label': ' Sinus', 'value': SINE_WAVE},
                {'label': ' Dreieck', 'value': TRIANGLE_WAVE},
                {'label': ' Rechteck', 'value': SQUARE_WAVE}
            ],
            value=SINE_WAVE,
            labelStyle={'display': 'inline-block', 'marginRight': '20px', 'cursor': 'pointer'},
            style={'marginBottom': '30px'}
        ),
        
        html.Div([
            html.Button('Signal aktivieren / Aktualisieren', id='activate-button', n_clicks=0, 
                        style={'backgroundColor': '#28a745', 'color': 'white', 'border': 'none', 'padding': '12px 24px', 'borderRadius': '5px', 'cursor': 'pointer', 'marginRight': '10px'}),
            html.Button('Reset', id='reset-button', n_clicks=0,
                        style={'backgroundColor': '#dc3545', 'color': 'white', 'border': 'none', 'padding': '12px 24px', 'borderRadius': '5px', 'cursor': 'pointer'})
        ], style={'textAlign': 'center'})
    ])
])

# Callbacks für Interaktivität
@callback(
    Output('status-display', 'children'),
    Input('activate-button', 'n_clicks'),
    Input('reset-button', 'n_clicks'),
    State('frequency-input', 'value'),
    State('waveform-selector', 'value'),
    prevent_initial_call=True
)
def handle_button_actions(activate_clicks, reset_clicks, frequency_str, waveform):
    """Behandelt Button-Aktionen und aktualisiert den Status"""
    global current_status
    from dash import callback_context
    
    button_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'activate-button':
        try:
            # Versuche, den String in eine Gleitkommazahl umzuwandeln
            frequency = float(frequency_str)
        except (ValueError, TypeError):
            # Schlägt fehl, wenn der String leer ist oder keine Zahl darstellt
            current_status = "Ungültige Frequenzeingabe. Bitte geben Sie eine Zahl ein."
            return html.Span(current_status, style={'color': '#dc3545'})
        
        success = combined_init_and_configure(frequency, waveform)
        if success:
            # Überprüfen, ob die Frequenz im gültigen Bereich lag
            if not (MIN_FREQUENCY <= frequency <= MAX_FREQUENCY):
                 return html.Span(current_status, style={'color': '#dc3545'}) # Zeigt die Fehlermeldung aus configure_AD9833
            
            waveform_names = {SINE_WAVE: "Sinus", TRIANGLE_WAVE: "Dreieck", SQUARE_WAVE: "Rechteck"}
            waveform_name = waveform_names.get(waveform, "Unbekannt")
            status_msg = f"Aktiv: {frequency} Hz, {waveform_name}"
            return html.Span(status_msg, style={'color': '#28a745'})
        else:
            return html.Span(current_status, style={'color': '#dc3545'})
    
    elif button_id == 'reset-button':
        if not SIMULATION_MODE and (gpio_handle is None or spi is None):
            init_AD9833() # Sicherstellen, dass die Hardware initialisiert ist
            
        if write_to_AD9833(RESET):
            current_status = "AD9833 zurückgesetzt. Ausgabe gestoppt."
            return html.Span(current_status, style={'color': '#007BFF'})
        else:
            current_status = "Reset fehlgeschlagen."
            return html.Span(current_status, style={'color': '#dc3545'})
    
    return current_status

# Callback zur Initialisierung beim Start und zur Anzeige des Anfangsstatus
@callback(
    Output('status-display', 'children', allow_duplicate=True),
    Input('control-panel', 'id'),
    prevent_initial_call=True
)
def auto_init_on_load(_):
    init_AD9833()
    return current_status

if __name__ == '__main__':
    print(f"Starte Funktionsgenerator im {'Simulation' if SIMULATION_MODE else 'Hardware'}-Modus")
    
    # Initialisierung
    init_AD9833()
    
    # Cleanup beim Beenden registrieren
    import atexit
    atexit.register(cleanup_AD9833)
    
    try:
        ip_address = get_ip_address()
        print(f"Server läuft auf http://{ip_address}:8060")
        app.run(host=ip_address, port=8060, debug=False)
    except Exception as e:
        print(f"Fehler beim Starten des Servers: {e}")
    finally:
        print("\nRäume auf und beende die Anwendung...")
        cleanup_AD9833()