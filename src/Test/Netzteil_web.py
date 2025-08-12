Ja, selbstverständlich. Die Anwendung kann auch ohne `dash-bootstrap-components` erstellt werden, indem stattdessen Standard-HTML-Komponenten (`dash.html`) und Inline-CSS für das Styling verwendet werden.

Der funktionale Kern der Anwendung und die Logik der Callbacks bleiben identisch. Lediglich das Layout wird neu aufgebaut, was zu einem schlichteren, aber genauso funktionalen Design führt.

### Code ohne `dash-bootstrap-components`

Hier ist die angepasste Version des Skripts. Sie können es auf dieselbe Weise wie die vorherige Version ausführen (`sudo python3 netzteil_web_app_no_bootstrap.py`).

**Änderungen:**

  * Alle `dbc.*` Komponenten wurden durch `html.*` oder `dcc.*` Äquivalente ersetzt.
  * Das Layout (z.B. Spalten) und das Design (z.B. Farben, Abstände) werden nun durch `style`-Attribute direkt im Code definiert.
  * Die Abhängigkeit von `dash-bootstrap-components` wurde entfernt. Sie müssen es also nicht installieren.

<!-- end list -->

```python
#!/usr/bin/env python3
"""
Web-Anwendung für Labornetzteil (ohne Bootstrap-Komponenten)
- Steuerung via Webbrowser mit Python Dash
- Kombiniert Funktionalität für positive und negative Spannung
- Automatische Kalibrierung und Interpolation
- Kontinuierliche Stromüberwachung mit Korrektur
- Überstromschutz und Not-Aus
"""

import spidev
import time
import lgpio
import atexit
import socket
import numpy as np
from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go

# ----------------- Globale Konstanten und Konfiguration -----------------
# Hardware-Konstanten
CS_PIN = 22 #
SHUNT_WIDERSTAND = 0.1 #
VERSTAERKUNG = 69.0 #
READ_ALL_AVAILABLE = -1 #

# Anwendungs-Konstanten
MAX_STROM_MA = 500.0 #
MAX_SPANNUNG_NEGATIV = -10.0 #
MAX_SPANNUNG_POSITIV = 10.75

# Korrekturwerte für die Strommessung [Offset (a), Gain (b)]
# I_true = a + b * I_mcc
strom_korrektur_params = {
    'positiv': {'a': -0.134738, 'b': 0.078004}, #
    'negativ': {'a': -0.279388, 'b': 1.782842}  #
}

# ----------------- Hardware Initialisierung -----------------
spi = spidev.SpiDev() #
spi.open(0, 0) #
spi.max_speed_hz = 1000000 #
spi.mode = 0b00 #

gpio_handle = lgpio.gpiochip_open(0) #
lgpio.gpio_claim_output(gpio_handle, CS_PIN) #
lgpio.gpio_write(gpio_handle, CS_PIN, 1) #

try:
    hat_address = select_hat_device(HatIDs.MCC_118) #
    hat = mcc118(hat_address) #
except HatError as e:
    print(f"Fehler bei der Initialisierung des MCC 118 HAT: {e}")
    hat = None

# ----------------- DAC- und Kalibrierungsfunktionen -----------------
def write_dac(value, mode='positiv'):
    """Schreibt einen 12-Bit-Wert (0-4095) an den DAC. Der Modus bestimmt das Kontroll-Byte."""
    if not (0 <= value <= 4095): #
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    
    if mode == 'positiv':
        control = 0b0011000000000000 #
    else: # negativ
        control = 0b1011000000000000 #
        
    data = control | (value & 0xFFF) #
    high_byte = (data >> 8) & 0xFF #
    low_byte  = data & 0xFF #
    
    lgpio.gpio_write(gpio_handle, CS_PIN, 0) #
    spi.xfer2([high_byte, low_byte]) #
    lgpio.gpio_write(gpio_handle, CS_PIN, 1) #

def kalibrieren(mode, sp_step=32, settle=0.05): #
    """Führt eine Spannungskalibrierung durch und gibt die Kalibriertabelle zurück."""
    if not hat:
        raise RuntimeError("MCC 118 HAT nicht initialisiert.")
        
    kalibrier_tabelle = [] #
    
    for dac_wert in range(0, 4096, sp_step): #
        write_dac(dac_wert, mode) #
        time.sleep(settle) #
        spannung = hat.a_in_read(0) #
        
        if (mode == 'positiv' and spannung >= 0) or (mode == 'negativ' and spannung <= 0): #
            kalibrier_tabelle.append((spannung, dac_wert)) #
            
    write_dac(4095, mode) #
    time.sleep(settle) #
    spannung = hat.a_in_read(0) #
    if (mode == 'positiv' and spannung >= 0) or (mode == 'negativ' and spannung <= 0): #
        kalibrier_tabelle.append((spannung, 4095)) #
        
    write_dac(0, mode) #
    kalibrier_tabelle.sort(key=lambda x: x[0]) #
    return kalibrier_tabelle

def spannung_zu_dac_interpoliert(ziel_spannung, kalibrier_tabelle): #
    """Findet den DAC-Wert für eine Zielspannung durch lineare Interpolation."""
    if not kalibrier_tabelle: #
        raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
        
    if ziel_spannung <= kalibrier_tabelle[0][0]: #
        return kalibrier_tabelle[0][1] #
    if ziel_spannung >= kalibrier_tabelle[-1][0]: #
        return kalibrier_tabelle[-1][1] #
        
    for i in range(len(kalibrier_tabelle) - 1): #
        u1, d1 = kalibrier_tabelle[i] #
        u2, d2 = kalibrier_tabelle[i+1] #
        if u1 <= ziel_spannung <= u2: #
            if u2 == u1: return d1 #
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1) #
            return int(round(dac)) #
            
    if ziel_spannung < 0: #
        for i in range(len(kalibrier_tabelle) - 1): #
            u1, d1 = kalibrier_tabelle[i] #
            u2, d2 = kalibrier_tabelle[i+1] #
            if u2 <= ziel_spannung <= u1:
                 if u1 == u2: return d1 #
                 dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1) #
                 return int(round(dac)) #

    raise ValueError("Interpolation fehlgeschlagen.") #

def apply_strom_korrektur(i_mcc_mA, mode): #
    """Wendet die Korrektur auf den gemessenen Strom an."""
    params = strom_korrektur_params[mode]
    return params['a'] + params['b'] * i_mcc_mA #

# ----------------- Aufräum- und Hilfsfunktionen -----------------
def cleanup(): #
    """Setzt Hardware zurück und schließt Handles."""
    print("\nFühre Cleanup durch...")
    try:
        write_dac(0, 'positiv')
        write_dac(0, 'negativ')
        if hat and hat.is_scan_running():
            hat.a_in_scan_stop()
        print("DAC auf 0 gesetzt.")
    except Exception as e:
        print(f"Fehler beim Zurücksetzen des DAC: {e}")
    finally:
        spi.close() #
        lgpio.gpiochip_close(gpio_handle) #
        print("SPI und GPIO geschlossen. Beendet.")

atexit.register(cleanup)

def get_ip_address():
    """Ermittelt die primäre IP-Adresse des Geräts."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

# ----------------- Dash App Layout (mit Standard HTML & CSS) -----------------
app = dash.Dash(__name__)

# CSS-Stile für ein dunkles Design
styles = {
    'body': {'backgroundColor': '#1e1e1e', 'color': '#f0f0f0', 'fontFamily': 'sans-serif'},
    'container': {'padding': '20px'},
    'title': {'textAlign': 'center', 'marginBottom': '20px'},
    'radio_container': {'textAlign': 'center', 'marginBottom': '20px'},
    'main_flex_container': {'display': 'flex', 'flexWrap': 'wrap'},
    'col_control': {'flex': '1', 'minWidth': '300px', 'padding': '10px'},
    'col_display': {'flex': '2', 'minWidth': '400px', 'padding': '10px'},
    'card': {'backgroundColor': '#2a2a2a', 'padding': '20px', 'borderRadius': '5px', 'marginBottom': '20px'},
    'button': {'width': '100%', 'padding': '10px', 'fontSize': '16px', 'cursor': 'pointer', 'border': '1px solid #555', 'borderRadius': '5px', 'marginBottom': '10px'},
    'button_primary': {'backgroundColor': '#007bff', 'color': 'white'},
    'button_success': {'backgroundColor': '#28a745', 'color': 'white'},
    'button_danger': {'backgroundColor': '#dc3545', 'color': 'white'},
    'input': {'width': 'calc(100% - 20px)', 'padding': '8px', 'marginBottom': '10px', 'backgroundColor': '#333', 'color': 'white', 'border': '1px solid #555'},
    'status_text': {'marginTop': '10px', 'color': '#aaa'},
    'strom_anzeige': {'fontSize': '2.5rem', 'fontWeight': 'bold', 'textAlign': 'center'},
}

app.layout = html.Div(style=styles['body'], children=[
    html.Div(style=styles['container'], children=[
        # Stores
        dcc.Store(id='kalibrier-tabelle-store', data={'positiv': [], 'negativ': []}),
        dcc.Store(id='strom-daten-store', data={'timestamps': [], 'strom_mA': []}),

        # Titel
        html.H1("Labornetzteil Web-Steuerung", style=styles['title']),
        
        # Modus-Auswahl
        html.Div(style=styles['radio_container'], children=[
            dcc.RadioItems(
                id='modus-wahl',
                options=[
                    {'label': '  Positive Spannung', 'value': 'positiv'},
                    {'label': '  Negative Spannung', 'value': 'negativ'},
                ],
                value='positiv',
                inline=True,
                labelStyle={'marginRight': '20px'}
            )
        ]),
        html.Hr(),

        # Haupt-Container
        html.Div(style=styles['main_flex_container'], children=[
            # Linke Spalte: Steuerung
            html.Div(style=styles['col_control'], children=[
                html.Div(style=styles['card'], children=[
                    html.H3("Steuerung"),
                    html.Button("Kalibrierung starten", id='kalibrier-button', style={**styles['button'], **styles['button_primary']}),
                    html.P("Status: ", id='kalibrier-status', style=styles['status_text']),
                    html.Hr(),
                    html.Label("Zielspannung (V):"),
                    dcc.Input(id='ziel-spannung-input', type='number', value=0, style=styles['input']),
                    html.Button("Spannung setzen & Überwachung starten", id='set-spannung-button', style={**styles['button'], **styles['button_success']}),
                    html.Hr(),
                    html.Button("NOT-AUS (Spannung aus)", id='not-aus-button', style={**styles['button'], **styles['button_danger']}),
                ])
            ]),
            
            # Rechte Spalte: Anzeige
            html.Div(style=styles['col_display'], children=[
                html.Div(style=styles['card'], children=[
                    html.H3("Live-Anzeige"),
                    html.P("0.00 mA", id='strom-anzeige', style=styles['strom_anzeige']),
                    dcc.Graph(id='strom-graph', animate=True)
                ])
            ]),
        ]),
        
        dcc.Interval(id='strom-mess-intervall', interval=500, n_intervals=0, disabled=True),
        html.Hr(),
        html.P("MCC 118 & MCP49xx Steuerung via Raspberry Pi & Dash", style={'textAlign': 'center', 'color': '#aaa'}),
    ])
])

# ----------------- Dash Callbacks (unverändert) -----------------
# Die Callbacks sind identisch zur vorherigen Version, da sie auf die IDs der Komponenten reagieren,
# welche gleich geblieben sind.

@app.callback(
    Output('kalibrier-status', 'children'),
    Output('kalibrier-tabelle-store', 'data'),
    Input('kalibrier-button', 'n_clicks'),
    State('modus-wahl', 'value'),
    State('kalibrier-tabelle-store', 'data'),
    prevent_initial_call=True
)
def handle_kalibrierung(n_clicks, mode, stored_data):
    status = f"Starte Kalibrierung für '{mode}' Spannung..."
    print(status)
    try:
        tabelle = kalibrieren(mode)
        stored_data[mode] = tabelle
        status = f"Kalibrierung für '{mode}' abgeschlossen. {len(tabelle)} Punkte gespeichert."
        print(status)
        return status, stored_data
    except Exception as e:
        status = f"Fehler bei der Kalibrierung: {e}"
        print(status)
        return status, stored_data

@app.callback(
    Output('strom-mess-intervall', 'disabled'),
    Output('strom-daten-store', 'data'),
    Input('set-spannung-button', 'n_clicks'),
    Input('not-aus-button', 'n_clicks'),
    State('ziel-spannung-input', 'value'),
    State('modus-wahl', 'value'),
    State('kalibrier-tabelle-store', 'data'),
    prevent_initial_call=True
)
def steuere_spannung_und_messung(set_clicks, aus_clicks, ziel_spannung, mode, kalibrier_data):
    ctx = callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'set-spannung-button':
        try:
            tabelle = kalibrier_data.get(mode, [])
            if not tabelle:
                print("Fehler: Bitte zuerst kalibrieren.")
                return True, {'timestamps': [], 'strom_mA': []}
            
            dac_wert = spannung_zu_dac_interpoliert(ziel_spannung, tabelle)
            write_dac(dac_wert, mode)
            print(f"Spannung auf {ziel_spannung:.3f}V gesetzt (DAC={dac_wert}, Modus={mode}). Starte Stromüberwachung.")
            
            return False, {'timestamps': [], 'strom_mA': []}
        except Exception as e:
            print(f"Fehler beim Setzen der Spannung: {e}")
            return True, {'timestamps': [], 'strom_mA': []}

    if button_id == 'not-aus-button':
        print("NOT-AUS ausgelöst. Setze DAC auf 0.")
        write_dac(0, mode)
        return True, {'timestamps': [], 'strom_mA': []}

    return True, {'timestamps': [], 'strom_mA': []}

@app.callback(
    Output('strom-anzeige', 'children'),
    Output('strom-graph', 'figure'),
    Output('strom-mess-intervall', 'disabled', allow_duplicate=True),
    Input('strom-mess-intervall', 'n_intervals'),
    State('modus-wahl', 'value'),
    State('strom-daten-store', 'data'),
    prevent_initial_call=True
)
def update_strom_anzeige(n, mode, strom_data):
    if not hat:
        return "HAT Fehler", go.Figure(), True

    try:
        strom_kanal = 4 if mode == 'positiv' else 5
        
        shunt_v = hat.a_in_read(strom_kanal) #
        current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0 #
        current_true_mA = apply_strom_korrektur(current_mcc_mA, mode) #

        if current_true_mA > MAX_STROM_MA: #
            write_dac(0, mode) #
            print(f"ÜBERSTROM! {current_true_mA:.1f}mA > {MAX_STROM_MA:.1f}mA. Netzteil abgeschaltet.")
            error_fig = go.Figure()
            error_fig.update_layout(title_text=f"ÜBERSTROM! Netzteil abgeschaltet.", xaxis={'visible': False}, yaxis={'visible': False}, template="plotly_dark")
            return f"{current_true_mA:.2f} mA (ÜBERSTROM!)", error_fig, True

        timestamps = strom_data['timestamps']
        strom_werte = strom_data['strom_mA']
        timestamps.append(time.time())
        strom_werte.append(current_true_mA)
        
        if len(timestamps) > 60:
            timestamps.pop(0)
            strom_werte.pop(0)
        
        strom_data['timestamps'] = timestamps
        strom_data['strom_mA'] = strom_werte

        fig = go.Figure(data=[go.Scatter(x=list(range(len(strom_werte))), y=strom_werte, mode='lines+markers', name='Strom (mA)')])
        fig.update_layout(
            title="Stromverlauf (letzte 30s)",
            yaxis_title="Strom (mA)",
            xaxis_title="Zeit (Messpunkte)",
            template="plotly_dark",
            margin=dict(l=40, r=20, t=40, b=30)
        )
        
        return f"{current_true_mA:.2f} mA", fig, False

    except Exception as e:
        print(f"Fehler bei der Strommessung: {e}")
        return "Messfehler", go.Figure(), True

# ----------------- Hauptprogramm -----------------
if __name__ == '__main__':
    host_ip = get_ip_address()
    print(f"Starte Dash Server auf http://{host_ip}:8070")
    app.run(host=host_ip, port=8070, debug=True)
```