#!/usr/bin/env python3

import time
import lgpio
from daqhats import mcc118, HatIDs
from daqhats_utils import select_hat_device

# ======================================
# KONSTANTEN
# ======================================

V_REF = 2.5  # Referenzspannung z. B. LM285-Z2.5

GAIN_A1 = 25
R_SHUNT_A1 = 0.1  # Ohm → Bereich ±0.8 A

GAIN_A4 = 200
R_SHUNT_A4 = 1.0  # Ohm → Bereich ±10 mA

MUX_GPIO_PIN = 17  # GPIO zum Umschalten des Multiplexers (BCM Nummer)
ADC_CHANNEL = 1    # Kanal am MCC 118 (0–7) für die INA190-Ausgabe

# ======================================
# INITIALISIERUNG
# ======================================

# Multiplexer GPIO initialisieren
gpio_handle = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(gpio_handle, MUX_GPIO_PIN)

# MCC 118 Gerät auswählen & initialisieren
ADDRESS = select_hat_device(HatIDs.MCC_118)
hat = mcc118(ADDRESS)

print(f"MCC 118 @ Adresse {ADDRESS} auf Kanal {ADC_CHANNEL}")
print(f"Multiplexer-Steuerung über GPIO {MUX_GPIO_PIN}\n")

# ======================================
# FUNKTIONEN
# ======================================

def read_voltage():
    """Spannung vom INA-Ausgang lesen (via MCC 118)."""
    return hat.a_in_read(ADC_CHANNEL)

def calculate_current(vout, gain, r_shunt):
    """Berechne Strom aus Vout, Gain & Rshunt."""
    #return (vout - V_REF) / (gain * r_shunt)
    return (vout) / (gain * r_shunt)

def read_current(mode='A1'):
    """Strom messen im gewünschten Modus: 'A1' oder 'A4'."""
    if mode == 'A1':
        lgpio.gpio_write(gpio_handle, MUX_GPIO_PIN, 1)
        gain = GAIN_A1
        r_shunt = R_SHUNT_A1
    elif mode == 'A4':
        lgpio.gpio_write(gpio_handle, MUX_GPIO_PIN, 0)
        gain = GAIN_A4
        r_shunt = R_SHUNT_A4
    else:
        raise ValueError("Modus muss 'A1' oder 'A4' sein.")

    time.sleep(2)  # Umschaltpause für MUX
    vout = read_voltage()
    current = calculate_current(vout, gain, r_shunt)
    return current, vout

# ======================================
# HAUPTPROGRAMM
# ======================================

def main():
    try:
        while True:
            #current_a1, vout_a1 = read_current('A1')
            #time.sleep(0.5)
            current_a4, vout_a4 = read_current('A4')

            #print(f"Raw Vout: {vout_a1:.3f} V\n")


            print("========== Strommessung ==========")
            #print(f"[A1 ±0.8A ] Vout: {vout_a1:.3f} V → I: {current_a1*1000:.2f} mA")
            print(f"[A4 ±10mA] Vout: {vout_a4:.3f} V → I: {current_a4*1000:.2f} mA")
            print("----------------------------------\n")

            time.sleep(1.5)

    except KeyboardInterrupt:
        print("Beendet durch Benutzer.")

    finally:
        lgpio.gpiochip_close(gpio_handle)

if __name__ == '__main__':
    main()
