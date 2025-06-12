
# -*- coding: utf-8 -*-
"""
Web-basierter Funktionsgenerator für AD9833 mit Dash
Terminal-Funktionalität in Web-Interface übertragen
"""

import socket
from dash import Dash, dcc, html, Input, Output, State, callback
import sys
import time

# AD9833 Register-Konstanten
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
CONTROL_REG = 0x2000

# Wellenform-Konstanten
SINE_WAVE = 0x2000      # Sinuswelle
TRIANGLE_WAVE = 0x2002  # Dreieckswelle
SQUARE_WAVE = 0x2028    # Rechteckwelle

# Frequenz-Konstanten
FMCLK = 25000000  # 25 MHz Standardtaktfrequenz
MAX_FREQUENCY = 20000  # Maximale Ausgangsfrequenz: 20 kHz
MIN_FREQUENCY = 0.1    # Minimale Ausgangsfrequenz: 0.1 Hz

# Simulation Mode
SIMULATION_MODE = '--simulate' in sys.argv

# Globale Variablen für Status
ist_initialisiert = False
aktuelle_wellenform = None
aktuelle_frequenz = None

# Mock Hardware Imports
if not SIMULATION_MODE:
    try:
        import RPi.GPIO as GPIO
        import spidev
    except ImportError as e:
        print(f"Fehler beim Importieren von RPi.GPIO oder spidev: {e}. Wechsle zu Simulation.")
        SIMULATION_MODE = True

# SPI Einstellungen (nur wenn nicht simuliert)
if not SIMULATION_MODE:
    SPI_BUS = 0
    SPI_DEVICE = 0
    SPI_FREQUENCY = 1000000  # 1 MHz
    FSYNC_PIN = 25  # GPIO-Pin für FSYNC
    spi = None

def init_AD9833():
    """Initialisiert GPIO und SPI für AD9833 oder simuliert Initialisierung"""
    global ist_initialisiert, spi
    if SIMULATION_MODE:
        ist_initialisiert = True
        return True, "AD9833 simuliert initialisiert"
    
    try:
        # GPIO initialisieren
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(FSYNC_PIN, GPIO.OUT)
        GPIO.output(FSYNC_PIN, GPIO.HIGH)
        
        # SPI initialisieren
        spi = spidev.SpiDev()
        spi.open(SPI_BUS, SPI_DEVICE)
        spi.max_speed_hz = SPI_FREQUENCY
        spi.mode = 0b10  # SPI Modus 2
        
        # Reset des AD9833
        write_to_AD9833(0x2100)
        time.sleep(0.1)
        
        ist_initialisiert = True
        return True, "AD9833 erfolgreich initialisiert"
    except Exception as e:
        ist_initialisiert = False
        return False, f"Fehler beim Initialisieren: {str(e)}"

def write_to_AD9833(data):
    """Sendet 16-Bit Daten an AD9833 oder simuliert Schreiben"""
    if SIMULATION_MODE:
        return True
    
    if spi is None:
        return False
    try:
        GPIO.output(FSYNC_PIN, GPIO.LOW)
        spi.xfer2([data >> 8, data & 0xFF])
        GPIO.output(FSYNC_PIN, GPIO.HIGH)
        return True
    except Exception:
        return False

def set_frequency(freq):
    """Stellt die Ausgangsfrequenz ein (in Hz) oder simuliert"""
    global aktuelle_frequenz
    if SIMULATION_MODE:
        aktuelle_frequenz = freq
        return True
    
    try:
        # Berechne Frequenzregister-Wert
        freq_word = int((freq * 2**28) / FMCLK)
        
        # Reset aktivieren
        write_to_AD9833(0x2100)
        
        # Frequenzregister schreiben (in zwei 14-Bit Wörtern)
        write_to_AD9833(FREQ0_REG | (freq_word & 0x3FFF))
        write_to_AD9833(FREQ0_REG | ((freq_word >> 14) & 0x3FFF))
        
        aktuelle_frequenz = freq
        return True
    except Exception:
        return False

def set_waveform(waveform):
    """Stellt die Wellenform ein oder simuliert"""
    global aktuelle_wellenform
    if SIMULATION_MODE:
        aktuelle_wellenform = waveform
        return True
    
    try:
        write_to_AD9833(waveform)
        aktuelle_wellenform = waveform
        return True
    except Exception:
        return False

def cleanup():
    """Räumt Ressourcen auf oder simuliert Cleanup"""
    global spi, ist_initialisiert
    if SIMULATION_MODE:
        ist_initialisiert = False
        return
    
    try:
        # Gerät zurücksetzen
        if spi is not None:
            write_to_AD9833(0x2100)
    except:
        pass
    finally:
        # Ressourcen freigeben
        try:
            GPIO.cleanup()
        except:
            pass
        if spi is not None:
            spi.close()
            spi = None
        ist_initialisiert = False

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
app.title = "OurDAQ - Funktionsgenerator"

