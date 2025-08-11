#!/usr/bin/env python3
"""
Diodenkennlinie Messung
"""

from __future__ import print_function  # Python 2/3 Kompatibilität
import spidev                          # SPI-Kommunikation mit DAC
import time                           # Wartezeiten
import lgpio                          # Moderne GPIO-Steuerung
import matplotlib.pyplot as plt       # Diagramme erstellen

from daqhats import mcc118, OptionFlags, HatIDs    # MCC118 Hardware-Bibliothek
from daqhats_utils import select_hat_device        # Device-Auswahl

# === DAC Hardware-Parameter ===
CS_PIN = 22              # GPIO Pin für Chip Select (SPI)
MAX_DAC_VALUE = 4095     # Maximum DAC-Wert (12-Bit: 2^12 - 1)
MAX_SPANNUNG = 10.7      # Maximale Ausgangsspannung in Volt

# Auflösung berechnen
SPANNUNG_PRO_BIT = MAX_SPANNUNG / MAX_DAC_VALUE  # ≈ 2.61 mV pro Bit

gpio_handle = None

def init_hardware():
    """
    Hardware-Initialisierung mit lgpio
    """
    global gpio_handle
    
    # === lgpio Chip öffnen ===
    gpio_handle = lgpio.gpiochip_open(0)  # GPIO Chip 0 öffnen
    if gpio_handle < 0:
        raise Exception("Fehler beim Öffnen des GPIO Chips")
    
    # === CS Pin als Ausgang konfigurieren ===
    ret = lgpio.gpio_claim_output(gpio_handle, CS_PIN, lgpio.SET_PULL_NONE)
    if ret < 0:
        raise Exception(f"Fehler beim Konfigurieren von GPIO Pin {CS_PIN}")
    
    # CS initial auf HIGH (inaktiv)
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)
    
    # === SPI-Schnittstelle konfigurieren ===
    spi = spidev.SpiDev()
    spi.open(0, 0)              # Bus 0, Device 0
    spi.max_speed_hz = 1000000  # 1 MHz Übertragungsgeschwindigkeit
    spi.mode = 0b00             # SPI Mode 0 (CPOL=0, CPHA=0)
    
    print("✅ Hardware erfolgreich initialisiert (lgpio)")
    return spi

def write_dac(spi, value):
    """
    Schreibt einen Wert an den DAC (0-4095) mit lgpio
    
    Parameter:
    spi: SPI-Objekt
    value: DAC-Wert (0 bis 4095)
    
    DAC-Register-Aufbau (16 Bit):
    - Bit 15: Channel Select (0=A, 1=B) 
    - Bit 14: Buffer Control (1=buffered)
    - Bit 13: Gain Select (0=2x, 1=1x)
    - Bit 12: Shutdown (1=active, 0=shutdown)
    - Bit 11-0: Data (12-Bit DAC-Wert)
    """
    global gpio_handle
    
    # Eingabe validieren
    assert 0 <= value <= MAX_DAC_VALUE, f"DAC-Wert muss zwischen 0 und {MAX_DAC_VALUE} liegen!"
    
    # === Kontrollbits zusammensetzen ===
    control = 0
    control |= 0 << 15  # Channel A auswählen (0)
    control |= 1 << 14  # Buffered Mode aktivieren (1)
    control |= 0 << 13  # Gain = 2x für vollen Spannungsbereich (0)
    control |= 1 << 12  # Normal Operation, nicht Shutdown (1)
    
    # === Datenpaket erstellen ===
    data = control | (value & 0xFFF)  # 12-Bit Daten hinzufügen
    high_byte = (data >> 8) & 0xFF    # Obere 8 Bit
    low_byte = data & 0xFF            # Untere 8 Bit

    # Debug-Ausgabe (optional)
    spannung = (value / MAX_DAC_VALUE) * MAX_SPANNUNG
    print(f"DAC: {value:4d} → {spannung:.3f}V | SPI: 0x{high_byte:02X}{low_byte:02X}")
    
    # === SPI-Übertragung mit lgpio ===
    lgpio.gpio_write(gpio_handle, CS_PIN, 0)     # Chip Select aktivieren
    spi.xfer2([high_byte, low_byte])             # 16-Bit Daten senden
    lgpio.gpio_write(gpio_handle, CS_PIN, 1)     # Chip Select deaktivieren

