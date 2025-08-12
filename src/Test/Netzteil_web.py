#!/usr/bin/env python3
"""
Web-basiertes Steuerprogramm für ein Labornetzteil
"""

import dash
from dash import dcc, html, Input, Output, State, no_update
import dash_bootstrap_components as dbc
from dash.long_callback import DiskcacheManager
import diskcache
import time
import lgpio
import spidev
import numpy as np
import socket
import atexit

# Hardware-Bibliotheken (DAQ HAT)
try:
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    from daqhats_utils import select_hat_device, chan_list_to_mask
    HARDWARE_AVAILABLE = True
except ImportError:
    print("WARNUNG: DAQ HAT Bibliothek nicht gefunden. Hardware-Funktionen sind deaktiviert.")
    HARDWARE_AVAILABLE = False


# ----------------- Globale Konfiguration & Hardware Initialisierung -----------------

# Cache für Hintergrund-Callbacks von Dash
cache = diskcache.Cache("./callback_cache")
long_callback_manager = DiskcacheManager(cache)

# --- Konstanten ---
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin
READ_ALL_AVAILABLE = -1
MAX_STROM_MA = 500.0        # Überstromschutz (mA)
MAX_SPANNUNG_NEGATIV = -10  # Minimale negative Spannung

# --- Zustandsverwaltung für beide Netzteile ---
# Hier werden Kalibrierdaten und Korrekturfaktoren gespeichert
STATE = {
    'plus': {
        'kalibrier_tabelle': [],
        'corr_a': -0.134738,
        'corr_b': 0.078004,
        'mcc_voltage_channel': 0,
        'mcc_current_channel': 4,
        'dac_control_byte': 0b0011000000000000,
    },
    'minus': {
        'kalibrier_tabelle': [],
        'corr_a': -0.279388,
        'corr_b': 1.782842,
        'mcc_voltage_channel': 0, # Annahme: Gleicher Kanal für Spannungsmessung
        'mcc_current_channel': 5,
        'dac_control_byte': 0b1011000000000000,
    }
}

# --- Hardware-Objekte ---
# Diese werden nur initialisiert, wenn die Bibliotheken verfügbar sind.
spi = None
gpio_handle = None
hat = None

def init_hardware():
    global spi, gpio_handle, hat
    if not HARDWARE_AVAILABLE:
        return

    try:
        # SPI für DAC
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00

        # GPIO für Chip Select
        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN)
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

        # MCC 118 HAT
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        print("Hardware erfolgreich initialisiert.")
    except Exception as e:
        print(f"FEHLER bei der Hardware-Initialisierung: {e}")
        # Setze die globalen Variablen zurück, um Fehler zu vermeiden
        spi, gpio_handle, hat = None, None, None
        raise RuntimeError("Konnte die Hardware nicht initialisieren. Läuft das Skript mit den nötigen Rechten auf einem Raspberry Pi?")


# ----------------- Kombinierte Hardware-Funktionen -----------------

def write_dac(value, mode='plus'):
    """Schreibt einen 12-bit Wert an den DAC für den gewählten Modus."""
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    if not spi or not gpio_handle:
        print(f"MOCK DAC WRITE: value={value}, mode={mode}")
        return

    control = STATE[mode]['dac_control_byte']
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte  = data & 0xFF

    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)


def kalibrieren(mode, sp_step=32, settle=0.05):
    """
    Führt die Spannungs-Kalibrierung für den gewählten Modus durch.
    Gibt die Kalibriertabelle und eine Log-Nachricht zurück.
    """
    if not hat:
        # Mock-Daten für Tests ohne Hardware
        mock_table = [(i / 400.0, i) for i in range(0, 4096, sp_step)]
        if mode == 'minus':
            mock_table = [(-v, d) for v, d in mock_table]
        time.sleep(3) # Simuliere lange Laufzeit
        return mock_table, f"Mock-Kalibrierung für Modus '{mode}' abgeschlossen."

    kalibrier_tabelle = []
    log_output = f"Starte Kalibrierung für Modus '{mode}'...\n"
    channel = STATE[mode]['mcc_voltage_channel']

    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert, mode)
        time.sleep(settle)
        spannung = hat.a_in_read(channel)
        
        log_line = f"  DAC {dac_wert:4d} -> {spannung:8.5f} V"
        
        # Logik für negativen Modus: nur negative Spannungen speichern
        if mode == 'minus' and spannung > 0:
            log_line += " (ignoriert, da nicht negativ)\n"
        else:
            kalibrier_tabelle.append((spannung, dac_wert))
            log_line += "\n"
        
        log_output += log_line

    # Letzten Punkt (4095) sicherstellen
    write_dac(4095, mode)
    time.sleep(settle)
    spannung = hat.a_in_read(channel)
    log_line = f"  DAC {4095:4d} -> {spannung:8.5f} V"
    if mode == 'minus' and spannung > 0:
        log_line += " (ignoriert, da nicht negativ)\n"
    else:
        kalibrier_tabelle.append((spannung, 4095))
        log_line += "\n"
    log_output += log_line

    write_dac(0, mode)  # Sicher zurücksetzen
    kalibrier_tabelle.sort(key=lambda x: x[0]) # Sortieren nach Spannung
    log_output += f"Kalibrierung abgeschlossen. {len(kalibrier_tabelle)} Punkte gespeichert.\n"

    return kalibrier_tabelle, log_output


