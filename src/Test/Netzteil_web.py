from flask import Flask, request, jsonify, render_template_string
import time
import threading
from datetime import datetime
import numpy as np
from mcculw import ul
from mcculw.enums import ULRange
import Adafruit_MCP4725
import busio
import board

app = Flask(__name__)

# Globale Konstanten
SHUNT_WIDERSTAND = 0.1  # Shunt resistor in ohms
VERSTAERKUNG = 69.0     # Current sense amplifier gain
DAC_VREF = 5.0          # MCP4725 outputs 0-5V
CS_PIN = 22             # Unused for I2C DAC
MAX_STROM_MA = 500.0    # Max current in mA
MAX_SPANNUNG_NEGATIV = -10  # Max negative voltage
MAX_SPANNUNG_POSITIV = 10   # Max positive voltage

# Zustandsvariablen
current_mode = 'positive'
kalibrier_tabelle = []
corr_a = -0.13473834089564027
corr_b = 0.07800453738409945
monitoring_active = False
current_dac = 0
correction_points = []
monitoring_output = ["System initialisiert.", "Bereit für Kalibrierung und Betrieb."]

# Hardware Initialisierung
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    dac = Adafruit_MCP4725.MCP4725(i2c)
    BOARD_NUM = 0
    ul.set_config(70, BOARD_NUM, 0, 0)  # Configure MCC 118
except Exception as e:
    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Hardware-Initialisierungsfehler: {str(e)}")
    raise

def write_dac(value):
    global current_dac
    if value < 0 or value > 4095:
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    try:
        dac.set_voltage(value, False)  # Set DAC output (0-4095 maps to 0-5V)
        current_dac = value
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] DAC gesetzt auf: {value}")
        return True
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] DAC Fehler: {str(e)}")
        raise

def read_mcc118_channel(channel):
    try:
        if channel not in (0, 4, 5):
            raise ValueError(f"Ungültiger Kanal: {channel}")
        value = ul.a_in(BOARD_NUM, channel, ULRange.BIP10VOLTS)
        voltage = ul.to_eng_units(BOARD_NUM, ULRange.BIP10VOLTS, value)
        return voltage
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] MCC118 Fehler: {str(e)}")
        raise

