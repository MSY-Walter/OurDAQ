#  -*- coding: utf-8 -*-
import socket
import json
from time import sleep
from collections import deque
from typing import List, Dict, Any, Union, Optional

# Moderne Dash-Importierungen
from dash import Dash, dcc, html, Input, Output, State, callback
import plotly.graph_objects as go
from daqhats import hat_list, mcc118, HatIDs, OptionFlags


app = Dash(__name__)
app.css.config.serve_locally = True
app.scripts.config.serve_locally = True

# Globaler HAT-Objekt für die Verwendung in mehreren Callbacks
HAT = None

MCC118_CHANNEL_COUNT = 8
ALL_AVAILABLE = -1
RETURN_IMMEDIATELY = 0


def create_hat_selector() -> dcc.Dropdown:
    """
    Ruft eine Liste der verfügbaren MCC 118-Geräte ab und erstellt ein entsprechendes
    Dash-Dropdown-Element für die Benutzeroberfläche.

    Returns:
        dcc.Dropdown: Ein Dash-Dropdown-Objekt.
    """
    hats = hat_list(filter_by_id=HatIDs.MCC_118)
    hat_selection_options = []
    for hat in hats:
        # Erstellt das Label aus der Adresse und dem Produktnamen
        label = f'{hat.address}: {hat.product_name}'
        # Erstellt den Wert durch Konvertierung des Deskriptors in ein JSON-Objekt
        option = {'label': label, 'value': json.dumps(hat._asdict())}
        hat_selection_options.append(option)

    selection = None
    if hat_selection_options:
        selection = hat_selection_options[0]['value']

    return dcc.Dropdown(
        id='hatSelector', 
        options=hat_selection_options,
        value=selection, 
        clearable=False
    )


def init_chart_data(number_of_channels: int, number_of_samples: int) -> str:
    """
    Initialisiert das Diagramm mit der angegebenen Anzahl von Samples.

    Args:
        number_of_channels: Die Anzahl der anzuzeigenden Kanäle.
        number_of_samples: Die Anzahl der anzuzeigenden Samples.

    Returns:
        Ein String, der ein JSON-Objekt mit den Diagrammdaten darstellt.
    """
    samples = list(range(number_of_samples))
    data = [[None] * number_of_samples for _ in range(number_of_channels)]

    chart_data = {'data': data, 'samples': samples, 'sample_count': 0}

    return json.dumps(chart_data)


# Definition des HTML-Layouts für die Benutzeroberfläche
app.layout = html.Div([
    html.H1(
        children='OurDAQ - Oszilloskop',
        id='exampleTitle'
    ),
    html.Div([
        html.Div(
            id='rightContent',
            children=[
                dcc.Graph(id='stripChart'),
                html.Div(id='errorDisplay',
                         children='',
                         style={'font-weight': 'bold', 'color': 'red'})
            ], 
            style={'width': '100%', 'box-sizing': 'border-box',
                   'float': 'left', 'padding-left': 320}
        ),
        html.Div(
            id='leftContent',
            children=[
                html.Label('Wählen Sie ein HAT...', style={'font-weight': 'bold'}),
                create_hat_selector(),
                html.Label('Abtastrate (Hz)',
                           style={'font-weight': 'bold', 'display': 'block',
                                  'margin-top': 10}),
                dcc.Input(id='sampleRate', type='number', max=100000.0,
                          step=1, value=1000.0,
                          style={'width': 100, 'display': 'block'}),
                html.Label('Anzuzeigende Samples',
                           style={'font-weight': 'bold',
                                  'display': 'block', 'margin-top': 10}),
                dcc.Input(id='samplesToDisplay', type='number', min=1,
                          max=1000, step=1, value=100,
                          style={'width': 100, 'display': 'block'}),
                html.Label('Aktive Kanäle',
                           style={'font-weight': 'bold', 'display': 'block',
                                  'margin-top': 10}),
                dcc.Checklist(
                    id='channelSelections',
                    options=[
                        {'label': f'Kanal {i}', 'value': i} for i in range(MCC118_CHANNEL_COUNT)
                    ],
                    labelStyle={'display': 'block'},
                    value=[2] # Standardmäßig Kanal 2 aktiv
                ),
                html.Button(
                    children='Konfigurieren',
                    id='startStopButton',
                    style={'width': 100, 'height': 35, 'text-align': 'center',
                           'margin-top': 10}
                ),
            ], 
            style={'width': 320, 'box-sizing': 'border-box', 'padding': 10,
                   'position': 'absolute', 'top': 0, 'left': 0}
        ),
    ], 
    style={'position': 'relative', 'display': 'block', 'overflow': 'hidden'}),
    dcc.Interval(
        id='timer',
        interval=1000*60*60*24,  # in Millisekunden (1 Tag)
        n_intervals=0
    ),
    html.Div(
        id='chartData',
        style={'display': 'none'},
        children=init_chart_data(1, 1000)
    ),
    html.Div(
        id='chartInfo',
        style={'display': 'none'},
        children=json.dumps({'sample_count': 0})
    ),
    html.Div(
        id='status',
        style={'display': 'none'}
    ),
])


