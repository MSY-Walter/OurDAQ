#!/usr/bin/env python3
"""
Funktionsgenerator Web-Interface
"""

import dash
from dash import dcc, html, Input, Output, callback_context
import plotly.graph_objects as go
import lgpio
import spidev
import time
import threading

# AD9833 Register-Konstanten
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
CONTROL_REG = 0x2000

# Wellenform-Konstanten
SINE_WAVE = 0x2000      # Sinuswelle
TRIANGLE_WAVE = 0x2002  # Dreieckswelle
SQUARE_WAVE = 0x2028    # Rechteckwelle

# Reset-Konstante
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

# Globale Variablen für Hardware-Zugriff
gpio_handle = None
spi = None
current_freq = 1000.0  # Aktuelle Frequenz
current_waveform = SINE_WAVE  # Aktuelle Wellenform
hardware_initialized = False

class AD9833Controller:
    """Klasse zur Steuerung des AD9833"""
    
    def __init__(self):
        self.gpio_handle = None
        self.spi = None
        self.initialized = False
        
    def init_hardware(self):
        """Hardware initialisieren"""
        try:
            # GPIO-Chip öffnen
            self.gpio_handle = lgpio.gpiochip_open(4)  # gpiochip4 für Raspberry Pi 5
            
            # FSYNC Pin als Ausgang konfigurieren
            lgpio.gpio_claim_output(self.gpio_handle, FSYNC_PIN, lgpio.SET)
            
            # SPI initialisieren
            self.spi = spidev.SpiDev()
            self.spi.open(SPI_BUS, SPI_DEVICE)
            self.spi.max_speed_hz = SPI_FREQUENCY
            self.spi.mode = 0b10  # SPI Modus 2
            
            # Initiales Reset
            self.write_to_ad9833(RESET)
            time.sleep(0.1)
            
            self.initialized = True
            return True
            
        except Exception as e:
            print(f"Fehler bei Hardware-Initialisierung: {e}")
            self.cleanup()
            return False
    
    def write_to_ad9833(self, data):
        """16-Bit Daten an AD9833 senden"""
        if not self.initialized or self.gpio_handle is None or self.spi is None:
            return False
            
        try:
            # FSYNC auf LOW (Übertragung startet)
            lgpio.gpio_write(self.gpio_handle, FSYNC_PIN, lgpio.CLEAR)
            
            # 16-Bit Daten in zwei 8-Bit Bytes aufteilen
            high_byte = (data >> 8) & 0xFF
            low_byte = data & 0xFF
            self.spi.xfer2([high_byte, low_byte])
            
            # FSYNC auf HIGH (Übertragung beendet)
            lgpio.gpio_write(self.gpio_handle, FSYNC_PIN, lgpio.SET)
            
            return True
            
        except Exception as e:
            print(f"Fehler beim Schreiben: {e}")
            return False
    
    def set_frequency(self, freq_hz):
        """Frequenz einstellen"""
        if not (MIN_FREQUENCY <= freq_hz <= MAX_FREQUENCY):
            return False
            
        try:
            # Frequenzwort berechnen (28-Bit)
            freq_word = int((freq_hz * (2**28)) / FMCLK)
            
            # Kritische Übertragungssequenz
            if not self.write_to_ad9833(RESET):
                return False
            
            # Lower 14 Bits
            if not self.write_to_ad9833(FREQ0_REG | (freq_word & 0x3FFF)):
                return False
            
            # Upper 14 Bits
            if not self.write_to_ad9833(FREQ0_REG | ((freq_word >> 14) & 0x3FFF)):
                return False
            
            return True
            
        except Exception as e:
            print(f"Fehler beim Setzen der Frequenz: {e}")
            return False
    
    def set_waveform(self, waveform):
        """Wellenform aktivieren"""
        try:
            return self.write_to_ad9833(waveform)
        except Exception as e:
            print(f"Fehler beim Setzen der Wellenform: {e}")
            return False
    
    def configure(self, freq_hz, waveform):
        """Vollständige Konfiguration"""
        if not self.set_frequency(freq_hz):
            return False
        
        if not self.set_waveform(waveform):
            return False
            
        return True
    
    def cleanup(self):
        """Ressourcen freigeben"""
        try:
            if self.initialized and self.gpio_handle is not None and self.spi is not None:
                self.write_to_ad9833(RESET)
                time.sleep(0.1)
            
            if self.gpio_handle is not None:
                lgpio.gpio_free(self.gpio_handle, FSYNC_PIN)
                lgpio.gpiochip_close(self.gpio_handle)
                self.gpio_handle = None
            
            if self.spi is not None:
                self.spi.close()
                self.spi = None
                
            self.initialized = False
            
        except Exception as e:
            print(f"Fehler beim Cleanup: {e}")

