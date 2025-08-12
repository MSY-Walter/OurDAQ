#!/usr/bin/env python3
"""
Dash Web App to control a dual-polarity power supply
"""

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
import threading
import time
import socket
import logging

# --- Mock Hardware for testing without actual hardware ---
# Set this to False when running on the Raspberry Pi
IS_MOCK_HARDWARE = False

if IS_MOCK_HARDWARE:
    # Mock-Klassen, um die Ausführung ohne echte Hardware zu ermöglichen
    class MockSpiDev:
        def open(self, bus, device): pass
        def xfer2(self, data): pass
        def close(self): pass

    class MockLgpio:
        def gpiochip_open(self, chip): return 1
        def gpio_claim_output(self, handle, pin): pass
        def gpio_write(self, handle, pin, level): pass
        def gpiochip_close(self, handle): pass

    class MockMcc118:
        def __init__(self, address): pass
        def a_in_read(self, channel, options=0):
            # Simuliert eine Spannung basierend auf dem letzten DAC-Wert
            global last_dac_value, active_dac
            if active_dac == 'A': # Positiv
                return (last_dac_value / 4095.0) * 10.0
            else: # Negativ
                return -(last_dac_value / 4095.0) * 10.0

        def a_in_scan_start(self, mask, samples, rate, options): pass
        def a_in_scan_read(self, samples, timeout):
            # Simuliert eine Strommessung
            from collections import namedtuple
            ReadResult = namedtuple('ReadResult', ['data'])
            # Simuliert einen kleinen Strom
            return ReadResult(data=[0.1 + (last_dac_value / 40950.0)])
        def a_in_scan_stop(self): pass

    spidev = MockSpiDev()
    lgpio = MockLgpio()
    mcc118 = MockMcc118
    from daqhats_utils import chan_list_to_mask
    from daqhats import OptionFlags, HatIDs
else:
    import spidev
    import lgpio
    from daqhats import mcc118, OptionFlags, HatIDs, HatError
    from daqhats_utils import select_hat_device, chan_list_to_mask

# ----------------- Globale Variablen und Konstanten -----------------
# Hardware-Konstanten
CS_PIN_A = 22  # DAC für positive Spannung
CS_PIN_B = 27  # DAC für negative Spannung
SHUNT_WIDERSTAND = 0.1
VERSTAERKUNG = 69.0
READ_ALL_AVAILABLE = -1
MAX_STROM_MA = 500.0

# Globale Zustandsvariablen
app_running = True
last_dac_value = 0
active_dac = 'A' # 'A' für positiv, 'B' für negativ

# Kalibrierungsdaten
kalibrier_tabelle_pos = []
kalibrier_tabelle_neg = []

# Stromkorrektur (Beispielwerte, können über die UI angepasst werden)
corr_a_pos, corr_b_pos = -0.1347, 0.0780
corr_a_neg, corr_b_neg = -0.2793, 1.7828

# Daten für die grafische Darstellung
strom_daten = {'time': [], 'strom_mA': []}
spannungs_daten = {'time': [], 'spannung_V': []}
daten_sperre = threading.Lock() # Lock für Thread-sicheren Zugriff

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO)

# ----------------- Hardware-Initialisierung -----------------
spi = spidev.SpiDev()
gpio_handle = -1

def init_hardware():
    global spi, gpio_handle
    try:
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00

        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN_A)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN_B)
        lgpio.gpio_write(gpio_handle, CS_PIN_A, 1)
        lgpio.gpio_write(gpio_handle, CS_PIN_B, 1)
        logging.info("Hardware initialisiert.")
        return True
    except Exception as e:
        logging.error(f"Fehler bei der Hardware-Initialisierung: {e}")
        return False

# ----------------- DAC-Funktionen -----------------
def write_dac(value, dac_channel='A'):
    """Schreibt einen 12-Bit-Wert an den ausgewählten DAC."""
    global last_dac_value, active_dac
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")

    last_dac_value = value
    active_dac = dac_channel

    if dac_channel == 'A': # Positiver DAC
        control = 0b0011000000000000
        cs_pin = CS_PIN_A
    else: # Negativer DAC
        control = 0b1011000000000000
        cs_pin = CS_PIN_B

    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte = data & 0xFF

    if not IS_MOCK_HARDWARE:
        lgpio.gpio_write(gpio_handle, cs_pin, 0)
        spi.xfer2([high_byte, low_byte])
        lgpio.gpio_write(gpio_handle, cs_pin, 1)

