
#!/usr/bin/env python3

"""
Combined web interface for both positive and negative power supply controls.
Integrates logic from Netzteil_plus.py and Netzteil_minus.py exactly, but exposes via Flask API and SocketIO for real-time.
Everything in a single file.
"""

import spidev
import time
import lgpio
from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit
import threading
import queue
import numpy as np
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Shared constants
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
CS_PIN = 22                 # Chip Select Pin
READ_ALL_AVAILABLE = -1

# Hardware initialization (shared)
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b00

gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, CS_PIN)
lgpio.gpio_write(gpio_handle, CS_PIN, 1)  # CS inaktiv (HIGH)

# ----------------- Plus Power Supply -----------------

class PlusPowerSupply:
    def __init__(self):
        self.MAX_STROM_MA = 500.0
        self.kalibrier_tabelle = []
        self.corr_a = -0.13473834089564027
        self.corr_b = 0.07800453738409945
        self.monitor_thread = None
        self.monitor_running = False
        self.hat = None

    def write_dac(self, value):
        if not (0 <= value <= 4095):
            raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
        control = 0b0011000000000000
        data = control | (value & 0xFFF)
        high_byte = (data >> 8) & 0xFF
        low_byte = data & 0xFF
        lgpio.gpio_write(gpio_handle, CS_PIN, 0)
        spi.xfer2([high_byte, low_byte])
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)

    def kalibrieren(self, sp_step=32, settle=0.05):
        self.kalibrier_tabelle.clear()
        emit('plus_output', {'data': "Starte Kalibrierung (Spannungs-Mapping)..."})
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        for dac_wert in range(0, 4096, sp_step):
            self.write_dac(dac_wert)
            time.sleep(settle)
            spannung = hat.a_in_read(0)
            self.kalibrier_tabelle.append((spannung, dac_wert))
            emit('plus_output', {'data': f"DAC {dac_wert:4d} -> {spannung:8.5f} V"})

        if not any(dac == 4095 for _, dac in self.kalibrier_tabelle):
            self.write_dac(4095)
            time.sleep(settle)
            spannung = hat.a_in_read(0)
            if spannung >= 0:
                self.kalibrier_tabelle.append((spannung, 4095))
                emit('plus_output', {'data': f"DAC 4095 -> {spannung:8.5f} V"})

        self.write_dac(0)
        self.kalibrier_tabelle.sort(key=lambda x: x[0])
        emit('plus_output', {'data': f"Kalibrierung abgeschlossen. Gespeicherte Punkte: {len(self.kalibrier_tabelle)}"})

    def spannung_zu_dac_interpoliert(self, ziel_spannung):
        if not self.kalibrier_tabelle:
            raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
        if ziel_spannung <= self.kalibrier_tabelle[0][0]:
            return self.kalibrier_tabelle[0][1]
        if ziel_spannung >= self.kalibrier_tabelle[-1][0]:
            return self.kalibrier_tabelle[-1][1]
        for i in range(len(self.kalibrier_tabelle) - 1):
            u1, d1 = self.kalibrier_tabelle[i]
            u2, d2 = self.kalibrier_tabelle[i+1]
            if u1 <= ziel_spannung <= u2:
                if u2 == u1:
                    return d1
                dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
                return int(round(dac))
        raise ValueError("Interpolation fehlgeschlagen.")

    def kalibriere_stromkorrektur(self, mcc_list_mA, true_list_mA):
        mcc = np.array(mcc_list_mA, dtype=float)
        true = np.array(true_list_mA, dtype=float)
        A = np.vstack([np.ones_like(mcc), mcc]).T
        a, b = np.linalg.lstsq(A, true, rcond=None)[0]
        self.corr_a, self.corr_b = float(a), float(b)
        emit('plus_output', {'data': f"Neue Korrektur gesetzt: a={self.corr_a:.6f} mA, b={self.corr_b:.9f}"})

    def apply_strom_korrektur(self, i_mcc_mA):
        return self.corr_a + self.corr_b * i_mcc_mA

    def strom_ueberwachung(self):
        channels = [4]
        channel_mask = chan_list_to_mask(channels)
        num_channels = len(channels)
        scan_rate = 1000.0
        options = OptionFlags.CONTINUOUS

        address = select_hat_device(HatIDs.MCC_118)
        self.hat = mcc118(address)
        self.hat.a_in_scan_start(channel_mask, 0, scan_rate, options)

        emit('plus_output', {'data': "Stromüberwachung läuft"})
        emit('plus_output', {'data': "Shunt-Spannung (V)   MCC_mA   Korrigiert_mA"})

        while self.monitor_running:
            read_result = self.hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.5)
            if len(read_result.data) >= num_channels:
                shunt_v = read_result.data[-1]
                current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA = self.apply_strom_korrektur(current_mcc_mA)
                emit('plus_output', {'data': f"{shunt_v:10.5f} V   {current_mcc_mA:7.2f} mA   {current_true_mA:9.2f} mA"})

                if current_true_mA > self.MAX_STROM_MA:
                    self.write_dac(0)
                    emit('plus_output', {'data': f"⚠️  ÜBERSTROM: {current_true_mA:.1f} mA > {self.MAX_STROM_MA:.1f} mA  -- DAC auf 0 gesetzt."})
                    break
            time.sleep(0.05)

        if self.hat:
            self.hat.a_in_scan_stop()
            self.hat = None

