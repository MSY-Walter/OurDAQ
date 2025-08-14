#!/usr/bin/env python3
"""
Steuerprogramm für Labornetzteil – Negative Spannung
Web-Implementierung mit Dash auf Port 8070
"""

import spidev
import time
import lgpio
import numpy as np
import dash
from dash import dcc, html, Input, Output, State, no_update
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask
from collections import deque

# ----------------- Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin
MAX_SPANNUNG_NEGATIV = -10  # minimaler Wert (negativ)
MAX_STROM_MA = 500.0        # Überstromschutz (mA)

# ----------------- Globale Korrekturvariablen (werden durch UI aktualisiert) -----------------
# Diese müssen global bleiben, damit der schnelle Interval-Callback darauf zugreifen kann
corr_a = -0.279388
corr_b = 1.782842

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
    # Beenden, wenn die Hardware nicht initialisiert werden kann
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
        spannung = hat.a_in_read(0)
        
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
    
    # Konvertiere zu numpy arrays für effizientere Suche
    spannungen = np.array([p[0] for p in kalibrier_tabelle])
    dac_werte = np.array([p[1] for p in kalibrier_tabelle])

    # np.interp ist perfekt für diese Aufgabe
    # Wichtig: np.interp erwartet x-Werte (Spannungen) in aufsteigender Reihenfolge
    # Da unsere Spannungen negativ sind (z.B. -10, -9, ...), sind sie bereits sortiert.
    interpolated_dac = np.interp(ziel_spannung, spannungen, dac_werte)
    return int(round(interpolated_dac))

# ----------------- Stromkorrektur -----------------
def kalibriere_stromkorrektur(mcc_list_mA, true_list_mA):
    mcc = np.array(mcc_list_mA, dtype=float)
    true = np.array(true_list_mA, dtype=float)
    A = np.vstack([np.ones_like(mcc), mcc]).T
    try:
        a, b = np.linalg.lstsq(A, true, rcond=None)[0]
        return float(a), float(b)
    except np.linalg.LinAlgError:
        return None, None

def apply_strom_korrektur(i_mcc_mA):
    return corr_a + corr_b * i_mcc_mA

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

# Deques für die Graphen-Daten (schnelles Anfügen/Entfernen)
MAX_GRAPH_POINTS = 100
time_deque = deque(maxlen=MAX_GRAPH_POINTS)
current_deque = deque(maxlen=MAX_GRAPH_POINTS)


# ----------------- App Layout -----------------
app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '1000px', 'margin': 'auto', 'padding': '20px'}, children=[
    html.H1("Labornetzteil Steuerung (Negative Spannung)"),
    
    # Store-Komponenten zum Speichern von Daten im Browser
    dcc.Store(id='kalibrier-tabelle-store'),
    dcc.Store(id='korrektur-faktoren-store', data={'a': corr_a, 'b': corr_b}),
    
    # Interval für kontinuierliche Strommessung
    dcc.Interval(id='strom-mess-interval', interval=500, n_intervals=0, disabled=True), # Startet deaktiviert
    
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
        html.P("Stellen Sie die gewünschte negative Spannung ein. Die Stromüberwachung wird automatisch gestartet."),
        dcc.Slider(id='spannung-slider', min=MAX_SPANNUNG_NEGATIV, max=0, step=0.01, value=0, marks={i: f'{i}V' for i in range(int(MAX_SPANNUNG_NEGATIV), 1, 2)}),
        dcc.Input(id='spannung-input', type='number', min=MAX_SPANNUNG_NEGATIV, max=0, step=0.01, value=0, style={'marginLeft': '20px', 'width': '100px'}),
        html.Div(id='spannung-status', style={'marginTop': '10px', 'fontWeight': 'bold'}),
    ]),
    
    # Sektion 3: Live-Überwachung
    html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
        html.H2("3. Live-Überwachung"),
        html.Div(id='overcurrent-warning', style={'color': 'white', 'background': 'red', 'padding': '10px', 'fontWeight': 'bold', 'textAlign': 'center', 'display': 'none', 'marginBottom': '10px'}),
        html.Table([
            html.Tr([html.Th("Shunt-Spannung (V)"), html.Th("MCC Strom (mA)"), html.Th("Korrigierter Strom (mA)")]),
            html.Tr([html.Td(id='shunt-v-display', style={'textAlign':'center'}), html.Td(id='mcc-ma-display', style={'textAlign':'center'}), html.Td(id='true-ma-display', style={'textAlign':'center'})], style={'fontSize': '1.5em', 'fontWeight': 'bold'})
        ], style={'width': '100%'}),
        dcc.Graph(id='strom-graph')
    ]),

    # Sektion 4: Stromkorrektur
    html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px'}, children=[
        html.H2("4. Stromkorrektur anpassen"),
        html.P("Geben Sie Messwertpaare ein (ein Paar pro Zeile), getrennt durch Leerzeichen oder Komma. Beispiel: 6.0 0.328"),
        dcc.Textarea(id='korrektur-input', style={'width': '100%', 'height': 100, 'marginBottom': '10px'}),
        html.Button("Neue Korrekturfaktoren berechnen", id="berechne-korrektur-btn"),
        html.Div(id="korrektur-output", style={'marginTop': '10px', 'fontWeight': 'bold'})
    ])
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