# ----------------- Kalibrierung -----------------
def kalibrieren():
    """Führt die Kalibrierung für beide Polaritäten durch."""
    global kalibrier_tabelle_pos, kalibrier_tabelle_neg
    logging.info("Starte Kalibrierung...")
    if IS_MOCK_HARDWARE:
        # Dummy-Kalibrierdaten für den Test
        kalibrier_tabelle_pos = [(i/409.5, i) for i in range(0, 4096, 32)]
        kalibrier_tabelle_neg = [(-i/409.5, i) for i in range(0, 4096, 32)]
        logging.info("Mock-Kalibrierung abgeschlossen.")
        return

    try:
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
    except HatError as e:
        logging.error(f"Fehler beim Zugriff auf das DAQ HAT: {e}")
        return

    # Positive Kalibrierung
    kalibrier_tabelle_pos.clear()
    logging.info("Kalibriere positive Spannung...")
    for dac_wert in range(0, 4096, 64):
        write_dac(dac_wert, 'A')
        time.sleep(0.05)
        spannung = hat.a_in_read(0) # Kanal 0 für positive Spannung
        kalibrier_tabelle_pos.append((spannung, dac_wert))
    write_dac(0, 'A')
    kalibrier_tabelle_pos.sort(key=lambda x: x[0])

    # Negative Kalibrierung
    kalibrier_tabelle_neg.clear()
    logging.info("Kalibriere negative Spannung...")
    for dac_wert in range(0, 4096, 64):
        write_dac(dac_wert, 'B')
        time.sleep(0.05)
        spannung = hat.a_in_read(1) # Kanal 1 für negative Spannung
        if spannung <= 0:
            kalibrier_tabelle_neg.append((spannung, dac_wert))
    write_dac(0, 'B')
    kalibrier_tabelle_neg.sort(key=lambda x: x[0])

    logging.info("Kalibrierung abgeschlossen.")

def spannung_zu_dac_interpoliert(ziel_spannung):
    """Interpoliert die Zielspannung zu einem DAC-Wert."""
    if ziel_spannung >= 0:
        tabelle = kalibrier_tabelle_pos
        # Sicherstellen, dass die Spannung im positiven Bereich liegt
        if not tabelle or ziel_spannung > tabelle[-1][0]:
             return tabelle[-1][1] if tabelle else 4095
        if ziel_spannung < tabelle[0][0]:
            return tabelle[0][1]
    else:
        tabelle = kalibrier_tabelle_neg
        # Sicherstellen, dass die Spannung im negativen Bereich liegt
        if not tabelle or ziel_spannung < tabelle[0][0]:
            return tabelle[0][1] if tabelle else 4095
        if ziel_spannung > tabelle[-1][0]:
            return tabelle[-1][1]

    for i in range(len(tabelle) - 1):
        u1, d1 = tabelle[i]
        u2, d2 = tabelle[i+1]
        if u1 <= ziel_spannung <= u2 or u2 <= ziel_spannung <= u1:
            if u2 == u1:
                return d1
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return int(round(dac))
    return tabelle[-1][1] # Fallback

# ----------------- Stromüberwachung -----------------
def apply_strom_korrektur(i_mcc_mA, polaritaet):
    """Wendet die lineare Korrektur an."""
    if polaritaet == 'pos':
        return corr_a_pos + corr_b_pos * i_mcc_mA
    else:
        return corr_a_neg + corr_b_neg * i_mcc_mA

