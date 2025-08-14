#!/usr/bin/env python3
"""
Kombiniertes Steuerprogramm für Labornetzteil (Positive & Negative Spannung)
- Web-Implementierung mit Dash
- Modus-Umschaltung zwischen Positiv und Negativ
- Getrennte, automatische Kalibrierung für jeden Modus
- Lineare Interpolation der Kalibrierpunkte
- Dauerhafte Stromüberwachung mit linearer Korrektur
- Überstromschutz
"""
import spidev
import time
import lgpio
import numpy as np
import dash
from dash import dcc, html, Input, Output, State, no_update
from daqhats import mcc118, HatIDs, HatError
from daqhats_utils import select_hat_device
from collections import deque

# ----------------- Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin
MAX_STROM_MA = 500.0        # Überstromschutz (mA)

# Spannungs-Grenzwerte
MAX_SPANNUNG_POSITIV = 10.0
MAX_SPANNUNG_NEGATIV = -10.0

# ----------------- Anfangswerte für Stromkorrektur -----------------
# Diese Werte werden in der App für den jeweiligen Modus geladen und können neu berechnet werden.
# I_true_mA = a + b * I_mcc_mA
INITIAL_CORR = {
    'plus': {'a': -0.134738, 'b': 0.078004},
    'minus': {'a': -0.279388, 'b': 1.782842}
}

# ----------------- Hardware initialisieren (einmalig beim Start) -----------------
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1000000
    spi.mode = 0b00

    gpio_handle = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(gpio_handle, CS_PIN)
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)
    print("Hardware erfolgreich initialisiert.")
except Exception as e:
    print(f"FEHLER bei der Hardware-Initialisierung: {e}")
    exit()

# ----------------- Kernfunktionen -----------------
def write_dac(value, mode):
    """Schreibt 12-bit Wert 0..4095 an den DAC, abhängig vom Modus."""
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    
    # Steuerbits je nach Modus anpassen
    if mode == 'plus':
        control = 0b0011000000000000  # Für positive Spannung
    elif mode == 'minus':
        control = 0b1011000000000000  # Für negative Spannung
    else:
        raise ValueError("Ungültiger Modus für write_dac")

    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte  = data & 0xFF
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)

def do_calibration(sp_step, settle, mode):
    """Führt Kalibrierung durch und gibt Log und Tabelle zurück."""
    log_output = f"Starte Kalibrierung ({mode.capitalize()}e Spannung)...\n"
    kalibrier_tabelle = []
    
    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert, mode)
        time.sleep(settle)
        spannung = hat.a_in_read(0)
        log_line = f"  DAC {dac_wert:4d} -> {spannung:8.5f} V"

        # Nur relevante Spannungen speichern
        if (mode == 'plus' and spannung >= 0) or (mode == 'minus' and spannung <= 0):
            kalibrier_tabelle.append((spannung, dac_wert))
            log_output += log_line + "\n"
        else:
            log_output += log_line + " (ignoriert)\n"
    
    write_dac(4095, mode)
    time.sleep(settle)
    spannung = hat.a_in_read(0)
    log_line = f"  DAC 4095 -> {spannung:8.5f} V"
    if (mode == 'plus' and spannung >= 0) or (mode == 'minus' and spannung <= 0):
        kalibrier_tabelle.append((spannung, 4095))
        log_output += log_line + "\n"
    
    write_dac(0, mode) # Sicher zurücksetzen
    kalibrier_tabelle.sort(key=lambda x: x[0])
    log_output += f"Kalibrierung abgeschlossen. {len(kalibrier_tabelle)} Punkte gespeichert.\n"
    return log_output, kalibrier_tabelle

def spannung_zu_dac_interpoliert(ziel_spannung, kalibrier_tabelle):
    """Lineare Interpolation -> DAC-Wert (int)."""
    if not kalibrier_tabelle:
        raise RuntimeError("Keine Kalibrierdaten vorhanden.")
    
    spannungen = np.array([p[0] for p in kalibrier_tabelle])
    dac_werte = np.array([p[1] for p in kalibrier_tabelle])
    interpolated_dac = np.interp(ziel_spannung, spannungen, dac_werte)
    return int(round(interpolated_dac))

