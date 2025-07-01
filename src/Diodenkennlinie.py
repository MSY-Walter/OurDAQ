# Alternative Implementierung mit Raspberry Pi und externem ADC
import lgpio
import spidev
import numpy as np
import time
import matplotlib.pyplot as plt

class FrequenzAnalysator:
    def __init__(self):
        """Initialisierung mit SPI ADC (z.B. MCP3208)"""
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)  # SPI Bus 0, Device 0
        self.spi.max_speed_hz = 1000000  # 1MHz SPI Takt
        self.gpio_handle = lgpio.gpiochip_open(0)
        
    def adc_lesen(self, kanal):
        """ADC Kanal lesen (MCP3208 Beispiel)"""
        if kanal < 0 or kanal > 7:
            raise ValueError("Kanal muss zwischen 0 und 7 liegen")
        
        # MCP3208 Kommando zusammenstellen
        kommando = [1, (8 + kanal) << 4, 0]
        antwort = self.spi.xfer2(kommando)
        
        # 12-Bit Wert extrahieren
        wert = ((antwort[1] & 3) << 8) + antwort[2]
        spannung = (wert / 4095.0) * 3.3  # Auf 3.3V referenziert
        return spannung
    
    def signale_erfassen(self, abtastrate, anzahl_proben):
        """Zwei Kanäle gleichzeitig abtasten"""
        kanal_eingang = 0  # ADC Kanal für Eingangssignal
        kanal_ausgang = 1  # ADC Kanal für Ausgangssignal
        
        eingang_daten = []
        ausgang_daten = []
        zeitstempel = []
        
        abtast_intervall = 1.0 / abtastrate
        start_zeit = time.time()
        
        for i in range(anzahl_proben):
            # Beide Kanäle schnell hintereinander lesen
            eingang_wert = self.adc_lesen(kanal_eingang)
            ausgang_wert = self.adc_lesen(kanal_ausgang)
            
            eingang_daten.append(eingang_wert)
            ausgang_daten.append(ausgang_wert)
            zeitstempel.append(time.time() - start_zeit)
            
            # Warten bis zum nächsten Abtastzeitpunkt
            naechste_abtastung = (i + 1) * abtast_intervall
            wartezeit = naechste_abtastung - (time.time() - start_zeit)
            if wartezeit > 0:
                time.sleep(wartezeit)
        
        return np.array(eingang_daten), np.array(ausgang_daten)
    
    def phase_berechnen(self, signal, abtastrate, frequenz):
        """Phase und Amplitude mittels FFT bestimmen"""
        N = len(signal)
        fenster = np.hanning(N)
        fft = np.fft.fft(signal * fenster)
        frequenzen = np.fft.fftfreq(N, 1/abtastrate)
        
        # Index der gewünschten Frequenz finden
        idx = np.argmin(np.abs(frequenzen - frequenz))
        return np.angle(fft[idx]), np.abs(fft[idx])
    
    def frequenzgang_messen(self, start_freq, stop_freq, schritte):
        """Komplette Frequenzgangmessung"""
        frequenzen = np.logspace(np.log10(start_freq), np.log10(stop_freq), schritte)
        verstaerkung_ergebnisse = []
        phasen_ergebnisse = []
        
        abtastrate = 10000  # 10kHz (begrenzt durch Python/SPI Geschwindigkeit)
        anzahl_proben = 2000
        
        for freq in frequenzen:
            print(f"\nFunktionsgenerator auf {freq:.2f} Hz einstellen")
            input("Enter drücken wenn bereit...")
            
            # Signale erfassen
            eingang, ausgang = self.signale_erfassen(abtastrate, anzahl_proben)
            
            # Phasen und Amplituden berechnen
            phase_ein, amp_ein = self.phase_berechnen(eingang, abtastrate, freq)
            phase_aus, amp_aus = self.phase_berechnen(ausgang, abtastrate, freq)
            
            # Phasendifferenz und Verstärkung
            phasendiff = np.rad2deg((phase_aus - phase_ein + np.pi) % (2 * np.pi) - np.pi)
            verstaerkung = 20 * np.log10(amp_aus / amp_ein) if amp_ein > 0 else -np.inf
            
            print(f"  → Phasendifferenz: {phasendiff:.2f}°")
            print(f"  → Verstärkung: {verstaerkung:.2f} dB")
            
            phasen_ergebnisse.append(phasendiff)
            verstaerkung_ergebnisse.append(verstaerkung)
        
        return frequenzen, verstaerkung_ergebnisse, phasen_ergebnisse
    
    def ergebnisse_plotten(self, frequenzen, verstaerkung, phase):
        """Frequenzgang grafisch darstellen"""
        plt.figure(figsize=(10, 6))
        
        plt.subplot(2, 1, 1)
        plt.semilogx(frequenzen, verstaerkung, marker='o')
        plt.ylabel("Verstärkung (dB)")
        plt.title("Frequenzgang")
        plt.grid(True)
        
        plt.subplot(2, 1, 2)
        plt.semilogx(frequenzen, phase, marker='x', color='orange')
        plt.xlabel("Frequenz (Hz)")
        plt.ylabel("Phasendifferenz (°)")
        plt.grid(True)
        
        plt.tight_layout()
        plt.show()
    
    def schliessen(self):
        """Ressourcen freigeben"""
        self.spi.close()
        lgpio.gpiochip_close(self.gpio_handle)

# Verwendungsbeispiel
if __name__ == "__main__":
    analysator = FrequenzAnalysator()
    
    try:
        # Parameter eingeben
        start_freq = float(input("Startfrequenz (Hz): "))
        stop_freq = float(input("Stoppfrequenz (Hz): "))
        schritte = int(input("Anzahl Messpunkte: "))
        
        # Messung durchführen
        freq, gain, phase = analysator.frequenzgang_messen(start_freq, stop_freq, schritte)
        
        # Ergebnisse anzeigen
        analysator.ergebnisse_plotten(freq, gain, phase)
        
    finally:
        analysator.schliessen()