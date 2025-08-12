
#!/usr/bin/env python3
"""
Web-Steuerprogramm für Labornetzteil.
Bietet eine Flask-Weboberfläche zur Einstellung der Spannung und
zur Überwachung des Stroms, die sowohl positive als auch negative
Spannungen unterstützt.
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
SHUNT_WIDERSTAND = 0.1     # Ohm
VERSTAERKUNG = 69.0        # Verstärkungsfaktor Stromverstärker
DAC_VREF = 10.75           # Referenzspannung DAC (V)
CS_PIN = 22                # Chip Select Pin
READ_ALL_AVAILABLE = -1

MAX_STROM_MA = 500.0       # Überstromschutz (mA)
MAX_SPANNUNG_NEGATIV = -10 # minimaler Wert für negative Spannung

# ----------------- Globale Zustandsvariablen -----------------
current_mode = 'positive'  # 'positive' oder 'negative'
kalibrier_tabelle = []     # Liste von (spannung_in_v, dac_wert)
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
        last_error = ""
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
    """Schreibt 12-bit Wert 0..4095 an DAC (MCP4922-kompatibel)."""
    global dac_value, last_error
    try:
        if not (0 <= value <= 4095):
            raise ValueError("DAC-Wert muss zwischen 0 und 4095 liegen.")
        
        # Korrigierte Control-Werte für MCP4922
        if current_mode == 'positive':
            # Kanal A für positive Spannung
            control = 0b0011000000000000  # Kanal A, Puffer ein, Gain 1x, kein Shutdown
        else: # 'negative'
            # Kanal B für negative Spannung  
            control = 0b1011000000000000  # Kanal B, Puffer ein, Gain 1x, kein Shutdown
        
        data = control | (value & 0xFFF)
        high_byte = (data >> 8) & 0xFF
        low_byte  = data & 0xFF
        
        if gpio_handle != -1 and spi:
            lgpio.gpio_write(gpio_handle, CS_PIN, 0)
            spi.xfer2([high_byte, low_byte])
            lgpio.gpio_write(gpio_handle, CS_PIN, 1)
        
        dac_value = value
        print(f"DAC geschrieben: Wert={value}, Modus={current_mode}, Control=0x{control:04x}")
        last_error = ""
    except Exception as e:
        last_error = f"Fehler beim Schreiben an den DAC: {e}"
        print(last_error)

# ----------------- Kalibrierung (Spannungs-Mapping) -----------------
def get_voltage_measurement_channel():
    """Gibt den korrekten ADC-Kanal für die Spannungsmessung zurück."""
    # Annahme: Kanal 0 für positive Spannung, Kanal 1 für negative Spannung
    # Passen Sie dies an Ihre Hardware-Konfiguration an
    return 0 if current_mode == 'positive' else 1

def get_dac_range():
    """Gibt den DAC-Wertebereich für den aktuellen Modus zurück."""
    if current_mode == 'positive':
        return range(0, 4096, 100)  # 0 bis +10V
    else:
        # Für negative Spannungen könnte ein anderer Bereich nötig sein
        # Je nach Hardware-Konfiguration
        return range(0, 4096, 100)  # Anpassung je nach Hardware

def kalibrieren():
    """
    Führt die Kalibrierung basierend auf dem aktuellen Modus durch.
    Korrigierte Version mit verbesserter Logik für negative Spannungen.
    """
    global kalibrier_tabelle, last_error
    kalibrier_tabelle.clear()
    
    if not hat:
        last_error = "Hardware nicht initialisiert!"
        print(last_error)
        return False
    
    print(f"\nStarte Kalibrierung (Modus: {current_mode})...")
    
    voltage_channel = get_voltage_measurement_channel()
    dac_range = get_dac_range()
    
    print(f"Verwende ADC-Kanal {voltage_channel} für Spannungsmessung")
    
    gueltige_punkte = 0
    
    for dac_wert in dac_range:
        try:
            write_dac(dac_wert)
            time.sleep(0.2)  # Längere Wartezeit für Stabilisierung
            
            spannung = hat.a_in_read(voltage_channel)
            
            # Verbesserte Validierungslogik
            spannung_gueltig = False
            
            if current_mode == 'positive':
                # Für positive Spannung: Spannung sollte >= 0 sein
                # Toleranz für kleine negative Werte bei DAC=0
                if spannung >= -0.1:  # Kleine Toleranz
                    spannung_gueltig = True
            else:  # 'negative'
                # Für negative Spannung: Spannung sollte <= 0 sein
                # Toleranz für kleine positive Werte bei DAC=0
                if spannung <= 0.1:  # Kleine Toleranz
                    spannung_gueltig = True
            
            if spannung_gueltig:
                kalibrier_tabelle.append((spannung, dac_wert))
                gueltige_punkte += 1
                print(f"  DAC {dac_wert:4d} -> {spannung:8.5f} V (gespeichert)")
            else:
                print(f"  DAC {dac_wert:4d} -> {spannung:8.5f} V (ignoriert - falscher Polarität)")
                
        except Exception as e:
            print(f"  Fehler bei DAC {dac_wert}: {e}")
            continue

    # Sortieren nach Spannung
    kalibrier_tabelle.sort(key=lambda x: x[0])
    
    # Sicher zurücksetzen
    write_dac(0)
    
    print(f"Kalibrierung abgeschlossen. {gueltige_punkte} gültige Punkte gefunden.")
    
    if gueltige_punkte < 5:  # Mindestens 5 Punkte für brauchbare Interpolation
        last_error = f"WARNUNG: Nur {gueltige_punkte} gültige Kalibrierungspunkte gefunden! Überprüfen Sie die Hardware."
        print(last_error)
        return False
    
    # Debug-Ausgabe der Kalibrierungstabelle
    print("Kalibrierungstabelle:")
    for i, (u, d) in enumerate(kalibrier_tabelle[:5]):  # Erste 5 Punkte
        print(f"  {i}: {u:8.5f} V -> DAC {d}")
    if len(kalibrier_tabelle) > 5:
        print(f"  ... und {len(kalibrier_tabelle)-5} weitere Punkte")
        for i, (u, d) in enumerate(kalibrier_tabelle[-3:], len(kalibrier_tabelle)-3):  # Letzte 3 Punkte
            print(f"  {i}: {u:8.5f} V -> DAC {d}")
    
    last_error = ""
    return True

def spannung_zu_dac_interpoliert(ziel_spannung):
    """
    Findet den passenden DAC-Wert für eine Zielspannung durch lineare Interpolation.
    """
    if not kalibrier_tabelle:
        raise ValueError("Keine Kalibrierdaten vorhanden. Bitte kalibrieren.")
    
    # Validierung der Zielspannung basierend auf dem Modus
    if current_mode == 'negative' and ziel_spannung > 0.1:  # Kleine Toleranz
        raise ValueError("Nur negative Spannungen erlaubt im negativen Modus.")
    
    if current_mode == 'positive' and ziel_spannung < -0.1:  # Kleine Toleranz
        raise ValueError("Nur positive Spannungen erlaubt im positiven Modus.")

    # Grenzfälle
    u_min, d_min = kalibrier_tabelle[0]
    u_max, d_max = kalibrier_tabelle[-1]
    
    print(f"Interpolation: Ziel={ziel_spannung:.3f}V, Bereich=[{u_min:.3f}V bis {u_max:.3f}V]")
    
    # Außerhalb des Bereichs - verwende Grenzwerte
    if current_mode == 'positive':
        if ziel_spannung <= u_min:
            print(f"Zielspannung unter Minimum, verwende DAC {d_min}")
            return d_min
        if ziel_spannung >= u_max:
            print(f"Zielspannung über Maximum, verwende DAC {d_max}")
            return d_max
    else:  # negative
        if ziel_spannung >= u_max:  # Bei negativen Spannungen ist u_max näher an 0
            print(f"Zielspannung über Maximum, verwende DAC {d_max}")
            return d_max
        if ziel_spannung <= u_min:  # u_min ist die negativste Spannung
            print(f"Zielspannung unter Minimum, verwende DAC {d_min}")
            return d_min
    
    # Lineare Interpolation zwischen benachbarten Punkten
    for i in range(len(kalibrier_tabelle) - 1):
        u1, d1 = kalibrier_tabelle[i]
        u2, d2 = kalibrier_tabelle[i + 1]
        
        if current_mode == 'positive':
            if u1 <= ziel_spannung <= u2:
                if abs(u2 - u1) < 1e-6:  # Vermeidung von Division durch Null
                    dac = d1
                else:
                    dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
                dac_int = int(round(dac))
                print(f"Interpoliert zwischen [{u1:.3f}V,DAC{d1}] und [{u2:.3f}V,DAC{d2}] -> DAC{dac_int}")
                return dac_int
        else:  # negative
            if u2 <= ziel_spannung <= u1:  # Bei negativen Spannungen ist die Reihenfolge umgekehrt
                if abs(u2 - u1) < 1e-6:  # Vermeidung von Division durch Null
                    dac = d1
                else:
                    dac = d1 + (d2 - d1) * (ziel_spannung - u1) / (u2 - u1)
                dac_int = int(round(dac))
                print(f"Interpoliert zwischen [{u1:.3f}V,DAC{d1}] und [{u2:.3f}V,DAC{d2}] -> DAC{dac_int}")
                return dac_int
    
    # Fallback (sollte nicht erreicht werden)
    print(f"Fallback: verwende letzten DAC-Wert {d_max}")
    return d_max

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
    print(f"Korrekturwerte gesetzt für {current_mode}: a={corr_a}, b={corr_b}")

def apply_strom_korrektur(i_mcc):
    """Wendet die lineare Korrektur auf den MCC-Strommesswert an."""
    return corr_a + corr_b * i_mcc

def read_current_ma():
    """Liest den korrigierten Stromwert vom MCC118-ADC."""
    try:
        # MCC118 Channel 4 für positiven Strom, 5 für negativen
        channel = 4 if current_mode == 'positive' else 5
        v_shunt = hat.a_in_read(channel)
        strom_ma_roh = (v_shunt / (VERSTAERKUNG * SHUNT_WIDERSTAND)) * 1000.0
        return apply_strom_korrektur(strom_ma_roh)
    except Exception as e:
        print(f"Fehler beim Lesen des Stroms: {e}")
        return 0.0

def monitoring_loop():
    """Hintergrund-Thread für die kontinuierliche Überwachung."""
    global current_voltage, current_current_ma, last_error, monitoring_active
    while monitoring_active:
        try:
            # Lese Ausgangsspannung vom korrekten Kanal
            voltage_channel = get_voltage_measurement_channel()
            current_voltage = hat.a_in_read(voltage_channel)
            
            # Lese Strom und wende Korrektur an
            current_current_ma = read_current_ma()
            
            # Überstromschutz
            if abs(current_current_ma) > MAX_STROM_MA:
                print(f"ACHTUNG: Überstrom ({current_current_ma:.3f} mA)! DAC wird auf 0 gesetzt.")
                write_dac(0)
                last_error = f"Überstrom erkannt: {current_current_ma:.3f} mA! DAC auf 0 gesetzt."
            
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
            #message-box { min-height: 40px; }
            .message-error { background-color: #fee2e2; color: #dc2626; border: 1px solid #dc2626; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold; }
            .message-info { background-color: #dbeafe; color: #1e40af; border: 1px solid #1e40af; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold; }
            .message-success { background-color: #d1fae5; color: #059669; border: 1px solid #059669; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold; }
        </style>
    </head>
    <body class="bg-gray-100 flex items-center justify-center min-h-screen p-4">
        <div class="container mx-auto p-8 bg-gray-50 rounded-2xl shadow-xl">
            <h1 class="text-4xl font-bold mb-6 text-center text-gray-800">Labornetzteil Steuerung</h1>

            <div id="message-box" class="mb-6"></div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 text-center">
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-2 text-gray-700">Aktueller Status</h2>
                    <p class="text-gray-600">Modus: <span id="mode" class="font-bold"></span></p>
                    <p class="text-gray-600">DAC-Wert: <span id="dac_val" class="font-bold"></span></p>
                    <p class="text-gray-600">Kalibr.-Punkte: <span id="cal_points" class="font-bold"></span></p>
                </div>
                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-2 text-gray-700">Live-Messwerte</h2>
                    <p class="text-gray-600">Spannung: <span id="live_voltage" class="font-bold text-blue-600"></span> V</p>
                    <p class="text-gray-600">Strom: <span id="live_current" class="font-bold text-green-600"></span> mA</p>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

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

                <div class="card p-6">
                    <h2 class="text-2xl font-semibold mb-4 text-gray-700">Kalibrierung</h2>
                    <button id="calibrate-btn" class="btn w-full bg-green-600 text-white p-3 rounded-md font-semibold hover:bg-green-700 mb-2">Kalibrierung starten</button>
                    <button id="reset-btn" class="btn w-full bg-red-600 text-white p-3 rounded-md font-semibold hover:bg-red-700">DAC auf 0 setzen</button>
                </div>
            </div>
        </div>

        <script>
            // Funktion zum Anzeigen von Nachrichten im Meldungsfeld
            const showMessage = (message, type = 'info') => {
                const messageBox = document.getElementById('message-box');
                messageBox.className = 'mb-6'; // Basis-Klassen beibehalten
                messageBox.textContent = '';
                if (message) {
                    messageBox.textContent = message;
                    messageBox.classList.add(`message-${type}`);
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
                    document.getElementById('cal_points').textContent = data.calibration_points;
                    document.getElementById('live_voltage').textContent = data.current_voltage.toFixed(3);
                    document.getElementById('live_current').textContent = data.current_current_ma.toFixed(3);
                    
                    // Zeige Fehler oder Kalibrierungsaufforderung im Meldungsfeld an
                    if (data.last_error) {
                        showMessage(data.last_error, 'error');
                    } else if (data.calibration_needed) {
                        showMessage("Bitte kalibrieren Sie das Netzteil für den aktuellen Modus.", 'info');
                    } else {
                        // Nur löschen wenn keine anderen Nachrichten angezeigt werden
                        if (!document.getElementById('message-box').textContent.includes('erfolgreich')) {
                            showMessage("");
                        }
                    }
                } catch (error) {
                    console.error('Fetch error:', error);
                    showMessage('Fehler beim Abrufen der Daten: ' + error.message, 'error');
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
                showMessage("Spannung wird gesetzt...", 'info');
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
                        showMessage(result.error, 'error');
                    } else {
                        showMessage("Spannung erfolgreich gesetzt.", 'success');
                        setTimeout(() => {
                            if (document.getElementById('message-box').textContent.includes('erfolgreich gesetzt')) {
                                showMessage("");
                            }
                        }, 3000);
                    }
                    fetchData();
                } catch (error) {
                    showMessage('Fehler beim Senden der Spannung: ' + error.message, 'error');
                }
            });

            // Button für Kalibrierung
            document.getElementById('calibrate-btn').addEventListener('click', async () => {
                showMessage("Kalibrierung wird gestartet...", 'info');
                try {
                    const response = await fetch('/calibrate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({})
                    });
                    const result = await response.json();
                    
                    if (result.error) {
                        showMessage(result.error, 'error');
                    } else {
                        showMessage("Kalibrierung erfolgreich abgeschlossen.", 'success');
                        setTimeout(() => {
                            if (document.getElementById('message-box').textContent.includes('erfolgreich abgeschlossen')) {
                                showMessage("");
                            }
                        }, 5000);
                    }
                    fetchData();
                } catch (error) {
                    showMessage('Fehler beim Starten der Kalibrierung: ' + error.message, 'error');
                }
            });
            
            // Button für Reset
            document.getElementById('reset-btn').addEventListener('click', async () => {
                try {
                    const response = await fetch('/reset_dac', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({})
                    });
                    const result = await response.json();
                    
                    if (result.error) {
                        showMessage(result.error, 'error');
                    } else {
                        showMessage("DAC auf 0 gesetzt.", 'success');
                        setTimeout(() => {
                            if (document.getElementById('message-box').textContent.includes('DAC auf 0')) {
                                showMessage("");
                            }
                        }, 3000);
                    }
                    fetchData();
                } catch (error) {
                    showMessage('Fehler beim Reset: ' + error.message, 'error');
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
    global kalibrier_tabelle
    return jsonify({
        'current_mode': current_mode,
        'dac_value': dac_value,
        'current_voltage': current_voltage,
        'current_current_ma': current_current_ma,
        'last_error': last_error,
        'calibration_points': len(kalibrier_tabelle),
        'calibration_needed': not bool(kalibrier_tabelle),
    })

@app.route('/set_voltage', methods=['POST'])
def set_voltage():
    """Stellt die Spannung basierend auf dem gewählten Modus ein."""
    global current_mode, last_error
    data = request.json
    
    new_mode = data.get('mode')
    target_voltage = data.get('voltage')

    if new_mode and new_mode != current_mode:
        print(f"Moduswechsel von '{current_mode}' zu '{new_mode}'")
        current_mode = new_mode
        set_correction_values()
        # Bei Moduswechsel Kalibrierungstabelle leeren, um Neukalibrierung zu erzwingen
        kalibrier_tabelle.clear()
        write_dac(0)

    try:
        if not kalibrier_tabelle:
            raise ValueError(f"Bitte kalibrieren Sie das System im '{current_mode}'-Modus, bevor Sie eine Spannung setzen.")
            
        dac_wert = spannung_zu_dac_interpoliert(target_voltage)
        write_dac(dac_wert)
        last_error = ""
        return jsonify({"success": True})
    except Exception as e:
        last_error = f"Fehler beim Setzen der Spannung: {e}"
        print(last_error)
        return jsonify({"error": last_error}), 400

@app.route('/calibrate', methods=['POST'])
def calibrate():
    """Führt die Kalibrierung durch."""
    if kalibrieren():
        return jsonify({"success": True, "message": "Kalibrierung erfolgreich."})
    else:
        return jsonify({"error": last_error}), 400

@app.route('/reset_dac', methods=['POST'])
def reset_dac():
    """Setzt den DAC-Wert auf 0."""
    try:
        write_dac(0)
        global current_voltage, current_current_ma
        current_voltage = 0.0
        current_current_ma = 0.0
        return jsonify({"success": True, "message": "DAC erfolgreich auf 0 gesetzt."})
    except Exception as e:
        last_error = f"Fehler beim Reset des DAC: {e}"
        return jsonify({"error": last_error}), 400

# ----------------- Startpunkt -----------------
if __name__ == '__main__':
    init_hardware()
    try:
        # Standard-Kalibrierung für den initialen positiven Modus
        kalibrieren()
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        cleanup()