def spannung_zu_dac_interpoliert(ziel_spannung, mode):
    """Lineare Interpolation zur Ermittlung des DAC-Wertes."""
    tabelle = STATE[mode]['kalibrier_tabelle']
    if not tabelle:
        raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte zuerst kalibrieren.")
    
    # Randbehandlung
    if ziel_spannung <= tabelle[0][0]: return tabelle[0][1]
    if ziel_spannung >= tabelle[-1][0]: return tabelle[-1][1]

    # Suche Intervall und interpoliere
    for i in range(len(tabelle) - 1):
        u1, d1 = tabelle[i]
        u2, d2 = tabelle[i+1]
        if u1 <= ziel_spannung <= u2:
            return int(round(d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1))) if u2 != u1 else d1
            
    raise ValueError("Interpolation fehlgeschlagen. Zielspannung außerhalb des Kalibrierbereichs.")


def kalibriere_stromkorrektur(mcc_list_mA, true_list_mA):
    """Berechnet lineare Korrekturfaktoren a und b."""
    mcc = np.array(mcc_list_mA, dtype=float)
    true = np.array(true_list_mA, dtype=float)
    A = np.vstack([np.ones_like(mcc), mcc]).T
    a, b = np.linalg.lstsq(A, true, rcond=None)[0]
    return float(a), float(b)


