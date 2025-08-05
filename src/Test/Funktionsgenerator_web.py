#!/usr/bin/env python3
"""
Web-basierter Funktionsgenerator mit AD9833
"""

import socket
import sys
import time
import logging
from dash import Dash, dcc, html, Input, Output, State, callback

# AD9833 Register-Konstanten
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
CONTROL_REG = 0x2000

# Wellenform-Konstanten - korrigierte Werte für AD9833
SINE_WAVE = 0x2000      # Sinus: D5=0, D1=0, D3=0
TRIANGLE_WAVE = 0x2002  # Dreieck: D5=0, D1=1, D3=0  
SQUARE_WAVE = 0x2020    # Rechteck: D5=1, D1=0, D3=0

# Frequenz-Konstanten
FMCLK = 25000000
MAX_FREQUENCY = 20000
MIN_FREQUENCY = 0.1

# Simulation Mode
SIMULATION_MODE = '--simulate' in sys.argv

# Logging konfigurieren - detaillierter für Debugging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Globale Variablen
gpio_handle = None
spi_handle = None

# Mock Hardware Imports
if not SIMULATION_MODE:
    try:
        import lgpio
        import spidev
    except ImportError as e:
        logger.warning(f"Fehler beim Importieren von lgpio oder spidev: {e}. Wechsle zu Simulation.")
        SIMULATION_MODE = True

# SPI und GPIO Einstellungen
if not SIMULATION_MODE:
    SPI_BUS = 0
    SPI_DEVICE = 0
    SPI_FREQUENCY = 1000000
    FSYNC_PIN = 25

def init_AD9833():
    """
    Initialisiert GPIO und SPI für AD9833 oder simuliert
    KRITISCHE ÄNDERUNG: Führt bei jedem Aufruf eine vollständige Neukonfiguration durch
    """
    global gpio_handle, spi_handle
    
    if SIMULATION_MODE:
        logger.info("AD9833 Simulation-Modus initialisiert")
        return True, "AD9833 Simulation-Modus initialisiert"
    
    try:
        # WICHTIG: Cleanup der bestehenden Verbindungen vor Neuinitialisierung
        cleanup_existing_connections()
        
        # lgpio Handle öffnen
        gpio_handle = lgpio.gpiochip_open(0)
        logger.info(f"GPIO Handle geöffnet: {gpio_handle}")
        
        # FSYNC Pin als Ausgang konfigurieren
        lgpio.gpio_claim_output(gpio_handle, FSYNC_PIN, lgpio.SET_PULL_NONE)
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 1)  # HIGH setzen
        logger.info(f"FSYNC Pin {FSYNC_PIN} konfiguriert und auf HIGH gesetzt")
        
        # SPI initialisieren
        spi_handle = spidev.SpiDev()
        spi_handle.open(SPI_BUS, SPI_DEVICE)
        spi_handle.max_speed_hz = SPI_FREQUENCY
        spi_handle.mode = 0b10  # CPOL=1, CPHA=0
        logger.info(f"SPI konfiguriert: Bus={SPI_BUS}, Device={SPI_DEVICE}, Speed={SPI_FREQUENCY}Hz")
        
        # ERWEITERTE Reset-Sequenz für AD9833
        logger.info("Starte vollständige AD9833 Reset-Sequenz...")
        
        # Schritt 1: Hardware-Reset durch längeres RESET-Signal
        if not write_to_AD9833(0x2100):  # Reset aktivieren
            raise Exception("Fehler beim Aktivieren des Reset")
        time.sleep(0.05)  # Längere Pause für sauberen Reset
        
        # Schritt 2: Reset deaktivieren und Chip stabilisieren
        if not write_to_AD9833(0x2000):  # Reset deaktivieren, Sinus-Modus
            raise Exception("Fehler beim Deaktivieren des Reset")
        time.sleep(0.02)
        
        # Schritt 3: Register-Zustand löschen durch Dummy-Schreibvorgänge
        write_to_AD9833(0x0000)  # Null-Kommando für Register-Clearing
        time.sleep(0.01)
        
        logger.info("AD9833 vollständige Reset-Sequenz abgeschlossen")
        return True, "AD9833 erfolgreich initialisiert"
        
    except Exception as e:
        logger.error(f"Initialisierungsfehler: {str(e)}")
        cleanup_existing_connections()
        return False, f"Fehler beim Initialisieren: {str(e)}"