def strom_ueberwachungs_thread():
    """Thread zur kontinuierlichen Überwachung von Strom und Spannung."""
    logging.info("Stromüberwachungs-Thread gestartet.")
    if IS_MOCK_HARDWARE:
        hat = MockMcc118(0)
    else:
        try:
            address = select_hat_device(HatIDs.MCC_118)
            hat = mcc118(address)
            # Kanal 4 für pos Strom, 5 für neg Strom
            hat.a_in_scan_start(chan_list_to_mask([0, 1, 4, 5]), 0, 100.0, OptionFlags.CONTINUOUS)
        except HatError as e:
            logging.error(f"Fehler beim Starten des Scans: {e}")
            return

    while app_running:
        try:
            read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.5)
            if read_result.data:
                # Annahme: Kanal 0=Vpos, 1=Vneg, 4=Ipos, 5=Ineg
                v_pos = read_result.data[-4] if len(read_result.data) >= 4 else 0
                v_neg = read_result.data[-3] if len(read_result.data) >= 3 else 0
                shunt_v_pos = read_result.data[-2] if len(read_result.data) >= 2 else 0
                shunt_v_neg = read_result.data[-1]

                # Aktuellen Strom berechnen
                current_mcc_mA_pos = (shunt_v_pos / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA_pos = apply_strom_korrektur(current_mcc_mA_pos, 'pos')

                current_mcc_mA_neg = (shunt_v_neg / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA_neg = apply_strom_korrektur(current_mcc_mA_neg, 'neg')

                # Wähle den relevanten Strom basierend auf dem aktiven DAC
                strom_mA = current_true_mA_pos if active_dac == 'A' else current_true_mA_neg
                spannung_V = v_pos if active_dac == 'A' else v_neg

                with daten_sperre:
                    now = time.time()
                    strom_daten['time'].append(now)
                    strom_daten['strom_mA'].append(strom_mA)
                    spannungs_daten['time'].append(now)
                    spannungs_daten['spannung_V'].append(spannung_V)
                    # Begrenze die Datenlänge
                    if len(strom_daten['time']) > 200:
                        strom_daten['time'].pop(0)
                        strom_daten['strom_mA'].pop(0)
                        spannungs_daten['time'].pop(0)
                        spannungs_daten['spannung_V'].pop(0)

                # Überstromschutz
                if abs(strom_mA) > MAX_STROM_MA:
                    write_dac(0, 'A')
                    write_dac(0, 'B')
                    logging.warning(f"ÜBERSTROM! {strom_mA:.1f} mA. DACs auf 0 gesetzt.")
                    # Hier könnte man den Thread anhalten oder eine UI-Benachrichtigung senden

            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Fehler im Überwachungs-Thread: {e}")
            time.sleep(1)

    if not IS_MOCK_HARDWARE:
        hat.a_in_scan_stop()
    logging.info("Stromüberwachungs-Thread beendet.")

# ----------------- Dash App Layout und Callbacks -----------------
app = dash.Dash(__name__)

app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '800px', 'margin': 'auto'}, children=[
    html.H1("Labornetzteil Steuerung"),

    # Spannungs- und Stromeinstellungen
    html.Div(className='row', style={'display': 'flex'}, children=[
        html.Div(className='six columns', style={'flex': 1, 'padding': '10px'}, children=[
            html.H3("Spannung einstellen"),
            dcc.Input(id='ziel-spannung', type='number', value=0, step=0.1, style={'width': '100px'}),
            html.Button('Setzen', id='set-spannung-button', n_clicks=0, style={'marginLeft': '10px'}),
            html.P(id='dac-output', style={'marginTop': '10px'}),
        ]),
        html.Div(className='six columns', style={'flex': 1, 'padding': '10px'}, children=[
            html.H3("Stromgrenze (mA)"),
            dcc.Input(id='max-strom', type='number', value=MAX_STROM_MA, step=10),
            html.Button('Setzen', id='set-strom-button', n_clicks=0, style={'marginLeft': '10px'}),
        ]),
    ]),

    # Graphen für Live-Daten
    html.H3("Live-Messwerte"),
    dcc.Graph(id='strom-graph'),
    dcc.Graph(id='spannung-graph'),
    dcc.Interval(id='interval-component', interval=500, n_intervals=0), # 2 Hz Update

    html.H3("Status"),
    html.Div(id='status-anzeige', style={'border': '1px solid #ccc', 'padding': '10px', 'borderRadius': '5px'})
])

