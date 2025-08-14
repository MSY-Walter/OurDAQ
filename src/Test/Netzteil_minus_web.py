#!/usr/bin/env python3
"""
Einfaches Web-Interface für Labornetzteil – Negative Spannung
Exakt wie das ursprüngliche Programm, nur mit Flask Web-Interface
"""

from flask import Flask, render_template_string, request, redirect, url_for
import spidev
import time
import lgpio
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask
import threading
import signal
import sys

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
current_status = "Bereit"
current_voltage = 0.0
current_current = 0.0

app = Flask(__name__)

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

# ----------------- Kalibrierung (Spannungs-Mapping) -----------------
def kalibrieren(sp_step=32, settle=0.05):
    """
    Führt DAC von 0..4095 mit Schritt sp_step, misst MCC118 Channel 0,
    und füllt kalibrier_tabelle mit (gemessene_spannung_V, dac_wert).
    Nur negative Spannungen werden gespeichert.
    """
    global kalibrier_tabelle, current_status
    kalibrier_tabelle.clear()
    current_status = "Kalibrierung läuft..."
    print("\nStarte Kalibrierung (Negative Spannung)...")
    address = select_hat_device(HatIDs.MCC_118)
    hat = mcc118(address)

    for dac_wert in range(0, 4096, sp_step):
        write_dac(dac_wert)
        time.sleep(settle)
        spannung = hat.a_in_read(0)  # Channel 0 misst Ausgangsspannung
        # Nur negative Spannungen speichern, andere ignorieren
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, dac_wert))
            print(f"  DAC {dac_wert:4d} -> {spannung:8.5f} V")

    # Sicherstellen, dass DAC 4095 auch dabei ist
    if not any(dac == 4095 for _, dac in kalibrier_tabelle):
        write_dac(4095)
        time.sleep(settle)
        spannung = hat.a_in_read(0)
        if spannung <= 0:
            kalibrier_tabelle.append((spannung, 4095))

    write_dac(0)
    kalibrier_tabelle.sort(key=lambda x: x[0])
    current_status = f"Kalibriert ({len(kalibrier_tabelle)} Punkte)"
    print("Kalibrierung abgeschlossen.")

def spannung_zu_dac_interpoliert(ziel_spannung):
    """Lineare Interpolation zwischen Kalibrierpunkten -> DAC-Wert (int)."""
    if not kalibrier_tabelle:
        raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
    if ziel_spannung > 0:
        raise ValueError("Nur negative Spannungen erlaubt.")
    # Randbehandlung
    if ziel_spannung <= kalibrier_tabelle[0][0]:
        return kalibrier_tabelle[0][1]
    if ziel_spannung >= kalibrier_tabelle[-1][0]:
        return kalibrier_tabelle[-1][1]
    # Suche Intervall
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i+1]
        if u1 <= ziel_spannung <= u2:
            if u2 == u1:
                return d1
            # lineare Interpolation
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return int(round(dac))
    raise ValueError("Interpolation fehlgeschlagen.")

# ----------------- Stromkorrektur -----------------
def apply_strom_korrektur(i_mcc_mA):
    return corr_a + corr_b * i_mcc_mA

def kalibriere_stromkorrektur(mcc_list_mA, true_list_mA):
    global corr_a, corr_b
    import numpy as np
    mcc = np.array(mcc_list_mA, dtype=float)
    true = np.array(true_list_mA, dtype=float)
    A = np.vstack([np.ones_like(mcc), mcc]).T
    a, b = np.linalg.lstsq(A, true, rcond=None)[0]
    corr_a, corr_b = float(a), float(b)

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
    print("\nStromüberwachung läuft")

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
                    monitoring_active = False
                    break
            time.sleep(0.1)

    except Exception as e:
        current_status = f"Fehler: {e}"

    finally:
        try:
            hat.a_in_scan_stop()
        except Exception:
            pass
        if monitoring_active:
            current_status = "Überwachung gestoppt"
        monitoring_active = False

# ----------------- Web Routes -----------------
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, 
                                  status=current_status,
                                  voltage=current_voltage,
                                  current=current_current,
                                  corr_a=corr_a,
                                  corr_b=corr_b,
                                  calibrated=len(kalibrier_tabelle) > 0,
                                  monitoring=monitoring_active)

@app.route('/kalibrieren', methods=['POST'])
def web_kalibrieren():
    global monitoring_active
    if monitoring_active:
        return redirect(url_for('index'))
    
    threading.Thread(target=kalibrieren, daemon=True).start()
    time.sleep(0.5)  # Kurz warten damit Status aktualisiert wird
    return redirect(url_for('index'))

@app.route('/spannung_setzen', methods=['POST'])
def web_spannung_setzen():
    global current_voltage, monitoring_active
    
    try:
        ziel = float(request.form['spannung'])
        if ziel > 0 or ziel < MAX_SPANNUNG_NEGATIV:
            return redirect(url_for('index'))
        
        dac = spannung_zu_dac_interpoliert(ziel)
        write_dac(dac)
        current_voltage = ziel
        
        # Stromüberwachung starten
        if not monitoring_active:
            monitoring_active = True
            threading.Thread(target=strom_ueberwachung, daemon=True).start()
            
    except Exception as e:
        print(f"Fehler: {e}")
    
    return redirect(url_for('index'))