def cleanup_existing_connections():
    """
    Räumt bestehende GPIO/SPI Verbindungen auf
    NEUE FUNKTION: Verhindert Konflikte bei Reinitialisierung
    """
    global gpio_handle, spi_handle
    
    try:
        if gpio_handle is not None:
            try:
                lgpio.gpio_free(gpio_handle, FSYNC_PIN)
            except:
                pass  # Ignoriere Fehler beim Freigeben
            try:
                lgpio.gpiochip_close(gpio_handle)
            except:
                pass
            gpio_handle = None
        
        if spi_handle is not None:
            try:
                spi_handle.close()
            except:
                pass
            spi_handle = None
            
        logger.debug("Bestehende Verbindungen erfolgreich bereinigt")
    except Exception as e:
        logger.warning(f"Fehler beim Bereinigen bestehender Verbindungen: {e}")

def write_to_AD9833(data):
    """
    Sendet 16-Bit Daten an AD9833 oder simuliert
    VERBESSERT: Robustere Fehlerbehandlung und Timing
    """
    if SIMULATION_MODE:
        logger.debug(f"Simuliert: Sende 0x{data:04X} an AD9833")
        return True
    
    if spi_handle is None or gpio_handle is None:
        logger.error("SPI oder GPIO nicht initialisiert")
        return False
        
    try:
        # FSYNC LOW für Datenübertragung mit verbessertem Timing
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 0)
        time.sleep(0.002)  # Erweiterte Pause für saubere Flanke
        
        # Daten als 16-Bit übertragen (MSB first)
        result = spi_handle.xfer2([data >> 8, data & 0xFF])
        
        time.sleep(0.002)  # Erweiterte Pause vor FSYNC HIGH
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 1)
        time.sleep(0.001)  # Zusätzliche Stabilisierungszeit
        
        logger.debug(f"Erfolgreich gesendet: 0x{data:04X}")
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Schreiben: {str(e)}")
        return False

def configure_complete_signal(freq, waveform):
    """
    NEUE HAUPTFUNKTION: Komplette Signalkonfiguration in korrekter Reihenfolge
    Implementiert die bewährte Sequenz aus funktionierenden Projektdateien
    """
    logger.info(f"Starte komplette Signalkonfiguration: {freq} Hz, Wellenform 0x{waveform:04X}")
    
    try:
        # Schritt 1: Vollständige Initialisierung (auch bei bestehender Verbindung)
        success_init, message_init = init_AD9833()
        if not success_init:
            return False, f"Initialisierung fehlgeschlagen: {message_init}"
        
        # Schritt 2: Frequenz-Word berechnen
        freq_word = int((freq * 2**28) / FMCLK)
        logger.info(f"Berechnetes Frequenz-Word: 0x{freq_word:08X}")
        
        # Schritt 3: KRITISCHE SEQUENZ für AD9833 (basierend auf funktionierenden Code)
        
        # 3a: Reset aktivieren für saubere Konfiguration
        if not write_to_AD9833(0x2100):
            return False, "Fehler beim Reset-Aktivieren"
        time.sleep(0.01)
        
        # 3b: Niederwertiges 14-Bit Frequenz-Word senden
        freq_lsb = FREQ0_REG | (freq_word & 0x3FFF)
        if not write_to_AD9833(freq_lsb):
            return False, "Fehler beim Senden des LSB Frequenz-Words"
        logger.debug(f"Frequenz LSB gesendet: 0x{freq_lsb:04X}")
        
        # 3c: Höherwertiges 14-Bit Frequenz-Word senden
        freq_msb = FREQ0_REG | ((freq_word >> 14) & 0x3FFF)
        if not write_to_AD9833(freq_msb):
            return False, "Fehler beim Senden des MSB Frequenz-Words"
        logger.debug(f"Frequenz MSB gesendet: 0x{freq_msb:04X}")
        
        # 3d: Wellenform aktivieren (beendet Reset und startet Ausgabe)
        if not write_to_AD9833(waveform):
            return False, "Fehler beim Aktivieren der Wellenform"
        
        # Schritt 4: Finale Stabilisierung
        time.sleep(0.05)  # Wartezeit für Signalstabilisierung
        
        wellenform_namen = {SINE_WAVE: "Sinuswelle", TRIANGLE_WAVE: "Dreieckswelle", SQUARE_WAVE: "Rechteckwelle"}
        wellenform_name = wellenform_namen.get(waveform, f"Unbekannt (0x{waveform:04X})")
        
        success_message = f"Signal erfolgreich konfiguriert: {freq} Hz, {wellenform_name}"
        logger.info(success_message)
        return True, success_message
        
    except Exception as e:
        error_message = f"Fehler bei Signalkonfiguration: {str(e)}"
        logger.error(error_message)
        return False, error_message

