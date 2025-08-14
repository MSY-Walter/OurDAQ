#!/usr/bin/env python3
"""
Dash Web-Interface für Labornetzteil – Negative Spannung
Exakt wie das ursprüngliche Programm, nur mit Dash
"""

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
import spidev
import time
import lgpio
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask
import threading
import numpy as np

# ----------------- Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin
READ_ALL_AVAILABLE = -1

MAX_SPANNUNG_NEGATIV = -10  # minimaler Wert (negativ)
MAX_STROM_MA = 500.0       # Überstromschutz (mA)

# ----------------- Kalibrierdaten (Spannung <-> DAC) -----------------
kalibrier_tabelle = []  # Liste von (spannung_in_v, dac_wert)

# ----------------- Korrektur für MCC Strommessung -----------------
corr_a = -0.279388
corr_b = 1.782842

# ----------------- Hardware initialisieren -----------------
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, CS_PIN)
lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

# ----------------- Globale Variablen -----------------
monitoring_active = False
current_status = "System bereit"
current_voltage = 0.0
current_current = 0.0
status_log = []

# ----------------- DAC Funktionen -----------------
def write_dac(value):
    """Schreibt 12-bit Wert 0..4095 an DAC (MCP49xx-kompatibel)."""
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    control = 0b1011000000000000
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte  = data & 0xFF
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

# ----------------- Kalibrierung -----------------
def kalibrieren(sp_step=32, settle=0.05):
    """Kalibrierung wie im Original"""
    global kalibrier_tabelle, current_status
    kalibrier_tabelle.clear()
    current_status = "Kalibrierung läuft..."
    add_log("Starte Kalibrierung...")
    
    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)

    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert)
        time.sleep(settle)
        spannung = hat.a_in_read(0)
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, dac_wert))

    # DAC 4095 sicherstellen
    if not any(dac == 4095 for _, dac in kalibrier_tabelle):
        write_dac(4095)
        time.sleep(settle)
        spannung = hat.a_in_read(0)
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, 4095))

    write_dac(0)
    kalibrier_tabelle.sort(key=lambda x: x[0])
    current_status = f"Kalibriert ({len(kalibrier_tabelle)} Punkte)"
    add_log(f"Kalibrierung abgeschlossen: {len(kalibrier_tabelle)} Punkte")

def spannung_zu_dac_interpoliert(ziel_spannung):
    """Lineare Interpolation zwischen Kalibrierpunkten -> DAC-Wert (int)."""
    if not kalibrier_tabelle:
        raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
    if ziel_spannung > 0:
        raise ValueError("Nur negative Spannungen erlaubt.")
    
    if ziel_spannung <= kalibrier_tabelle[0][0]:
        return kalibrier_tabelle[0][1]
    if ziel_spannung >= kalibrier_tabelle[-1][0]:
        return kalibrier_tabelle[-1][1]
    
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i+1]
        if u1 <= ziel_spannung <= u2:
            if u2 == u1:
                return d1
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return int(round(dac))
    
    raise ValueError("Interpolation fehlgeschlagen.")

# ----------------- Stromkorrektur -----------------
def apply_strom_korrektur(i_mcc_mA):
    return corr_a + corr_b * i_mcc_mA

def kalibriere_stromkorrektur(mcc_list_mA, true_list_mA):
    global corr_a, corr_b
    mcc = np.array(mcc_list_mA, dtype=float)
    true = np.array(true_list_mA, dtype=float)
    A = np.vstack([np.ones_like(mcc), mcc]).T
    a, b = np.linalg.lstsq(A, true, rcond=None)[0]
    corr_a, corr_b = float(a), float(b)
    add_log(f"Stromkorrektur aktualisiert: a={corr_a:.6f}, b={corr_b:.9f}")

# ----------------- Stromüberwachung -----------------
def strom_ueberwachung(max_strom_ma=MAX_STROM_MA):
    global monitoring_active, current_status, current_current
    
    channels = [5]
    channel_mask = chan_list_to_mask(channels)
    num_channels = len(channels)
    scan_rate = 1000.0
    options = OptionFlags.CONTINUOUS

    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)
    hat.a_in_scan_start(channel_mask, 0, scan_rate, options)

    current_status = "Stromüberwachung aktiv"
    add_log("Stromüberwachung gestartet")

    try:
        while monitoring_active:
            read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.5)
            if len(read_result.data) >= num_channels:
                shunt_v = read_result.data[-1]
                current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA = apply_strom_korrektur(current_mcc_mA)
                current_current = current_true_mA

                if current_true_mA > max_strom_ma:
                    write_dac(0)
                    current_status = f"ÜBERSTROM: {current_true_mA:.1f} mA"
                    add_log(f"ÜBERSTROM ERKANNT: {current_true_mA:.1f} mA > {max_strom_ma:.1f} mA")
                    monitoring_active = False
                    break
            time.sleep(0.1)

    except Exception as e:
        current_status = f"Überwachung Fehler: {e}"
        add_log(f"Überwachung Fehler: {e}")

    finally:
        try:
            hat.a_in_scan_stop()
        except Exception:
            pass
        if monitoring_active:
            current_status = "Überwachung gestoppt"
            add_log("Überwachung gestoppt")
        monitoring_active = False