@callback(
    Output('status', 'children'),
    Input('startStopButton', 'n_clicks'),
    State('startStopButton', 'children'),
    State('hatSelector', 'value'),
    State('sampleRate', 'value'),
    State('samplesToDisplay', 'value'),
    State('channelSelections', 'value')
)
def start_stop_click(
    n_clicks: Optional[int], 
    button_label: str, 
    hat_descriptor_json_str: str,
    sample_rate_val: float, 
    samples_to_display: int, 
    active_channels: List[int]
) -> str:
    """
    Ein Callback-Funktion zum Ändern des Anwendungsstatus, wenn die Schaltfläche 'Konfigurieren',
    'Start' oder 'Stop' angeklickt wird.

    Args:
        n_clicks: Anzahl der Schaltflächenklicks - löst den Callback aus.
        button_label: Das aktuelle Label auf der Schaltfläche.
        hat_descriptor_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und den Deskriptor für das ausgewählte MCC 118 DAQ HAT enthält.
        sample_rate_val: Der vom Benutzer angegebene Abtastratenwert.
        samples_to_display: Die Anzahl der anzuzeigenden Samples.
        active_channels: Eine Liste von Ganzzahlen, die den vom Benutzer
            ausgewählten aktiven Kanälen entsprechen.

    Returns:
        Der neue Anwendungsstatus - "idle", "configured", "running" oder "error"
    """
    output = 'idle'
    if n_clicks is not None and n_clicks > 0:
        if button_label == 'Konfigurieren':
            if (1 < samples_to_display <= 1000
                    and active_channels
                    and sample_rate_val <= (100000 / len(active_channels))):
                # Bei Konfiguration das HAT-Objekt erstellen
                if hat_descriptor_json_str:
                    hat_descriptor = json.loads(hat_descriptor_json_str)
                    # Das HAT-Objekt wird als Global für die Verwendung in
                    # anderen Callbacks beibehalten
                    global HAT
                    HAT = mcc118(hat_descriptor['address'])
                    output = 'configured'
            else:
                output = 'error'
        elif button_label == 'Start':
            # Beim Starten die a_in_scan_start-Funktion aufrufen
            sample_rate = float(sample_rate_val)
            channel_mask = 0x0
            for channel in active_channels:
                channel_mask |= 1 << channel
            hat = globals()['HAT']
            # 5 Sekunden Daten puffern
            samples_to_buffer = int(5 * sample_rate)
            hat.a_in_scan_start(channel_mask, samples_to_buffer,
                                sample_rate, OptionFlags.CONTINUOUS)
            sleep(0.5)
            output = 'running'
        elif button_label == 'Stop':
            # Beim Stoppen die a_in_scan_stop und a_in_scan_cleanup-Funktionen aufrufen
            hat = globals()['HAT']
            hat.a_in_scan_stop()
            hat.a_in_scan_cleanup()
            output = 'idle'

    return output