# HTML/CSS/JavaScript (unchanged)
index_html = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Labornetzteil Steuerung</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72, #2a5298);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        .mode-selector {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
        }
        .mode-btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
        }
        .mode-btn.positive {
            background: linear-gradient(45deg, #28a745, #34ce57);
            color: white;
        }
        .mode-btn.negative {
            background: linear-gradient(45deg, #dc3545, #e74c3c);
            color: white;
        }
        .mode-btn.active {
            transform: scale(1.05);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        .mode-btn:not(.active) {
            opacity: 0.6;
        }
        .main-panel {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        .control-panel, .monitoring-panel {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .panel-title {
            font-size: 1.4rem;
            margin-bottom: 20px;
            text-align: center;
            color: #fff;
        }
        .input-group {
            margin-bottom: 20px;
        }
        .input-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
        }
        .input-group input {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: rgba(255,255,255,0.9);
            color: #333;
            font-size: 1rem;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
            margin-bottom: 10px;
        }
        .btn-primary {
            background: linear-gradient(45deg, #007bff, #0056b3);
            color: white;
        }
        .btn-success {
            background: linear-gradient(45deg, #28a745, #1e7e34);
            color: white;
        }
        .btn-warning {
            background: linear-gradient(45deg, #ffc107, #e0a800);
            color: #333;
        }
        .btn-danger {
            background: linear-gradient(45deg, #dc3545, #bd2130);
            color: white;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .status-display {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        .status-item {
            background: rgba(0,0,0,0.2);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .status-value {
            font-size: 1.8rem;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .status-label {
            font-size: 0.9rem;
            opacity: 0.8;
        }
        .monitoring-output {
            background: rgba(0,0,0,0.3);
            padding: 20px;
            border-radius: 10px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            min-height: 200px;
            overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .calibration-panel {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .calibration-input {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
            align-items: center;
        }
        .calibration-input input {
            flex: 1;
            padding: 8px 12px;
            border: none;
            border-radius: 6px;
            background: rgba(255,255,255,0.9);
            color: #333;
        }
        .calibration-input button {
            padding: 8px 15px;
            border: none;
            border-radius: 6px;
            background: #28a745;
            color: white;
            cursor: pointer;
        }
        .alert {
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-weight: bold;
            text-align: center;
            animation: pulse 1s infinite;
        }
        .alert-danger {
            background: rgba(220, 53, 69, 0.9);
            border: 2px solid #dc3545;
        }
        .alert-warning {
            background: rgba(255, 193, 7, 0.9);
            color: #333;
            border: 2px solid #ffc107;
        }
        .alert-success {
            background: rgba(40, 167, 69, 0.9);
            border: 2px solid #28a745;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 15px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(45deg, #28a745, #34ce57);
            transition: width 0.3s ease;
            border-radius: 10px;
        }
        @media (max-width: 768px) {
            .main-panel {
                grid-template-columns: 1fr;
            }
            .mode-selector {
                flex-direction: column;
                align-items: center;
            }
            .status-display {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Labornetzteil Steuerung</h1>
            <p>Präzise Spannungs- und Stromregelung mit Überwachung</p>
        </div>
        <div class="mode-selector">
            <button class="mode-btn positive active" onclick="switchMode('positive')">
                + Positive Spannung
            </button>
            <button class="mode-btn negative" onclick="switchMode('negative')">
                - Negative Spannung
            </button>
        </div>
        <div id="alertContainer"></div>
        <div class="main-panel">
            <div class="control-panel">
                <h2 class="panel-title">Steuerung</h2>
                <div class="status-display">
                    <div class="status-item">
                        <div class="status-value" id="currentVoltage">0.000</div>
                        <div class="status-label">Spannung (V)</div>
                    </div>
                    <div class="status-item">
                        <div class="status-value" id="currentCurrent">0.00</div>
                        <div class="status-label">Strom (mA)</div>
                    </div>
                </div>
                <div class="input-group">
                    <label for="targetVoltage">Zielspannung eingeben:</label>
                    <input type="number" id="targetVoltage" step="0.001" placeholder="0.000">
                </div>
                <button class="btn btn-success" onclick="setVoltage()">
                    🎯 Spannung einstellen
                </button>
                <button class="btn btn-primary" onclick="startMonitoring()">
                    📊 Stromüberwachung starten
                </button>
                <button class="btn btn-warning" onclick="stopMonitoring()">
                    ⏹️ Überwachung stoppen
                </button>
                <button class="btn btn-danger" onclick="emergencyStop()">
                    🚨 NOTAUS
                </button>
            </div>
            <div class="monitoring-panel">
                <h2 class="panel-title">Überwachung</h2>
                <div class="monitoring-output" id="monitoringOutput">
                    System bereit...<br>
                    Kalibrierung wird beim Start durchgeführt...<br>
                </div>
            </div>
        </div>
        <div class="calibration-panel">
            <h2 class="panel-title">🔧 Kalibrierung</h2>
            <div style="margin-bottom: 20px;">
                <button class="btn btn-primary" onclick="startCalibration()">
                    📐 Spannungskalibrierung starten
                </button>
                <div class="progress-bar" style="display: none;" id="calibrationProgress">
                    <div class="progress-fill" id="calibrationFill"></div>
                </div>
            </div>
            <h3 style="margin-bottom: 15px;">Stromkorrektur neu berechnen:</h3>
            <div id="correctionInputs">
                <div class="calibration-input">
                    <input type="number" placeholder="MCC mA" id="mccInput">
                    <input type="number" placeholder="True mA" id="trueInput">
                    <button onclick="addCorrectionPoint()">Hinzufügen</button>
                </div>
            </div>
            <div id="correctionPoints"></div>
            <button class="btn btn-warning" onclick="calculateCorrection()">
                🧮 Korrektur berechnen
            </button>
        </div>
    </div>
    <script>
        let monitoringInterval = null;
        function switchMode(mode) {
            fetch('/switch_mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mode: mode})
            })
            .then(response => response.json())
            .then(data => {
                document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelector(`.mode-btn.${mode}`).classList.add('active');
                updateDisplay(data.voltage, data.current);
                if (data.status === 'success') {
                    showAlert('Modus gewechselt', 'success');
                } else {
                    showAlert(data.message, 'danger');
                }
            });
        }
        function setVoltage() {
            const voltage = document.getElementById('targetVoltage').value;
            fetch('/set_voltage', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({voltage: voltage})
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    updateDisplay(data.voltage, data.current);
                    showAlert(data.messageEOA
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    updateCorrectionPoints(data.points);
                    document.getElementById('mccInput').value = '';
                    document.getElementById('trueInput').value = '';
                    showAlert('Korrekturpunkt hinzugefügt', 'success');
                } else {
                    showAlert(data.message, 'warning');
                }
            });
        }
        function removeCorrectionPoint(index) {
            fetch('/remove_correction_point', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({index: index})
            })
            .then(response => response.json())
            .then(data => {
                updateCorrectionPoints(data.points);
            });
        }
        function calculateCorrection() {
            fetch('/calculate_correction', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                showAlert(data.message, data.status);
            });
        }
        function updateMonitoring() {
            fetch('/get_monitoring_data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('monitoringOutput').innerHTML = data.output.join('<br>');
                    updateDisplay(data.voltage, data.current);
                    if (!data.monitoring_active && monitoringInterval) {
                        clearInterval(monitoringInterval);
                        monitoringInterval = null;
                    }
                });
        }
        function updateDisplay(voltage, current) {
            document.getElementById('currentVoltage').textContent = voltage.toFixed(3);
            document.getElementById('currentCurrent').textContent = current.toFixed(2);
        }
        function showAlert(message, type = 'danger') {
            const alertContainer = document.getElementById('alertContainer');
            const alert = document.createElement('div');
            alert.className = `alert alert-${type}`;
            alert.textContent = message;
            alertContainer.appendChild(alert);
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 5000);
        }
        function updateCorrectionPoints(points) {
            const pointsDiv = document.getElementById('correctionPoints');
            pointsDiv.innerHTML = '';
            points.forEach((point, i) => {
                const pointDiv = document.createElement('div');
                pointDiv.style.cssText = 'background: rgba(0,0,0,0.2); padding: 8px; margin: 5px 0; border-radius: 5px; display: flex; justify-content: space-between; align-items: center;';
                pointDiv.innerHTML = `
                    <span>MCC: ${point.mcc} mA, True: ${point.true} mA</span>
                    <button onclick="removeCorrectionPoint(${i})" style="background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer;">❌</button>
                `;
                pointsDiv.appendChild(pointDiv);
            });
        }
        window.onload = function() {
            updateMonitoring();
            setTimeout(startCalibration, 1000);
        };
        window.onbeforeunload = function() {
            fetch('/stop_monitoring', {method: 'POST', headers: {'Content-Type': 'application/json'}});
            fetch('/emergency_stop', {method: 'POST', headers: {'Content-Type': 'application/json'}});
        };
    </script>
</body>
</html>
"""

# Flask Routen
@app.route('/')
def index():
    return render_template_string(index_html)

@app.route('/switch_mode', methods=['POST'])
def switch_mode():
    global current_mode, corr_a, corr_b
    mode = request.json['mode']
    current_mode = mode
    if mode == 'negative':
        corr_a = -0.279388
        corr_b = 1.782842
    else:
        corr_a = -0.13473834089564027
        corr_b = 0.07800453738409945
    try:
        write_dac(0)
        # Force recalibration after mode switch
        kalibrier_tabelle.clear()
        result = _run_calibration()
        if result['status'] != 'success':
            monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Moduswechsel-Kalibrierung fehlgeschlagen: {result['message']}")
            return jsonify({'status': 'error', 'message': f"Kalibrierung nach Moduswechsel fehlgeschlagen: {result['message']}", 'voltage': 0, 'current': 0})
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Modus gewechselt zu: {'Positive' if mode == 'positive' else 'Negative'} Spannung")
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Korrekturwerte: a={corr_a:.6f}, b={corr_b:.9f}")
        return jsonify({'status': 'success', 'voltage': 0, 'current': 0})
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Moduswechsel-Fehler: {str(e)}")
        return jsonify({'status': 'error', 'message': f"Fehler beim Moduswechsel: {str(e)}", 'voltage': 0, 'current': 0})

@app.route('/set_voltage', methods=['POST'])
def set_voltage():
    try:
        ziel = float(request.json['voltage'])
        if current_mode == 'negative' and (ziel > 0 or ziel < MAX_SPANNUNG_NEGATIV):
            return jsonify({'status': 'error', 'message': f"Bitte nur negative Spannung im Bereich {MAX_SPANNUNG_NEGATIV} bis 0 eingeben!"})
        if current_mode == 'positive' and (ziel < 0 or ziel > MAX_SPANNUNG_POSITIV):
            return jsonify({'status': 'error', 'message': f"Bitte nur positive Spannung im Bereich 0 bis {MAX_SPANNUNG_POSITIV} eingeben!"})
        
        dac = spannung_zu_dac_interpoliert(ziel)
        write_dac(dac)
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Spannung eingestellt: {ziel:.3f} V (DAC={dac})")
        return jsonify({'status': 'success', 'voltage': ziel, 'current': 0, 'message': f"Spannung auf {ziel:.3f} V eingestellt"})
    except ValueError as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Fehler: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Hardware-Fehler: {str(e)}")
        return jsonify({'status': 'error', 'message': "Hardware-Fehler beim Einstellen der Spannung!"})

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    global monitoring_active
    if monitoring_active:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Überwachung läuft bereits.")
        return jsonify({'status': 'warning', 'message': "Überwachung läuft bereits."})
    
    monitoring_active = True
    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Stromüberwachung gestartet - Strg+C zum Beenden")
    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Shunt-Spannung (V)   MCC_mA   Korrigiert_mA")
    
    def monitor():
        global monitoring_active
        while monitoring_active:
            try:
                channel = 4 if current_mode == 'positive' else 5
                shunt_v = read_mcc118_channel(channel)
                current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA = apply_strom_korrektur(current_mcc_mA)
                current_voltage = read_mcc118_channel(0)
                monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] {shunt_v:.5f} V   {current_mcc_mA:.2f} mA   {current_true_mA:.2f} mA")
                
                if current_true_mA > MAX_STROM_MA:
                    write_dac(0)
                    monitoring_active = False
                    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ ÜBERSTROM: {current_true_mA:.1f} mA > {MAX_STROM_MA:.1f} mA -- DAC auf 0 gesetzt (Netzteil AUS).")
                    break
                time.sleep(0.1)
            except Exception as e:
                monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Überwachungsfehler: {str(e)}")
                monitoring_active = False
                break
    
    threading.Thread(target=monitor, daemon=True).start()
    return jsonify({'status': 'success', 'message': "Stromüberwachung gestartet"})

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    global monitoring_active
    if not monitoring_active:
        return jsonify({'status': 'success', 'message': "Überwachung nicht aktiv."})
    monitoring_active = False
    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Überwachung beendet.")
    return jsonify({'status': 'success', 'message': "Überwachung beendet."})

@app.route('/emergency_stop', methods=['POST'])
def emergency_stop():
    global monitoring_active
    try:
        write_dac(0)
        monitoring_active = False
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚨 NOTAUS - DAC auf 0 gesetzt")
        return jsonify({'status': 'success', 'message': "NOTAUS aktiviert - Netzteil abgeschaltet!", 'voltage': 0, 'current': 0})
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] NOTAUS-Fehler: {str(e)}")
        return jsonify({'status': 'error', 'message': "Fehler beim NOTAUS!"})

def _run_calibration():
    global kalibrier_tabelle
    kalibrier_tabelle = []
    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Starte Kalibrierung für {current_mode} Modus...")
    
    sp_step = 32
    settle = 0.05
    total_steps = (4096 // sp_step) + 1
    current_step = 0
    valid_points = 0
    
    try:
        for dac_wert in range(0, 4096, sp_step):
            write_dac(dac_wert)
            time.sleep(settle)
            spannung = read_mcc118_channel(0)
            
            # Relaxed condition to log all points for debugging
            kalibrier_tabelle.append([spannung, dac_wert])
            monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] DAC {dac_wert:4} -> {spannung:.5f} V")
            if (current_mode == 'positive' and spannung >= 0) or (current_mode == 'negative' and spannung <= 0):
                valid_points += 1
            
            current_step += 1
        
        write_dac(4095)
        time.sleep(settle)
        spannung = read_mcc118_channel(0)
        kalibrier_tabelle.append([spannung, 4095])
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] DAC 4095 -> {spannung:.5f} V")
        if (current_mode == 'positive' and spannung >= 0) or (current_mode == 'negative' and spannung <= 0):
            valid_points += 1
        
        write_dac(0)
        kalibrier_tabelle.sort(key=lambda x: x[0])
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Kalibrierung abgeschlossen. {len(kalibrier_tabelle)} Punkte gespeichert, {valid_points} gültig.")
        if valid_points < 10:  # Arbitrary threshold to detect calibration issues
            return {'status': 'warning', 'message': f"Kalibrierung unvollständig: Nur {valid_points} gültige Punkte. Überprüfen Sie die Hardware!", 'progress': 100}
        return {'status': 'success', 'message': "Kalibrierung erfolgreich abgeschlossen!", 'progress': 100}
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Kalibrierungsfehler: {str(e)}")
        return {'status': 'error', 'message': f"Kalibrierungsfehler: {str(e)}", 'progress': 0}

@app.route('/start_calibration', methods=['POST'])
def start_calibration():
    result = _run_calibration()
    return jsonify(result)

@app.route('/add_correction_point', methods=['POST'])
def add_correction_point():
    try:
        mcc = float(request.json['mcc'])
        true_val = float(request.json['true'])
        correction_points.append({'mcc': mcc, 'true': true_val})
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Korrekturpunkt hinzugefügt: MCC={mcc}, True={true_val}")
        return jsonify({'status': 'success', 'points': correction_points})
    except ValueError:
        return jsonify({'status': 'error', 'message': "Bitte gültige Werte eingeben!"})

@app.route('/remove_correction_point', methods=['POST'])
def remove_correction_point():
    index = request.json['index']
    if 0 <= index < len(correction_points):
        correction_points.pop(index)
    return jsonify({'status': 'success', 'points': correction_points})

@app.route('/calculate_correction', methods=['POST'])
def calculate_correction():
    global corr_a, corr_b
    if len(correction_points) < 2:
        return jsonify({'status': 'error', 'message': "Mindestens 2 Korrekturpunkte erforderlich!"})
    
    n = len(correction_points)
    sum_mcc = sum(point['mcc'] for point in correction_points)
    sum_true = sum(point['true'] for point in correction_points)
    sum_mcc_true = sum(point['mcc'] * point['true'] for point in correction_points)
    sum_mcc_sq = sum(point['mcc'] * point['mcc'] for point in correction_points)
    
    new_b = (n * sum_mcc_true - sum_mcc * sum_true) / (n * sum_mcc_sq - sum_mcc * sum_mcc)
    new_a = (sum_true - new_b * sum_mcc) / n
    
    corr_a = new_a
    corr_b = new_b
    
    monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Neue Korrektur berechnet: a={corr_a:.6f} mA, b={corr_b:.9f}")
    return jsonify({'status': 'success', 'message': f"Korrektur aktualisiert: a={corr_a:.6f}, b={corr_b:.9f}"})

@app.route('/get_monitoring_data', methods=['GET'])
def get_monitoring_data():
    try:
        return jsonify({
            'output': monitoring_output[-10:],
            'voltage': read_mcc118_channel(0),
            'current': apply_strom_korrektur((read_mcc118_channel(4 if current_mode == 'positive' else 5) / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0),
            'monitoring_active': monitoring_active
        })
    except Exception as e:
        monitoring_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] Überwachungsfehler: {str(e)}")
        return jsonify({'output': monitoring_output[-10:], 'voltage': 0, 'current': 0, 'monitoring_active': monitoring_active})

def spannung_zu_dac_interpoliert(ziel_spannung):
    if not kalibrier_tabelle:
        raise ValueError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
    
    if current_mode == 'negative' and (ziel_spannung > 0 or ziel_spannung < MAX_SPANNUNG_NEGATIV):
        raise ValueError(f"Nur negative Spannungen im Bereich {MAX_SPANNUNG_NEGATIV} bis 0 erlaubt.")
    if current_mode == 'positive' and (ziel_spannung < 0 or ziel_spannung > MAX_SPANNUNG_POSITIV):
        raise ValueError(f"Nur positive Spannungen im Bereich 0 bis {MAX_SPANNUNG_POSITIV} erlaubt.")
    
    if ziel_spannung <= kalibrier_tabelle[0][0]:
        return kalibrier_tabelle[0][1]
    if ziel_spannung >= kalibrier_tabelle[-1][0]:
        return kalibrier_tabelle[-1][1]
    
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i + 1]
        if u1 <= ziel_spannung <= u2:
            if u2 == u1:
                return d1
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return round(dac)
    
    raise ValueError("Interpolation fehlgeschlagen.")

def apply_strom_korrektur(i_mcc_mA):
    return corr_a + corr_b * i_mcc_mA

if __name__ == '__main__':
    # Starte Kalibrierung nach Serverstart
    threading.Thread(target=_run_calibration, daemon=True).start()
    app.run(debug=True)
