#!/usr/bin/env python3
"""
Web-Interface für Labornetzteil – Negative Spannung
- Automatische Kalibrierung (MCC118 Channel 0)
- Lineare Interpolation der Kalibrierpunkte
- Dauerhafte Stromüberwachung (MCC118 Channel 4) in mA
- Lineare Kalibrierkorrektur für MCC-Strommessung (Offset + Gain)
- Überstromschutz: bei > MAX_STROM_MA wird DAC sofort auf 0 gesetzt
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import spidev
import time
import lgpio
import threading
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask
import numpy as np
import atexit

# ----------------- Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin
READ_ALL_AVAILABLE = -1

MAX_SPANNUNG_NEGATIV = -10  # minimaler Wert (negativ)
MAX_STROM_MA = 500.0       # Überstromschutz (mA)

# ----------------- Globale Variablen -----------------
kalibrier_tabelle = []  # Liste von (spannung_in_v, dac_wert)
corr_a = -0.279388
corr_b = 1.782842
monitoring_active = False
monitoring_thread = None
current_voltage = 0.0
current_dac = 0

# Hardware initialisierung
spi = None
gpio_handle = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'netzteil_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# ----------------- Hardware initialisieren -----------------
def init_hardware():
    global spi, gpio_handle
    try:
        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b00

        gpio_handle = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(gpio_handle, CS_PIN)
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)
        return True
    except Exception as e:
        print(f"Hardware Initialisierung fehlgeschlagen: {e}")
        return False

# ----------------- DAC Funktionen -----------------
def write_dac(value):
    """Schreibt 12-bit Wert 0..4095 an DAC (MCP49xx-kompatibel)."""
    global current_dac
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    
    if spi is None or gpio_handle is None:
        raise RuntimeError("Hardware nicht initialisiert")
        
    control = 0b1011000000000000
    data = control | (value & 0xFFF)
    high_byte = (data >> 8) & 0xFF
    low_byte  = data & 0xFF
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)
    spi.xfer2([high_byte, low_byte])
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)
    current_dac = value

# ----------------- Kalibrierung -----------------
def kalibrieren(sp_step=32, settle=0.05):
    global kalibrier_tabelle
    kalibrier_tabelle.clear()
    
    try:
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        for dac_wert in range(0, 4096, sp_step):
            write_dac(dac_wert)
            time.sleep(settle)
            spannung = hat.a_in_read(0)  # Channel 0 misst Ausgangsspannung
            if spannung <= 0:
                kalibrier_tabelle.append((spannung, dac_wert))
                socketio.emit('calibration_update', {
                    'dac': dac_wert, 
                    'voltage': spannung,
                    'progress': int((dac_wert / 4096) * 100)
                })

        # DAC 4095 sicherstellen
        if not any(dac == 4095 for _, dac in kalibrier_tabelle):
            write_dac(4095)
            time.sleep(settle)
            spannung = hat.a_in_read(0)
            if spannung <= 0:
                kalibrier_tabelle.append((spannung, 4095))

        write_dac(0)
        kalibrier_tabelle.sort(key=lambda x: x[0])
        
        socketio.emit('calibration_complete', {
            'points': len(kalibrier_tabelle),
            'min_voltage': kalibrier_tabelle[0][0] if kalibrier_tabelle else 0,
            'max_voltage': kalibrier_tabelle[-1][0] if kalibrier_tabelle else 0
        })
        
        return True
    except Exception as e:
        socketio.emit('error', {'message': f'Kalibrierung fehlgeschlagen: {e}'})
        return False

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

def update_strom_korrektur(mcc_list, true_list):
    global corr_a, corr_b
    try:
        mcc = np.array(mcc_list, dtype=float)
        true = np.array(true_list, dtype=float)
        A = np.vstack([np.ones_like(mcc), mcc]).T
        a, b = np.linalg.lstsq(A, true, rcond=None)[0]
        corr_a, corr_b = float(a), float(b)
        return True
    except Exception:
        return False

# ----------------- Stromüberwachung -----------------
def strom_monitoring_thread():
    global monitoring_active
    
    try:
        channels = [5]
        channel_mask = chan_list_to_mask(channels)
        num_channels = len(channels)
        scan_rate = 1000.0
        options = OptionFlags.CONTINUOUS

        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        hat.a_in_scan_start(channel_mask, 0, scan_rate, options)

        while monitoring_active:
            try:
                read_result = hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.5)
                if len(read_result.data) >= num_channels:
                    shunt_v = read_result.data[-1]
                    current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                    current_true_mA = apply_strom_korrektur(current_mcc_mA)
                    
                    socketio.emit('current_data', {
                        'shunt_voltage': shunt_v,
                        'mcc_current': current_mcc_mA,
                        'true_current': current_true_mA,
                        'dac_value': current_dac,
                        'set_voltage': current_voltage
                    })

                    if current_true_mA > MAX_STROM_MA:
                        write_dac(0)
                        monitoring_active = False
                        socketio.emit('overcurrent', {
                            'current': current_true_mA,
                            'limit': MAX_STROM_MA
                        })
                        break
                        
                time.sleep(0.1)
            except Exception as e:
                break

        try:
            hat.a_in_scan_stop()
        except Exception:
            pass
            
    except Exception as e:
        socketio.emit('error', {'message': f'Stromüberwachung Fehler: {e}'})
    finally:
        monitoring_active = False

# ----------------- Web Routes -----------------
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on('connect')
def handle_connect():
    emit('status', {
        'calibrated': len(kalibrier_tabelle) > 0,
        'monitoring': monitoring_active,
        'current_voltage': current_voltage,
        'current_dac': current_dac,
        'correction_a': corr_a,
        'correction_b': corr_b
    })

@socketio.on('start_calibration')
def handle_calibration(data):
    sp_step = data.get('step', 32)
    settle = data.get('settle', 0.05)
    
    def calibration_worker():
        emit('calibration_started')
        success = kalibrieren(sp_step, settle)
        if not success:
            emit('error', {'message': 'Kalibrierung fehlgeschlagen'})
    
    threading.Thread(target=calibration_worker, daemon=True).start()

@socketio.on('set_voltage')
def handle_set_voltage(data):
    global current_voltage, monitoring_active, monitoring_thread
    
    try:
        target_voltage = float(data['voltage'])
        
        if target_voltage > 0 or target_voltage < MAX_SPANNUNG_NEGATIV:
            emit('error', {'message': f'Spannung muss zwischen {MAX_SPANNUNG_NEGATIV} und 0 V liegen'})
            return
        
        dac_value = spannung_zu_dac_interpoliert(target_voltage)
        write_dac(dac_value)
        current_voltage = target_voltage
        
        # Stromüberwachung starten
        if not monitoring_active:
            monitoring_active = True
            monitoring_thread = threading.Thread(target=strom_monitoring_thread, daemon=True)
            monitoring_thread.start()
        
        emit('voltage_set', {
            'voltage': target_voltage,
            'dac': dac_value,
            'monitoring_started': True
        })
        
    except Exception as e:
        emit('error', {'message': f'Spannungseinstellung fehlgeschlagen: {e}'})

@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    global monitoring_active
    monitoring_active = False
    write_dac(0)
    emit('monitoring_stopped')

@socketio.on('update_correction')
def handle_update_correction(data):
    try:
        mcc_values = [float(x) for x in data['mcc_values']]
        true_values = [float(x) for x in data['true_values']]
        
        if len(mcc_values) != len(true_values) or len(mcc_values) < 2:
            emit('error', {'message': 'Mindestens 2 Wertepaaare erforderlich'})
            return
            
        if update_strom_korrektur(mcc_values, true_values):
            emit('correction_updated', {
                'a': corr_a,
                'b': corr_b
            })
        else:
            emit('error', {'message': 'Korrektur-Update fehlgeschlagen'})
            
    except Exception as e:
        emit('error', {'message': f'Korrektur-Update Fehler: {e}'})

# ----------------- Cleanup -----------------
def cleanup():
    global monitoring_active, spi, gpio_handle
    monitoring_active = False
    
    try:
        if spi:
            write_dac(0)
            spi.close()
    except Exception:
        pass
    
    try:
        if gpio_handle:
            lgpio.gpiochip_close(gpio_handle)
    except Exception:
        pass

atexit.register(cleanup)

# ----------------- HTML Template -----------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Labornetzteil Steuerung - Negative Spannung</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header { background: #2c3e50; color: white; text-align: center; padding: 20px; border-radius: 8px; }
        .status { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .status-item { background: #ecf0f1; padding: 15px; border-radius: 5px; text-align: center; }
        .status-item.active { background: #2ecc71; color: white; }
        .status-item.warning { background: #f39c12; color: white; }
        .status-item.error { background: #e74c3c; color: white; }
        .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .input-group { margin: 10px 0; }
        .input-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .input-group input, .input-group button { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .input-group button { background: #3498db; color: white; border: none; cursor: pointer; }
        .input-group button:hover { background: #2980b9; }
        .input-group button:disabled { background: #95a5a6; cursor: not-allowed; }
        .emergency-stop { background: #e74c3c !important; font-size: 18px; font-weight: bold; }
        .emergency-stop:hover { background: #c0392b !important; }
        .log { height: 200px; overflow-y: auto; background: #2c3e50; color: #2ecc71; font-family: monospace; padding: 10px; border-radius: 4px; }
        .calibration-progress { width: 100%; height: 20px; background: #ecf0f1; border-radius: 10px; overflow: hidden; }
        .calibration-progress-bar { height: 100%; background: #3498db; transition: width 0.3s; }
        .correction-inputs { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Labornetzteil Steuerung</h1>
            <h2>Negative Spannung (-10V bis 0V)</h2>
        </div>

        <div class="card">
            <h3>📊 Status</h3>
            <div class="status">
                <div class="status-item" id="calibration-status">
                    <strong>Kalibrierung</strong><br>
                    <span id="cal-text">Nicht kalibriert</span>
                </div>
                <div class="status-item" id="monitoring-status">
                    <strong>Überwachung</strong><br>
                    <span id="mon-text">Gestoppt</span>
                </div>
                <div class="status-item" id="voltage-status">
                    <strong>Ausgangsspannung</strong><br>
                    <span id="volt-text">0.000 V</span>
                </div>
                <div class="status-item" id="current-status">
                    <strong>Ausgangsstrom</strong><br>
                    <span id="curr-text">0.00 mA</span>
                </div>
            </div>
        </div>

        <div class="controls">
            <div class="card">
                <h3>🔧 Kalibrierung</h3>
                <div class="input-group">
                    <label>Schrittgröße (DAC):</label>
                    <input type="number" id="cal-step" value="32" min="1" max="100">
                </div>
                <div class="input-group">
                    <label>Wartezeit (s):</label>
                    <input type="number" id="cal-settle" value="0.05" step="0.01" min="0.01" max="1">
                </div>
                <div class="input-group">
                    <button id="start-calibration" onclick="startCalibration()">Kalibrierung starten</button>
                </div>
                <div class="calibration-progress hidden" id="cal-progress">
                    <div class="calibration-progress-bar" id="cal-progress-bar"></div>
                </div>
            </div>

            <div class="card">
                <h3>⚡ Spannungssteuerung</h3>
                <div class="input-group">
                    <label>Zielspannung (V):</label>
                    <input type="number" id="target-voltage" step="0.001" min="-10" max="0" value="0">
                </div>
                <div class="input-group">
                    <button id="set-voltage" onclick="setVoltage()" disabled>Spannung einstellen</button>
                </div>
                <div class="input-group">
                    <button class="emergency-stop" onclick="emergencyStop()">🚨 NOTAUS</button>
                </div>
            </div>
        </div>

        <div class="card">
            <h3>📈 Stromkorrektur</h3>
            <p>Geben Sie Messwertpaare ein (MCC-Wert in mA, Echter Wert in mA):</p>
            <div id="correction-pairs">
                <div class="correction-inputs">
                    <input type="number" placeholder="MCC Wert (mA)" step="0.001" class="mcc-input">
                    <input type="number" placeholder="Echter Wert (mA)" step="0.001" class="true-input">
                </div>
            </div>
            <div class="input-group">
                <button onclick="addCorrectionPair()">+ Weiteres Paar hinzufügen</button>
            </div>
            <div class="input-group">
                <button onclick="updateCorrection()">Korrektur aktualisieren</button>
            </div>
            <div class="input-group">
                <strong>Aktuelle Korrektur:</strong>
                <span id="correction-formula">i_true = 0.000 + 1.000 * i_mcc</span>
            </div>
        </div>

        <div class="card">
            <h3>📋 Live-Daten</h3>
            <div class="log" id="data-log"></div>
        </div>
    </div>

    <script>
        const socket = io();
        let isCalibrated = false;
        let isMonitoring = false;

        // Socket Event Handlers
        socket.on('status', function(data) {
            isCalibrated = data.calibrated;
            isMonitoring = data.monitoring;
            updateStatus(data);
            updateCorrectionFormula(data.correction_a, data.correction_b);
        });

        socket.on('calibration_started', function() {
            document.getElementById('cal-progress').classList.remove('hidden');
            document.getElementById('start-calibration').disabled = true;
            logMessage('Kalibrierung gestartet...');
        });

        socket.on('calibration_update', function(data) {
            const progressBar = document.getElementById('cal-progress-bar');
            progressBar.style.width = data.progress + '%';
            logMessage(`Kalibrierung: DAC ${data.dac} -> ${data.voltage.toFixed(5)} V`);
        });

        socket.on('calibration_complete', function(data) {
            isCalibrated = true;
            document.getElementById('cal-progress').classList.add('hidden');
            document.getElementById('start-calibration').disabled = false;
            document.getElementById('set-voltage').disabled = false;
            document.getElementById('calibration-status').className = 'status-item active';
            document.getElementById('cal-text').textContent = `${data.points} Punkte`;
            logMessage(`Kalibrierung abgeschlossen: ${data.points} Punkte, Bereich: ${data.min_voltage.toFixed(3)}V bis ${data.max_voltage.toFixed(3)}V`);
        });

        socket.on('voltage_set', function(data) {
            document.getElementById('volt-text').textContent = `${data.voltage.toFixed(3)} V (DAC: ${data.dac})`;
            logMessage(`Spannung eingestellt: ${data.voltage.toFixed(3)} V`);
            if (data.monitoring_started) {
                isMonitoring = true;
                document.getElementById('monitoring-status').className = 'status-item active';
                document.getElementById('mon-text').textContent = 'Aktiv';
            }
        });

        socket.on('current_data', function(data) {
            document.getElementById('curr-text').textContent = `${data.true_current.toFixed(2)} mA`;
            logMessage(`Strom: ${data.true_current.toFixed(2)} mA (Shunt: ${data.shunt_voltage.toFixed(5)} V)`);
        });

        socket.on('overcurrent', function(data) {
            document.getElementById('current-status').className = 'status-item error';
            document.getElementById('monitoring-status').className = 'status-item error';
            document.getElementById('mon-text').textContent = 'ÜBERSTROM!';
            document.getElementById('volt-text').textContent = '0.000 V';
            logMessage(`⚠️ ÜBERSTROM: ${data.current.toFixed(1)} mA > ${data.limit.toFixed(1)} mA - Netzteil abgeschaltet!`, 'error');
            isMonitoring = false;
        });

        socket.on('monitoring_stopped', function() {
            isMonitoring = false;
            document.getElementById('monitoring-status').className = 'status-item';
            document.getElementById('mon-text').textContent = 'Gestoppt';
            document.getElementById('volt-text').textContent = '0.000 V';
            document.getElementById('curr-text').textContent = '0.00 mA';
            logMessage('Überwachung gestoppt');
        });

        socket.on('correction_updated', function(data) {
            updateCorrectionFormula(data.a, data.b);
            logMessage(`Korrektur aktualisiert: a=${data.a.toFixed(6)}, b=${data.b.toFixed(9)}`);
        });

        socket.on('error', function(data) {
            logMessage(`❌ Fehler: ${data.message}`, 'error');
        });

        // UI Functions
        function updateStatus(data) {
            if (data.calibrated) {
                document.getElementById('calibration-status').className = 'status-item active';
                document.getElementById('cal-text').textContent = 'Bereit';
                document.getElementById('set-voltage').disabled = false;
            }

            if (data.monitoring) {
                document.getElementById('monitoring-status').className = 'status-item active';
                document.getElementById('mon-text').textContent = 'Aktiv';
            }

            document.getElementById('volt-text').textContent = `${data.current_voltage.toFixed(3)} V`;
        }

        function updateCorrectionFormula(a, b) {
            document.getElementById('correction-formula').textContent = 
                `i_true = ${a.toFixed(6)} + ${b.toFixed(9)} * i_mcc`;
        }

        function startCalibration() {
            const step = parseInt(document.getElementById('cal-step').value);
            const settle = parseFloat(document.getElementById('cal-settle').value);
            socket.emit('start_calibration', {step: step, settle: settle});
        }

        function setVoltage() {
            const voltage = parseFloat(document.getElementById('target-voltage').value);
            socket.emit('set_voltage', {voltage: voltage});
        }

        function emergencyStop() {
            socket.emit('stop_monitoring');
        }

        function addCorrectionPair() {
            const container = document.getElementById('correction-pairs');
            const div = document.createElement('div');
            div.className = 'correction-inputs';
            div.innerHTML = `
                <input type="number" placeholder="MCC Wert (mA)" step="0.001" class="mcc-input">
                <input type="number" placeholder="Echter Wert (mA)" step="0.001" class="true-input">
            `;
            container.appendChild(div);
        }

        function updateCorrection() {
            const mccInputs = document.querySelectorAll('.mcc-input');
            const trueInputs = document.querySelectorAll('.true-input');
            
            const mccValues = [];
            const trueValues = [];
            
            for (let i = 0; i < mccInputs.length; i++) {
                const mccVal = parseFloat(mccInputs[i].value);
                const trueVal = parseFloat(trueInputs[i].value);
                
                if (!isNaN(mccVal) && !isNaN(trueVal)) {
                    mccValues.push(mccVal);
                    trueValues.push(trueVal);
                }
            }
            
            if (mccValues.length < 2) {
                alert('Mindestens 2 gültige Wertepaare erforderlich!');
                return;
            }
            
            socket.emit('update_correction', {
                mcc_values: mccValues,
                true_values: trueValues
            });
        }

        function logMessage(message, type = 'info') {
            const log = document.getElementById('data-log');
            const timestamp = new Date().toLocaleTimeString();
            const color = type === 'error' ? '#e74c3c' : '#2ecc71';
            log.innerHTML += `<div style="color: ${color}">[${timestamp}] ${message}</div>`;
            log.scrollTop = log.scrollHeight;
        }

        // Initialize
        logMessage('Webinterface gestartet - Verbinde mit Server...');
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("Initialisiere Hardware...")
    if init_hardware():
        print("Hardware erfolgreich initialisiert")
        print("Starte automatische Kalibrierung...")
        if kalibrieren():
            print("Kalibrierung abgeschlossen")
        print("Starte Webserver...")
        print("Zugriff über: http://0.0.0.0:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    else:
        print("Hardware-Initialisierung fehlgeschlagen!")