@callback(
    Output('timer', 'interval'),
    Input('status', 'children'),
    Input('chartData', 'children'),
    Input('chartInfo', 'children'),
    State('channelSelections', 'value'),
    State('samplesToDisplay', 'value')
)
def update_timer_interval(
    acq_state: str, 
    chart_data_json_str: str, 
    chart_info_json_str: str,
    active_channels: List[int], 
    samples_to_display: int
) -> int:
    """
    Eine Callback-Funktion zum Aktualisieren des Timer-Intervalls. Der Timer wird vorübergehend
    deaktiviert, während Daten verarbeitet werden, indem das Intervall auf 1 Tag gesetzt wird, und dann
    wieder aktiviert, wenn die gelesenen Daten geplottet wurden. Der Intervallwert, wenn aktiviert,
    wird basierend auf dem erforderlichen Datendurchsatz berechnet, mit einem Minimum von 500 ms
    und einem Maximum von 4 Sekunden.

    Args:
        acq_state: Der Anwendungsstatus "idle", "configured", "running" oder "error" - 
            löst den Callback aus.
        chart_data_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und die aktuellen Diagrammdaten enthält - löst den Callback aus.
        chart_info_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und den aktuellen Diagrammstatus enthält - löst den Callback aus.
        active_channels: Eine Liste von Ganzzahlen, die den vom Benutzer
            ausgewählten aktiven Kanälen entsprechen.
        samples_to_display: Die Anzahl der anzuzeigenden Samples.

    Returns:
        Das neue Timer-Intervall in Millisekunden.
    """
    chart_data = json.loads(chart_data_json_str)
    chart_info = json.loads(chart_info_json_str)
    num_channels = int(len(active_channels))
    refresh_rate = 1000*60*60*24  # 1 Tag

    if acq_state == 'running':
        # Den Timer aktivieren, wenn die Anzahl der im Diagramm angezeigten Samples
        # mit der Anzahl der vom HAT-Gerät gelesenen Samples übereinstimmt
        if 0 < chart_info['sample_count'] == chart_data['sample_count']:
            # Die Aktualisierungsrate basierend auf der Menge der angezeigten
            # Daten bestimmen
            refresh_rate = int(num_channels * samples_to_display / 2)
            if refresh_rate < 500:
                refresh_rate = 500  # Minimum von 500 ms

    return refresh_rate


@callback(
    Output('hatSelector', 'disabled'),
    Input('status', 'children')
)
def disable_hat_selector_dropdown(acq_state: str) -> bool:
    """
    Eine Callback-Funktion zum Deaktivieren des HAT-Auswahlmenüs, wenn der
    Anwendungsstatus zu 'configured' oder 'running' wechselt.
    """
    disabled = False
    if acq_state == 'configured' or acq_state == 'running':
        disabled = True
    return disabled


@callback(
    Output('sampleRate', 'disabled'),
    Input('status', 'children')
)
def disable_sample_rate_input(acq_state: str) -> bool:
    """
    Eine Callback-Funktion zum Deaktivieren der Abtastraten-Eingabe, wenn der
    Anwendungsstatus zu 'configured' oder 'running' wechselt.
    """
    disabled = False
    if acq_state == 'configured' or acq_state == 'running':
        disabled = True
    return disabled


@callback(
    Output('samplesToDisplay', 'disabled'),
    Input('status', 'children')
)
def disable_samples_to_disp_input(acq_state: str) -> bool:
    """
    Eine Callback-Funktion zum Deaktivieren der Eingabe der Anzahl von Samples zur Anzeige,
    wenn der Anwendungsstatus zu 'configured' oder 'running' wechselt.
    """
    disabled = False
    if acq_state == 'configured' or acq_state == 'running':
        disabled = True
    return disabled


