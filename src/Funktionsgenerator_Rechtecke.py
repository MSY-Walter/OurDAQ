# -*- coding: utf-8 -*-

"""
GPIO_Rechteckwelle.py
Erzeugt eine Rechteckwelle über GPIO ohne Abhängigkeit von DAQ HAT
"""

import RPi.GPIO as GPIO
import time
import threading
import sys

class GPIORechteckwelle:
    def __init__(self, gpio_pin=18, frequenz=1000, duty_cycle=50):
        self.gpio_pin = gpio_pin
        self.frequenz = frequenz
        self.duty_cycle = duty_cycle  # in Prozent (0-100)
        self.running = False
        self.thread = None
        
        # GPIO initialisieren
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        
        print(f"Rechteckwellengenerator initialisiert auf Pin {gpio_pin}")
    
    def start(self):
        """Startet die Erzeugung der Rechteckwelle in einem separaten Thread"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._generate_square_wave)
        self.thread.daemon = True
        self.thread.start()
        print(f"Rechteckwelle mit {self.frequenz} Hz und {self.duty_cycle}% Duty-Cycle gestartet")
    
    def stop(self):
        """Stoppt die Rechteckwellenerzeugung"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        print("Rechteckwellenerzeugung gestoppt")
    
    def set_frequency(self, frequenz):
        """Ändert die Frequenz der Rechteckwelle"""
        self.frequenz = frequenz
        print(f"Frequenz auf {self.frequenz} Hz gesetzt")
    
    def set_duty_cycle(self, duty_cycle):
        """Ändert den Duty-Cycle der Rechteckwelle"""
        self.duty_cycle = max(0, min(100, duty_cycle))
        print(f"Duty-Cycle auf {self.duty_cycle}% gesetzt")
    
    def _generate_square_wave(self):
        """Erzeugt die Rechteckwelle"""
        try:
            while self.running:
                if self.frequenz <= 0:
                    time.sleep(0.1)
                    continue
                
                # Berechne Periodendauer und Hoch-/Niedrig-Zeiten
                period = 1.0 / self.frequenz
                high_time = period * (self.duty_cycle / 100.0)
                low_time = period - high_time
                
                # Erzeuge Rechteckwelle
                if self.running:
                    GPIO.output(self.gpio_pin, GPIO.HIGH)
                    time.sleep(high_time)
                
                if self.running:
                    GPIO.output(self.gpio_pin, GPIO.LOW)
                    time.sleep(low_time)
        
        except Exception as e:
            print(f"Fehler bei der Rechteckwellenerzeugung: {e}")
            self.running = False
            GPIO.output(self.gpio_pin, GPIO.LOW)

def main():
    try:
        # Standard-GPIO-Pin für die Rechteckwelle
        DEFAULT_PIN = 18
        
        # Frage den Benutzer nach dem zu verwendenden Pin
        pin = DEFAULT_PIN
        try:
            pin_input = input(f"GPIO-Pin für Rechteckwelle (Standard: {DEFAULT_PIN}): ")
            if pin_input.strip():
                pin = int(pin_input)
        except ValueError:
            print(f"Ungültige Eingabe, verwende Standard-Pin {DEFAULT_PIN}")
        
        # Initialisiere den Rechteckwellengenerator
        generator = GPIORechteckwelle(gpio_pin=pin)
        
        while True:
            print("\nRechteckwellengenerator")
            print("1. Start")
            print("2. Stop")
            print("3. Frequenz ändern")
            print("4. Duty-Cycle ändern")
            print("5. Beenden")
            
            auswahl = input("Auswahl: ")
            
            if auswahl == "1":
                generator.start()
            elif auswahl == "2":
                generator.stop()
            elif auswahl == "3":
                try:
                    frequenz = float(input("Neue Frequenz (Hz): "))
                    generator.set_frequency(frequenz)
                    if generator.running:
                        print("Neustart des Generators erforderlich...")
                        generator.stop()
                        generator.start()
                except ValueError:
                    print("Ungültige Eingabe")
            elif auswahl == "4":
                try:
                    duty_cycle = float(input("Neuer Duty-Cycle (0-100%): "))
                    generator.set_duty_cycle(duty_cycle)
                    if generator.running:
                        print("Neustart des Generators erforderlich...")
                        generator.stop()
                        generator.start()
                except ValueError:
                    print("Ungültige Eingabe")
            elif auswahl == "5":
                generator.stop()
                break
            else:
                print("Ungültige Auswahl")
    
    except KeyboardInterrupt:
        print("\nProgramm beendet")
    finally:
        if 'generator' in locals():
            generator.stop()
        GPIO.cleanup()
        print("GPIO aufgeräumt")

if __name__ == "__main__":
    main()