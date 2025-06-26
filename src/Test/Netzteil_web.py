# -*- coding: utf-8 -*-
"""
Netzteil Web Interface für OurDAQ Dashboard
Integriert Spannungseinstellung mit Strommessung
"""

import argparse
import time
import threading
from datetime import datetime
from collections import deque
import json
import sys
import platform

# Dash und Plotly
from dash import Dash, dcc, html, Input, Output, State, callback_context, callback
import plotly.graph_objs as go
import plotly.express as px

# Hardware-spezifische Imports (nur auf Raspberry Pi)
try:
    import spidev
    import lgpio
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    
    # Erweiterte daqhats_utils Import-Behandlung
    try:
        from daqhats_utils import select_hat_device, chan_list_to_string, chan_list_to_mask
    except ImportError:
        # Fallback: nur grundlegende Funktionen importieren
        try:
            from daqhats_utils import select_hat_device
            # Definiere fehlende Funktionen lokal
            def chan_list_to_string(channels):
                """Hilfsfunktion für Kanalliste zu String-Konvertierung"""
                return ', '.join(map(str, channels))
                
            def chan_list_to_mask(channels):
                """Hilfsfunktion für Kanalliste zu Bitmask-Konvertierung"""
                mask = 0
                for channel in channels:
                    mask |= (1 << channel)
                return mask
        except ImportError:
            # Wenn select_hat_device auch fehlt, definiere alle Funktionen
            def select_hat_device(hat_id):
                """Fallback-Funktion für HAT-Geräteauswahl"""
                return 0  # Standard-Adresse
                
            def chan_list_to_string(channels):
                return ', '.join(map(str, channels))
                
            def chan_list_to_mask(channels):
                mask = 0
                for channel in channels:
                    mask |= (1 << channel)
                return mask
    
    HARDWARE_AVAILABLE = True
    print("Hardware-Module erfolgreich geladen")
    
except ImportError as e:
    print(f"Hardware-Module nicht verfügbar: {e}")
    HARDWARE_AVAILABLE = False
    # Dummy-Klassen/Module definieren um NameError zu vermeiden
    spidev = None
    lgpio = None
    
    # Dummy-Funktionen für daqhats_utils
    def select_hat_device(hat_id):
        return 0
        
    def chan_list_to_string(channels):
        return ', '.join(map(str, channels))
        
    def chan_list_to_mask(channels):
        mask = 0
        for channel in channels:
            mask |= (1 << channel)
        return mask

# Unter Windows UTF-8 für die Konsole erzwingen
if platform.system() == "Windows":
    sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# KONFIGURATION
# =============================================================================

# Hardware-Parameter
SHUNT_WIDERSTAND = 0.1   # Ohm
VERSTAERKUNG = 69.0      # Verstärkungsfaktor
CS_PIN = 22              # Chip Select Pin
DAC_MAX_VALUE = 4095     # 12-bit DAC
VOLTAGE_REFERENCE = 10.0  # Referenzspannung in Volt (für +10V bis -10V)

# Mess-Parameter
SAMPLE_RATE = 1000.0     # Hz
BUFFER_SIZE = 1000       # Anzahl der zu speichernden Messpunkte
UPDATE_INTERVAL = 100    # ms

# =============================================================================
# NETZTEIL CONTROLLER KLASSE
# =============================================================================