@app.route('/stopp')
def web_stopp():
    global monitoring_active, current_voltage, current_current, current_status
    monitoring_active = False
    write_dac(0)
    current_voltage = 0.0
    current_current = 0.0
    current_status = "Gestoppt"
    return redirect(url_for('index'))

@app.route('/korrektur', methods=['POST'])
def web_korrektur():
    try:
        # Parse input pairs
        input_text = request.form['korrektur_daten']
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
            
    except Exception as e:
        print(f"Korrektur Fehler: {e}")
    
    return redirect(url_for('index'))

# ----------------- Cleanup -----------------
def cleanup():
    global monitoring_active
    monitoring_active = False
    write_dac(0)
    spi.close()
    lgpio.gpiochip_close(gpio_handle)

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ----------------- HTML Template -----------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Labornetzteil Steuerung</title>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="2">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        .header { text-align: center; color: #333; border-bottom: 2px solid #007acc; padding-bottom: 10px; }
        .status { background: #e8f4f8; padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid #007acc; }
        .form-group { margin: 15px 0; padding: 15px; background: #f9f9f9; border-radius: 5px; }
        .form-group h3 { margin-top: 0; color: #007acc; }
        input[type="number"], textarea { width: 200px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        textarea { width: 300px; height: 100px; }
        button { padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #007acc; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; font-weight: bold; }
        .btn-warning { background: #ffc107; color: black; }
        .btn:hover { opacity: 0.8; }
        .status-active { color: #28a745; font-weight: bold; }
        .status-error { color: #dc3545; font-weight: bold; }
        .info { background: #d1ecf1; padding: 10px; margin: 10px 0; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Labornetzteil Steuerung</h1>
            <h2>Negative Spannung (-10V bis 0V)</h2>
        </div>

        <div class="status">
            <h3>📊 Aktueller Status</h3>
            <p><strong>System:</strong> 
                {% if 'Überstrom' in status or 'Fehler' in status %}
                    <span class="status-error">{{ status }}</span>
                {% elif monitoring %}
                    <span class="status-active">{{ status }}</span>
                {% else %}
                    {{ status }}
                {% endif %}
            </p>
            <p><strong>Ausgangsspannung:</strong> {{ "%.3f"|format(voltage) }} V</p>
            <p><strong>Ausgangsstrom:</strong> {{ "%.2f"|format(current) }} mA</p>
            <p><strong>Kalibriert:</strong> {{ "Ja" if calibrated else "Nein" }}</p>
            <p><strong>Stromkorrektur:</strong> i_true = {{ "%.6f"|format(corr_a) }} + {{ "%.9f"|format(corr_b) }} * i_mcc</p>
        </div>

        <div class="form-group">
            <h3>🔧 Kalibrierung</h3>
            <form method="POST" action="/kalibrieren">
                <button type="submit" class="btn-warning" 
                        {% if monitoring %}disabled{% endif %}>
                    Kalibrierung starten
                </button>
            </form>
            <div class="info">
                <small>Führt automatische Kalibrierung durch (dauert ca. 1-2 Minuten)</small>
            </div>
        </div>

        <div class="form-group">
            <h3>⚡ Spannung einstellen</h3>
            <form method="POST" action="/spannung_setzen">
                <label>Zielspannung (V): </label>
                <input type="number" name="spannung" step="0.001" min="-10" max="0" value="0" required>
                <button type="submit" class="btn-success" 
                        {% if not calibrated or monitoring %}disabled{% endif %}>
                    Spannung setzen
                </button>
            </form>
            <div class="info">
                <small>Startet automatisch die Stromüberwachung</small>
            </div>
        </div>

        <div class="form-group">
            <h3>🚨 Notaus</h3>
            <a href="/stopp">
                <button class="btn-danger">STOPP - Netzteil AUS</button>
            </a>
            <div class="info">
                <small>Setzt DAC auf 0 und stoppt Überwachung</small>
            </div>
        </div>

        <div class="form-group">
            <h3>📈 Stromkorrektur</h3>
            <form method="POST" action="/korrektur">
                <p>Messwertpaare eingeben (eine Zeile pro Paar: mcc_mA true_mA):</p>
                <textarea name="korrektur_daten" placeholder="6.0 0.328
12.5 0.654
18.2 0.982"></textarea><br>
                <button type="submit" class="btn-primary">Korrektur berechnen</button>
            </form>
            <div class="info">
                <small>Mindestens 2 Messwertpaare erforderlich</small>
            </div>
        </div>

        <div class="info">
            <p><strong>Hinweise:</strong></p>
            <ul>
                <li>Seite aktualisiert sich automatisch alle 2 Sekunden</li>
                <li>Bei Überstrom wird das Netzteil automatisch abgeschaltet</li>
                <li>Kalibrierung muss vor der ersten Nutzung durchgeführt werden</li>
            </ul>
        </div>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    # Automatische Kalibrierung beim Start
    print("Starte automatische Kalibrierung...")
    kalibrieren()
    
    print("Starte Webserver auf Port 5000...")
    print("Zugriff über: http://0.0.0.0:5000")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        cleanup()