@app.callback(
    [Output('dac-output', 'children'),
     Output('status-anzeige', 'children')],
    [Input('set-spannung-button', 'n_clicks')],
    [State('ziel-spannung', 'value')]
)
def update_spannung(n_clicks, spannung):
    if n_clicks > 0:
        try:
            dac_wert = spannung_zu_dac_interpoliert(spannung)
            dac_channel = 'A' if spannung >= 0 else 'B'
            # Den anderen Kanal auf 0 setzen
            write_dac(0, 'B' if dac_channel == 'A' else 'A')
            time.sleep(0.01)
            write_dac(dac_wert, dac_channel)
            msg = f"Spannung auf {spannung:.3f}V gesetzt (DAC {dac_channel} = {dac_wert})."
            logging.info(msg)
            return msg, f"Letzte Aktion: {msg}"
        except Exception as e:
            logging.error(f"Fehler beim Setzen der Spannung: {e}")
            return f"Fehler: {e}", f"Letzte Aktion: Fehler beim Setzen der Spannung."
    return "Noch keine Spannung gesetzt.", "Bereit."

@app.callback(
    Output('strom-graph', 'figure'),
    [Input('interval-component', 'n_intervals')]
)
def update_strom_graph(n):
    with daten_sperre:
        fig = go.Figure(
            data=[go.Scatter(x=list(strom_daten['time']), y=list(strom_daten['strom_mA']), mode='lines+markers')],
            layout=go.Layout(
                title='Stromverlauf',
                xaxis_title='Zeit',
                yaxis_title='Strom (mA)',
                yaxis=dict(range=[-10, MAX_STROM_MA + 50]) # Fester Bereich für bessere Lesbarkeit
            )
        )
    return fig

@app.callback(
    Output('spannung-graph', 'figure'),
    [Input('interval-component', 'n_intervals')]
)
def update_spannung_graph(n):
    with daten_sperre:
        fig = go.Figure(
            data=[go.Scatter(x=list(spannungs_daten['time']), y=list(spannungs_daten['spannung_V']), mode='lines+markers', line=dict(color='orange'))],
            layout=go.Layout(
                title='Spannungsverlauf',
                xaxis_title='Zeit',
                yaxis_title='Spannung (V)',
                yaxis=dict(range=[-12, 12])
            )
        )
    return fig

@app.callback(
    Output('max-strom', 'value'),
    [Input('set-strom-button', 'n_clicks')],
    [State('max-strom', 'value')]
)
def update_max_strom(n_clicks, strom):
    global MAX_STROM_MA
    if n_clicks > 0 and strom is not None:
        MAX_STROM_MA = float(strom)
        logging.info(f"Stromgrenze auf {MAX_STROM_MA} mA gesetzt.")
    return MAX_STROM_MA

# ----------------- Hilfsfunktionen und Main Block -----------------
def get_ip_address():
    """Ermittelt die lokale IP-Adresse."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def cleanup():
    """Räumt Ressourcen auf."""
    global app_running
    app_running = False
    logging.info("Räume auf...")
    try:
        write_dac(0, 'A')
        write_dac(0, 'B')
        if not IS_MOCK_HARDWARE:
            spi.close()
            lgpio.gpiochip_close(gpio_handle)
    except Exception as e:
        logging.error(f"Fehler beim Aufräumen: {e}")
    logging.info("Aufräumen beendet.")

if __name__ == '__main__':
    if IS_MOCK_HARDWARE or init_hardware():
        # Kalibrierung durchführen
        kalibrieren()

        # Starte den Überwachungs-Thread
        monitor_thread = threading.Thread(target=strom_ueberwachungs_thread)
        monitor_thread.daemon = True
        monitor_thread.start()

        # Starte die Dash App
        ip_address = get_ip_address()
        port = 8070
        print(f"Dash App läuft auf http://{ip_address}:{port}")
        app.run(host=ip_address, port=port, debug=True)

        # Nach dem Beenden der App aufräumen
        cleanup()
        monitor_thread.join()
    else:
        print("Konnte Hardware nicht initialisieren. App wird nicht gestartet.")