class NetzteilController:
    def __init__(self, simulation_mode=False):
        self.simulation_mode = simulation_mode or not HARDWARE_AVAILABLE or platform.system() == "Windows"
        self.running = False
        self.current_voltage = 0
        self.measured_current = 0
        self.measured_voltage = 0
        
        # Hardware-Objekte initialisieren
        self.spi = None
        self.hat = None
        self.gpio_handle = None
        
        # Datenhistorie
        self.voltage_history = deque(maxlen=BUFFER_SIZE)
        self.current_history = deque(maxlen=BUFFER_SIZE)
        self.time_history = deque(maxlen=BUFFER_SIZE)
        
        # Hardware-Initialisierung nur wenn verfügbar
        if not self.simulation_mode and HARDWARE_AVAILABLE:
            self.init_hardware()
        else:
            print("Simulation Mode: Netzteil läuft im Simulationsmodus")
            
    def init_hardware(self):
        """Initialisiert die Hardware-Komponenten"""
        try:
            # SPI für DAC initialisieren
            self.spi = spidev.SpiDev()
            self.spi.open(0, 0)
            self.spi.max_speed_hz = 1000000
            self.spi.mode = 0b00
            
            # GPIO für Chip Select
            self.gpio_handle = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self.gpio_handle, CS_PIN)
            lgpio.gpio_write(self.gpio_handle, CS_PIN, 1)
            
            # MCC 118 für ADC initialisieren mit verbesserter Fehlerbehandlung
            try:
                address = select_hat_device(HatIDs.MCC_118)
                self.hat = mcc118(address)
                print(f"MCC 118 HAT erfolgreich initialisiert an Adresse {address}")
            except Exception as hat_error:
                print(f"Warnung: MCC 118 HAT konnte nicht initialisiert werden: {hat_error}")
                print("Weiter nur mit DAC-Funktionalität...")
                self.hat = None
            
            print("Hardware-Grundinitialisierung abgeschlossen")
            
        except Exception as e:
            print(f"Fehler bei Hardware-Initialisierung: {e}")
            self.simulation_mode = True
            self.spi = None
            self.hat = None
            self.gpio_handle = None
            
    def write_dac_channel(self, value):
        """Schreibt Wert an DAC-Kanal"""
        if self.simulation_mode or not HARDWARE_AVAILABLE:
            # Simulation
            voltage = ((value / DAC_MAX_VALUE) * (2 * VOLTAGE_REFERENCE)) - VOLTAGE_REFERENCE
            self.current_voltage = voltage
            return
            
        try:
            assert 0 <= value <= DAC_MAX_VALUE
            
            control = 0
            control |= 0 << 15  # Channel A=0
            control |= 1 << 14  # Buffered
            control |= 0 << 13  # Gain 0=2x
            control |= 1 << 12  # Shutdown=0
            
            data = control | (value & 0xFFF)
            high_byte = (data >> 8) & 0xFF
            low_byte = data & 0xFF
            
            if self.spi and self.gpio_handle:
                lgpio.gpio_write(self.gpio_handle, CS_PIN, 0)
                self.spi.xfer2([high_byte, low_byte])
                lgpio.gpio_write(self.gpio_handle, CS_PIN, 1)
                
                # Aktuelle Spannung aktualisieren
                voltage = ((value / DAC_MAX_VALUE) * (2 * VOLTAGE_REFERENCE)) - VOLTAGE_REFERENCE
                self.current_voltage = voltage
            else:
                print("Hardware nicht verfügbar, verwende Simulation")
                self.simulation_mode = True
                self.write_dac_channel(value)  # Rekursiver Aufruf im Simulationsmodus
                
        except Exception as e:
            print(f"Fehler beim DAC-Schreiben: {e}")
            
    def set_voltage(self, voltage):
        """Setzt Ausgangsspannung"""
        voltage = max(-VOLTAGE_REFERENCE, min(VOLTAGE_REFERENCE, voltage))  # Spannung begrenzen (-10V bis +10V)
        # Skaliere die Spannung auf den DAC-Bereich (0 bis 4095)
        dac_value = int(((voltage + VOLTAGE_REFERENCE) / (2 * VOLTAGE_REFERENCE)) * DAC_MAX_VALUE)
        dac_value = max(0, min(DAC_MAX_VALUE, dac_value))
        self.write_dac_channel(dac_value)
        print(f"Spannung gesetzt: {voltage:.2f}V (DAC: {dac_value})")
        
    def read_current(self):
        """Liest Strom über MCC 118 Kanal 5"""
        if self.simulation_mode or not HARDWARE_AVAILABLE or not self.hat:
            # Simuliere Strom basierend auf Spannung (Ohm'sches Gesetz)
            total_voltage = abs(self.current_voltage)
            simulated_current = total_voltage / 10.0  # Annahme: 10 Ohm Last
            # Füge etwas Rauschen hinzu für realistischere Simulation
            noise = (time.time() % 1) * 0.001 - 0.0005
            self.measured_current = simulated_current + noise
            return self.measured_current
            
        try:
            # Einzelne Messung über Kanal 5
            voltage = self.hat.a_in_read(5)
            current = voltage / (VERSTAERKUNG * SHUNT_WIDERSTAND)
            self.measured_current = current
            return current
            
        except Exception as e:
            print(f"Fehler beim Strom lesen: {e}")
            # Fallback auf Simulation
            if not self.simulation_mode:
                print("Wechsle zu Simulationsmodus für Strommessung")
                self.simulation_mode = True
            return self.read_current()
            
    def start_monitoring(self):
        """Startet kontinuierliches Monitoring"""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """Stoppt Monitoring"""
        self.running = False
        
    def _monitor_loop(self):
        """Monitoring-Schleife"""
        while self.running:
            try:
                current = self.read_current()
                total_voltage = self.current_voltage
                
                # Historie aktualisieren
                now = datetime.now()
                self.time_history.append(now)
                self.current_history.append(current)
                self.voltage_history.append(total_voltage)
                
                time.sleep(0.1)  # 10 Hz Update-Rate
                
            except Exception as e:
                print(f"Fehler im Monitoring: {e}")
                time.sleep(1)
                
    def get_status(self):
        """Liefert aktuellen Status"""
        return {
            'voltage': self.current_voltage,
            'current': self.measured_current,
            'power': abs(self.current_voltage) * abs(self.measured_current),
            'simulation_mode': self.simulation_mode,
            'monitoring': self.running
        }
        
    def emergency_stop(self):
        """Notaus - alle Ausgänge auf 0V"""
        self.set_voltage(0)
        print("NOTAUS aktiviert - alle Ausgänge auf 0V")
        
    def cleanup(self):
        """Cleanup der Hardware"""
        self.stop_monitoring()
        self.emergency_stop()
        
        if not self.simulation_mode and HARDWARE_AVAILABLE:
            try:
                if self.spi:
                    self.spi.close()
                if self.gpio_handle:
                    lgpio.gpiochip_close(self.gpio_handle)
                print("Hardware-Cleanup abgeschlossen")
            except Exception as e:
                print(f"Cleanup-Warnung: {e}")