@callback(
    Output('channelSelections', 'options'),
    Input('status', 'children')
)
def disable_channel_checkboxes(acq_state: str) -> List[Dict[str, Any]]:
    """
    Eine Callback-Funktion zum Deaktivieren der Kontrollkästchen für aktive Kanäle,
    wenn der Anwendungsstatus zu 'configured' oder 'running' wechselt.
    """
    options = []
    for channel in range(MCC118_CHANNEL_COUNT):
        label = f'Kanal {channel}'
        disabled = False
        if acq_state == 'configured' or acq_state == 'running':
            disabled = True
        options.append({'label': label, 'value': channel, 'disabled': disabled})
    return options


@callback(
    Output('startStopButton', 'children'),
    Input('status', 'children')
)
def update_start_stop_button_name(acq_state: str) -> str:
    """
    Eine Callback-Funktion zum Aktualisieren der Beschriftung auf der Schaltfläche,
    wenn sich der Anwendungsstatus ändert.

    Args:
        acq_state: Der Anwendungsstatus "idle", "configured",
            "running" oder "error" - löst den Callback aus.

    Returns:
        Die neue Schaltflächenbeschriftung "Konfigurieren", "Start" oder "Stop"
    """
    output = 'Konfigurieren'
    if acq_state == 'configured':
        output = 'Start'
    elif acq_state == 'running':
        output = 'Stop'
    return output


@callback(
    Output('chartData', 'children'),
    Input('timer', 'n_intervals'),
    Input('status', 'children'),
    State('chartData', 'children'),
    State('samplesToDisplay', 'value'),
    State('channelSelections', 'value')
)
def update_strip_chart_data(
    _n_intervals: int, 
    acq_state: str, 
    chart_data_json_str: str,
    samples_to_display_val: int, 
    active_channels: List[int]
) -> str:
    """
    Eine Callback-Funktion zum Aktualisieren der im chartData HTML-div-Element gespeicherten
    Diagrammdaten. Das chartData-Element wird verwendet, um die vorhandenen Datenwerte zu speichern,
    was den Austausch von Daten zwischen Callback-Funktionen ermöglicht.

    Args:
        _n_intervals: Anzahl der Timer-Intervalle - löst den Callback aus.
        acq_state: Der Anwendungsstatus "idle", "configured",
            "running" oder "error" - löst den Callback aus.
        chart_data_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und die aktuellen Diagrammdaten enthält.
        samples_to_display_val: Die Anzahl der anzuzeigenden Samples.
        active_channels: Eine Liste von Ganzzahlen, die den vom Benutzer
            ausgewählten aktiven Kanälen entsprechen.

    Returns:
        Eine Zeichenfolge, die ein JSON-Objekt mit den aktualisierten Diagrammdaten darstellt.
    """
    updated_chart_data = chart_data_json_str
    samples_to_display = int(samples_to_display_val)
    num_channels = len(active_channels)
    if acq_state == 'running':
        hat = globals()['HAT']
        if hat is not None:
            chart_data = json.loads(chart_data_json_str)

            # Durch Angabe von -1 für den samples_per_channel-Parameter wird das
            # Timeout ignoriert und alle verfügbaren Daten werden gelesen
            read_result = hat.a_in_scan_read(ALL_AVAILABLE, RETURN_IMMEDIATELY)

            if ('hardware_overrun' not in chart_data.keys()
                    or not chart_data['hardware_overrun']):
                chart_data['hardware_overrun'] = read_result.hardware_overrun
            if ('buffer_overrun' not in chart_data.keys()
                    or not chart_data['buffer_overrun']):
                chart_data['buffer_overrun'] = read_result.buffer_overrun

            # Die gelesenen Samples zum chart_data-Objekt hinzufügen
            sample_count = add_samples_to_data(samples_to_display, num_channels,
                                               chart_data, read_result)

            # Die Gesamtzahl der Samples aktualisieren
            chart_data['sample_count'] = sample_count
            updated_chart_data = json.dumps(chart_data)

    elif acq_state == 'configured':
        # Die Daten im Strip-Chart löschen, wenn auf Konfigurieren geklickt wird
        updated_chart_data = init_chart_data(num_channels, samples_to_display)

    return updated_chart_data


