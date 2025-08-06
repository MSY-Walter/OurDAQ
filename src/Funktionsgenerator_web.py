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
CONTROL_REG = 0x2000

# Wellenform-Konstanten
SINE_WAVE = 0x2000      # Sinuswelle
TRIANGLE_WAVE = 0x2002  # Dreieckswelle
SQUARE_WAVE = 0x2028    # Rechteckwelle
RESET = 0x2100          # Reset-Befehl

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
        return False

def set_ad9833_frequency(freq_hz: float) -> bool:
    """Stellt die Ausgangsfrequenz des AD9833 ein"""
    global current_status
    
    if not (MIN_FREQUENCY <= freq_hz <= MAX_FREQUENCY):
        current_status = f"Frequenz {freq_hz} Hz außerhalb des gültigen Bereichs"
        return False
    
    try:
        # Frequenzwort berechnen (28-Bit)
        freq_word = int((freq_hz * (2**28)) / FMCLK)
        
        # KRITISCHE ÜBERTRAGUNGSSEQUENZ
        # 1. Reset aktivieren
        if not write_to_AD9833(RESET):
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
        
        current_status = f"Frequenz auf {freq_hz} Hz eingestellt"
        return True
        
    except Exception as e:
        current_status = f"Fehler beim Setzen der Frequenz: {e}"
        return False

def activate_waveform(waveform: int) -> bool:
    """Aktiviert die gewählte Wellenform"""
    global current_status
    
    waveform_names = {
        SINE_WAVE: "Sinuswelle",
        TRIANGLE_WAVE: "Dreieckswelle", 
        SQUARE_WAVE: "Rechteckwelle"
    }
    
    try:
        # Wellenform aktivieren (beendet gleichzeitig Reset-Zustand)
        if not write_to_AD9833(waveform):
            current_status = "Wellenform-Aktivierung fehlgeschlagen"
            return False
        
        waveform_name = waveform_names.get(waveform, f"Unbekannt (0x{waveform:04X})")
        current_status = f"Wellenform {waveform_name} aktiviert"
        return True
        
    except Exception as e:
        current_status = f"Fehler beim Aktivieren der Wellenform: {e}"
        return False

def combined_init_and_configure(freq_hz: float, waveform: int) -> bool:
    """Kombinierte Initialisierung und Konfiguration in einem Schritt"""
    global current_status
    
    # Schritt 1: Hardware initialisieren falls noch nicht geschehen
    if gpio_handle is None or spi is None:
        if not init_AD9833():
            return False
    
    # Schritt 2: Signal konfigurieren
    return configure_AD9833(freq_hz, waveform)
    """Komplette Konfiguration des AD9833 mit korrekter Sequenz"""
    global current_status
    
    try:
        # Schritt 1: Frequenz einstellen
        if not set_ad9833_frequency(freq_hz):
            return False
        
        # Schritt 2: Wellenform aktivieren
        if not activate_waveform(waveform):
            return False
        
        current_status = f"Konfiguration erfolgreich abgeschlossen"
        return True
        
    except Exception as e:
        current_status = f"Konfigurationsfehler: {e}"
        return False

def cleanup_AD9833():
    """Räumt GPIO und SPI Ressourcen auf"""
    global gpio_handle, spi, current_status
    
    if SIMULATION_MODE:
        return
    
    try:
        # AD9833 zurücksetzen vor dem Beenden
        if gpio_handle is not None and spi is not None:
            try:
                write_to_AD9833(RESET)
                time.sleep(0.1)
            except:
                pass  # Ignoriere Fehler beim Reset
        
        # GPIO freigeben - nur wenn es tatsächlich allokiert war
        if gpio_handle is not None:
            try:
                # Prüfe ob GPIO bereits allokiert ist bevor wir versuchen es freizugeben
                lgpio.gpio_free(gpio_handle, FSYNC_PIN)
            except Exception as gpio_error:
                # GPIO war möglicherweise nicht allokiert - das ist ok
                if "not allocated" not in str(gpio_error).lower():
                    print(f"GPIO-Freigabe Warnung: {gpio_error}")
            
            try:
                lgpio.gpiochip_close(gpio_handle)
            except Exception as chip_error:
                print(f"GPIO-Chip schließen Warnung: {chip_error}")
            
            gpio_handle = None
        
        # SPI schließen
        if spi is not None:
            try:
                spi.close()
            except Exception as spi_error:
                print(f"SPI schließen Warnung: {spi_error}")
            spi = None
            
        current_status = "Ressourcen freigegeben"
            
    except Exception as e:
        current_status = f"Cleanup-Fehler: {e}"
        print(f"Cleanup-Fehler: {e}")  # Für Debugging