# ----------------- Hilfsfunktionen -----------------
def add_log(message):
    global status_log
    timestamp = time.strftime("%H:%M:%S")
    status_log.append(f"[{timestamp}] {message}")
    if len(status_log) > 10:  # Nur die letzten 10 Einträge behalten
        status_log = status_log[-10:]

def cleanup():
    global monitoring_active
    monitoring_active = False
    write_dac(0)
    spi.close()
    lgpio.gpiochip_close(gpio_handle)

# ----------------- Dash App -----------------
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("⚡ Labornetzteil Steuerung", style={'textAlign': 'center', 'color': '#2c3e50'}),
    html.H2("Negative Spannung (-10V bis 0V)", style={'textAlign': 'center', 'color': '#7f8c8d'}),
    
    # Status Anzeige
    html.Div([
        html.H3("📊 Status"),
        html.Div(id='status-display'),
    ], style={'border': '2px solid #3498db', 'padding': '15px', 'margin': '10px', 'borderRadius': '10px'}),
    
    # Kalibrierung
    html.Div([
        html.H3("🔧 Kalibrierung"),
        html.Button('Kalibrierung starten', id='cal-button', n_clicks=0, 
                   style={'padding': '10px', 'backgroundColor': '#f39c12', 'color': 'white', 'border': 'none', 'borderRadius': '5px'}),
        html.Div(id='cal-status')
    ], style={'border': '2px solid #f39c12', 'padding': '15px', 'margin': '10px', 'borderRadius': '10px'}),
    
    # Spannung einstellen
    html.Div([
        html.H3("⚡ Spannung einstellen"),
        dcc.Input(id='voltage-input', type='number', min=-10, max=0, step=0.001, value=0, 
                 placeholder='Spannung in V'),
        html.Button('Spannung setzen', id='set-voltage-button', n_clicks=0,
                   style={'padding': '10px', 'margin': '10px', 'backgroundColor': '#27ae60', 'color': 'white', 'border': 'none', 'borderRadius': '5px'}),
        html.Div(id='voltage-status')
    ], style={'border': '2px solid #27ae60', 'padding': '15px', 'margin': '10px', 'borderRadius': '10px'}),
    
    # Notaus
    html.Div([
        html.H3("🚨 Notaus"),
        html.Button('STOPP - Netzteil AUS', id='stop-button', n_clicks=0,
                   style={'padding': '15px', 'backgroundColor': '#e74c3c', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'fontSize': '16px', 'fontWeight': 'bold'})
    ], style={'border': '2px solid #e74c3c', 'padding': '15px', 'margin': '10px', 'borderRadius': '10px'}),
    
    # Stromkorrektur
    html.Div([
        html.H3("📈 Stromkorrektur"),
        html.P("Messwertpaare eingeben (eine Zeile pro Paar: mcc_mA true_mA):"),
        dcc.Textarea(id='correction-input', placeholder='6.0 0.328\n12.5 0.654\n18.2 0.982',
                    style={'width': '100%', 'height': '100px'}),
        html.Button('Korrektur berechnen', id='correction-button', n_clicks=0,
                   style={'padding': '10px', 'margin': '10px', 'backgroundColor': '#3498db', 'color': 'white', 'border': 'none', 'borderRadius': '5px'}),
        html.Div(id='correction-status')
    ], style={'border': '2px solid #3498db', 'padding': '15px', 'margin': '10px', 'borderRadius': '10px'}),
    
    # Log
    html.Div([
        html.H3("📋 Status Log"),
        html.Div(id='log-display', style={'height': '200px', 'overflow': 'auto', 'backgroundColor': '#2c3e50', 'color': '#2ecc71', 'fontFamily': 'monospace', 'padding': '10px', 'borderRadius': '5px'})
    ], style={'border': '2px solid #95a5a6', 'padding': '15px', 'margin': '10px', 'borderRadius': '10px'}),
    
    # Interval für Updates
    dcc.Interval(id='interval-component', interval=2000, n_intervals=0)  # Update alle 2 Sekunden
])

