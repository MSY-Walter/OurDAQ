# -*- coding: utf-8 -*-
"""
Web-basierter Funktionsgenerator für AD9833 mit Dash
Kompakte UI ohne Scrollen mit sichtbarer Signalvorschau
Verwendet lgpio anstelle von RPi.GPIO
"""

import socket
import sys
import time
import logging
from dash import Dash, dcc, html, Input, Output, State, callback
import math

# AD9833 Register-Konstanten
FREQ0_REG = 0x4000
PHASE0_REG = 0xC000
CONTROL_REG = 0x2000

# Wellenform-Konstanten - korrigierte Werte für AD9833
SINE_WAVE = 0x2000      # Sinus: D5=0, D1=0, D3=0
TRIANGLE_WAVE = 0x2002  # Dreieck: D5=0, D1=1, D3=0  
SQUARE_WAVE = 0x2020    # Rechteck: D5=1, D1=0, D3=0 (korrigiert!)

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
ist_initialisiert = False
aktuelle_wellenform = None
aktuelle_frequenz = None
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
    """Initialisiert GPIO und SPI für AD9833 oder simuliert"""
    global ist_initialisiert, gpio_handle, spi_handle
    if ist_initialisiert:
        logger.info("AD9833 bereits initialisiert")
        return True, "AD9833 bereits initialisiert"

    if SIMULATION_MODE:
        ist_initialisiert = True
        logger.info("AD9833 simuliert initialisiert")
        return True, "AD9833 simuliert initialisiert"
    
    try:
        # Cleanup falls vorherige Handles noch offen
        if gpio_handle is not None:
            try:
                lgpio.gpiochip_close(gpio_handle)
            except:
                pass
        if spi_handle is not None:
            try:
                spi_handle.close()
            except:
                pass
        
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
        logger.info(f"SPI konfiguriert: Bus={SPI_BUS}, Device={SPI_DEVICE}, Speed={SPI_FREQUENCY}Hz, Mode={spi_handle.mode}")
        
        # Erweiterte Reset-Sequenz für AD9833
        logger.info("Starte AD9833 Reset-Sequenz...")
        
        # Master Reset
        write_to_AD9833(0x2100)  # Reset aktivieren
        time.sleep(0.01)
        
        # Reset deaktivieren und Chip für Konfiguration vorbereiten
        write_to_AD9833(0x2000)  # Reset deaktivieren
        time.sleep(0.01)
        
        # Standardkonfiguration setzen
        write_to_AD9833(0x2000)  # Sinuswelle, normale Operation
        time.sleep(0.01)
        
        logger.info("AD9833 Reset-Sequenz abgeschlossen")
        
        ist_initialisiert = True
        logger.info("AD9833 erfolgreich initialisiert mit lgpio")
        return True, "AD9833 erfolgreich initialisiert mit lgpio"
    except Exception as e:
        ist_initialisiert = False
        logger.error(f"Fehler beim Initialisieren: {str(e)}")
        return False, f"Fehler beim Initialisieren: {str(e)}"

def write_to_AD9833(data):
    """Sendet 16-Bit Daten an AD9833 oder simuliert"""
    if SIMULATION_MODE:
        logger.debug(f"Simuliert: Sende 0x{data:04X} an AD9833")
        return True
    
    if spi_handle is None or gpio_handle is None:
        logger.error("SPI oder GPIO nicht initialisiert")
        return False
    try:
        # FSYNC LOW für Datenübertragung
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 0)
        time.sleep(0.001)  # Kurze Pause für saubere Flanke
        
        # Daten als 16-Bit übertragen (MSB first)
        result = spi_handle.xfer2([data >> 8, data & 0xFF])
        
        time.sleep(0.001)  # Kurze Pause vor FSYNC HIGH
        # FSYNC HIGH nach Übertragung
        lgpio.gpio_write(gpio_handle, FSYNC_PIN, 1)
        
        logger.debug(f"Erfolgreich gesendet: 0x{data:04X}, Antwort: {result}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Schreiben: {str(e)}")
        return False

