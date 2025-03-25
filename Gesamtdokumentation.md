
# Gesamtdokumentation – Projekt Messdatenerfassung mit Raspberry Pi
**Datum:** 22.03.2025

## 1. Projektziel
Entwicklung eines modularen Messdatenerfassungssystems mit dem Raspberry Pi und MCC DAQ HAT 118.  
Ziel: Vergleichbare Funktionalität wie das NI MyDAQ inkl. Multimeter-, Oszilloskop-, Netzteil- und Generatorfunktionen.

## 2. Analysephase
- Auswertung der Spezifikation MCC 118
- Auswertung der Spezifikation NI MyDAQ
- Vergleichstabelle wurde erstellt und diskutiert

### Vergleich MCC 118 vs. NI MyDAQ (Auszug)

| Kategorie              | MCC 118                   | NI MyDAQ                   |
|------------------------|---------------------------|----------------------------|
| Analoge Eingänge       | 8 SE, 12 Bit, ±10 V       | 2 diff., 16 Bit, ±10 V     |
| Abtastrate             | 100 kS/s (320 kS/s Stack) | 200 kS/s                   |
| Analoge Ausgänge       | –                         | 2 Kanäle, ±10 V            |
| Trigger                | extern, konfigurierbar    | softwarebasiert            |
| Multimeterfunktion     | nicht integriert          | voll integriert            |
| Versorgung             | über GPIO                 | inkl. ±15 V, 5 V Ausgänge  |
| Bus                    | SPI                       | USB                        |
| Software               | Open Source, Python       | NI MAX, LabVIEW            |

## 3. Anforderungen
- 13 Anforderungen definiert (funktional + nicht-funktional)
- In Pflichtenheft überführt

## 4. Pflichtenheft
- Enthält: Ziel, Anforderungen, Systemgrenzen, Ergebnisse, Schnittstellen, Konzeptbewertung, Blockschaltbild, Funktionsgruppenplan, Softwarearchitektur

## 5. Konzeptentscheidung
- Morphologischer Kasten + Bewertungsmatrix
- Bewertete Konzepte: Einfach (67 Pkt), Mittel (60 Pkt), Aufwendig (56 Pkt)
- Entscheidung für das **einfache Konzept**

## 6. Systementwurf
- Blockschaltbild erstellt (Text und Bild)
- Funktionsgruppenplan mit 8 Modulen

## 7. Softwarearchitektur & Datenfluss
- Layer-Architektur (Input, Processing, Control, Output, Interface)
- Grafisches Datenflussdiagramm zusätzlich erstellt

## 8. Nächste Schritte (geplant)
- Python-Moduldesign und Klassendiagramm
- Erstellung der Hardware-Stückliste
- GUI-Entwurf

---

Diese Gesamtdokumentation fasst alle Dialogschritte, Analysen und Entwurfsentscheidungen vom 22.03.2025 zusammen.