def add_samples_to_data(
    samples_to_display: int, 
    num_chans: int, 
    chart_data: Dict[str, Any], 
    read_result: Any
) -> int:
    """
    Fügt die vom mcc118 HAT-Gerät gelesenen Samples zum chart_data-Objekt hinzu,
    das zur Aktualisierung des Strip-Charts verwendet wird.

    Args:
        samples_to_display: Die Anzahl der anzuzeigenden Samples.
        num_chans: Die Anzahl der ausgewählten Kanäle.
        chart_data: Ein Dictionary mit den Daten zur Aktualisierung der
            Strip-Chart-Anzeige.
        read_result: Ein namedtuple mit Status und Daten, die vom mcc118 zurückgegeben werden.

    Returns:
        Die aktualisierte Gesamtzahl der Samples nach dem Hinzufügen der Daten.
    """
    num_samples_read = int(len(read_result.data) / num_chans)
    current_sample_count = int(chart_data['sample_count'])

    # Listen in deque-Objekte mit der auf die Anzahl der anzuzeigenden
    # Samples festgelegten maximalen Länge konvertieren. Dies löscht automatisch
    # die ältesten Daten, wenn neue Daten angehängt werden
    chart_data['samples'] = deque(chart_data['samples'],
                                  maxlen=samples_to_display)
    for chan in range(num_chans):
        chart_data['data'][chan] = deque(chart_data['data'][chan],
                                         maxlen=samples_to_display)

    start_sample = 0
    if num_samples_read > samples_to_display:
        start_sample = num_samples_read - samples_to_display

    for sample in range(start_sample, num_samples_read):
        chart_data['samples'].append(current_sample_count + sample)
        for chan in range(num_chans):
            data_index = sample * num_chans + chan
            chart_data['data'][chan].append(read_result.data[data_index])

    # Deque-Objekte zurück in Listen konvertieren, damit sie in das div-Element
    # geschrieben werden können
    chart_data['samples'] = list(chart_data['samples'])
    for chan in range(num_chans):
        chart_data['data'][chan] = list(chart_data['data'][chan])

    return current_sample_count + num_samples_read


@callback(
    Output('stripChart', 'figure'),
    Input('chartData', 'children'),
    State('channelSelections', 'value')
)
def update_strip_chart(chart_data_json_str: str, active_channels: List[int]) -> Dict[str, Any]:
    """
    Eine Callback-Funktion zum Aktualisieren der Strip-Chart-Anzeige, wenn neue Daten gelesen werden.

    Args:
        chart_data_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und die aktuellen Diagrammdaten enthält - löst den Callback aus.
        active_channels: Eine Liste von Ganzzahlen, die den vom Benutzer
            ausgewählten aktiven Kanälen entspricht.

    Returns:
        Ein Figure-Objekt für einen dash-core-components Graph, aktualisiert mit
        den zuletzt gelesenen Daten.
    """
    data = []
    xaxis_range = [0, 1000]
    chart_data = json.loads(chart_data_json_str)
    if 'samples' in chart_data and chart_data['samples']:
        xaxis_range = [min(chart_data['samples']), max(chart_data['samples'])]
    if 'data' in chart_data:
        data = chart_data['data']

    plot_data = []
    colors = ['#DD3222', '#FFC000', '#3482CB', '#FF6A00',
              '#75B54A', '#808080', '#6E1911', '#806000']
    # Die Seriendaten für jeden aktiven Kanal aktualisieren
    for chan_idx, channel in enumerate(active_channels):
        scatter_serie = go.Scatter(
            x=list(chart_data['samples']),
            y=list(data[chan_idx]),
            name=f'Kanal {channel}',
            marker={'color': colors[channel]}
        )
        plot_data.append(scatter_serie)

    figure = {
        'data': plot_data,
        'layout': go.Layout(
            xaxis=dict(title='Samples', range=xaxis_range),
            yaxis=dict(title='Spannung (V)'),
            margin={'l': 40, 'r': 40, 't': 50, 'b': 40, 'pad': 0},
            showlegend=True,
            title='Messwerte'
        )
    }

    return figure