def get_current(mode):
    """Liest einen Stromwert, korrigiert ihn und gibt alle Werte zurück."""
    if not hat:
        # Mock-Daten für Tests ohne Hardware
        mock_shunt_v = np.random.rand() * 0.1
        mock_mcc_ma = (mock_shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
        corr_a = STATE[mode]['corr_a']
        corr_b = STATE[mode]['corr_b']
        mock_true_ma = corr_a + corr_b * mock_mcc_ma
        return mock_shunt_v, mock_mcc_ma, mock_true_ma

    channel = STATE[mode]['mcc_current_channel']
    
    # Für eine einzelne Messung ist a_in_read ausreichend
    shunt_v = hat.a_in_read(channel)
    
    current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
    
    corr_a = STATE[mode]['corr_a']
    corr_b = STATE[mode]['corr_b']
    current_true_mA = corr_a + corr_b * current_mcc_mA
    
    return shunt_v, current_mcc_mA, current_true_mA


def cleanup():
    """Räumt auf und gibt Hardware-Ressourcen frei."""
    print("\nAufräumen und beenden...")
    if HARDWARE_AVAILABLE:
        try:
            # DAC auf 0 setzen für beide Modi zur Sicherheit
            write_dac(0, 'plus')
            write_dac(0, 'minus')
        except Exception as e:
            print(f"Fehler beim Zurücksetzen des DAC: {e}")
        
        if spi: spi.close()
        if gpio_handle: lgpio.gpiochip_close(gpio_handle)
    print("Beendet.")


def get_ip_address():
    """Ermittelt die lokale IP-Adresse des Hosts."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ----------------- Dash App Layout -----------------

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], long_callback_manager=long_callback_manager)
app.title = "Labornetzteil Steuerung"

# Layout für die Anzeige der aktuellen Messwerte
current_display = dbc.Card(
    dbc.CardBody([
        html.H4("Live-Strommessung", className="card-title"),
        dbc.Row([
            dbc.Col(html.Div("Shunt-Spannung:"), width=6),
            dbc.Col(html.Div(id='display-shunt-v', children="--- V"), width=6)
        ]),
        dbc.Row([
            dbc.Col(html.Div("MCC Strom (gemessen):"), width=6),
            dbc.Col(html.Div(id='display-mcc-ma', children="--- mA"), width=6)
        ]),
        dbc.Row([
            dbc.Col(html.Div("Strom (korrigiert):"), width=6),
            dbc.Col(html.B(id='display-true-ma', children="--- mA"), width=6)
        ]),
    ])
)

# Layout für die Steuerung
controls = dbc.Card(
    dbc.CardBody([
        dbc.Row([
            dbc.Col(dbc.Label("Gewünschte Spannung (V):"), width="auto"),
            dbc.Col(dcc.Input(id='input-voltage', type='number', value=0, step=0.01, className="form-control")),
            dbc.Col(dbc.Button("Spannung setzen", id='btn-set-voltage', color="primary"), width="auto"),
        ]),
        html.Hr(),
        dbc.Label("Stromüberwachung:"),
        dbc.Switch(id='switch-monitoring', value=False, label="Aktivieren/Deaktivieren"),
    ])
)

app.layout = dbc.Container([
    # Store-Komponenten zum Speichern von Zuständen im Browser
    dcc.Store(id='store-mode', data='plus'),
    dcc.Store(id='store-calibration-plus'),
    dcc.Store(id='store-calibration-minus'),
    dcc.Store(id='store-correction-plus', data={'a': STATE['plus']['corr_a'], 'b': STATE['plus']['corr_b']}),
    dcc.Store(id='store-correction-minus', data={'a': STATE['minus']['corr_a'], 'b': STATE['minus']['corr_b']}),

    # Titel
    html.H1("Labornetzteil Web-Steuerung"),
    html.Hr(),

    # Moduswahl und Kalibrierung
    dbc.Row([
        dbc.Col([
            dbc.Label("Netzteil-Modus wählen:"),
            dbc.RadioItems(
                id='radio-mode-select',
                options=[
                    {'label': 'Positives Netzteil', 'value': 'plus'},
                    {'label': 'Negatives Netzteil', 'value': 'minus'},
                ],
                value='plus',
                inline=True
            ),
            html.Br(),
            dbc.Button("Spannungs-Kalibrierung starten", id='btn-calibrate', color="info"),
            dbc.Spinner(html.Div(id="spinner-calibration"))
        ], width=6),
        dbc.Col([
            dbc.Alert("Willkommen! Bitte wählen Sie einen Modus und starten Sie die Kalibrierung.", color="info"),
            dbc.Alert(id='alert-status', is_open=False),
            dbc.Alert(id='alert-overcurrent', is_open=False, color="danger", duration=10000)
        ], width=6),
    ]),
    
    # Kalibrierungs-Log
    html.Pre(id='log-calibration', style={'height': '150px', 'overflowY': 'scroll', 'border': '1px solid #ccc', 'padding': '10px', 'marginTop': '10px'}),

    html.Hr(),

    # Hauptsteuerung und Anzeige
    dbc.Row([
        dbc.Col(controls, md=6),
        dbc.Col(current_display, md=6),
    ], className="g-4"),

    # Akkordion für erweiterte Funktionen (Stromkorrektur)
    dbc.Accordion([
        dbc.AccordionItem([
            html.P("Geben Sie paarweise Messwerte ein, um die Korrekturfaktoren neu zu berechnen. Jede Zeile ein Paar: 'gemessener_mA wahrer_mA'."),
            dbc.Textarea(id='input-recal-current-data', style={'height': '150px', 'fontFamily': 'monospace'}),
            dbc.Button("Neue Korrekturfaktoren berechnen & anwenden", id='btn-recal-current', color="secondary", className="mt-2"),
            html.Div(id='output-recal-current-result', className="mt-2")
        ], title="Strommessung neu kalibrieren")
    ], start_collapsed=True, className="mt-4"),
    
    # Intervall-Timer für die Live-Anzeige
    dcc.Interval(id='interval-monitor', interval=500, disabled=True) # 500ms = 2 Hz
], fluid=True, className="p-4")


# ----------------- Dash Callbacks -----------------

@app.callback(
    Output('store-mode', 'data'),
    Input('radio-mode-select', 'value')
)
def update_mode_store(mode):
    """Speichert den gewählten Modus."""
    return mode

@app.long_callback(
    output=[
        Output('store-calibration-plus', 'data', allow_duplicate=True),
        Output('store-calibration-minus', 'data', allow_duplicate=True),
        Output('log-calibration', 'children'),
        Output('alert-status', 'is_open', allow_duplicate=True),
        Output('alert-status', 'children', allow_duplicate=True),
    ],
    inputs=Input('btn-calibrate', 'n_clicks'),
    state=State('store-mode', 'data'),
    running=[
        (Output("btn-calibrate", "disabled"), True, False),
        (Output("btn-set-voltage", "disabled"), True, False),
        (Output("spinner-calibration", "style"), {"display": "inline-block"}, {"display": "none"}),
    ],
    prevent_initial_call=True,
    manager=long_callback_manager
)
def handle_calibration(n_clicks, mode):
    """Führt die Kalibrierung im Hintergrund aus."""
    tabelle, log = kalibrieren(mode)
    
    # Zustand im Hauptprogramm aktualisieren
    STATE[mode]['kalibrier_tabelle'] = tabelle
    
    # Outputs für den jeweiligen Modus-Store vorbereiten
    plus_data = tabelle if mode == 'plus' else no_update
    minus_data = tabelle if mode == 'minus' else no_update
    
    status_msg = f"Kalibrierung für Modus '{mode}' erfolgreich abgeschlossen."
    
    return plus_data, minus_data, log, True, status_msg

@app.callback(
    [Output('alert-status', 'is_open'),
     Output('alert-status', 'children'),
     Output('alert-status', 'color')],
    Input('btn-set-voltage', 'n_clicks'),
    [State('input-voltage', 'value'),
     State('store-mode', 'data')]
)
def set_voltage(n_clicks, voltage, mode):
    """Setzt die Ausgangsspannung."""
    if n_clicks is None:
        return no_update

    try:
        dac_val = spannung_zu_dac_interpoliert(voltage, mode)
        write_dac(dac_val, mode)
        msg = f"Spannung für Modus '{mode}' auf {voltage:.3f} V gesetzt (DAC={dac_val})."
        return True, msg, "success"
    except Exception as e:
        return True, f"Fehler beim Setzen der Spannung: {e}", "danger"

@app.callback(
    Output('interval-monitor', 'disabled'),
    Input('switch-monitoring', 'value')
)
def toggle_monitoring(is_on):
    """Aktiviert/Deaktiviert den Intervall-Timer."""
    return not is_on

@app.callback(
    [Output('display-shunt-v', 'children'),
     Output('display-mcc-ma', 'children'),
     Output('display-true-ma', 'children'),
     Output('alert-overcurrent', 'is_open'),
     Output('alert-overcurrent', 'children'),
     Output('switch-monitoring', 'value', allow_duplicate=True)],
    Input('interval-monitor', 'n_intervals'),
    State('store-mode', 'data'),
    prevent_initial_call=True
)
def update_current_display(n, mode):
    """Liest Strom, aktualisiert die Anzeige und prüft auf Überstrom."""
    try:
        shunt_v, mcc_ma, true_ma = get_current(mode)
        
        # Überstromprüfung
        if true_ma > MAX_STROM_MA:
            write_dac(0, mode) # Netzteil AUS
            msg = f"ÜBERSTROM DETEKTIERT! ({true_ma:.1f} mA > {MAX_STROM_MA:.1f} mA). Ausgang wurde deaktiviert."
            return (f"{shunt_v:7.4f} V", 
                    f"{mcc_ma:7.2f} mA", 
                    f"{true_ma:7.2f} mA", 
                    True, 
                    msg,
                    False) # Schaltet den Switch aus
            
        return (f"{shunt_v:7.4f} V", 
                f"{mcc_ma:7.2f} mA", 
                f"{true_ma:7.2f} mA", 
                False, "", no_update)

    except Exception as e:
        print(f"Fehler bei der Strommessung: {e}")
        return no_update


@app.callback(
    [Output('store-correction-plus', 'data'),
     Output('store-correction-minus', 'data'),
     Output('output-recal-current-result', 'children')],
    Input('btn-recal-current', 'n_clicks'),
    [State('input-recal-current-data', 'value'),
     State('store-mode', 'data')]
)
def handle_current_recalibration(n_clicks, data, mode):
    """Verarbeitet die manuelle Eingabe für die Strom-Neukalibrierung."""
    if n_clicks is None or not data:
        return no_update
    
    mccs, trues = [], []
    try:
        for line in data.strip().split('\n'):
            if not line.strip(): continue
            mcc_val, true_val = map(float, line.split())
            mccs.append(mcc_val)
            trues.append(true_val)
        
        if len(mccs) < 2:
            raise ValueError("Mindestens 2 Datenpunkte erforderlich.")
            
        a, b = kalibriere_stromkorrektur(mccs, trues)
        
        # Zustand im Hauptprogramm aktualisieren
        STATE[mode]['corr_a'] = a
        STATE[mode]['corr_b'] = b
        
        msg = f"Neue Korrektur für Modus '{mode}' gesetzt: a={a:.6f}, b={b:.9f}"
        
        plus_data = {'a': a, 'b': b} if mode == 'plus' else no_update
        minus_data = {'a': a, 'b': b} if mode == 'minus' else no_update

        return plus_data, minus_data, dbc.Alert(msg, color="success")
        
    except Exception as e:
        return no_update, no_update, dbc.Alert(f"Fehler bei der Verarbeitung: {e}", color="danger")


# ----------------- Hauptprogramm -----------------

if __name__ == '__main__':
    try:
        init_hardware()
        atexit.register(cleanup)
        host_ip = get_ip_address()
        print(f"Dash-Server startet. Zugriff über http://{host_ip}:8070 oder http://127.0.0.1:8070")
        app.run(host=host_ip, port=8070, debug=True)
    except Exception as e:
        print(f"Fehler beim Starten der Anwendung: {e}")
    finally:
        cleanup()