# 📊 Datenerfassungssystem auf Raspberry Pi

## 📋 Projektbeschreibung

Dieses Projekt zielt auf die Entwicklung eines prototypischen Messdatenerfassungssystems (DAQ) basierend auf Raspberry Pi und Digilent MCC DAQ HATs ab. Das System bietet oszilloskop- und netzteilähnliche Funktionen und dient als Grundlage für ein studentisches Messtechniklabor.

## 💻 Hardwareanforderungen

- `Raspberry Pi`
- Digilent MCC DAQ HAT `MCC 118`
- Externe Peripherie:
  - DAC + OPV + Mosfet für Spannungsversorgung
  - Gehäuse mit geplanten Anschlüssen und Steckern

## 🛠️ Softwareanforderungen

- `Linux`
- `Python 3.8+`
- `PYQT5`
- Folgende Python-Pakete:
  - `numpy`
  - `matplotlib`
  - `pandas`
  - `daqhats`
  - `mcculw`
  - `PyQt5`
  - `pyqtgraph`
  - `openpyxl`

## ⚙️ Installation

1. Raspberry Pi OS installieren
2. Python update und upgrade:

   ```bash
   sudo apt update
   sudo apt upgrade
   ```

3. Repository klonen:

   ```bash
   git clone https://github.com/MSY-Walter/Projektarbeit.git
   ```

### Entwicklungsumgebung

1. Virtuelle Umgebung erstellen:

   ```bash
   python -m venv .venv
   ```

2. Umgebung aktivieren:

   ```bash
   source .venv/bin/activate
   ```

3. Abhängigkeiten und Pakete installieren:

   ```bash
   sudo apt install -y python3-pyqt5
   pip install uv
   uv pip install -r requirements.txt
   ```

## 🚀 Verwendung

Das System bietet folgende Standard-Messroutinen:

- Multimeter-Funktionalität
- Oszilloskop-Funktionalität
- Netzteil-Funktionalität
- Funktionsgenerator-Funktionalität
- Diodenkennlinie/Filterkennlinie-Funktionalität

## 📂 Projektstruktur

- `docs/`: Dokumentation
- `src/`: Quellcode-Verzeichnis
  - `Dashboard_V1.py`: Dashboard für alle Funktionalität (Version 1)
  - `Diodenkennlinie_V1.py`: Dashboard für Diodenkennlinie (Version 1)
  - `DMM_V1.py`: Dashboard für Multimeter (Version 1)
  - `DMM_V2.py`: Dashboard für Multimeter (Version 2)
  - `Filterkennlinie_V1.py`: Dashboard für Filterkennlinie (Version 1)
  - `Funktionsgenerator_V1.py`: Dashboard zu Erzeugung der Signale (Version 1)
  - `Funktionsgenerator_V2.py`: Dashboard zu Erzeugung der Signale (Version 2)
  - `Oszilloskop_V1.py`: Dashboard für Oszilloskop (Version 1)
  - `Spannung_Strom_Generator.py`: Datei zu Erzeugung der simulierte Spannung und Strom
- `.gitignore`: Bei commit ignorieren
- `LICENSE`: MIT License
- `README.md`: Diese Datei
- `requirements.txt`: Python-Pakete

## 🤝 Beitrag leisten

## 📜 Lizenz

Dieses Projekt steht unter [`MIT License`](LICENSE)