def cleanup_hardware(spi):
    """
    Hardware-Cleanup mit lgpio
    """
    global gpio_handle
    
    try:
        # DAC auf 0V setzen
        if spi and gpio_handle is not None:
            write_dac(spi, 0)
        
        # SPI schließen
        if spi:
            spi.close()
        
        # GPIO freigeben und Chip schließen
        if gpio_handle is not None:
            lgpio.gpio_free(gpio_handle, CS_PIN)  # Pin freigeben
            lgpio.gpiochip_close(gpio_handle)     # Chip schließen
            gpio_handle = None
            
        print("🧹 Hardware-Cleanup abgeschlossen (lgpio)")
    except Exception as e:
        print(f"⚠️  Cleanup-Fehler: {e}")

def improved_measurement(hat, channel, num_samples=10):
    """
    Verbesserte Spannungsmessung mit Mittelwertbildung
    """
    samples = []
    for _ in range(num_samples):
        samples.append(hat.a_in_read(channel))
        time.sleep(0.001)  # Kurze Pause zwischen Messungen
    
    return sum(samples) / len(samples)  # Mittelwert

def find_threshold(voltages, currents, threshold_current):
    """Findet Schwellenspannung für gegebenen Strom"""
    for v, i in zip(voltages, currents):
        if i >= threshold_current:
            return v
    return None

def analyze_diode_curve(voltages, currents):
    """
    Erweiterte Analyse der Diodenkennlinie
    """
    # Schwellenspannung bestimmen (verschiedene Kriterien)
    thresholds = {
        "1mA": find_threshold(voltages, currents, 0.001),
        "10mA": find_threshold(voltages, currents, 0.010),
        "1% Max": find_threshold(voltages, currents, max(currents) * 0.01)
    }
    
    return thresholds