def kalibriere_stromkorrektur(mcc_list_mA, true_list_mA):
    """Berechnet lineare Korrekturfaktoren a und b."""
    mcc = np.array(mcc_list_mA, dtype=float)
    true = np.array(true_list_mA, dtype=float)
    A = np.vstack([np.ones_like(mcc), mcc]).T
    try:
        a, b = np.linalg.lstsq(A, true, rcond=None)[0]
        return float(a), float(b)
    except np.linalg.LinAlgError:
        return None, None

def cleanup():
    print("\nAufräumen...")
    try:
        write_dac(0, 'plus')
        write_dac(0, 'minus')
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
        print("Hardware erfolgreich zurückgesetzt.")
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")

# ----------------- Dash App Initialisierung -----------------
app = dash.Dash(__name__)
app.title = "Labornetzteil Steuerung"
MAX_GRAPH_POINTS = 100
time_deque = deque(maxlen=MAX_GRAPH_POINTS)
current_deque = deque(maxlen=MAX_GRAPH_POINTS)

# ----------------- App Layout -----------------
app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '1000px', 'margin': 'auto', 'padding': '20px'}, children=[
    html.H1("Labornetzteil Steuerung"),
    
    # Stores zum Speichern der Zustände
    dcc.Store(id='kalibrier-tabelle-plus-store'),
    dcc.Store(id='kalibrier-tabelle-minus-store'),
    dcc.Store(id='korrektur-faktoren-plus-store', data=INITIAL_CORR['plus']),
    dcc.Store(id='korrektur-faktoren-minus-store', data=INITIAL_CORR['minus']),

    dcc.Interval(id='strom-mess-interval', interval=500, n_intervals=0, disabled=True),
    
    html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px', 'background': '#eef'}, children=[
        html.H2("Modus auswählen"),
        dcc.RadioItems(
            id='modus-selector',
            options=[
                {'label': 'Positive Spannung', 'value': 'plus'},
                {'label': 'Negative Spannung', 'value': 'minus'},
            ],
            value='plus',
            labelStyle={'display': 'inline-block', 'margin-right': '20px'}
        ),
    ]),
    
    html.Div(id='main-content'), # Der Inhalt wird dynamisch je nach Modus geladen
])

# ----------------- Callbacks -----------------

@app.callback(
    Output('main-content', 'children'),
    Input('modus-selector', 'value')
)
def render_main_content(mode):
    """Erstellt die Benutzeroberfläche dynamisch basierend auf dem Modus."""
    if mode == 'plus':
        max_val, min_val, step, marks = MAX_SPANNUNG_POSITIV, 0, 0.01, {i: f'{i}V' for i in range(0, int(MAX_SPANNUNG_POSITIV) + 1, 2)}
    else: # minus
        max_val, min_val, step, marks = 0, MAX_SPANNUNG_NEGATIV, -0.01, {i: f'{i}V' for i in range(int(MAX_SPANNUNG_NEGATIV), 1, 2)}

    # UI-Layout ist für beide Modi strukturell gleich, nur die Werte ändern sich
    return html.Div([
        # Sektion 1: Kalibrierung
        html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
            html.H2(f"1. Kalibrierung ({mode.capitalize()}e Spannung)"),
            html.Button("Kalibrierung starten", id="start-kalibrierung-btn", n_clicks=0),
            dcc.Loading(id="loading-kalibrierung", children=[html.Pre(id="kalibrierung-output")])
        ]),
        
        # Sektion 2: Spannung einstellen
        html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
            html.H2("2. Spannung einstellen"),
            dcc.Slider(id='spannung-slider', min=min_val, max=max_val, step=0.01, value=0, marks=marks),
            dcc.Input(id='spannung-input', type='number', min=min_val, max=max_val, step=0.01, value=0, style={'marginLeft': '20px'}),
            html.Div(id='spannung-status', style={'marginTop': '10px', 'fontWeight': 'bold'}),
        ]),
        
        # Sektion 3: Live-Überwachung
        html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '20px'}, children=[
            html.H2("3. Live-Überwachung"),
            html.Div(id='overcurrent-warning', style={'display': 'none'}),
            html.Table([
                html.Tr([html.Th("Shunt-Spannung (V)"), html.Th("MCC Strom (mA)"), html.Th("Korrigierter Strom (mA)")]),
                html.Tr([html.Td(id='shunt-v-display'), html.Td(id='mcc-ma-display'), html.Td(id='true-ma-display')], style={'fontSize': '1.5em'})
            ], style={'width': '100%', 'textAlign': 'center'}),
            dcc.Graph(id='strom-graph')
        ]),

        # Sektion 4: Stromkorrektur
        html.Div(className="card", style={'border': '1px solid #ddd', 'padding': '15px', 'borderRadius': '5px'}, children=[
            html.H2("4. Stromkorrektur anpassen"),
            html.P(id='current-corr-factors-display'),
            dcc.Textarea(id='korrektur-input', placeholder="Ein Messwertpaar pro Zeile, z.B.: 6.0 0.328", style={'width': '100%', 'height': 80}),
            html.Button("Neue Faktoren berechnen", id="berechne-korrektur-btn", style={'marginTop': '10px'}),
            html.Div(id="korrektur-output", style={'marginTop': '10px', 'fontWeight': 'bold'})
        ])
    ])