def set_frequency(freq):
    """Stellt die Ausgangsfrequenz ein (in Hz)"""
    global aktuelle_frequenz
    if SIMULATION_MODE:
        aktuelle_frequenz = freq
        logger.info(f"Frequenz simuliert gesetzt: {freq} Hz")
        return True
    
    try:
        # Frequenz-Word berechnen
        freq_word = int((freq * 2**28) / FMCLK)
        logger.info(f"Setze Frequenz {freq} Hz, Freq-Word: 0x{freq_word:08X}")
        
        # Frequenz setzen OHNE die Wellenform zu überschreiben
        # B28-Bit setzen, aber aktuelle Wellenform beibehalten
        current_control = aktuelle_wellenform if aktuelle_wellenform else SINE_WAVE
        control_with_b28 = current_control | 0x0100  # B28-Bit setzen
        
        if not write_to_AD9833(control_with_b28):
            return False
        
        # Niederwertiges 14-Bit Wort senden
        freq_lsb = FREQ0_REG | (freq_word & 0x3FFF)
        if not write_to_AD9833(freq_lsb):
            return False
        logger.debug(f"Frequenz LSB gesendet: 0x{freq_lsb:04X}")
        
        # Höherwertiges 14-Bit Wort senden
        freq_msb = FREQ0_REG | ((freq_word >> 14) & 0x3FFF)
        if not write_to_AD9833(freq_msb):
            return False
        logger.debug(f"Frequenz MSB gesendet: 0x{freq_msb:04X}")
        
        # B28-Bit wieder deaktivieren, Wellenform beibehalten
        if not write_to_AD9833(current_control):
            return False
        
        aktuelle_frequenz = freq
        logger.info(f"Frequenz erfolgreich gesetzt: {freq} Hz (Wellenform beibehalten)")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Setzen der Frequenz: {str(e)}")
        return False

def set_waveform(waveform):
    """Stellt die Wellenform ein"""
    global aktuelle_wellenform
    if SIMULATION_MODE:
        aktuelle_wellenform = waveform
        logger.info(f"Wellenform simuliert gesetzt: 0x{waveform:04X}")
        return True
    
    try:
        wellenform_namen = {SINE_WAVE: "Sinus", TRIANGLE_WAVE: "Dreieck", SQUARE_WAVE: "Rechteck"}
        waveform_name = wellenform_namen.get(waveform, f"Unbekannt (0x{waveform:04X})")
        logger.info(f"Setze Wellenform: {waveform_name} (0x{waveform:04X})")
        
        if not write_to_AD9833(waveform):
            return False
        
        # Kurze Pause nach Wellenform-Änderung
        time.sleep(0.01)
        
        aktuelle_wellenform = waveform
        logger.info(f"Wellenform erfolgreich gesetzt: {waveform_name}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Setzen der Wellenform: {str(e)}")
        return False

def cleanup():
    """Räumt Ressourcen auf"""
    global spi_handle, gpio_handle, ist_initialisiert
    if SIMULATION_MODE:
        ist_initialisiert = False
        logger.info("Simulierter Cleanup abgeschlossen")
        return
    
    try:
        # AD9833 reset vor Cleanup
        if spi_handle is not None and gpio_handle is not None:
            write_to_AD9833(0x2100)
    except:
        pass
    finally:
        try:
            # GPIO Handle schließen
            if gpio_handle is not None:
                lgpio.gpiochip_close(gpio_handle)
                gpio_handle = None
        except:
            pass
        
        try:
            # SPI Handle schließen
            if spi_handle is not None:
                spi_handle.close()
                spi_handle = None
        except:
            pass
        
        ist_initialisiert = False
        logger.info("Cleanup mit lgpio abgeschlossen")