# Callback 4: Spannung setzen und Überwachung (de-)aktivieren
@app.callback(
    Output('spannung-status', 'children'),
    Output('strom-mess-interval', 'disabled'),
    Input('spannung-input', 'value'),
    State('kalibrier-tabelle-store', 'data')
)
def set_voltage(ziel_spannung, kalibrier_tabelle):
    ctx = dash.callback_context
    if not ctx.triggered or not kalibrier_tabelle:
        is_disabled = True # Interval deaktiviert lassen
        status_msg = "Bitte zuerst kalibrieren." if not kalibrier_tabelle else "Spannung einstellen, um Überwachung zu starten."
        return status_msg, is_disabled

    try:
        dac_wert = spannung_zu_dac_interpoliert(float(ziel_spannung), kalibrier_tabelle)
        write_dac(dac_wert)
        status_msg = f"Spannung auf {ziel_spannung:.3f} V gesetzt (DAC={dac_wert}). Überwachung aktiv."
        # Aktiviere das Interval, wenn eine Spannung eingestellt wird
        is_disabled = False 
        
        # Wenn Spannung 0V ist, Überwachung deaktivieren
        if float(ziel_spannung) == 0:
            is_disabled = True
            status_msg = "Spannung auf 0V gesetzt. Überwachung gestoppt."

    except (ValueError, RuntimeError) as e:
        status_msg = f"Fehler: {e}"
        is_disabled = True

    return status_msg, is_disabled

# Callback 5: Kontinuierliche Strommessung (durch dcc.Interval getriggert)
@app.callback(
    Output('shunt-v-display', 'children'),
    Output('mcc-ma-display', 'children'),
    Output('true-ma-display', 'children'),
    Output('overcurrent-warning', 'children'),
    Output('overcurrent-warning', 'style'),
    Output('strom-mess-interval', 'disabled', allow_duplicate=True),
    Output('strom-graph', 'figure'),
    Input('strom-mess-interval', 'n_intervals'),
    prevent_initial_call=True
)
def update_strom_messung(n):
    global time_deque, current_deque
    
    try:
        # Kanal 4 ist laut Originalskript für die Strommessung
        shunt_v = hat.a_in_read(4) 
        
        # Vermeide Division durch Null, falls Widerstand/Verstärkung 0 ist
        divisor = VERSTAERKUNG * SHUNT_WIDERSTAND
        if divisor == 0:
            return "Error", "Error", "Error", no_update, no_update, True, no_update

        current_mcc_mA = (shunt_v / divisor) * 1000.0
        current_true_mA = apply_strom_korrektur(current_mcc_mA)

        # Überstromprüfung
        if current_true_mA > MAX_STROM_MA:
            write_dac(0)
            warning_text = f"⚠️ ÜBERSTROM: {current_true_mA:.1f} mA > {MAX_STROM_MA:.1f} mA! DAC auf 0 gesetzt."
            warning_style = {'color': 'white', 'background': 'red', 'padding': '10px', 'fontWeight': 'bold', 'textAlign': 'center', 'display': 'block', 'marginBottom': '10px'}
            disable_interval = True # Stoppt weitere Messungen
        else:
            warning_text = ""
            warning_style = {'display': 'none'}
            disable_interval = False
        
        # Graphen-Daten aktualisieren
        time_deque.append(time.time())
        current_deque.append(current_true_mA)

        graph_fig = {
            'data': [{
                'x': list(time_deque),
                'y': list(current_deque),
                'mode': 'lines',
                'name': 'Korrigierter Strom'
            }],
            'layout': {
                'title': 'Stromverlauf',
                'xaxis': {'title': 'Zeit'},
                'yaxis': {'title': 'Strom (mA)', 'range': [min(current_deque)-10 if current_deque else -10, max(current_deque)+10 if current_deque else 10]},
                'margin': {'l': 50, 'r': 10, 't': 40, 'b': 40},
                'uirevision': 'dont_reset_zoom' # Behält Zoom/Pan bei Updates
            }
        }
        
        return (f"{shunt_v:7.4f}", 
                f"{current_mcc_mA:7.2f}", 
                f"{current_true_mA:7.2f}", 
                warning_text, 
                warning_style, 
                disable_interval,
                graph_fig)

    except HatError as e:
        # Fehler bei der Kommunikation mit dem HAT
        return "HAT Error", "HAT Error", "HAT Error", f"HAT Error: {e}", {'display': 'block'}, True, no_update

# Callback 6: Stromkorrektur berechnen und anwenden
@app.callback(
    Output('korrektur-output', 'children'),
    Input('berechne-korrektur-btn', 'n_clicks'),
    State('korrektur-input', 'value'),
    prevent_initial_call=True
)
def update_strom_korrektur(n_clicks, text_data):
    global corr_a, corr_b
    if not text_data:
        return "Bitte geben Sie Messwerte ein."

    mccs, trues = [], []
    lines = text_data.strip().split('\n')
    for line in lines:
        try:
            # Erlaubt Komma oder Leerzeichen als Trennzeichen
            parts = line.replace(',', ' ').split()
            if len(parts) == 2:
                mcc_val, true_val = map(float, parts)
                mccs.append(mcc_val)
                trues.append(true_val)
        except ValueError:
            return f"Ungültige Zeile gefunden: '{line}'. Bitte Format 'mcc_mA true_mA' verwenden."
    
    if len(mccs) < 2:
        return "Mindestens 2 Datenpunkte erforderlich."
    
    new_a, new_b = kalibriere_stromkorrektur(mccs, trues)
    if new_a is not None and new_b is not None:
        corr_a, corr_b = new_a, new_b
        return f"Neue Korrekturfaktoren gesetzt: a = {corr_a:.6f}, b = {corr_b:.9f}"
    else:
        return "Fehler bei der Berechnung. Stellen Sie sicher, dass die Datenpunkte nicht kollinear sind."


# ----------------- Hauptprogramm -----------------
if __name__ == "__main__":
    try:
        # Starte den Dash-Server auf Port 8070 und mache ihn im Netzwerk sichtbar
        app.run_server(host='0.0.0.0', port=8070, debug=False)
    finally:
        # Diese Funktion wird aufgerufen, wenn der Server beendet wird (z.B. mit Strg+C)
        cleanup()