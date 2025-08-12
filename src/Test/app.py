#!/usr/bin/env python3
"""
Web-Steuerprogramm für Labornetzteil.
Bietet eine Flask-Weboberfläche zur Einstellung der Spannung und
zur Überwachung des Stroms, die sowohl positive als auch negative
Spannungen unterstützt.

Dieses Skript wurde gründlich überarbeitet, um eine reibungslose
Funktionalität in beiden Modi zu gewährleisten. Es enthält Mock-Hardware-
Funktionen, die es ermöglichen, die App ohne die tatsächliche Hardware
(MCC118 DAQ HAT und DAC) zu starten und die Oberfläche zu testen.
"""

from flask import Flask, render_template_string, request, jsonify
import threading
import time
from datetime import datetime
import random
import numpy as np
import os

# --- Globale Konstanten ---
# Diese Werte sollten an Ihre tatsächliche Hardware angepasst werden
SHUNT_WIDERSTAND = 0.1      # Ohm
VERSTAERKUNG = 69.0         # Verstärkungsfaktor des Stromverstärkers
DAC_VREF = 10.75            # Referenzspannung DAC (V)
MAX_STROM_MA = 500.0        # Überstromschutz (mA)

# --- Globale Zustandsvariablen ---
current_mode = 'positive'   # 'positive' oder 'negative'
kalibrier_tabelle = []      # Liste von (spannung_in_v, dac_wert)
corr_a = 0.0
corr_b = 0.0
dac_value = 0
current_voltage = 0.0
current_current_ma = 0.0
last_error = ""
monitoring_active = False
monitoring_thread = None

# --- Mock Hardware-Funktionen (für Tests ohne Hardware) ---
# Diese Funktionen simulieren die Interaktion mit dem DAC und dem ADC.
def write_dac_mock(value):
    """Simuliert das Schreiben eines 12-bit Werts an einen DAC."""
    global dac_value
    if not (0 <= value <= 4095):
        raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
    dac_value = value

def read_mcc118_channel_mock(channel):
    """
    Simuliert das Lesen einer Spannung von einem MCC118 ADC-Kanal.
    Die Werte werden anhand des aktuellen DAC-Wertes simuliert, um die
    Funktionalität der Kalibrierung zu testen.
    """
    global dac_value, current_mode
    # Simuliere Channel 0 (Spannung) basierend auf dem DAC-Wert
    if channel == 0:
        # Die Spannungsberechnung wird so simuliert, dass ein linearer
        # Zusammenhang zwischen DAC und Spannung besteht.
        # Im negativen Modus wird die Spannung invertiert.
        if current_mode == 'positive':
            simulated_voltage = (dac_value / 4095.0) * DAC_VREF
        else: # negative
            simulated_voltage = -((4095 - dac_value) / 4095.0) * DAC_VREF
        
        # Füge ein wenig Rauschen hinzu
        return simulated_voltage + random.uniform(-0.01, 0.01)
    
    # Simuliere Channel 4/5 (Strom) basierend auf der Spannung und Rauschen
    elif channel in [4, 5]:
        # Ein einfacher Zusammenhang: Strom steigt mit der Spannung
        simulated_current_v = abs(current_voltage) * random.uniform(0.001, 0.005)
        return simulated_current_v + random.uniform(-0.005, 0.005)

    return 0.0

# --- Echte Hardware-Funktionen (deaktiviert, falls nicht benötigt) ---
# Wenn Sie echte Hardware verwenden, ersetzen Sie die `_mock`-Funktionen
# mit den entsprechenden `daqhats`- und `spidev`-Aufrufen.
def init_hardware_real():
    """Initialisiert SPI, GPIO und MCC118 DAQ HAT (echte Hardware)."""
    # Hier würde der echte Hardware-Initialisierungscode stehen
    # z.B. spidev.SpiDev(), lgpio.gpiochip_open(), mcc118(...)
    print("Echte Hardware-Initialisierung nicht implementiert.")
    pass

