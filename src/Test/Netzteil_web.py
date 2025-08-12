#!/usr/bin/env python3
"""
Web-Steuerprogramm für Labornetzteil.
Bietet eine Flask-Weboberfläche zur Einstellung der Spannung und
zur Überwachung des Stroms.
"""

from flask import Flask, render_template_string, request, jsonify
import spidev
import time
import lgpio
import numpy as np
from sys import stdout
from daqhats import mcc118, OptionFlags, HatIDs, HatError
from daqhats_utils import select_hat_device, chan_list_to_mask
import threading
from datetime import datetime

# ----------------- Globale Konstanten -----------------
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor Stromverstärker
DAC_VREF = 10.75            # Referenzspannung DAC (V)
CS_PIN = 22                 # Chip Select Pin
READ_ALL_AVAILABLE = -1

MAX_STROM_MA = 500.0        # Überstromschutz (mA)
MAX_SPANNUNG_NEGATIV = -10  # minimaler Wert für negative Spannung

# ----------------- Globale Zustandsvariablen -----------------
current_mode = 'positive'   # 'positive' oder 'negative'
kalibrier_tabelle = []      # Liste von (spannung_in_v, dac_wert)
corr_a = 0.0
corr_b = 0.0
spi = None
gpio_handle = -1
hat = None
monitoring_active = False
monitoring_thread = None
dac_value = 0
current_voltage = 0.0
current_current_ma = 0.0
last_error = ""

app = Flask(__name__)

# ----------------- Hardware initialisieren -----------------
def init_hardware():
    """Initialisiert SPI, GPIO und MCC118 DAQ HAT."""
    global spi, gpio_handle, hat, last_error
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
        print("Hardware-Initialisierung erfolgreich.")
        # Setze Initial-Korrekturwerte
        set_correction_values()
    except Exception as e:
        last_error = f"Fehler bei der Hardware-Initialisierung: {e}"
        print(last_error)

def cleanup():
    """Ressourcen freigeben."""
    global monitoring_active
    print("Fahre das System herunter...")
    try:
        if monitoring_active:
            monitoring_active = False
            if monitoring_thread:
                monitoring_thread.join()
        
        write_dac(0) # DAC auf Null setzen
        
        if gpio_handle != -1:
            lgpio.gpio_write(gpio_handle, CS_PIN, 1)
            lgpio.gpio_chip_close(gpio_handle)
        if spi:
            spi.close()
        if hat:
            hat.close()
    except Exception as e:
        print(f"Fehler beim Aufräumen: {e}")

# ----------------- DAC Funktionen -----------------
def write_dac(value):
    """Schreibt 12-bit Wert 0..4095 an DAC (MCP49xx-kompatibel)."""
    global dac_value, last_error
    try:
        if not (0 <= value <= 4095):
            raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
        
        control = 0b0011000000000000 # Für positive Spannung
        if current_mode == 'negative':
            control = 0b1011000000000000 # Für negative Spannung
        
        data = control | (value & 0xFFF)
        high_byte = (data >> 8) & 0xFF
        low_byte  = data & 0xFF
        
        if gpio_handle != -1:
            lgpio.gpio_write(gpio_handle, CS_PIN, 0)
            spi.xfer2([high_byte, low_byte])
            lgpio.gpio_write(gpio_handle, CS_PIN, 1)
        dac_value = value
        last_error = ""
    except Exception as e:
        last_error = f"Fehler beim Schreiben an den DAC: {e}"
        print(last_error)

# ----------------- Kalibrierung (Spannungs-Mapping) -----------------
def kalibrieren(sp_step, settle):
    """
    Fährt DAC in Schritten, misst die Spannung und füllt die Kalibrierungstabelle.
    """
    global kalibrier_tabelle, last_error
    try:
        kalibrier_tabelle.clear()
        
        for dac_wert in range(0, 4096, sp_step):
            write_dac(dac_wert)
            time.sleep(settle)
            spannung = hat.a_in_read(0) # Channel 0 misst Ausgangsspannung
            
            if (current_mode == 'positive' and spannung >= 0) or \
               (current_mode == 'negative' and spannung <= 0):
                kalibrier_tabelle.append((spannung, dac_wert))
                
        kalibrier_tabelle.sort(key=lambda x: x[0])
        last_error = ""
        return True
    except Exception as e:
        last_error = f"Fehler während der Kalibrierung: {e}"
        return False

