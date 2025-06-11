# -*- coding: utf-8 -*-
"""
Netzteil Web Interface für OurDAQ Dashboard
Integriert positive und negative Spannungseinstellung mit Strommessung
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
    import RPi.GPIO as GPIO
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    from daqhats_utils import select_hat_device, chan_list_to_string, chan_list_to_mask
    HARDWARE_AVAILABLE = True
    print("Hardware-Module erfolgreich geladen")
except ImportError as e:
    print(f"Hardware-Module nicht verfügbar: {e}")
    HARDWARE_AVAILABLE = False
    # Define dummy classes/modules to prevent NameError
    spidev = None
    GPIO = None

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
VOLTAGE_REFERENCE = 5.0  # Referenzspannung in Volt

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
        self.current_voltage_pos = 0
        self.current_voltage_neg = 0
        self.measured_current = 0
        self.measured_voltage = 0
        
        # Hardware-Objekte initialisieren
        self.spi = None
        self.hat = None
        
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
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(CS_PIN, GPIO.OUT)
            GPIO.output(CS_PIN, GPIO.HIGH)
            
            # MCC 118 für ADC initialisieren
            address = select_hat_device(HatIDs.MCC_118)
            self.hat = mcc118(address)
            
            print("Hardware erfolgreich initialisiert")
            
        except Exception as e:
            print(f"Fehler bei Hardware-Initialisierung: {e}")
            self.simulation_mode = True
            self.spi = None
            self.hat = None
            
    def write_dac_channel(self, channel, value):
        """Schreibt Wert an DAC-Kanal (0=positiv, 1=negativ)"""
        if self.simulation_mode or not HARDWARE_AVAILABLE:
            # Simulation
            voltage = (value / DAC_MAX_VALUE) * VOLTAGE_REFERENCE
            if channel == 0:
                self.current_voltage_pos = voltage
            else:
                self.current_voltage_neg = voltage
            return
            
        try:
            assert 0 <= value <= DAC_MAX_VALUE
            
            control = 0
            control |= channel << 15  # Channel A=0 oder B=1
            control |= 1 << 14        # Buffered
            control |= 0 << 13        # Gain 0=2x
            control |= 1 << 12        # Shutdown=0
            
            data = control | (value & 0xFFF)
            high_byte = (data >> 8) & 0xFF
            low_byte = data & 0xFF
            
            if self.spi and GPIO:
                GPIO.output(CS_PIN, GPIO.LOW)
                self.spi.xfer2([high_byte, low_byte])
                GPIO.output(CS_PIN, GPIO.HIGH)
                
                # Aktuelle Spannung aktualisieren
                voltage = (value / DAC_MAX_VALUE) * VOLTAGE_REFERENCE
                if channel == 0:
                    self.current_voltage_pos = voltage
                else:
                    self.current_voltage_neg = voltage
            else:
                print("Hardware nicht verfügbar, verwende Simulation")
                self.simulation_mode = True
                self.write_dac_channel(channel, value)  # Recursive call in simulation mode
                
        except Exception as e:
            print(f"Fehler beim DAC-Schreiben: {e}")
            
    def set_positive_voltage(self, voltage):
        """Setzt positive Ausgangsspannung"""
        voltage = max(0, min(VOLTAGE_REFERENCE, voltage))  # Clamp voltage
        dac_value = int((voltage / VOLTAGE_REFERENCE) * DAC_MAX_VALUE)
        dac_value = max(0, min(DAC_MAX_VALUE, dac_value))
        self.write_dac_channel(0, dac_value)
        print(f"Positive Spannung gesetzt: {voltage:.2f}V (DAC: {dac_value})")
        
    def set_negative_voltage(self, voltage):
        """Setzt negative Ausgangsspannung"""
        voltage = max(0, min(VOLTAGE_REFERENCE, voltage))  # Clamp voltage
        dac_value = int((voltage / VOLTAGE_REFERENCE) * DAC_MAX_VALUE)
        dac_value = max(0, min(DAC_MAX_VALUE, dac_value))
        self.write_dac_channel(1, dac_value)
        print(f"Negative Spannung gesetzt: {voltage:.2f}V (DAC: {dac_value})")
        
    def read_current(self):
        """Liest Strom über MCC 118 Kanal 5"""
        if self.simulation_mode or not HARDWARE_AVAILABLE or not self.hat:
            # Simuliere Strom basierend auf Spannung (Ohm'sches Gesetz)
            total_voltage = abs(self.current_voltage_pos - self.current_voltage_neg)
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
                total_voltage = self.current_voltage_pos - self.current_voltage_neg
                
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
            'voltage_pos': self.current_voltage_pos,
            'voltage_neg': self.current_voltage_neg,
            'voltage_total': self.current_voltage_pos - self.current_voltage_neg,
            'current': self.measured_current,
            'power': abs(self.current_voltage_pos - self.current_voltage_neg) * abs(self.measured_current),
            'simulation_mode': self.simulation_mode,
            'monitoring': self.running
        }
        
    def emergency_stop(self):
        """Notaus - alle Ausgänge auf 0V"""
        self.set_positive_voltage(0)
        self.set_negative_voltage(0)
        print("NOTAUS aktiviert - alle Ausgänge auf 0V")
        
    def cleanup(self):
        """Cleanup der Hardware"""
        self.stop_monitoring()
        self.emergency_stop()
        
        if not self.simulation_mode and HARDWARE_AVAILABLE:
            try:
                if self.spi:
                    self.spi.close()
                if GPIO:
                    GPIO.cleanup()
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
                # Positive Spannung
                html.Div([
                    html.H3("🔋 Positive Spannung", style={'color': '#27ae60', 'marginBottom': '15px'}),
                    html.Div([
                        html.Label("Spannung (V):", style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='voltage-pos-slider',
                            min=0,
                            max=5,
                            step=0.1,
                            value=0,
                            marks={i: f'{i}V' for i in range(6)},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], style={'marginBottom': '15px'}),
                    
                    html.Div([
                        dcc.Input(
                            id='voltage-pos-input',
                            type='number',
                            min=0,
                            max=5,
                            step=0.01,
                            value=0,
                            placeholder="Spannung eingeben",
                            style={'width': '120px', 'marginRight': '10px', 'padding': '5px'}
                        ),
                        html.Button(
                            '✓ Setzen',
                            id='set-pos-button',
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
                
                # Negative Spannung
                html.Div([
                    html.H3("🔋 Negative Spannung", style={'color': '#e74c3c', 'marginBottom': '15px'}),
                    html.Div([
                        html.Label("Spannung (V):", style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='voltage-neg-slider',
                            min=0,
                            max=5,
                            step=0.1,
                            value=0,
                            marks={i: f'{i}V' for i in range(6)},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ], style={'marginBottom': '15px'}),
                    
                    html.Div([
                        dcc.Input(
                            id='voltage-neg-input',
                            type='number',
                            min=0,
                            max=5,
                            step=0.01,
                            value=0,
                            placeholder="Spannung eingeben",
                            style={'width': '120px', 'marginRight': '10px', 'padding': '5px'}
                        ),
                        html.Button(
                            '✓ Setzen',
                            id='set-neg-button',
                            n_clicks=0,
                            style={
                                'backgroundColor': '#e74c3c',
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
                    'border': '2px solid #e74c3c'
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
                        '🔄 Reset',
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
        
        # Hidden Div for debugging
        html.Div(id='debug-output', style={'display': 'none'})
    ], style={'backgroundColor': '#f5f7fa', 'minHeight': '100vh'})
    
    # =============================================================================
    # CALLBACKS - Alle mit expliziten prevent_initial_call Settings
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
                html.Span("🔋 Pos. Spannung: ", style={'fontWeight': 'bold', 'color': '#27ae60'}),
                html.Span(f"{status['voltage_pos']:.2f} V")
            ], style={'marginBottom': '8px'}),
            
            html.Div([
                html.Span("🔋 Neg. Spannung: ", style={'fontWeight': 'bold', 'color': '#e74c3c'}),
                html.Span(f"{status['voltage_neg']:.2f} V")
            ], style={'marginBottom': '8px'}),
            
            html.Div([
                html.Span("⚡ Gesamt-Spannung: ", style={'fontWeight': 'bold', 'color': '#2c3e50'}),
                html.Span(f"{status['voltage_total']:.2f} V")
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
    
    # Positive Voltage Controls
    @app.callback(
        [Output('debug-output', 'children', allow_duplicate=True),
         Output('voltage-pos-slider', 'value', allow_duplicate=True)],
        Input('set-pos-button', 'n_clicks'),
        State('voltage-pos-input', 'value'),
        prevent_initial_call=True
    )
    def set_positive_voltage_button(n_clicks, voltage):
        if n_clicks is None or n_clicks == 0:
            return "", 0
            
        if voltage is None:
            return "Fehler: Keine Spannung eingegeben", 0
            
        try:
            voltage = float(voltage)
            voltage = max(0, min(5, voltage))  # Clamp to valid range
            if netzteil:
                netzteil.set_positive_voltage(voltage)
                return f"Positive Spannung auf {voltage:.2f}V gesetzt", voltage
            else:
                return "Fehler: Netzteil nicht verfügbar", 0
        except Exception as e:
            return f"Fehler: {str(e)}", 0
    
    @app.callback(
        Output('voltage-pos-input', 'value'),
        Input('voltage-pos-slider', 'value'),
        prevent_initial_call=False
    )
    def sync_pos_input_from_slider(slider_value):
        if slider_value is not None and netzteil:
            netzteil.set_positive_voltage(slider_value)
        return slider_value
    
    # Negative Voltage Controls
    @app.callback(
        [Output('debug-output', 'children', allow_duplicate=True),
         Output('voltage-neg-slider', 'value', allow_duplicate=True)],
        Input('set-neg-button', 'n_clicks'),
        State('voltage-neg-input', 'value'),
        prevent_initial_call=True
    )
    def set_negative_voltage_button(n_clicks, voltage):
        if n_clicks is None or n_clicks == 0:
            return "", 0
            
        if voltage is None:
            return "Fehler: Keine Spannung eingegeben", 0
            
        try:
            voltage = float(voltage)
            voltage = max(0, min(5, voltage))  # Clamp to valid range
            if netzteil:
                netzteil.set_negative_voltage(voltage)
                return f"Negative Spannung auf {voltage:.2f}V gesetzt", voltage
            else:
                return "Fehler: Netzteil nicht verfügbar", 0
        except Exception as e:
            return f"Fehler: {str(e)}", 0
    
    @app.callback(
        Output('voltage-neg-input', 'value'),
        Input('voltage-neg-slider', 'value'),
        prevent_initial_call=False
    )
    def sync_neg_input_from_slider(slider_value):
        if slider_value is not None and netzteil:
            netzteil.set_negative_voltage(slider_value)
        return slider_value
    
    # Emergency Stop
    @app.callback(
        [Output('emergency-stop', 'children'),
         Output('emergency-stop', 'style'),
         Output('voltage-pos-slider', 'value', allow_duplicate=True),
         Output('voltage-neg-slider', 'value', allow_duplicate=True)],
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
            }, 0, 0
            
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
        }, 0, 0
    
    # Reset Button
    @app.callback(
        [Output('reset-button', 'children'),
         Output('voltage-pos-slider', 'value', allow_duplicate=True),
         Output('voltage-neg-slider', 'value', allow_duplicate=True)],
        Input('reset-button', 'n_clicks'),
        prevent_initial_call=True
    )
    def reset_callback(n_clicks):
        if n_clicks is None or n_clicks == 0:
            return '🔄 Reset', 0, 0
            
        if netzteil:
            netzteil.emergency_stop()
            
        return '✅ Reset durchgeführt', 0, 0
    
    return app

# =============================================================================
# MAIN
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
    print(f"🎭 Simulation Mode: {'AN' if args.simulate else 'AUS'}")
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
        print("Cleanup abgeschlossen")

if __name__ == '__main__':
    main()