def cleanup_real():
    """Ressourcen freigeben (echte Hardware)."""
    # Hier würde der echte Aufräumcode stehen
    print("Echtes Hardware-Aufräumen nicht implementiert.")
    pass

# --- Flask-Anwendung ---
app = Flask(__name__)

# --- DAC- und Kalibrierungslogik ---
def write_dac(value):
    """Schreibt 12-bit Wert an DAC (verwendet die Mock-Funktion)."""
    global last_error
    try:
        write_dac_mock(value) # Oder `write_dac_real(value)`
        last_error = ""
    except Exception as e:
        last_error = f"Fehler beim Schreiben an den DAC: {e}"
        print(last_error)

def read_mcc118_channel(channel):
    """Liest einen Kanal vom MCC118 (verwendet die Mock-Funktion)."""
    return read_mcc118_channel_mock(channel) # Oder `read_mcc118_channel_real(channel)`

def kalibrieren():
    """
    Führt die Kalibrierung basierend auf dem aktuellen Modus durch.
    Im negativen Modus iterieren wir die DAC-Werte in umgekehrter
    Reihenfolge.
    """
    global kalibrier_tabelle, last_error
    kalibrier_tabelle.clear()
    
    print(f"\nStarte Kalibrierung (Modus: {current_mode})...")
    
    # Im negativen Modus kalibrieren wir von 4095 nach 0, um die
    # korrekte Zuordnung zu den negativen Spannungen zu finden.
    dac_range = range(0, 4096, 100) if current_mode == 'positive' else range(4095, -1, -100)

    for dac_wert in dac_range:
        write_dac(dac_wert)
        time.sleep(0.2) # Wartezeit für Stabilität
        spannung = read_mcc118_channel(0)  # Channel 0 misst Ausgangsspannung
        
        kalibrier_tabelle.append((spannung, dac_wert))
        print(f"  DAC {dac_wert:4d} -> {spannung:8.5f} V")

    # Sortieren nach Spannung, um eine korrekte lineare Interpolation zu gewährleisten.
    # Dies ist für beide Modi wichtig.
    kalibrier_tabelle.sort(key=lambda x: x[0])
    
    write_dac(0) # DAC sicher zurücksetzen
    print("Kalibrierung abgeschlossen.")
    if len(kalibrier_tabelle) < 2:
        last_error = "ACHTUNG: Mindestens 2 Kalibrierungspunkte erforderlich!"
    return True

def spannung_zu_dac_interpoliert(ziel_spannung):
    """
    Findet den passenden DAC-Wert für eine Zielspannung durch
    lineare Interpolation der Kalibrierpunkte.
    """
    if not kalibrier_tabelle:
        raise ValueError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
        
    u_vals = np.array([pt[0] for pt in kalibrier_tabelle])
    d_vals = np.array([pt[1] for pt in kalibrier_tabelle])

    # Überprüfen, ob die Zielspannung innerhalb des kalibrierten Bereichs liegt
    min_u = min(u_vals)
    max_u = max(u_vals)
    
    if ziel_spannung < min_u:
        return int(d_vals[np.argmin(u_vals)])
    if ziel_spannung > max_u:
        return int(d_vals[np.argmax(u_vals)])
    
    # Finden der beiden Kalibrierpunkte, zwischen denen die Zielspannung liegt
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i + 1]
        
        # Sicherstellen, dass die Punkte in der richtigen Reihenfolge sind
        if u1 > u2:
            u1, u2 = u2, u1
            d1, d2 = d2, d1
            
        if u1 <= ziel_spannung <= u2:
            if u2 == u1: return int(d1)
            dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
            return int(round(dac))
            
    return kalibrier_tabelle[-1][1]

def set_correction_values():
    """Setzt die Standardkorrekturwerte für den aktuellen Modus."""
    global corr_a, corr_b
    if current_mode == 'positive':
        corr_a = -0.134738
        corr_b = 0.078004
    else: # 'negative'
        corr_a = -0.279388
        corr_b = 1.782842