# Callbacks zur Synchronisierung von Slider und Input
@app.callback(Output('spannung-slider', 'value'), Input('spannung-input', 'value'), prevent_initial_call=True)
def update_slider_from_input(value): return value
@app.callback(Output('spannung-input', 'value'), Input('spannung-slider', 'value'), prevent_initial_call=True)
def update_input_from_slider(value): return value


@app.callback(
    Output('kalibrierung-output', 'children'),
    Output('kalibrier-tabelle-plus-store', 'data', allow_duplicate=True),
    Output('kalibrier-tabelle-minus-store', 'data', allow_duplicate=True),
    Input('start-kalibrierung-btn', 'n_clicks'),
    State('modus-selector', 'value'),
    prevent_initial_call=True
)
def update_kalibrierung(n_clicks, mode):
    log, tabelle = do_calibration(sp_step=32, settle=0.05, mode=mode)
    if mode == 'plus':
        return log, tabelle, no_update
    else: # minus
        return log, no_update, tabelle

@app.callback(
    Output('spannung-status', 'children'),
    Output('strom-mess-interval', 'disabled'),
    Input('spannung-input', 'value'),
    State('modus-selector', 'value'),
    State('kalibrier-tabelle-plus-store', 'data'),
    State('kalibrier-tabelle-minus-store', 'data')
)
def set_voltage(ziel_spannung, mode, tabelle_plus, tabelle_minus):
    tabelle = tabelle_plus if mode == 'plus' else tabelle_minus
    if not tabelle:
        return "Bitte zuerst diesen Modus kalibrieren.", True
    
    try:
        dac_wert = spannung_zu_dac_interpoliert(float(ziel_spannung), tabelle)
        write_dac(dac_wert, mode)
        is_disabled = float(ziel_spannung) == 0
        status_msg = f"Spannung auf {ziel_spannung:.3f} V gesetzt." if not is_disabled else "Spannung auf 0V gesetzt. Überwachung gestoppt."
        return status_msg, is_disabled
    except (ValueError, RuntimeError) as e:
        return f"Fehler: {e}", True

