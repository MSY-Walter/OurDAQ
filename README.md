# 📊 Datenerfassungssystem auf Raspberry Pi 4

## 📋 Projektbeschreibung

Dieses Projekt zielt auf die Entwicklung eines prototypischen Messdatenerfassungssystems (DAQ) basierend auf Raspberry Pi 4 und Digilent MCC DAQ HATs ab. Das System bietet oszilloskop- und netzteilähnliche Funktionen und dient als Grundlage für ein studentisches Messtechniklabor.

## 💻 Hardwareanforderungen

- `Raspberry Pi 4`
- Digilent MCC DAQ HAT `MCC 118`
- Externe Peripherie:
  - DAC + OPV + Mosfet für Spannungsversorgung
  - Gehäuse mit geplanten Anschlüssen und Steckern

## 🛠️ Softwareanforderungen

- `Linux`
- `Python 3.8+`
- `Jupyter Notebook`
- `tkinter`
- Folgende Python-Pakete:
  - `numpy`
  - `matplotlib`
  - `pandas`
  - `daqhats`
  - `PyQt5`
  - `pyqtgraph`

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
   pip install -r requirements.txt
   sudo apt install -y python3-tk
   ```

## 🚀 Verwendung

Das System bietet folgende Standard-Messroutinen:

- Multimeter-Funktionalität
- Oszilloskop-Funktionalität
- Netzteil-Funktionalität

## 📂 Projektstruktur

- `docs/`: Dokumentation
- `src/`: Quellcode-Verzeichnis
  - `DMM_V1.py`: Dashbord für Multimeter mit tkinter
  - `DMM_V2.py`: Dashbord für Multimeter mit PyQt5
  - `Oszilloskop_V1_Basis.py`: Basis-Dashboard für Oszilloskop mit tkinter
  - `Oszilloskop_V1_Erweiterung.py`: Erweiteres Dashboard für Oszilloskop mit tkinter
  - `Oszilloskop_V2.py`: Dashboard für Oszilloskop mit PyQt5
  - `Signal_Generator.py`: Datei zu Erzeugung der simulierte Signale
  - `Spannung_Strom_Generator.py`: Datei zu Erzeugung der simulierte Spannung und Strom
- `.gitignore`: Bei commit ignorieren
- `LICENSE`: MIT License
- `README.md`: Diese Datei
- `requirements.txt`: Python-Pakete

## 🤝 Beitrag leisten

## 📜 Lizenz

Dieses Projekt steht unter [`MIT License`](LICENSE)