# Layout der Dash-Anwendung
app.layout = html.Div([
    # Header
    html.H1("AD9833 Funktionsgenerator", 
            style={'textAlign': 'center', 'color': 'white', 'backgroundColor': '#e74c3c',
                   'padding': '20px', 'margin': '0 0 30px 0', 'borderRadius': '8px'}),
    
    # Status-Anzeige
    html.Div([
        html.H3("Status:", style={'color': '#2c3e50', 'marginBottom': '10px'}),
        html.Div(id='status-display', 
                style={'padding': '15px', 'backgroundColor': '#ecf0f1', 
                       'borderRadius': '5px', 'marginBottom': '30px',
                       'border': '2px solid #bdc3c7'})
    ]),
    
    # Steuerungsbereich
    html.Div([
        # Frequenz-Einstellung
        html.Div([
            html.H3("Frequenz", style={'color': '#2c3e50', 'marginBottom': '15px'}),
            html.Label(f"Frequenz ({MIN_FREQUENCY} - {MAX_FREQUENCY} Hz):", 
                      style={'fontWeight': 'bold', 'marginBottom': '10px', 'display': 'block'}),
            dcc.Input(
                id='frequency-input',
                type='number',
                min=MIN_FREQUENCY,
                max=MAX_FREQUENCY,
                step=0.1,
                value=1000,
                style={'width': '200px', 'padding': '10px', 'fontSize': '16px',
                       'border': '2px solid #bdc3c7', 'borderRadius': '5px'}
            ),
            html.Span(" Hz", style={'marginLeft': '10px', 'fontSize': '16px'})
        ], style={'marginBottom': '30px'}),
        
        # Wellenform-Auswahl
        html.Div([
            html.H3("Wellenform", style={'color': '#2c3e50', 'marginBottom': '15px'}),
            dcc.RadioItems(
                id='waveform-selector',
                options=[
                    {'label': ' Sinuswelle', 'value': SINE_WAVE},
                    {'label': ' Dreieckswelle', 'value': TRIANGLE_WAVE},
                    {'label': ' Rechteckwelle', 'value': SQUARE_WAVE}
                ],
                value=SINE_WAVE,
                style={'fontSize': '16px'},
                labelStyle={'display': 'block', 'marginBottom': '10px', 'cursor': 'pointer'}
            )
        ], style={'marginBottom': '40px'}),
        
        # Steuerungsbuttons
        html.Div([
            html.Button(
                'Signal aktivieren',
                id='activate-button',
                style={'backgroundColor': '#27ae60', 'color': 'white', 'border': 'none',
                       'padding': '15px 30px', 'fontSize': '16px', 'borderRadius': '5px',
                       'cursor': 'pointer', 'marginRight': '20px', 'fontWeight': 'bold'}
            ),
            html.Button(
                'Reset',
                id='reset-button',
                style={'backgroundColor': '#e67e22', 'color': 'white', 'border': 'none',
                       'padding': '15px 30px', 'fontSize': '16px', 'borderRadius': '5px',
                       'cursor': 'pointer', 'fontWeight': 'bold'}
            )
        ], style={'textAlign': 'center', 'marginBottom': '40px'})
    ], style={'maxWidth': '600px', 'margin': '0 auto', 'padding': '20px'})
])

# Callbacks für Interaktivität
@app.callback(
    Output('status-display', 'children'),
    [Input('activate-button', 'n_clicks'),
     Input('reset-button', 'n_clicks')],
    [State('frequency-input', 'value'),
     State('waveform-selector', 'value')]
)
def handle_button_actions(activate_clicks, reset_clicks, frequency, waveform):
    """Behandelt Button-Aktionen und aktualisiert den Status"""
    global current_status
    
    # Bestimme welcher Button gedrückt wurde
    from dash import callback_context
    
    if not callback_context.triggered:
        return current_status
    
    button_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'activate-button' and activate_clicks:
        if frequency is None:
            current_status = "Bitte geben Sie eine gültige Frequenz ein"
            return html.Span(current_status, style={'color': '#e67e22', 'fontWeight': 'bold'})
        
        success = combined_init_and_configure(frequency, waveform)
        if success:
            waveform_names = {SINE_WAVE: "Sinuswelle", TRIANGLE_WAVE: "Dreieckswelle", SQUARE_WAVE: "Rechteckwelle"}
            waveform_name = waveform_names.get(waveform, "Unbekannt")
            status_msg = f"Signal aktiv: {frequency} Hz, {waveform_name}"
            return html.Span(status_msg, style={'color': '#27ae60', 'fontWeight': 'bold'})
        else:
            return html.Span(current_status, style={'color': '#e74c3c', 'fontWeight': 'bold'})
    
    elif button_id == 'reset-button' and reset_clicks:
        if write_to_AD9833(RESET):
            current_status = "AD9833 wurde zurückgesetzt"
            return html.Span(current_status, style={'color': '#3498db', 'fontWeight': 'bold'})
        else:
            current_status = "Reset fehlgeschlagen"
            return html.Span(current_status, style={'color': '#e74c3c', 'fontWeight': 'bold'})
    
    return html.Span(current_status, style={'color': '#7f8c8d'})

# Automatische Hardware-Initialisierung beim Start
@app.callback(
    Output('activate-button', 'style'),
    [Input('activate-button', 'id')]
)
def auto_init_on_start(button_id):
    """Automatische Initialisierung beim Start der Anwendung"""
    init_AD9833()
    return {'backgroundColor': '#27ae60', 'color': 'white', 'border': 'none',
            'padding': '15px 30px', 'fontSize': '16px', 'borderRadius': '5px',
            'cursor': 'pointer', 'marginRight': '20px', 'fontWeight': 'bold'}

if __name__ == '__main__':
    print(f"Starte Funktionsgenerator im {'Simulation' if SIMULATION_MODE else 'Hardware'}-Modus")
    
    # Automatische Initialisierung beim Start
    init_AD9833()
    
    # Cleanup beim Beenden registrieren
    import atexit
    atexit.register(cleanup_AD9833)
    
    try:
        # Server auf Port 8060 starten, Terminal-Logs unterdrücken
        ip_address = get_ip_address()
        app.run(host=ip_address, port=8060, debug=True)
    except KeyboardInterrupt:
        print("\nAnwendung durch Benutzer beendet")
        cleanup_AD9833()
    finally:
        cleanup_AD9833()