@app.callback(
    Output('shunt-v-display', 'children'),
    Output('mcc-ma-display', 'children'),
    Output('true-ma-display', 'children'),
    Output('overcurrent-warning', 'children'),
    Output('overcurrent-warning', 'style'),
    Output('strom-mess-interval', 'disabled', allow_duplicate=True),
    Output('strom-graph', 'figure'),
    Input('strom-mess-interval', 'n_intervals'),
    State('modus-selector', 'value'),
    State('korrektur-faktoren-plus-store', 'data'),
    State('korrektur-faktoren-minus-store', 'data'),
    prevent_initial_call=True
)
def update_strom_messung(n, mode, corr_plus, corr_minus):
    global time_deque, current_deque
    corr_factors = corr_plus if mode == 'plus' else corr_minus
    
    try:
        shunt_v = hat.a_in_read(4) # Strom wird immer über Channel 4 gemessen
        divisor = VERSTAERKUNG * SHUNT_WIDERSTAND
        current_mcc_mA = (shunt_v / divisor) * 1000.0 if divisor != 0 else 0
        current_true_mA = corr_factors['a'] + corr_factors['b'] * current_mcc_mA

        warning_text, warning_style, disable_interval = "", {'display': 'none'}, False
        if current_true_mA > MAX_STROM_MA:
            write_dac(0, mode) # DAC für den aktuellen Modus auf 0 setzen
            warning_text = f"⚠️ ÜBERSTROM: {current_true_mA:.1f} mA! DAC auf 0 gesetzt."
            warning_style = {'color': 'white', 'background': 'red', 'padding': '10px', 'fontWeight': 'bold', 'display': 'block'}
            disable_interval = True
        
        time_deque.append(time.time())
        current_deque.append(current_true_mA)
        graph_fig = {'data': [{'x': list(time_deque), 'y': list(current_deque), 'mode': 'lines'}],
                     'layout': {'yaxis': {'title': 'Strom (mA)'}, 'uirevision': 'dont_reset_zoom'}}
        
        return (f"{shunt_v:7.4f}", f"{current_mcc_mA:7.2f}", f"{current_true_mA:7.2f}", 
                warning_text, warning_style, disable_interval, graph_fig)
    except HatError as e:
        return "HAT Error", "HAT Error", "HAT Error", f"HAT Error: {e}", {'display': 'block'}, True, no_update

@app.callback(
    Output('korrektur-output', 'children'),
    Output('korrektur-faktoren-plus-store', 'data', allow_duplicate=True),
    Output('korrektur-faktoren-minus-store', 'data', allow_duplicate=True),
    Output('current-corr-factors-display', 'children'),
    Input('berechne-korrektur-btn', 'n_clicks'),
    Input('modus-selector', 'value'), # Auch bei Modus-Wechsel aktualisieren
    State('korrektur-input', 'value'),
    State('korrektur-faktoren-plus-store', 'data'),
    State('korrektur-faktoren-minus-store', 'data'),
    prevent_initial_call=True
)
def update_strom_korrektur(n_clicks, mode, text_data, corr_plus, corr_minus):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    corr_factors = corr_plus if mode == 'plus' else corr_minus
    display_text = f"Aktuelle Faktoren (a, b): {corr_factors['a']:.6f}, {corr_factors['b']:.6f}"

    if triggered_id != 'berechne-korrektur-btn':
        return no_update, no_update, no_update, display_text

    if not text_data:
        return "Bitte Messwerte eingeben.", no_update, no_update, display_text

    mccs, trues = [], []
    for line in text_data.strip().split('\n'):
        try:
            mcc_val, true_val = map(float, line.replace(',', ' ').split())
            mccs.append(mcc_val)
            trues.append(true_val)
        except (ValueError, IndexError):
            return f"Ungültige Zeile: '{line}'", no_update, no_update, display_text
    
    if len(mccs) < 2:
        return "Mindestens 2 Datenpunkte erforderlich.", no_update, no_update, display_text
    
    new_a, new_b = kalibriere_stromkorrektur(mccs, trues)
    if new_a is not None:
        new_corr = {'a': new_a, 'b': new_b}
        msg = f"Neue Faktoren gesetzt: a={new_a:.6f}, b={new_b:.9f}"
        display_text = f"Aktuelle Faktoren (a, b): {new_a:.6f}, {new_b:.6f}"
        if mode == 'plus':
            return msg, new_corr, no_update, display_text
        else: # minus
            return msg, no_update, new_corr, display_text
    else:
        return "Fehler bei der Berechnung.", no_update, no_update, display_text


# ----------------- Hauptprogramm -----------------
if __name__ == "__main__":
    try:
        app.run(host='0.0.0.0', port=8070, debug=False)
    finally:
        cleanup()