# Globaler Controller
ad9833 = AD9833Controller()

# Dash App erstellen
app = dash.Dash(__name__)

# CSS-Styling für besseres Aussehen
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

# App Layout definieren
app.layout = html.Div([
    html.Div([
        html.H1("AD9833 Funktionsgenerator", 
                style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '30px'}),
        
        # Status-Anzeige
        html.Div(id="status-display", 
                style={'textAlign': 'center', 'marginBottom': '20px', 'padding': '10px',
                      'backgroundColor': '#ecf0f1', 'borderRadius': '5px'}),
        
        # Frequenz-Eingabe
        html.Div([
            html.Label("Frequenz (Hz):", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.Input(
                id="frequency-input",
                type="number",
                value=1000,
                min=MIN_FREQUENCY,
                max=MAX_FREQUENCY,
                step=0.1,
                style={'width': '200px', 'padding': '5px', 'marginRight': '10px'}
            ),
            html.Span(f"Bereich: {MIN_FREQUENCY} - {MAX_FREQUENCY} Hz", 
                     style={'color': '#7f8c8d', 'fontSize': '14px'})
        ], style={'marginBottom': '20px'}),
        
        # Wellenform-Auswahl
        html.Div([
            html.Label("Wellenform:", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
            dcc.RadioItems(
                id="waveform-selector",
                options=[
                    {'label': ' Sinuswelle', 'value': SINE_WAVE},
                    {'label': ' Dreieckswelle', 'value': TRIANGLE_WAVE},
                    {'label': ' Rechteckwelle', 'value': SQUARE_WAVE}
                ],
                value=SINE_WAVE,
                style={'marginBottom': '20px'}
            )
        ], style={'marginBottom': '20px'}),
        
        # Steuerungsbuttons
        html.Div([
            html.Button('Hardware Initialisieren', id='init-button', n_clicks=0,
                       style={'marginRight': '10px', 'padding': '10px 20px', 
                             'backgroundColor': '#3498db', 'color': 'white', 'border': 'none',
                             'borderRadius': '5px', 'cursor': 'pointer'}),
            html.Button('Konfiguration Anwenden', id='apply-button', n_clicks=0,
                       style={'marginRight': '10px', 'padding': '10px 20px',
                             'backgroundColor': '#27ae60', 'color': 'white', 'border': 'none',
                             'borderRadius': '5px', 'cursor': 'pointer'}),
            html.Button('Stop/Reset', id='stop-button', n_clicks=0,
                       style={'padding': '10px 20px', 'backgroundColor': '#e74c3c', 'color': 'white',
                             'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'})
        ], style={'textAlign': 'center', 'marginBottom': '20px'}),
        
        # Aktuelle Einstellungen anzeigen
        html.Div(id="current-settings",
                style={'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                      'border': '1px solid #dee2e6'})
        
    ], style={'maxWidth': '600px', 'margin': '0 auto', 'padding': '20px'})
])

# Callback für Hardware-Initialisierung
@app.callback(
    Output('status-display', 'children'),
    Input('init-button', 'n_clicks')
)
def initialize_hardware(n_clicks):
    """Hardware initialisieren"""
    if n_clicks > 0:
        try:
            if ad9833.init_hardware():
                return html.Div("✅ Hardware erfolgreich initialisiert", 
                              style={'color': '#27ae60', 'fontWeight': 'bold'})
            else:
                return html.Div("❌ Hardware-Initialisierung fehlgeschlagen", 
                              style={'color': '#e74c3c', 'fontWeight': 'bold'})
        except Exception as e:
            return html.Div(f"❌ Fehler: {str(e)}", 
                          style={'color': '#e74c3c', 'fontWeight': 'bold'})
    else:
        return html.Div("Hardware nicht initialisiert", 
                       style={'color': '#f39c12', 'fontWeight': 'bold'})

# Callback für Konfiguration anwenden
@app.callback(
    Output('current-settings', 'children'),
    [Input('apply-button', 'n_clicks'),
     Input('stop-button', 'n_clicks')],
    [dash.dependencies.State('frequency-input', 'value'),
     dash.dependencies.State('waveform-selector', 'value')]
)
def apply_configuration(apply_clicks, stop_clicks, frequency, waveform):
    """Konfiguration auf Hardware anwenden"""
    ctx = callback_context
    
    if not ctx.triggered:
        return html.Div("Keine Konfiguration aktiv")
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Wellenform-Namen für Anzeige
    waveform_names = {
        SINE_WAVE: "Sinuswelle",
        TRIANGLE_WAVE: "Dreieckswelle", 
        SQUARE_WAVE: "Rechteckwelle"
    }
    
    if button_id == 'stop-button' and stop_clicks > 0:
        # Stop/Reset
        try:
            if ad9833.initialized:
                ad9833.write_to_ad9833(RESET)
                return html.Div([
                    html.H4("⏹️ Generator Gestoppt", style={'color': '#e74c3c'}),
                    html.P("AD9833 wurde zurückgesetzt")
                ])
            else:
                return html.Div("Hardware nicht initialisiert", 
                              style={'color': '#f39c12'})
        except Exception as e:
            return html.Div(f"Fehler beim Stoppen: {str(e)}", 
                          style={'color': '#e74c3c'})
    
    elif button_id == 'apply-button' and apply_clicks > 0:
        # Konfiguration anwenden
        if not ad9833.initialized:
            return html.Div("❌ Hardware nicht initialisiert! Bitte zuerst Hardware initialisieren.", 
                          style={'color': '#e74c3c', 'fontWeight': 'bold'})
        
        if frequency is None or not (MIN_FREQUENCY <= frequency <= MAX_FREQUENCY):
            return html.Div(f"❌ Ungültige Frequenz! Bereich: {MIN_FREQUENCY} - {MAX_FREQUENCY} Hz", 
                          style={'color': '#e74c3c', 'fontWeight': 'bold'})
        
        try:
            if ad9833.configure(frequency, waveform):
                global current_freq, current_waveform
                current_freq = frequency
                current_waveform = waveform
                
                return html.Div([
                    html.H4("✅ Konfiguration Aktiv", style={'color': '#27ae60'}),
                    html.P(f"Frequenz: {frequency} Hz"),
                    html.P(f"Wellenform: {waveform_names.get(waveform, 'Unbekannt')}"),
                    html.P("Signal wird ausgegeben!", style={'fontWeight': 'bold'})
                ])
            else:
                return html.Div("❌ Konfiguration fehlgeschlagen", 
                              style={'color': '#e74c3c', 'fontWeight': 'bold'})
        except Exception as e:
            return html.Div(f"❌ Fehler: {str(e)}", 
                          style={'color': '#e74c3c', 'fontWeight': 'bold'})
    
    # Standardanzeige
    return html.Div([
        html.P(f"Eingestellte Frequenz: {frequency} Hz"),
        html.P(f"Eingestellte Wellenform: {waveform_names.get(waveform, 'Unbekannt')}")
    ])

# Cleanup beim Beenden
import atexit
def cleanup_on_exit():
    """Cleanup beim Beenden der App"""
    ad9833.cleanup()

atexit.register(cleanup_on_exit)

if __name__ == '__main__':
    try:
        print("=" * 50)
        print("AD9833 Funktionsgenerator Web-Interface")
        print("=" * 50)
        print(f"Frequenzbereich: {MIN_FREQUENCY} - {MAX_FREQUENCY} Hz")
        print("Verfügbare Wellenformen:")
        print("  - Sinuswelle")
        print("  - Dreieckswelle") 
        print("  - Rechteckwelle")
        print()
        print("Öffnen Sie http://localhost:8060 im Browser")
        print("Drücken Sie Ctrl+C zum Beenden")
        print("=" * 50)
        
        # App starten
        app.run(debug=False, host='0.0.0.0', port=8060)
        
    except KeyboardInterrupt:
        print("\nProgramm durch Benutzer beendet")
    except Exception as e:
        print(f"Fehler beim Starten der App: {e}")
    finally:
        ad9833.cleanup()
        print("Cleanup abgeschlossen")