def spannung_zu_dac_interpoliert(ziel_spannung):
    """
    Findet den passenden DAC-Wert für eine Zielspannung durch lineare Interpolation.
    """
    if not kalibrier_tabelle:
        raise ValueError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")

    u1, d1 = kalibrier_tabelle[0]
    u2, d2 = kalibrier_tabelle[-1]
    
    if ziel_spannung <= u1: return d1
    if ziel_spannung >= u2: return d2
    
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i + 1]
        if u1 <= ziel_spannung <= u2:
            if u2 == u1: return d1
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return int(round(dac))
            
    return kalibrier_tabelle[-1][1]

# ----------------- Strommessung und Korrektur -----------------
def set_correction_values():
    """Setzt die Standardkorrekturwerte basierend auf dem Modus."""
    global corr_a, corr_b
    if current_mode == 'positive':
        corr_a = -0.13473834089564027
        corr_b = 0.07800453738409945
    else: # 'negative'
        corr_a = -0.279388
        corr_b = 1.782842

def apply_strom_korrektur(i_mcc):
    """Wendet die lineare Korrektur auf den MCC-Strommesswert an."""
    return corr_a + corr_b * i_mcc

def read_current_ma():
    """Liest den korrigierten Stromwert vom MCC118-ADC."""
    channel = 4 if current_mode == 'positive' else 5
    v_shunt = hat.a_in_read(channel)
    strom_ma_roh = (v_shunt / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
    return apply_strom_korrektur(strom_ma_roh)

def monitoring_loop():
    """Hintergrund-Thread für die kontinuierliche Überwachung."""
    global current_voltage, current_current_ma, last_error, monitoring_active
    while monitoring_active:
        try:
            # Lese Ausgangsspannung von MCC118 Channel 0
            current_voltage = hat.a_in_read(0)
            
            # Lese Strom und wende Korrektur an
            current_current_ma = read_current_ma()
            
            # Überstromschutz
            if current_current_ma > MAX_STROM_MA:
                print(f"ACHTUNG: Überstrom ({current_current_ma:.3f} mA)! DAC wird auf 0 gesetzt.")
                write_dac(0)
                last_error = f"Überstrom erkannt: {current_current_ma:.3f} mA! DAC auf 0 gesetzt."
            
            last_error = ""
        except Exception as e:
            last_error = f"Fehler bei der Überwachung: {e}"
            print(last_error)
            
        time.sleep(0.5)

# ----------------- Flask-Routen -----------------
@app.route('/')
def index():
    """Rendert die Hauptseite mit der Benutzeroberfläche."""
    global monitoring_thread, monitoring_active
    
    # Starte den Überwachungs-Thread, wenn er nicht läuft
    if not monitoring_thread or not monitoring_thread.is_alive():
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitoring_loop)
        monitoring_thread.daemon = True
        monitoring_thread.start()
    
    # HTML-Template für die Web-Oberfläche
    html_template = """
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Labornetzteil Steuerung</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #f3f4f6; }
            .container { max-width: 900px; }
            .btn { transition: all 0.2s; }
            .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .card { background-color: white; border-radius: 1rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        </style>
    </head>
    <body class="bg-gray-100 flex items-center justify-center min-h-screen p-4">
        <div class="container mx-auto p-8 bg-gray-50 rounded-2xl shadow-xl">
            <h1 class="text-4xl font-bold mb-6 text-center text-gray-800">Labornetzteil Steuerung</h1>

            <!-- Status und Live-Daten -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 text-center">
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-2 text-gray-700">Aktueller Status</h2>
                    <p class="text-gray-600">Modus: <span id="mode" class="font-bold"></span></p>
                    <p class="text-gray-600">DAC-Wert: <span id="dac_val" class="font-bold"></span></p>
                    <p class="text-gray-600">Letzter Fehler: <span id="error_msg" class="font-bold text-red-500"></span></p>
                </div>
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-2 text-gray-700">Live-Messwerte</h2>
                    <p class="text-gray-600">Spannung: <span id="live_voltage" class="font-bold text-blue-600"></span> V</p>
                    <p class="text-gray-600">Strom: <span id="live_current" class="font-bold text-green-600"></span> mA</p>
                </div>
            </div>

            <!-- Steuerungssektionen -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

                <!-- Modus- und Spannungssteuerung -->
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-4 text-gray-700">Spannungseinstellung</h2>
                    <form id="voltage-form" class="space-y-4">
                        <div>
                            <label for="mode-select" class="block text-gray-700 font-medium">Modus wählen:</label>
                            <select id="mode-select" name="mode" class="w-full mt-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500">
                                <option value="positive" selected>Positiv</option>
                                <option value="negative">Negativ</option>
                            </select>
                        </div>
                        <div>
                            <label for="voltage" class="block text-gray-700 font-medium">Spannung in V:</label>
                            <input type="number" id="voltage" name="voltage" step="0.01" class="w-full mt-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500" required>
                        </div>
                        <button type="submit" class="btn w-full bg-blue-600 text-white p-3 rounded-md font-semibold hover:bg-blue-700">Spannung setzen</button>
                    </form>
                </div>

                <!-- Kalibrierung -->
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-4 text-gray-700">Kalibrierung</h2>
                    <form id="calibration-form" class="space-y-4">
                        <div>
                            <label for="step" class="block text-gray-700 font-medium">DAC-Schrittgröße:</label>
                            <input type="number" id="step" name="step" value="100" class="w-full mt-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500" required>
                        </div>
                        <div>
                            <label for="settle" class="block text-gray-700 font-medium">Wartezeit (s):</label>
                            <input type="number" id="settle" name="settle" value="0.1" step="0.01" class="w-full mt-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500" required>
                        </div>
                        <button type="submit" class="btn w-full bg-green-600 text-white p-3 rounded-md font-semibold hover:bg-green-700">Kalibrierung starten</button>
                    </form>
                </div>
            </div>
        </div>

        <script>
            // Skript zur Aktualisierung der Live-Daten
            const fetchData = async () => {
                try {
                    const response = await fetch('/get_data');
                    if (!response.ok) throw new Error('Network response was not ok');
                    const data = await response.json();
                    document.getElementById('mode').textContent = data.current_mode === 'positive' ? 'Positiv' : 'Negativ';
                    document.getElementById('dac_val').textContent = data.dac_value;
                    document.getElementById('live_voltage').textContent = data.current_voltage.toFixed(3);
                    document.getElementById('live_current').textContent = data.current_current_ma.toFixed(3);
                    document.getElementById('error_msg').textContent = data.last_error;
                } catch (error) {
                    console.error('Fetch error:', error);
                }
            };

            // Initiales Laden und periodisches Aktualisieren
            document.addEventListener('DOMContentLoaded', () => {
                fetchData();
                setInterval(fetchData, 1000); // 1-Sekunden-Aktualisierung
            });
            
            // Formular für Spannungs- und Modusänderung
            document.getElementById('voltage-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const mode = formData.get('mode');
                const voltage = formData.get('voltage');
                
                try {
                    const response = await fetch('/set_voltage', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ mode: mode, voltage: parseFloat(voltage) })
                    });
                    const result = await response.json();
                    if (result.error) {
                        alert(result.error);
                    }
                    fetchData();
                } catch (error) {
                    alert('Fehler beim Senden der Spannung: ' + error.message);
                }
            });

            // Formular für Kalibrierung
            document.getElementById('calibration-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const step = formData.get('step');
                const settle = formData.get('settle');

                document.getElementById('error_msg').textContent = "Kalibrierung läuft...";
                try {
                    const response = await fetch('/calibrate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ step: parseInt(step), settle: parseFloat(settle) })
                    });
                    const result = await response.json();
                    if (result.error) {
                        alert(result.error);
                    } else {
                        alert("Kalibrierung erfolgreich!");
                    }
                    fetchData();
                } catch (error) {
                    alert('Fehler beim Starten der Kalibrierung: ' + error.message);
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, current_mode=current_mode)

@app.route('/get_data', methods=['GET'])
def get_data():
    """Gibt die aktuellen Messwerte als JSON zurück."""
    return jsonify({
        'current_mode': current_mode,
        'dac_value': dac_value,
        'current_voltage': current_voltage,
        'current_current_ma': current_current_ma,
        'last_error': last_error
    })

@app.route('/set_voltage', methods=['POST'])
def set_voltage():
    """Empfängt die Spannungseinstellung und setzt den DAC."""
    global current_mode, last_error
    data = request.json
    mode = data.get('mode')
    voltage = data.get('voltage')

    if mode != current_mode:
        current_mode = mode
        set_correction_values()
        kalibrier_tabelle.clear()
        last_error = f"Modus auf '{current_mode}' gewechselt. Bitte Kalibrierung erneut durchführen."
        return jsonify({'error': last_error})

    try:
        dac = spannung_zu_dac_interpoliert(voltage)
        write_dac(dac)
        return jsonify({'success': True})
    except Exception as e:
        last_error = str(e)
        return jsonify({'error': last_error})

@app.route('/calibrate', methods=['POST'])
def calibrate_route():
    """Startet die Kalibrierung."""
    data = request.json
    sp_step = data.get('step')
    settle = data.get('settle')

    if not kalibrieren(sp_step, settle):
        return jsonify({'error': last_error})
    
    return jsonify({'success': True})

if __name__ == "__main__":
    init_hardware()
    # Der Flask-Server wird im Debug-Modus gestartet, damit er bei Änderungen neu lädt.
    # Für den produktiven Einsatz sollte debug=False gesetzt werden.
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