def get_ip_address():
    """Abrufen der IP-Adresse"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('1.1.1.1', 1))
            return sock.getsockname()[0]
    except Exception:
        return '127.0.0.1'

def generate_waveform_svg(waveform_type, width=400, height=140):
    """Generiert ein elegantes SVG für die Signalvorschau"""
    try:
        # SVG-Grundgerüst
        svg_parts = [
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border-radius: 6px; box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);">',
            
            # Gitter
            '<defs>',
            '<pattern id="grid" width="15" height="12" patternUnits="userSpaceOnUse">',
            '<path d="M 15 0 L 0 0 0 12" fill="none" stroke="#cbd5e1" stroke-width="0.5" opacity="0.4"/>',
            '</pattern>',
            '</defs>',
            '<rect width="100%" height="100%" fill="url(#grid)" />',
            
            # Achsen
            f'<line x1="15" y1="{height-15}" x2="{width-15}" y2="{height-15}" stroke="#64748b" stroke-width="1"/>',  # X-Achse
            f'<line x1="15" y1="15" x2="15" y2="{height-15}" stroke="#64748b" stroke-width="1"/>',  # Y-Achse
        ]
        
        # Wellenform generieren
        points = []
        center_y = height // 2
        amplitude = (height - 40) // 2
        wave_width = width - 40
        
        for i in range(wave_width):
            x = 20 + i
            t = (i / wave_width) * 4 * math.pi
            
            if waveform_type == SINE_WAVE:
                y = center_y - amplitude * math.sin(t)
            elif waveform_type == TRIANGLE_WAVE:
                # Dreieckswelle
                period = 2 * math.pi
                t_mod = t % period
                if t_mod < period / 2:
                    y = center_y - amplitude * (4 * t_mod / period - 1)
                else:
                    y = center_y - amplitude * (3 - 4 * t_mod / period)
            elif waveform_type == SQUARE_WAVE:
                y = center_y - amplitude * (1 if math.sin(t) > 0 else -1)
            else:
                y = center_y - amplitude * math.sin(t)
            
            points.append(f"{x},{y}")
        
        # Wellenform-Pfad hinzufügen
        path_data = "M" + " L".join(points)
        svg_parts.append(f'<path d="{path_data}" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round"/>')
        
        svg_parts.append('</svg>')
        return ''.join(svg_parts)
        
    except Exception as e:
        logger.error(f"Fehler beim Generieren des SVG: {e}")
        return f'<svg width="{width}" height="{height}"><text x="10" y="30" fill="red">Fehler beim Laden der Vorschau</text></svg>'

# Dash App
app = Dash(__name__, external_stylesheets=['https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'])
app.title = "OurDAQ - Funktionsgenerator (lgpio)"

# Layout
app.layout = html.Div([
    # Header - kompakter
    html.H1("🔬 OurDAQ Funktionsgenerator (lgpio)", 
            className="text-2xl font-bold text-white bg-gradient-to-r from-blue-800 via-blue-600 to-blue-800 p-4 text-center rounded-lg shadow-lg mb-4"),
    
    # Hauptcontainer - zentriert und breiter
    html.Div([
        # Linke Spalte: Konfiguration
        html.Div([
            html.H3("⚙️ Signalkonfiguration", className="text-lg font-bold text-gray-800 mb-4 pb-2 border-b-2 border-blue-200"),
            
            # Wellenform
            html.Div([
                html.Label("Wellenform:", className="font-semibold text-gray-700 text-base mb-3 block"),
                dcc.RadioItems(
                    id='wellenform-radio',
                    options=[
                        {'label': '📈 Sinus', 'value': SINE_WAVE},
                        {'label': '📉 Dreieck', 'value': TRIANGLE_WAVE},
                        {'label': '📏 Rechteck', 'value': SQUARE_WAVE}
                    ],
                    value=SINE_WAVE,
                    labelClassName="block mb-2 text-gray-600 text-base hover:text-blue-600 cursor-pointer p-2 rounded hover:bg-blue-50 transition-colors",
                    className="mb-5"
                ),
            ]),
            
            # Frequenz
            html.Div([
                html.Label(f"Frequenz ({MIN_FREQUENCY}-{MAX_FREQUENCY} Hz):", 
                          className="font-semibold text-gray-700 text-base mb-3 block"),
                dcc.Input(
                    id='frequenz-input',
                    type='number',
                    min=MIN_FREQUENCY,
                    max=MAX_FREQUENCY,
                    step=0.1,
                    value=1000,
                    className="w-full p-3 border-2 border-gray-300 rounded text-gray-700 text-base focus:ring-2 focus:ring-blue-500 focus:border-blue-500 mb-5"
                ),
            ]),
            
            # Konfigurieren Button
            html.Button(
                '🚀 Konfiguration anwenden',
                id='apply-button',
                className="w-full bg-gradient-to-r from-green-600 to-green-500 text-white font-bold py-4 px-6 rounded-lg hover:from-green-700 hover:to-green-600 transition duration-300 shadow-lg transform hover:scale-105"
            ),
        ], className="bg-white p-6 rounded-xl shadow-lg"),
        
        # Rechte Spalte: Status und Vorschau
        html.Div([
            html.H3("📊 Status & Signalvorschau", className="text-lg font-bold text-gray-800 mb-4 pb-2 border-b-2 border-green-200"),
            html.Div(id='status-display', 
                    className="bg-gray-50 p-4 rounded-lg border-2 font-mono text-sm text-gray-700 shadow-sm mb-4 min-h-[80px]", 
                    children="🔴 AD9833 nicht initialisiert"),
            html.Div([
                html.H4("🌊 Signalvorschau", className="text-base font-semibold text-gray-700 mb-3"),
                html.Div(id='wave-preview', 
                        className="w-full rounded-lg shadow-lg bg-gradient-to-br from-gray-50 to-blue-50 p-3",
                        style={'minHeight': '160px'})
            ])
        ], className="bg-white p-6 rounded-xl shadow-lg"),
        
    ], className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-5xl mx-auto"),
    
], className="max-w-7xl mx-auto p-4 bg-gradient-to-br from-gray-50 to-blue-50 min-h-screen")

@callback(
    [Output('status-display', 'children'),
     Output('status-display', 'className'),
     Output('wave-preview', 'children')],
    [Input('apply-button', 'n_clicks'),
     Input('wellenform-radio', 'value')],
    [State('frequenz-input', 'value')]
)
def handle_apply_configuration(n_clicks, wellenform, frequenz):
    base_style = "bg-gray-50 p-4 rounded-lg border-2 font-mono text-sm shadow-sm min-h-[80px]"
    
    # SVG-Signalvorschau als HTML-Component generieren
    wave_svg_html = generate_waveform_svg(wellenform)
    wave_preview = html.Div([
        html.Iframe(
            srcDoc=f'<!DOCTYPE html><html><body style="margin:0;padding:8px;background:#f8fafc;">{wave_svg_html}</body></html>',
            style={'width': '100%', 'height': '150px', 'border': 'none', 'borderRadius': '8px'}
        )
    ])
    
    if not n_clicks:
        return ('🔴 AD9833 nicht initialisiert\nBereit zur Konfiguration...', 
                f"{base_style} border-red-400 text-red-600", 
                wave_preview)
    
    if frequenz is None or not isinstance(frequenz, (int, float)) or frequenz < MIN_FREQUENCY or frequenz > MAX_FREQUENCY:
        return (f'❌ Fehler: Frequenz muss zwischen {MIN_FREQUENCY} und {MAX_FREQUENCY} Hz liegen', 
                f"{base_style} border-red-400 text-red-600", 
                wave_preview)
    
    success_init, message_init = init_AD9833()
    if not success_init:
        return (f'❌ Initialisierung fehlgeschlagen:\n{message_init}', 
                f"{base_style} border-red-400 text-red-600", 
                wave_preview)
    
    wellenform_namen = {SINE_WAVE: "Sinuswelle", TRIANGLE_WAVE: "Dreieckswelle", SQUARE_WAVE: "Rechteckwelle"}
    wellenform_name = wellenform_namen.get(wellenform, "Unbekannt")
    
    try:
        # WICHTIG: Zuerst Wellenform, dann Frequenz setzen!
        if not set_waveform(wellenform):
            return ('❌ Fehler beim Setzen der Wellenform', 
                    f"{base_style} border-red-400 text-red-600", 
                    wave_preview)
        
        if not set_frequency(frequenz):
            return ('❌ Fehler beim Setzen der Frequenz', 
                    f"{base_style} border-red-400 text-red-600", 
                    wave_preview)
        
        config_text = f"""✅ AKTIVE KONFIGURATION (lgpio)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌊 Wellenform: {wellenform_name}
⚡ Frequenz: {frequenz} Hz
🚀 Status: Signalausgabe aktiv{' (Simuliert)' if SIMULATION_MODE else ''}
📡 Hardware: {'Simulation' if SIMULATION_MODE else 'AD9833 bereit'}
🔧 GPIO: lgpio Library"""
        
        return (config_text, 
                f"{base_style} border-green-400 text-green-600", 
                wave_preview)
                
    except Exception as e:
        logger.error(f"Konfigurationsfehler: {str(e)}")
        return (f'❌ Fehler bei der Konfiguration:\n{str(e)}', 
                f"{base_style} border-red-400 text-red-600", 
                wave_preview)

# Cleanup
import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    logger.info(f"Starte Funktionsgenerator im {'Simulation' if SIMULATION_MODE else 'Hardware'} Modus mit lgpio")
    app.run(host=get_ip_address(), port=8060, debug=True, use_reloader=False)