@callback(
    Output('chartInfo', 'children'),
    Input('stripChart', 'figure'),
    State('chartData', 'children')
)
def update_chart_info(_figure: Dict[str, Any], chart_data_json_str: str) -> str:
    """
    Eine Callback-Funktion zum Festlegen der Sampleanzahl für die Anzahl der Samples,
    die im Diagramm angezeigt wurden.

    Args:
        _figure: Ein Figure-Objekt für einen dash-core-components Graph für
            das Strip-Chart - löst den Callback aus.
        chart_data_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und die aktuellen Diagrammdaten enthält.

    Returns:
        Eine Zeichenfolge, die ein JSON-Objekt mit den Diagramminfos und
        der aktualisierten Sampleanzahl darstellt.
    """
    chart_data = json.loads(chart_data_json_str)
    chart_info = {'sample_count': chart_data['sample_count']}
    return json.dumps(chart_info)


@callback(
    Output('errorDisplay', 'children'),
    Input('chartData', 'children'),
    Input('status', 'children'),
    State('hatSelector', 'value'),
    State('sampleRate', 'value'),
    State('samplesToDisplay', 'value'),
    State('channelSelections', 'value')
)
def update_error_message(
    chart_data_json_str: str, 
    acq_state: str, 
    hat_selection: str,
    sample_rate: float, 
    samples_to_display: int, 
    active_channels: List[int]
) -> str:
    """
    Eine Callback-Funktion zum Anzeigen von Fehlermeldungen.

    Args:
        chart_data_json_str: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und die aktuellen Diagrammdaten enthält - löst den Callback aus.
        acq_state: Der Anwendungsstatus "idle", "configured",
            "running" oder "error" - löst den Callback aus.
        hat_selection: Eine Zeichenfolge, die ein JSON-Objekt darstellt
            und den Deskriptor für das ausgewählte MCC 118 DAQ HAT enthält.
        sample_rate: Der vom Benutzer angegebene Abtastratenwert.
        samples_to_display: Die Anzahl der anzuzeigenden Samples.
        active_channels: Eine Liste von Ganzzahlen, die den vom Benutzer
            ausgewählten aktiven Kanälen entspricht.

    Returns:
        Die anzuzeigende Fehlermeldung.
    """
    error_message = ''
    if acq_state == 'running':
        chart_data = json.loads(chart_data_json_str)
        if ('hardware_overrun' in chart_data.keys()
                and chart_data['hardware_overrun']):
            error_message += 'Hardware-Überlauf aufgetreten; '
        if ('buffer_overrun' in chart_data.keys()
                and chart_data['buffer_overrun']):
            error_message += 'Puffer-Überlauf aufgetreten; '
    elif acq_state == 'error':
        num_active_channels = len(active_channels)
        max_sample_rate = 100000
        if not hat_selection:
            error_message += 'Ungültige HAT-Auswahl; '
        if num_active_channels <= 0:
            error_message += 'Ungültige Kanalauswahl (min 1); '
        else:
            max_sample_rate = 100000 / len(active_channels)
        if sample_rate > max_sample_rate:
            error_message += 'Ungültige Abtastrate (max: '
            error_message += str(max_sample_rate) + '); '
        if samples_to_display <= 1 or samples_to_display > 1000:
            error_message += 'Ungültige Anzahl anzuzeigender Samples (Bereich: 2-1000); '

    return error_message


def get_ip_address() -> str:
    """Hilfsfunktion zum Abrufen der IP-Adresse des Geräts."""
    ip_address = '127.0.0.1'  # Standardmäßig auf localhost
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(('1.1.1.1', 1))  # Muss nicht erreichbar sein
        ip_address = sock.getsockname()[0]
    finally:
        sock.close()

    return ip_address


if __name__ == '__main__':
    # Dies wird nur ausgeführt, wenn das Modul direkt aufgerufen wird.
    app.run(host=get_ip_address(), port=8080, debug=True)