def cleanup():
    """Räumt Ressourcen auf"""
    global spi_handle, gpio_handle
    
    if SIMULATION_MODE:
        logger.info("Simulierter Cleanup abgeschlossen")
        return
    
    try:
        # AD9833 reset vor Cleanup
        if spi_handle is not None and gpio_handle is not None:
            write_to_AD9833(0x2100)
            time.sleep(0.01)
    except:
        pass
    finally:
        cleanup_existing_connections()
        logger.info("Cleanup abgeschlossen")

def get_ip_address():
    """Abrufen der IP-Adresse"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('1.1.1.1', 1))
            return sock.getsockname()[0]
    except Exception:
        return '127.0.0.1'

# Dash App initialisieren
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "AD9833 Funktionsgenerator"

# App Layout
app.layout = html.Div([
    # Header
    html.Div([
        html.H1("AD9833 Funktionsgenerator", 
                style={'color': '#2c3e50', 'marginBottom': '5px', 'fontSize': '28px'}),
        html.P(f"Webinterface für Signalgenerierung {'(Simulation)' if SIMULATION_MODE else ''}", 
               style={'color': '#7f8c8d', 'fontSize': '14px', 'margin': '0'})
    ], style={'textAlign': 'center', 'marginBottom': '25px'}),
    
    # Hauptkonfiguration
    html.Div([
        # Wellenform-Auswahl
        html.Div([
            html.H3("Wellenform", style={'color': '#34495e', 'marginBottom': '10px'}),
            dcc.RadioItems(
                id='wellenform-radio',
                options=[
                    {'label': 'Sinuswelle', 'value': SINE_WAVE},
                    {'label': 'Dreieckswelle', 'value': TRIANGLE_WAVE},
                    {'label': 'Rechteckwelle', 'value': SQUARE_WAVE}
                ],
                value=SINE_WAVE,
                labelStyle={'display': 'block', 'marginBottom': '8px', 'fontSize': '16px'},
                style={'fontSize': '16px'}
            ),
        ], style={'width': '45%', 'display': 'inline-block', 'verticalAlign': 'top', 
                  'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '8px', 'marginRight': '5%'}),
        
        # Frequenz-Eingabe
        html.Div([
            html.H3("⚡ Frequenz", style={'color': '#34495e', 'marginBottom': '10px'}),
            html.Label(f"Bereich: {MIN_FREQUENCY} - {MAX_FREQUENCY} Hz", 
                      style={'fontSize': '12px', 'color': '#7f8c8d', 'marginBottom': '8px', 'display': 'block'}),
            dcc.Input(
                id='frequenz-input',
                type='number',
                value=1000,
                min=MIN_FREQUENCY,
                max=MAX_FREQUENCY,
                step=0.1,
                style={'width': '100%', 'padding': '12px', 'fontSize': '16px', 'borderRadius': '5px', 
                       'border': '2px solid #bdc3c7', 'marginBottom': '15px'}
            ),
            html.Div("Standard: 1000 Hz", style={'fontSize': '12px', 'color': '#95a5a6'})
        ], style={'width': '45%', 'display': 'inline-block', 'verticalAlign': 'top', 
                  'backgroundColor': '#f8f9fa', 'padding': '20px', 'borderRadius': '8px'}),
        
    ], style={'marginBottom': '25px'}),
    
    # Kontrollbereich
    html.Div([
        # Status-Anzeige
        html.Div([
            html.H3("📡 Status", style={'color': '#34495e', 'marginBottom': '15px'}),
            html.Div('AD9833 bereit für Konfiguration', 
                    id='status-display',
                    style={'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
                           'fontFamily': 'monospace', 'minHeight': '100px', 'border': '2px solid #e9ecef', 
                           'color': '#2c3e50', 'fontSize': '14px', 'whiteSpace': 'pre-line'})
        ], style={'width': '65%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '5%'}),
        
        # Aktions-Button
        html.Div([
            html.Button(
                '⚡ Konfiguration anwenden',
                id='apply-button',
                n_clicks=0,
                style={'width': '100%', 'height': '130px', 'backgroundColor': '#27ae60', 'color': 'white', 
                       'border': 'none', 'borderRadius': '5px', 'fontWeight': 'bold', 'fontSize': '16px', 
                       'cursor': 'pointer', 'boxShadow': '0 4px 8px rgba(0,0,0,0.1)'}
            ),
        ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top'}),
        
    ], style={'marginBottom': '20px'})
    
], style={'maxWidth': '900px', 'margin': '0 auto', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'minHeight': '100vh'})

# Hauptkonfiguration-Callback
@callback(
    [Output('status-display', 'children'),
     Output('status-display', 'style')],
    [Input('apply-button', 'n_clicks')],
    [State('wellenform-radio', 'value'),
     State('frequenz-input', 'value')]
)
def handle_configuration(n_clicks, wellenform, frequenz):
    """
    ÜBERARBEITETE HAUPTFUNKTION: Behandelt Signalkonfiguration mit robuster Fehlerbehandlung
    """
    base_style = {
        'backgroundColor': '#f8f9fa', 'padding': '15px', 'borderRadius': '5px',
        'fontFamily': 'monospace', 'minHeight': '100px', 'fontSize': '14px', 'whiteSpace': 'pre-line'
    }
    
    if not n_clicks:
        return ('AD9833 bereit für Konfiguration\n\nKlicken Sie "Konfiguration anwenden" um zu starten', 
                {**base_style, 'border': '2px solid #e9ecef', 'color': '#2c3e50'})
    
    # Eingabe-Validierung
    if not isinstance(frequenz, (int, float)) or frequenz < MIN_FREQUENCY or frequenz > MAX_FREQUENCY:
        return (f'❌ EINGABEFEHLER\n\nFrequenz muss zwischen {MIN_FREQUENCY} und {MAX_FREQUENCY} Hz liegen.\nEingegeben: {frequenz}', 
                {**base_style, 'border': '2px solid #e74c3c', 'color': '#e74c3c'})
    
    # Komplette Signalkonfiguration durchführen
    try:
        success, message = configure_complete_signal(frequenz, wellenform)
        
        if success:
            wellenform_namen = {SINE_WAVE: "Sinuswelle", TRIANGLE_WAVE: "Dreieckswelle", SQUARE_WAVE: "Rechteckwelle"}
            wellenform_name = wellenform_namen.get(wellenform, "Unbekannt")
            
            config_text = f"""✅ KONFIGURATION ERFOLGREICH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wellenform: {wellenform_name}
Frequenz: {frequenz} Hz
Status: Signalausgabe aktiv
Hardware: {'Simulation' if SIMULATION_MODE else 'AD9833'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bereit für weitere Konfigurationen"""
            
            return (config_text, {**base_style, 'border': '2px solid #27ae60', 'color': '#27ae60'})
        else:
            return (f'❌ KONFIGURATIONSFEHLER\n\n{message}\n\nÜberprüfen Sie die Hardware-Verbindungen', 
                    {**base_style, 'border': '2px solid #e74c3c', 'color': '#e74c3c'})
                    
    except Exception as e:
        logger.error(f"Unerwarteter Fehler in handle_configuration: {str(e)}")
        return (f'❌ UNERWARTETER FEHLER\n\n{str(e)}\n\nBitte versuchen Sie es erneut', 
                {**base_style, 'border': '2px solid #e74c3c', 'color': '#e74c3c'})

# Cleanup beim Beenden
import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    logger.info(f"Starte Funktionsgenerator im {'Simulation' if SIMULATION_MODE else 'Hardware'} Modus")
    app.run(host=get_ip_address(), port=8060, debug=True, use_reloader=False)