# Layout der App
app.layout = html.Div([
    # Header
    html.H1("OurDAQ - Funktionsgenerator", 
            style={'textAlign': 'center', 'color': 'white', 'backgroundColor': '#2c3e50',
                   'padding': '20px', 'margin': '0 0 20px 0', 'borderRadius': '8px'}),
    
    # Hauptinhalt Container
    html.Div([
        # Status-Bereich
        html.Div([
            html.H3("Status", style={'color': '#2c3e50', 'marginBottom': '15px'}),
            html.Div(id='status-display',
                    style={'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                           'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e9ecef'},
                    children='AD9833 nicht initialisiert'),
        ], style={'marginBottom': '30px'}),
        
        # Konfiguration
        html.Div([
            html.H3("Konfiguration", style={'color': '#2c3e50', 'marginBottom': '20px'}),
            
            # Layout für Wellenform und Frequenz nebeneinander
            html.Div([
                # Linke Spalte - Wellenform
                html.Div([
                    html.Label('Wellenform auswählen:', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '10px'}),
                    dcc.RadioItems(
                        id='wellenform-radio',
                        options=[
                            {'label': '1. Sinuswelle', 'value': SINE_WAVE},
                            {'label': '2. Dreieckswelle', 'value': TRIANGLE_WAVE},
                            {'label': '3. Rechteckwelle', 'value': SQUARE_WAVE}
                        ],
                        value=SINE_WAVE,
                        labelStyle={'display': 'block', 'marginBottom': '8px'}
                    ),
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                
                # Rechte Spalte - Frequenz
                html.Div([
                    html.Label(f'Frequenz eingeben ({MIN_FREQUENCY} - {MAX_FREQUENCY} Hz):', 
                              style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '10px'}),
                    dcc.Input(
                        id='frequenz-input',
                        type='number',
                        min=MIN_FREQUENCY,
                        max=MAX_FREQUENCY,
                        step=0.1,
                        value=1000,
                        style={'width': '150px', 'fontSize': '14px', 'padding': '8px'}
                    ),
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginLeft': '4%'}),
            ], style={'marginBottom': '25px'}),
            
            # Zentrale Schaltfläche
            html.Div([
                html.Button(
                    'Konfigurieren',
                    id='apply-button',
                    style={'width': '250px', 'height': '45px', 'backgroundColor': '#27ae60',
                           'color': 'white', 'border': 'none', 'borderRadius': '5px',
                           'fontWeight': 'bold', 'fontSize': '16px', 'cursor': 'pointer'}
                ),
            ], style={'textAlign': 'center'}),
            
        ], style={'backgroundColor': '#ecf0f1', 'padding': '25px', 'borderRadius': '8px'}),
        
    ], style={'maxWidth': '800px', 'margin': '0 auto', 'padding': '20px'}),
])

@callback(
    [Output('status-display', 'children'),
     Output('status-display', 'style')],
    [Input('apply-button', 'n_clicks')],
    [State('wellenform-radio', 'value'),
     State('frequenz-input', 'value')]
)
def handle_apply_configuration(n_clicks, wellenform, frequenz):
    if not n_clicks:
        return ('AD9833 nicht initialisiert', 
                {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                 'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e9ecef', 'color': '#e74c3c'})
    
    # Validierung der Eingaben
    if frequenz is None or frequenz < MIN_FREQUENCY or frequenz > MAX_FREQUENCY:
        return (f'Fehler: Frequenz muss zwischen {MIN_FREQUENCY} und {MAX_FREQUENCY} Hz liegen',
                {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                 'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e74c3c', 'color': '#e74c3c'})
    
    # Schritt 1: Initialisierung
    success_init, message_init = init_AD9833()
    if not success_init:
        return (f'Initialisierung fehlgeschlagen: {message_init}',
                {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                 'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e74c3c', 'color': '#e74c3c'})
    
    # Schritt 2: Konfiguration anwenden
    # Wellenform-Namen bestimmen
    wellenform_namen = {
        SINE_WAVE: "Sinuswelle",
        TRIANGLE_WAVE: "Dreieckswelle", 
        SQUARE_WAVE: "Rechteckwelle"
    }
    wellenform_name = wellenform_namen.get(wellenform, "Unbekannt")
    
    try:
        # Frequenz setzen
        if not set_frequency(frequenz):
            return ('Fehler beim Setzen der Frequenz',
                    {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                     'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e74c3c', 'color': '#e74c3c'})
        
        # Wellenform setzen
        if not set_waveform(wellenform):
            return ('Fehler beim Setzen der Wellenform',
                    {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                     'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e74c3c', 'color': '#e74c3c'})
        
        # Erfolgreiche Konfiguration
        config_text = f"""Aktive Konfiguration:
  Wellenform: {wellenform_name}
  Frequenz: {frequenz} Hz
  
Signalausgabe aktiv{' (Simuliert)' if SIMULATION_MODE else ''}!"""
        
        return (config_text,
                {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                 'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #27ae60', 'color': '#27ae60'})
                
    except Exception as e:
        return (f'Fehler bei der Konfiguration: {str(e)}',
                {'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                 'fontFamily': 'monospace', 'minHeight': '60px', 'border': '2px solid #e74c3c', 'color': '#e74c3c'})

# Cleanup beim Beenden der App
import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    print(f"Starting Funktionsgenerator in {'simulation' if SIMULATION_MODE else 'hardware'} mode")
    app.run(host=get_ip_address(), port=8060, debug=True)