# ----------------- Minus Power Supply -----------------

class MinusPowerSupply:
    def __init__(self):
        self.MAX_SPANNUNG_NEGATIV = -10
        self.MAX_STROM_MA = 500.0
        self.kalibrier_tabelle = []
        self.corr_a = -0.279388
        self.corr_b = 1.782842
        self.monitor_thread = None
        self.monitor_running = False
        self.hat = None

    def write_dac(self, value):
        if not (0 <= value <= 4095):
            raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
        control = 0b1011000000000000
        data = control | (value & 0xFFF)
        high_byte = (data >> 8) & 0xFF
        low_byte = data & 0xFF
        lgpio.gpio_write(gpio_handle, CS_PIN, 0)
        spi.xfer2([high_byte, low_byte])
        lgpio.gpio_write(gpio_handle, CS_PIN, 1)

    def kalibrieren(self, sp_step=32, settle=0.05):
        self.kalibrier_tabelle.clear()
        emit('minus_output', {'data': "Starte Kalibrierung (Negative Spannung)..."})
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)

        for dac_wert in range(0, 4096, sp_step):
            self.write_dac(dac_wert)
            time.sleep(settle)
            spannung = hat.a_in_read(0)
            if spannung <= 0:
                self.kalibrier_tabelle.append((spannung, dac_wert))
                emit('minus_output', {'data': f"DAC {dac_wert:4d} -> {spannung:8.5f} V"})
            else:
                emit('minus_output', {'data': f"DAC {dac_wert:4d} -> {spannung:8.5f} V (nicht negativ, ignoriert)"})

        if not any(dac == 4095 for _, dac in self.kalibrier_tabelle):
            self.write_dac(4095)
            time.sleep(settle)
            spannung = hat.a_in_read(0)
            if spannung <= 0:
                self.kalibrier_tabelle.append((spannung, 4095))
                emit('minus_output', {'data': f"DAC 4095 -> {spannung:8.5f} V"})

        self.write_dac(0)
        self.kalibrier_tabelle.sort(key=lambda x: x[0])
        emit('minus_output', {'data': f"Kalibrierung abgeschlossen. Gespeicherte Punkte: {len(self.kalibrier_tabelle)}"})

    def spannung_zu_dac_interpoliert(self, ziel_spannung):
        if not self.kalibrier_tabelle:
            raise RuntimeError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
        if ziel_spannung > 0:
            raise ValueError("Nur negative Spannungen erlaubt.")
        if ziel_spannung <= self.kalibrier_tabelle[0][0]:
            return self.kalibrier_tabelle[0][1]
        if ziel_spannung >= self.kalibrier_tabelle[-1][0]:
            return self.kalibrier_tabelle[-1][1]
        for i in range(len(self.kalibrier_tabelle) - 1):
            u1, d1 = self.kalibrier_tabelle[i]
            u2, d2 = self.kalibrier_tabelle[i+1]
            if u1 <= ziel_spannung <= u2:
                if u2 == u1:
                    return d1
                dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
                return int(round(dac))
        raise ValueError("Interpolation fehlgeschlagen.")

    def kalibriere_stromkorrektur(self, mcc_list_mA, true_list_mA):
        mcc = np.array(mcc_list_mA, dtype=float)
        true = np.array(true_list_mA, dtype=float)
        A = np.vstack([np.ones_like(mcc), mcc]).T
        a, b = np.linalg.lstsq(A, true, rcond=None)[0]
        self.corr_a, self.corr_b = float(a), float(b)
        emit('minus_output', {'data': f"Neue Korrektur gesetzt: a={self.corr_a:.6f} mA, b={self.corr_b:.9f}"})

    def apply_strom_korrektur(self, i_mcc_mA):
        return self.corr_a + self.corr_b * i_mcc_mA

    def strom_ueberwachung(self):
        channels = [5]
        channel_mask = chan_list_to_mask(channels)
        num_channels = len(channels)
        scan_rate = 1000.0
        options = OptionFlags.CONTINUOUS

        address = select_hat_device(HatIDs.MCC_118)
        self.hat = mcc118(address)
        self.hat.a_in_scan_start(channel_mask, 0, scan_rate, options)

        emit('minus_output', {'data': "Stromüberwachung läuft"})
        emit('minus_output', {'data': "Shunt-Spannung (V)   MCC_mA   Korrigiert_mA"})

        while self.monitor_running:
            read_result = self.hat.a_in_scan_read(READ_ALL_AVAILABLE, 0.5)
            if len(read_result.data) >= num_channels:
                shunt_v = read_result.data[-1]
                current_mcc_mA = (shunt_v / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
                current_true_mA = self.apply_strom_korrektur(current_mcc_mA)
                emit('minus_output', {'data': f"{shunt_v:10.5f} V   {current_mcc_mA:7.2f} mA   {current_true_mA:9.2f} mA"})

                if current_true_mA > self.MAX_STROM_MA:
                    self.write_dac(0)
                    emit('minus_output', {'data': f"⚠️  ÜBERSTROM: {current_true_mA:.1f} mA > {self.MAX_STROM_MA:.1f} mA  -- DAC auf 0 gesetzt."})
                    break
            time.sleep(0.1)

        if self.hat:
            self.hat.a_in_scan_stop()
            self.hat = None

# Instances
plus_ps = PlusPowerSupply()
minus_ps = MinusPowerSupply()

# API Routes for Plus
@app.route('/api/plus/calibrate', methods=['POST'])
def plus_calibrate():
    threading.Thread(target=plus_ps.kalibrieren).start()
    return jsonify({'status': 'Calibration started'})

@app.route('/api/plus/set_voltage', methods=['POST'])
def plus_set_voltage():
    data = request.json
    try:
        voltage = float(data['voltage'])
        dac = plus_ps.spannung_zu_dac_interpoliert(voltage)
        plus_ps.write_dac(dac)
        emit('plus_output', {'data': f"Spannung eingestellt: {voltage:.3f} V (DAC={dac})"})
        if plus_ps.monitor_thread is None or not plus_ps.monitor_thread.is_alive():
            plus_ps.monitor_running = True
            plus_ps.monitor_thread = threading.Thread(target=plus_ps.strom_ueberwachung)
            plus_ps.monitor_thread.start()
        return jsonify({'status': 'Voltage set'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/plus/stop_monitor', methods=['POST'])
def plus_stop_monitor():
    plus_ps.monitor_running = False
    if plus_ps.monitor_thread:
        plus_ps.monitor_thread.join()
    return jsonify({'status': 'Monitor stopped'})

@app.route('/api/plus/recalibrate_current', methods=['POST'])
def plus_recalibrate_current():
    data = request.json
    measurements = data.get('measurements', [])
    if len(measurements) < 2:
        return jsonify({'error': 'At least 2 points required'}), 400
    mcc_list = [m['mcc_mA'] for m in measurements]
    true_list = [m['true_mA'] for m in measurements]
    plus_ps.kalibriere_stromkorrektur(mcc_list, true_list)
    return jsonify({'status': 'Recalibrated'})

# API Routes for Minus
@app.route('/api/minus/calibrate', methods=['POST'])
def minus_calibrate():
    threading.Thread(target=minus_ps.kalibrieren).start()
    return jsonify({'status': 'Calibration started'})

@app.route('/api/minus/set_voltage', methods=['POST'])
def minus_set_voltage():
    data = request.json
    try:
        voltage = float(data['voltage'])
        if voltage > 0 or voltage < minus_ps.MAX_SPANNUNG_NEGATIV:
            raise ValueError(f"Voltage must be between {minus_ps.MAX_SPANNUNG_NEGATIV} and 0")
        dac = minus_ps.spannung_zu_dac_interpoliert(voltage)
        minus_ps.write_dac(dac)
        emit('minus_output', {'data': f"Spannung eingestellt: {voltage:.3f} V (DAC={dac})"})
        if minus_ps.monitor_thread is None or not minus_ps.monitor_thread.is_alive():
            minus_ps.monitor_running = True
            minus_ps.monitor_thread = threading.Thread(target=minus_ps.strom_ueberwachung)
            minus_ps.monitor_thread.start()
        return jsonify({'status': 'Voltage set'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/minus/stop_monitor', methods=['POST'])
def minus_stop_monitor():
    minus_ps.monitor_running = False
    if minus_ps.monitor_thread:
        minus_ps.monitor_thread.join()
    return jsonify({'status': 'Monitor stopped'})

@app.route('/api/minus/recalibrate_current', methods=['POST'])
def minus_recalibrate_current():
    data = request.json
    measurements = data.get('measurements', [])
    if len(measurements) < 2:
        return jsonify({'error': 'At least 2 points required'}), 400
    mcc_list = [m['mcc_mA'] for m in measurements]
    true_list = [m['true_mA'] for m in measurements]
    minus_ps.kalibriere_stromkorrektur(mcc_list, true_list)
    return jsonify({'status': 'Recalibrated'})

# Frontend HTML with React
@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Labornetzteil Steuerung</title>
  <script src="https://cdn.jsdelivr.net/npm/react@18.2.0/umd/react.production.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@babel/standalone@7.20.15/babel.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/socket.io-client@4.7.2/dist/socket.io.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100">
  <div id="root" class="container mx-auto p-4"></div>
  <script type="text/babel">
    const { useState, useEffect } = React;

    const App = () => {
      const [plusVoltage, setPlusVoltage] = useState('');
      const [minusVoltage, setMinusVoltage] = useState('');
      const [plusMeasurements, setPlusMeasurements] = useState([{ mcc_mA: '', true_mA: '' }]);
      const [minusMeasurements, setMinusMeasurements] = useState([{ mcc_mA: '', true_mA: '' }]);
      const [plusOutput, setPlusOutput] = useState([]);
      const [minusOutput, setMinusOutput] = useState([]);
      const [socket, setSocket] = useState(null);

      useEffect(() => {
        const newSocket = io();
        setSocket(newSocket);

        newSocket.on('plus_output', ({ data }) => {
          setPlusOutput((prev) => [...prev, data].slice(-50));
        });

        newSocket.on('minus_output', ({ data }) => {
          setMinusOutput((prev) => [...prev, data].slice(-50));
        });

        return () => newSocket.close();
      }, []);

      const handleAddMeasurement = (type) => {
        if (type === 'plus') {
          setPlusMeasurements([...plusMeasurements, { mcc_mA: '', true_mA: '' }]);
        } else {
          setMinusMeasurements([...minusMeasurements, { mcc_mA: '', true_mA: '' }]);
        }
      };

      const handleMeasurementChange = (type, index, field, value) => {
        if (type === 'plus') {
          const newMeas = [...plusMeasurements];
          newMeas[index][field] = value;
          setPlusMeasurements(newMeas);
        } else {
          const newMeas = [...minusMeasurements];
          newMeas[index][field] = value;
          setMinusMeasurements(newMeas);
        }
      };

      const handleCalibrate = (type) => {
        fetch(`/api/${type}/calibrate`, { method: 'POST' });
      };

      const handleSetVoltage = (type) => {
        const voltage = type === 'plus' ? plusVoltage : minusVoltage;
        fetch(`/api/${type}/set_voltage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ voltage }),
        });
      };

      const handleStopMonitor = (type) => {
        fetch(`/api/${type}/stop_monitor`, { method: 'POST' });
      };

      const handleRecalibrate = (type) => {
        const measurements = type === 'plus' ? plusMeasurements : minusMeasurements;
        fetch(`/api/${type}/recalibrate_current`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ measurements }),
        });
      };

      return (
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-white rounded shadow">
            <h2 className="text-xl font-bold mb-4">Positive Spannung</h2>
            <button onClick={() => handleCalibrate('plus')} className="bg-blue-500 text-white p-2 rounded mb-2">Kalibrieren</button>
            <input
              type="number"
              value={plusVoltage}
              onChange={(e) => setPlusVoltage(e.target.value)}
              placeholder="Spannung (V)"
              className="border p-2 mb-2 w-full"
            />
            <button onClick={() => handleSetVoltage('plus')} className="bg-green-500 text-white p-2 rounded mb-2">Spannung einstellen</button>
            <button onClick={() => handleStopMonitor('plus')} className="bg-red-500 text-white p-2 rounded mb-4">Überwachung stoppen</button>
            <h3 className="font-bold mb-2">Stromkorrektur</h3>
            {plusMeasurements.map((meas, idx) => (
              <div key={idx} className="flex mb-2">
                <input
                  type="number"
                  value={meas.mcc_mA}
                  onChange={(e) => handleMeasurementChange('plus', idx, 'mcc_mA', e.target.value)}
                  placeholder="MCC mA"
                  className="border p-2 mr-2"
                />
                <input
                  type="number"
                  value={meas.true_mA}
                  onChange={(e) => handleMeasurementChange('plus', idx, 'true_mA', e.target.value)}
                  placeholder="True mA"
                  className="border p-2"
                />
              </div>
            ))}
            <button onClick={() => handleAddMeasurement('plus')} className="bg-gray-500 text-white p-2 rounded mb-2">Punkt hinzufügen</button>
            <button onClick={() => handleRecalibrate('plus')} className="bg-purple-500 text-white p-2 rounded">Rekalibrieren</button>
            <div className="mt-4 h-64 overflow-y-auto bg-gray-100 p-2">
              <h3 className="font-bold">Ausgabe:</h3>
              {plusOutput.map((line, idx) => <p key={idx}>{line}</p>)}
            </div>
          </div>
          <div className="p-4 bg-white rounded shadow">
            <h2 className="text-xl font-bold mb-4">Negative Spannung</h2>
            <button onClick={() => handleCalibrate('minus')} className="bg-blue-500 text-white p-2 rounded mb-2">Kalibrieren</button>
            <input
              type="number"
              value={minusVoltage}
              onChange={(e) => setMinusVoltage(e.target.value)}
              placeholder="Spannung (-10 bis 0 V)"
              className="border p-2 mb-2 w-full"
            />
            <button onClick={() => handleSetVoltage('minus')} className="bg-green-500 text-white p-2 rounded mb-2">Spannung einstellen</button>
            <button onClick={() => handleStopMonitor('minus')} className="bg-red-500 text-white p-2 rounded mb-4">Überwachung stoppen</button>
            <h3 className="font-bold mb-2">Stromkorrektur</h3>
            {minusMeasurements.map((meas, idx) => (
              <div key={idx} className="flex mb-2">
                <input
                  type="number"
                  value={meas.mcc_mA}
                  onChange={(e) => handleMeasurementChange('minus', idx, 'mcc_mA', e.target.value)}
                  placeholder="MCC mA"
                  className="border p-2 mr-2"
                />
                <input
                  type="number"
                  value={meas.true_mA}
                  onChange={(e) => handleMeasurementChange('minus', idx, 'true_mA', e.target.value)}
                  placeholder="True mA"
                  className="border p-2"
                />
              </div>
            ))}
            <button onClick={() => handleAddMeasurement('minus')} className="bg-gray-500 text-white p-2 rounded mb-2">Punkt hinzufügen</button>
            <button onClick={() => handleRecalibrate('minus')} className="bg-purple-500 text-white p-2 rounded">Rekalibrieren</button>
            <div className="mt-4 h-64 overflow-y-auto bg-gray-100 p-2">
              <h3 className="font-bold">Ausgabe:</h3>
              {minusOutput.map((line, idx) => <p key={idx}>{line}</p>)}
            </div>
          </div>
        </div>
      );
    };

    ReactDOM.render(<App />, document.getElementById('root'));
  </script>
</body>
</html>
    ''')

def cleanup():
    print("Aufräumen...")
    try:
        plus_ps.write_dac(0)
        minus_ps.write_dac(0)
    except:
        pass
    try:
        spi.close()
        lgpio.gpiochip_close(gpio_handle)
    except:
        pass
    print("Beendet.")

import atexit
atexit.register(cleanup)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
