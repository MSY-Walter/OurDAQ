#!/usr/bin/env python3
"""
Steuerprogramm für Labornetzteil – Negative Spannung
Reduzierte Web-Implementierung mit Dash (nur Kalibrierung und Spannungseinstellung)
"""

import spidev
import time
import lgpio
import numpy as np
import dash
from dash import dcc, html, Input, Output, State

from daqhats import mcc118, HatIDs
from daqhats_utils import select_hat_device

# ----------------- Konstanten -----------------
CS_PIN = 27                 # Chip Select Pin
MAX_SPANNUNG_NEGATIV = -10  # minimaler Wert (negativ)

# ----------------- Hardware initialisieren (einmalig beim Start) -----------------
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1000000
    spi.mode = 0b00

    gpio_handle = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(gpio_handle, CS_PIN)
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

    # MCC118 initialisieren
    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)
    print("Hardware erfolgreich initialisiert.")
except Exception as e:
    print(f"FEHLER bei der Hardware-Initialisierung: {e}")
    print("Stellen Sie sicher, dass die SPI- und GPIO-Schnittstellen aktiv sind und die Hardware korrekt angeschlossen ist.")
    exit()

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

# ----------------- Kalibrierung & Interpolation -----------------
def do_calibration(sp_step, settle):
    """Führt Kalibrierung durch und gibt Log und Tabelle zurück."""
    log_output = "Starte Kalibrierung (Negative Spannung)...\n"
    kalibrier_tabelle = []
    
    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert)
        time.sleep(settle)
        spannung = hat.a_in_read(0) # Channel 0 misst Ausgangsspannung
        
        log_line = f"  DAC {dac_wert:4d} -> {spannung:8.5f} V"
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, dac_wert))
            log_output += log_line + "\n"
        else:
            log_output += log_line + " (nicht negativ, ignoriert)\n"

    # Sicherstellen, dass DAC 4095 auch dabei ist
    write_dac(4095)
    time.sleep(settle)
    spannung = hat.a_in_read(0)
    log_line = f"  DAC 4095 -> {spannung:8.5f} V"
    if spannung <= 0:
        kalibrier_tabelle.append((spannung, 4095))
        log_output += log_line + "\n"
    else:
        log_output += log_line + " (nicht negativ, ignoriert)\n"

    write_dac(0)
    kalibrier_tabelle.sort(key=lambda x: x[0])
    log_output += f"Kalibrierung abgeschlossen. {len(kalibrier_tabelle)} negative Punkte gespeichert.\n"
    return log_output, kalibrier_tabelle

def spannung_zu_dac_interpoliert(ziel_spannung, kalibrier_tabelle):
    """Lineare Interpolation -> DAC-Wert (int)."""
    if not kalibrier_tabelle:
        raise RuntimeError("Keine Kalibrierdaten vorhanden.")
    if ziel_spannung > 0:
        raise ValueError("Nur negative Spannungen erlaubt.")
    
    spannungen = np.array([p[0] for p in kalibrier_tabelle])
    dac_werte = np.array([p[1] for p in kalibrier_tabelle])

    interpolated_dac = np.interp(ziel_spannung, spannungen, dac_werte)
    return int(round(interpolated_dac))

# ----------------- Aufräumen -----------------
def cleanup():
    print("\nAufräumen...")
    try:
        write_dac(0)
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
        print("Hardware erfolgreich zurückgesetzt.")
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")

# ----------------- Dash App Initialisierung -----------------
app = dash.Dash(__name__)
app.title = "Labornetzteil Steuerung"

# ----------------- App Layout -----------------
app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '800px', 'margin': 'auto', 'padding': '20px'}, children=[
    html.H1("Labornetzteil Steuerung (Negative Spannung)"),
    
    # Store-Komponente zum Speichern von Daten im Browser
    dcc.Store(id='kalibrier-tabelle-store'),
    
    # Sektion 1: Kalibrierung
    html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
        html.H2("1. Kalibrierung"),
        html.Button("Automatische Kalibrierung starten", id="start-kalibrierung-btn", n_clicks=0),
        dcc.Loading(id="loading-kalibrierung", type="default", children=[
            html.Pre(id="kalibrierung-output", style={'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all', 'background': '#f4f4f4', 'padding': '10px', 'marginTop': '10px', 'maxHeight': '200px', 'overflowY': 'auto'})
        ])
    ]),
    
    # Sektion 2: Spannungsregelung
    html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
        html.H2("2. Spannung einstellen"),
        html.P("Stellen Sie die gewünschte negative Spannung ein (nur nach erfolgreicher Kalibrierung möglich)."),
        dcc.Slider(id='spannung-slider', min=MAX_SPANNUNG_NEGATIV, max=0, step=0.01, value=0, marks={i: f'{i}V' for i in range(int(MAX_SPANNUNG_NEGATIV), 1, 2)}),
        dcc.Input(id='spannung-input', type='number', min=MAX_SPANNUNG_NEGATIV, max=0, step=0.01, value=0, style={'marginLeft': '20px', 'width': '100px'}),
        html.Div(id='spannung-status', style={'marginTop': '10px', 'fontWeight': 'bold'}),
    ]),
])

# ----------------- Callbacks (Interaktivität) -----------------

# Callback 1: Kalibrierung durchführen
@app.callback(
    Output('kalibrierung-output', 'children'),
    Output('kalibrier-tabelle-store', 'data'),
    Input('start-kalibrierung-btn', 'n_clicks'),
    prevent_initial_call=True
)
def update_kalibrierung(n_clicks):
    log, tabelle = do_calibration(sp_step=32, settle=0.05)
    return log, tabelle

# Callback 2 & 3: Spannungseingabe und Slider synchronisieren
@app.callback(
    Output('spannung-slider', 'value'),
    Input('spannung-input', 'value')
)
def update_slider(value):
    return value

@app.callback(
    Output('spannung-input', 'value'),
    Input('spannung-slider', 'value')
)
def update_input(value):
    return value

# Callback 4: Spannung setzen
@app.callback(
    Output('spannung-status', 'children'),
    Input('spannung-input', 'value'),
    State('kalibrier-tabelle-store', 'data')
)
def set_voltage(ziel_spannung, kalibrier_tabelle):
    ctx = dash.callback_context
    if not ctx.triggered:
        return "Bitte zuerst kalibrieren und dann Spannung einstellen."
    
    if not kalibrier_tabelle:
        return "FEHLER: Bitte zuerst Kalibrierung durchführen."

    try:
        dac_wert = spannung_zu_dac_interpoliert(float(ziel_spannung), kalibrier_tabelle)
        write_dac(dac_wert)
        status_msg = f"Spannung auf {ziel_spannung:.3f} V gesetzt (DAC={dac_wert})."
    except (ValueError, RuntimeError) as e:
        status_msg = f"Fehler: {e}"

    return status_msg

# ----------------- Hauptprogramm -----------------
if __name__ == "__main__":
    try:
        # Starte den Dash-Server auf Port 8072 und mache ihn im Netzwerk sichtbar
        app.run(host='0.0.0.0', port=8072, debug=False)
    finally:
        # Diese Funktion wird aufgerufen, wenn der Server beendet wird (z.B. mit Strg+C)
        cleanup()