# =============================================================================
# DASH APP
# =============================================================================

# Globale Controller-Instanz
netzteil = None

def create_app(simulation_mode=False):
    global netzteil
    
    netzteil = NetzteilController(simulation_mode)
    netzteil.start_monitoring()
    
    # App mit suppress_callback_exceptions=True für bessere iframe-Kompatibilität
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = "OurDAQ Netzteil"
    
    # Layout
    app.layout = html.Div([
        # Header
        html.Div([
            html.H1([
                html.Span("⚡ ", style={'fontSize': '40px'}),
                "OurDAQ Netzteil"
            ], style={
                'textAlign': 'center',
                'color': 'white',
                'margin': '0',
                'fontSize': '28px'
            }),
            
            html.Div(id='status-indicator', style={
                'textAlign': 'center',
                'color': 'white',
                'fontSize': '14px',
                'marginTop': '10px'
            })
        ], style={
            'background': 'linear-gradient(135deg, #f39c12 0%, #e67e22 100%)',
            'padding': '20px',
            'marginBottom': '20px'
        }),
        
        # Hauptinhalt
        html.Div([
            # Kontrollen
            html.Div([
                # Spannung
                html.Div([
                    html.H3("🔋 Spannung", style={'color': '#27ae60', 'marginBottom': '15px'}),
                    html.Div([
                        html.Label("Spannung (V):", style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='voltage-slider',
                            min=-10,
                            max=10,
                            step=0.1,
                            value=0,
                            marks={i: f'{i}V' for i in range(-10, 11, 2)},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], style={'marginBottom': '15px'}),
                    
                    html.Div([
                        dcc.Input(
                            id='voltage-input',
                            type='number',
                            min=-10,
                            max=10,
                            step=0.01,
                            value=0,
                            placeholder="Spannung eingeben",
                            style={'width': '120px', 'marginRight': '10px', 'padding': '5px'}
                        ),
                        html.Button(
                            '✓ Setzen',
                            id='set-voltage-button',
                            n_clicks=0,
                            style={
                                'backgroundColor': '#27ae60',
                                'color': 'white',
                                'border': 'none',
                                'padding': '8px 15px',
                                'borderRadius': '4px',
                                'cursor': 'pointer'
                            }
                        )
                    ])
                ], style={
                    'backgroundColor': 'white',
                    'padding': '20px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                    'marginBottom': '20px',
                    'border': '2px solid #27ae60'
                }),
                
                # Notaus und Kontrollen
                html.Div([
                    html.Button(
                        '🛑 NOTAUS',
                        id='emergency-stop',
                        n_clicks=0,
                        style={
                            'backgroundColor': '#c0392b',
                            'color': 'white',
                            'border': 'none',
                            'padding': '15px 30px',
                            'borderRadius': '8px',
                            'fontSize': '18px',
                            'fontWeight': 'bold',
                            'cursor': 'pointer',
                            'width': '100%',
                            'marginBottom': '10px'
                        }
                    ),
                    
                    html.Button(
                        '🔄 Zurücksetzen',
                        id='reset-button',
                        n_clicks=0,
                        style={
                            'backgroundColor': '#34495e',
                            'color': 'white',
                            'border': 'none',
                            'padding': '10px 20px',
                            'borderRadius': '4px',
                            'cursor': 'pointer',
                            'width': '100%'
                        }
                    )
                ], style={
                    'backgroundColor': 'white',
                    'padding': '20px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
                })
                
            ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '2%'}),

            # Anzeigen und Diagramme
            html.Div([
                # Aktuelle Werte
                html.Div([
                    html.H3("📊 Aktuelle Messwerte", style={'color': '#2c3e50', 'marginBottom': '15px'}),
                    html.Div(id='current-values', style={'fontSize': '16px'})
                ], style={
                    'backgroundColor': 'white',
                    'padding': '20px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                    'marginBottom': '20px'
                }),
                
                # Zeitverlauf-Diagramm
                html.Div([
                    html.H3("📈 Zeitverlauf", style={'color': '#2c3e50', 'marginBottom': '15px'}),
                    dcc.Graph(id='time-series-plot')
                ], style={
                    'backgroundColor': 'white',
                    'padding': '20px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
                })
                
            ], style={'width': '68%', 'display': 'inline-block', 'verticalAlign': 'top'})
            
        ], style={'maxWidth': '1200px', 'margin': '0 auto', 'padding': '20px'}),
        
        # Update-Intervalle
        dcc.Interval(
            id='update-interval',
            interval=UPDATE_INTERVAL,
            n_intervals=0
        ),
        
        # Verstecktes Div für Debugging
        html.Div(id='debug-output', style={'display': 'none'})
    ], style={'backgroundColor': '#f5f7fa', 'minHeight': '100vh'})
    
    # =============================================================================
    # CALLBACKS - Alle mit expliziten prevent_initial_call Einstellungen
    # =============================================================================
    
    @app.callback(
        Output('status-indicator', 'children'),
        Input('update-interval', 'n_intervals'),
        prevent_initial_call=False
    )
    def update_status(n):
        if netzteil is None:
            return "Netzteil nicht initialisiert"
        status = netzteil.get_status()
        mode_text = "🎭 Simulation" if status['simulation_mode'] else "🔧 Hardware"
        monitor_text = "📊 Monitoring" if status['monitoring'] else "⏸️ Gestoppt"
        return f"{mode_text} | {monitor_text} | ⏰ {datetime.now().strftime('%H:%M:%S')}"
    
    @app.callback(
        Output('current-values', 'children'),
        Input('update-interval', 'n_intervals'),
        prevent_initial_call=False
    )
    def update_current_values(n):
        if netzteil is None:
            return "Warte auf Initialisierung..."
            
        status = netzteil.get_status()
        
        return html.Div([
            html.Div([
                html.Span("🔋 Spannung: ", style={'fontWeight': 'bold', 'color': '#27ae60'}),
                html.Span(f"{status['voltage']:.2f} V")
            ], style={'marginBottom': '8px'}),
            
            html.Div([
                html.Span("🔌 Strom: ", style={'fontWeight': 'bold', 'color': '#3498db'}),
                html.Span(f"{status['current']:.3f} A")
            ], style={'marginBottom': '8px'}),
            
            html.Div([
                html.Span("💡 Leistung: ", style={'fontWeight': 'bold', 'color': '#f39c12'}),
                html.Span(f"{status['power']:.3f} W")
            ])
        ])
    
    @app.callback(
        Output('time-series-plot', 'figure'),
        Input('update-interval', 'n_intervals'),
        prevent_initial_call=False
    )
    def update_plot(n):
        if netzteil is None or len(netzteil.time_history) == 0:
            # Leeres Diagramm mit Platzhalter
            fig = go.Figure()
            fig.update_layout(
                title='Warte auf Daten...',
                xaxis_title='Zeit',
                yaxis_title='Werte',
                height=400
            )
            return fig
        
        fig = go.Figure()
        
        # Spannungsverlauf
        fig.add_trace(go.Scatter(
            x=list(netzteil.time_history),
            y=list(netzteil.voltage_history),
            mode='lines',
            name='Spannung (V)',
            line=dict(color='#3498db', width=2),
            yaxis='y'
        ))
        
        # Stromverlauf
        fig.add_trace(go.Scatter(
            x=list(netzteil.time_history),
            y=list(netzteil.current_history),
            mode='lines',
            name='Strom (A)',
            line=dict(color='#e74c3c', width=2),
            yaxis='y2'
        ))
        
        fig.update_layout(
            title='📈 Spannungs- und Stromverlauf',
            xaxis_title='Zeit',
            yaxis=dict(
                title='Spannung (V)',
                side='left',
                color='#3498db'
            ),
            yaxis2=dict(
                title='Strom (A)',
                overlaying='y',
                side='right',
                color='#e74c3c'
            ),
            hovermode='x unified',
            height=400,
            showlegend=True
        )
        
        return fig
    
    # Spannungssteuerung
    @app.callback(
        [Output('debug-output', 'children', allow_duplicate=True),
         Output('voltage-slider', 'value', allow_duplicate=True)],
        Input('set-voltage-button', 'n_clicks'),
        State('voltage-input', 'value'),
        prevent_initial_call=True
    )
    def set_voltage_button(n_clicks, voltage):
        if n_clicks is None or n_clicks == 0:
            return "", 0
            
        if voltage is None:
            return "Fehler: Keine Spannung eingegeben", 0
            
        try:
            voltage = float(voltage)
            voltage = max(-10, min(10, voltage))  # Gültigen Bereich begrenzen (-10V bis +10V)
            if netzteil:
                netzteil.set_voltage(voltage)
                return f"Spannung auf {voltage:.2f}V gesetzt", voltage
            else:
                return "Fehler: Netzteil nicht verfügbar", 0
        except Exception as e:
            return f"Fehler: {str(e)}", 0
    
    @app.callback(
        Output('voltage-input', 'value'),
        Input('voltage-slider', 'value'),
        prevent_initial_call=False
    )
    def sync_input_from_slider(slider_value):
        if slider_value is not None and netzteil:
            netzteil.set_voltage(slider_value)
        return slider_value
    
    # Notaus
    @app.callback(
        [Output('emergency-stop', 'children'),
         Output('emergency-stop', 'style'),
         Output('voltage-slider', 'value', allow_duplicate=True)],
        Input('emergency-stop', 'n_clicks'),
        prevent_initial_call=True
    )
    def emergency_stop_callback(n_clicks):
        if n_clicks is None or n_clicks == 0:
            return '🛑 NOTAUS', {
                'backgroundColor': '#c0392b',
                'color': 'white',
                'border': 'none',
                'padding': '15px 30px',
                'borderRadius': '8px',
                'fontSize': '18px',
                'fontWeight': 'bold',
                'cursor': 'pointer',
                'width': '100%',
                'marginBottom': '10px'
            }, 0
            
        if netzteil:
            netzteil.emergency_stop()
            
        return '✅ NOTAUS aktiviert', {
            'backgroundColor': '#27ae60',
            'color': 'white',
            'border': 'none',
            'padding': '15px 30px',
            'borderRadius': '8px',
            'fontSize': '18px',
            'fontWeight': 'bold',
            'cursor': 'pointer',
            'width': '100%',
            'marginBottom': '10px'
        }, 0
    
    # Zurücksetzen-Button
    @app.callback(
        [Output('reset-button', 'children'),
         Output('voltage-slider', 'value', allow_duplicate=True)],
        Input('reset-button', 'n_clicks'),
        prevent_initial_call=True
    )
    def reset_callback(n_clicks):
        if n_clicks is None or n_clicks == 0:
            return '🔄 Zurücksetzen', 0
            
        if netzteil:
            netzteil.emergency_stop()
            
        return '✅ Zurücksetzung durchgeführt', 0
    
    return app

# =============================================================================
# HAUPTPROGRAMM
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='OurDAQ Netzteil Web Interface')
    parser.add_argument('--simulate', action='store_true', help='Simulationsmodus aktivieren')
    parser.add_argument('--host', default='0.0.0.0', help='Host-Adresse')
    parser.add_argument('--port', type=int, default=8072, help='Port')
    parser.add_argument('--debug', action='store_true', help='Debug-Modus')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("⚡ OurDAQ Netzteil Web Interface")
    print("=" * 60)
    print(f"🎭 Simulation Mode: {'EIN' if args.simulate else 'AUS'}")
    print(f"🌐 URL: http://{args.host}:{args.port}")
    print("=" * 60)
    
    app = create_app(simulation_mode=args.simulate)
    
    try:
        app.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        print("\nNetzteil wird beendet...")
    finally:
        if netzteil:
            netzteil.cleanup()
        print("Bereinigung abgeschlossen")

if __name__ == '__main__':
    main()