# ----------------- Callbacks -----------------
@app.callback(
    Output('status-display', 'children'),
    [Input('interval-component', 'n_intervals')]
)
def update_status(n):
    return html.Div([
        html.P(f"System: {current_status}"),
        html.P(f"Ausgangsspannung: {current_voltage:.3f} V"),
        html.P(f"Ausgangsstrom: {current_current:.2f} mA"),
        html.P(f"Kalibriert: {'Ja' if kalibrier_tabelle else 'Nein'} ({len(kalibrier_tabelle)} Punkte)"),
        html.P(f"Stromkorrektur: i_true = {corr_a:.6f} + {corr_b:.9f} * i_mcc"),
        html.P(f"Überwachung: {'Aktiv' if monitoring_active else 'Inaktiv'}")
    ])

@app.callback(
    Output('cal-status', 'children'),
    [Input('cal-button', 'n_clicks')]
)
def start_calibration(n_clicks):
    if n_clicks > 0:
        if not monitoring_active:
            threading.Thread(target=kalibrieren, daemon=True).start()
            return "Kalibrierung gestartet..."
        else:
            return "Kalibrierung nicht möglich - Überwachung aktiv"
    return ""

@app.callback(
    Output('voltage-status', 'children'),
    [Input('set-voltage-button', 'n_clicks')],
    [State('voltage-input', 'value')]
)
def set_voltage(n_clicks, voltage):
    global current_voltage, monitoring_active
    
    if n_clicks > 0 and voltage is not None:
        try:
            if voltage > 0 or voltage < MAX_SPANNUNG_NEGATIV:
                return f"Fehler: Spannung muss zwischen {MAX_SPANNUNG_NEGATIV} und 0 V liegen"
            
            if not kalibrier_tabelle:
                return "Fehler: Erst kalibrieren!"
            
            if monitoring_active:
                return "Fehler: Überwachung bereits aktiv - erst stoppen"
            
            dac = spannung_zu_dac_interpoliert(voltage)
            write_dac(dac)
            current_voltage = voltage
            add_log(f"Spannung gesetzt: {voltage:.3f} V (DAC: {dac})")
            
            # Stromüberwachung starten
            monitoring_active = True
            threading.Thread(target=strom_ueberwachung, daemon=True).start()
            
            return f"Spannung gesetzt: {voltage:.3f} V - Überwachung gestartet"
            
        except Exception as e:
            return f"Fehler: {e}"
    
    return ""

@app.callback(
    Output('log-display', 'children'),
    [Input('stop-button', 'n_clicks'), Input('interval-component', 'n_intervals')]
)
def update_log_and_stop(stop_clicks, n):
    global monitoring_active, current_voltage, current_current, current_status
    
    ctx = callback_context
    if ctx.triggered:
        prop_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if prop_id == 'stop-button' and stop_clicks > 0:
            monitoring_active = False
            write_dac(0)
            current_voltage = 0.0
            current_current = 0.0
            current_status = "Gestoppt - Netzteil AUS"
            add_log("NOTAUS aktiviert - System gestoppt")
    
    # Log anzeigen
    log_items = []
    for log_entry in status_log:
        log_items.append(html.Div(log_entry))
    
    return log_items

@app.callback(
    Output('correction-status', 'children'),
    [Input('correction-button', 'n_clicks')],
    [State('correction-input', 'value')]
)
def update_correction(n_clicks, input_text):
    if n_clicks > 0 and input_text:
        try:
            lines = [line.strip() for line in input_text.split('\n') if line.strip()]
            mcc_values = []
            true_values = []
            
            for line in lines:
                parts = line.split()
                if len(parts) == 2:
                    mcc_values.append(float(parts[0]))
                    true_values.append(float(parts[1]))
            
            if len(mcc_values) >= 2:
                kalibriere_stromkorrektur(mcc_values, true_values)
                return f"Korrektur aktualisiert: a={corr_a:.6f}, b={corr_b:.9f}"
            else:
                return "Fehler: Mindestens 2 Wertepaaare erforderlich"
                
        except Exception as e:
            return f"Fehler: {e}"
    
    return ""

# ----------------- Main -----------------
if __name__ == '__main__':
    # Automatische Kalibrierung beim Start
    add_log("System gestartet")
    add_log("Starte automatische Kalibrierung...")
    kalibrieren()
    
    print("Dash Server gestartet auf http://0.0.0.0:8050")
    
    try:
        app.run_server(host='0.0.0.0', port=8050, debug=False)
    except KeyboardInterrupt:
        cleanup()