def apply_strom_korrektur(i_mcc):
    """Wendet die lineare Korrektur auf den MCC-Strommesswert an."""
    global corr_a, corr_b
    return corr_a + corr_b * i_mcc

def monitoring_loop():
    """Hintergrund-Thread für die kontinuierliche Überwachung."""
    global current_voltage, current_current_ma, last_error, monitoring_active
    while monitoring_active:
        try:
            current_voltage = read_mcc118_channel(0)
            
            # MCC118 Channel 4 für positiven Strom, 5 für negativen
            channel = 4 if current_mode == 'positive' else 5
            v_shunt = read_mcc118_channel(channel)
            strom_ma_roh = (v_shunt / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
            current_current_ma = apply_strom_korrektur(strom_ma_roh)
            
            # Überstromschutz
            if current_current_ma > MAX_STROM_MA:
                print(f"ACHTUNG: Überstrom ({current_current_ma:.3f} mA)! DAC auf 0 gesetzt.")
                write_dac(0)
                last_error = f"Überstrom erkannt: {current_current_ma:.3f} mA! DAC auf 0 gesetzt."
            
        except Exception as e:
            last_error = f"Fehler bei der Überwachung: {e}"
            print(last_error)
            
        time.sleep(0.5)

# --- Flask-Routen und HTML-Template ---
@app.route('/')
def index():
    """Rendert die Hauptseite mit der Benutzeroberfläche."""
    global monitoring_thread, monitoring_active
    
    # Starte den Überwachungs-Thread, wenn er nicht läuft
    if not monitoring_thread or not monitoring_thread.is_alive():
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
    
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
            #message-box { min-height: 40px; }
            .message-error { background-color: #fee2e2; color: #dc2626; border: 1px solid #dc2626; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold; }
            .message-info { background-color: #dbeafe; color: #1e40af; border: 1px solid #1e40af; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold; }
            .input-group { display: flex; align-items: center; }
            .input-group span { min-width: 3rem; text-align: right; margin-right: 0.5rem; }
            .input-group input { flex-grow: 1; }
        </style>
    </head>
    <body class="bg-gray-100 flex items-center justify-center min-h-screen p-4">
        <div class="container mx-auto p-8 bg-gray-50 rounded-2xl shadow-xl">
            <h1 class="text-4xl font-bold mb-6 text-center text-gray-800">Labornetzteil Steuerung</h1>

            <!-- Meldungsfeld -->
            <div id="message-box" class="mb-6"></div>

            <!-- Status und Live-Daten -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 text-center">
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-2 text-gray-700">Aktueller Status</h2>
                    <p class="text-gray-600">Modus: <span id="mode" class="font-bold"></span></p>
                    <p class="text-gray-600">DAC-Wert: <span id="dac_val" class="font-bold"></span></p>
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
                    <div class="space-y-4">
                        <div>
                            <label for="mode-select" class="block text-gray-700 font-medium">Modus wählen:</label>
                            <select id="mode-select" name="mode" class="w-full mt-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500">
                                <option value="positive" selected>Positiv</option>
                                <option value="negative">Negativ</option>
                            </select>
                        </div>
                        <form id="voltage-form" class="space-y-4">
                            <div>
                                <label for="voltage" class="block text-gray-700 font-medium">Spannung in V:</label>
                                <input type="number" id="voltage" name="voltage" step="0.01" class="w-full mt-1 p-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500" required>
                            </div>
                            <button type="submit" class="btn w-full bg-blue-600 text-white p-3 rounded-md font-semibold hover:bg-blue-700">Spannung setzen</button>
                        </form>
                    </div>
                </div>

                <!-- Kalibrierung -->
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-4 text-gray-700">Kalibrierung</h2>
                    <button id="calibrate-btn" class="btn w-full bg-green-600 text-white p-3 rounded-md font-semibold hover:bg-green-700">Kalibrierung starten</button>
                </div>
            </div>
        </div>

        <script>
            // Funktion zum Anzeigen von Nachrichten im Meldungsfeld
            const showMessage = (message, type = 'info') => {
                const messageBox = document.getElementById('message-box');
                messageBox.innerHTML = ''; // Entfernt alte Inhalte
                if (message) {
                    messageBox.innerHTML = `<div class="message-${type}">${message}</div>`;
                }
            };
            
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
                    
                    if (data.last_error) {
                        showMessage(data.last_error, 'error');
                    } else if (data.calibration_needed) {
                        showMessage("Bitte kalibrieren Sie das Netzteil für den aktuellen Modus.", 'info');
                    } else {
                        showMessage("");
                    }
                } catch (error) {
                    console.error('Fetch error:', error);
                    showMessage('Fehler beim Abrufen der Daten: ' + error.message, 'error');
                }
            };
            
            document.addEventListener('DOMContentLoaded', () => {
                fetchData();
                setInterval(fetchData, 1000);
            });
            
            // Formular für Spannungs- und Modusänderung
            document.getElementById('voltage-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                showMessage("Spannung wird gesetzt...", 'info');
                const formData = new FormData(e.target);
                const mode = document.getElementById('mode-select').value;
                const voltage = formData.get('voltage');
                
                try {
                    const response = await fetch('/set_voltage', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ mode: mode, voltage: parseFloat(voltage) })
                    });
                    const result = await response.json();
                    if (result.error) {
                        showMessage(result.error, 'error');
                    } else {
                        showMessage("Spannung erfolgreich gesetzt.", 'info');
                    }
                    fetchData();
                } catch (error) {
                    showMessage('Fehler beim Senden der Spannung: ' + error.message, 'error');
                }
            });

            // Button für Kalibrierung
            document.getElementById('calibrate-btn').addEventListener('click', async () => {
                const selectedMode = document.getElementById('mode-select').value;
                showMessage("Kalibrierung wird gestartet...", 'info');
                try {
                    const response = await fetch('/calibrate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ mode: selectedMode })
                    });
                    const result = await response.json();
                    
                    if (result.error) {
                         showMessage(result.error, 'error');
                    } else {
                        showMessage("Kalibrierung erfolgreich abgeschlossen. Bitte Spannung setzen.", 'info');
                    }
                    fetchData();
                } catch (error) {
                    showMessage('Fehler beim Starten der Kalibrierung: ' + error.message, 'error');
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/get_data', methods=['GET'])
def get_data():
    """Gibt die aktuellen Messwerte als JSON zurück."""
    global kalibrier_tabelle
    return jsonify({
        'current_mode': current_mode,
        'dac_value': dac_value,
        'current_voltage': current_voltage,
        'current_current_ma': current_current_ma,
        'last_error': last_error,
        'calibration_needed': not bool(kalibrier_tabelle)
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
        if current_mode == 'positive' and voltage < 0:
            raise ValueError("Im positiven Modus ist nur eine Spannung >= 0V erlaubt.")
        if current_mode == 'negative' and voltage > 0:
            raise ValueError("Im negativen Modus ist nur eine Spannung <= 0V erlaubt.")

        dac = spannung_zu_dac_interpoliert(voltage)
        write_dac(dac)
        return jsonify({'success': True})
    except Exception as e:
        last_error = str(e)
        return jsonify({'error': last_error})

@app.route('/calibrate', methods=['POST'])
def calibrate_route():
    """Startet die Kalibrierung."""
    global last_error, current_mode
    data = request.json
    selected_mode = data.get('mode')
    
    current_mode = selected_mode 
    set_correction_values() 
    
    try:
        kalibrieren()
        last_error = "" 
        return jsonify({'success': True, 'message': 'Kalibrierung gestartet.'})
    except Exception as e:
        last_error = str(e)
        return jsonify({'error': last_error})


if __name__ == "__main__":
    try:
        # Hier würden Sie init_hardware_real() aufrufen, wenn Sie echte Hardware haben
        set_correction_values()
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        # Hier würden Sie cleanup_real() aufrufen, wenn Sie echte Hardware haben
        pass