def main():
    """
    Hauptfunktion für die Diodenkennlinienmessung mit lgpio
    
    Ablauf:
    1. Messparameter vom Benutzer abfragen
    2. Hardware initialisieren
    3. Spannungsrampe fahren und dabei messen
    4. Strom aus Spannung berechnen  
    5. Kennlinien-Diagramme erstellen
    """
    print("=" * 50)
    print("    DIODENKENNLINIE MESSUNG (lgpio)")
    print("=" * 50)

    spi = None
    hat = None

    try:
        # === Hardware initialisieren ===
        spi = init_hardware()
        
        # === Messparameter eingeben ===
        print("\n📋 Messparameter eingeben:")
        r_serie = float(input("Serienwiderstand [Ω] (z.B. 100): "))
        anzahl_punkte = int(input("Anzahl Messpunkte (mind. 15): "))
        
        # Mindestanzahl prüfen
        if anzahl_punkte < 15:
            print("⚠️  Mindestens 15 Punkte für aussagekräftige Kennlinie!")
            anzahl_punkte = 15

        spannung_max = float(input(f"Maximale Spannung [V] (max {MAX_SPANNUNG:.1f}V): "))
        if spannung_max > MAX_SPANNUNG:
            print(f"⚠️  Begrenze auf {MAX_SPANNUNG:.1f}V.")
            spannung_max = MAX_SPANNUNG

        # === MCC118 verbinden ===
        print("\n🔧 Verbinde MCC118...")
        address = select_hat_device(HatIDs.MCC_118)
        hat = mcc118(address)
        print(f"✅ MCC118 an Adresse {address} verbunden.")

        # === Messreihen vorbereiten ===
        eingestellte_spannungen = []  # U_DAC (Sollwert)
        diodenspannungen = []         # U_Diode (gemessen)
        stroeme = []                  # I_Diode (berechnet)

        print(f"\n📊 Starte Messung: 0V → {spannung_max:.1f}V in {anzahl_punkte} Schritten")
        print("=" * 80)
        print("  Nr. |  U_DAC [V] | U_Diode [V] | I_Diode [mA] | DAC-Wert")
        print("-" * 80)
        
        # === Messschleife ===
        for i in range(anzahl_punkte):
            # Spannung linear verteilen (0 bis spannung_max)
            spannung_dac = i * spannung_max / (anzahl_punkte - 1)
            
            # DAC-Wert berechnen
            dac_value = int((spannung_dac / MAX_SPANNUNG) * MAX_DAC_VALUE)
            
            # === DAC setzen ===
            write_dac(spi, dac_value)
            time.sleep(0.05)  # Einschwingzeit abwarten (wichtig!)

            # === Diodenspannung messen ===
            spannung_diode = improved_measurement(hat, 7, 5)  # Kanal 7, 5 Samples

            # === Strom berechnen ===
            strom = (spannung_dac - spannung_diode) / r_serie
            strom_ma = strom * 1000  # Umrechnung in mA für bessere Lesbarkeit

            # === Daten speichern ===
            eingestellte_spannungen.append(spannung_dac)
            diodenspannungen.append(spannung_diode)
            stroeme.append(strom)

            # === Fortschritt anzeigen ===
            print(f" {i+1:3d}. | {spannung_dac:8.3f} | {spannung_diode:9.5f} | "
                  f"{strom_ma:10.3f} | {dac_value:8d}")

        print("\n✅ Messung abgeschlossen!")

        # === Datenanalyse ===
        print(f"\n📈 Analysiere {len(stroeme)} Datenpunkte...")
        
        # Analysiere Kennlinie
        thresholds = analyze_diode_curve(diodenspannungen, stroeme)
        
        print("🔍 Schwellenspannungen:")
        for criterion, voltage in thresholds.items():
            if voltage:
                print(f"   • {criterion}: {voltage:.3f}V")
            else:
                print(f"   • {criterion}: nicht erreicht")

        # === Diagramme erstellen ===
        print("📊 Erstelle Diagramme...")
        
        plt.figure(figsize=(14, 6))

        # === Subplot 1: Klassische I-V Kennlinie ===
        plt.subplot(1, 2, 1)
        plt.plot(diodenspannungen, [i*1000 for i in stroeme], 'ro-', 
                linewidth=2, markersize=4, label='Messdaten')
        plt.xlabel("Diodenspannung U_D [V]", fontsize=11)
        plt.ylabel("Diodenstrom I_D [mA]", fontsize=11) 
        plt.title("Diodenkennlinie (I-V)", fontsize=12, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Schwellenspannung markieren
        if thresholds["1mA"]:
            plt.axvline(thresholds["1mA"], color='orange', linestyle='--', 
                       label=f'Schwelle (1mA) ≈ {thresholds["1mA"]:.3f}V')
            plt.legend()

        # === Subplot 2: Eingangs- vs. Ausgangskennlinie ===
        plt.subplot(1, 2, 2)
        plt.plot(eingestellte_spannungen, [i*1000 for i in stroeme], 'bo-',
                linewidth=2, markersize=4, label='I_D(U_DAC)')
        plt.xlabel("Eingangsspannung U_DAC [V]", fontsize=11)
        plt.ylabel("Diodenstrom I_D [mA]", fontsize=11)
        plt.title("Eingangsspannung vs. Strom", fontsize=12, fontweight='bold')
        plt.xlim(0, spannung_max)
        plt.grid(True, alpha=0.3)
        plt.legend()

        plt.tight_layout()
        plt.show()

        # === Zusammenfassung ausgeben ===
        max_strom = max(stroeme) * 1000
        max_spannung = max(diodenspannungen)
        print(f"\n📋 Messergebnisse:")
        print(f"   • Maximaler Strom: {max_strom:.2f} mA")
        print(f"   • Maximale Diodenspannung: {max_spannung:.3f} V")
        print(f"   • Serienwiderstand: {r_serie:.0f} Ω")

    except KeyboardInterrupt:
        print("\n⚠️  Messung durch Benutzer abgebrochen.")
    except Exception as e:
        print(f"❌ Fehler: {e}")
    finally:
        # === Cleanup (immer ausführen!) ===
        cleanup_hardware(spi)

# === Messung starten ===
if __name__ == "__main__":
    main()