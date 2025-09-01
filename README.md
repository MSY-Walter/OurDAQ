# Datenerfassungssystem auf Raspberry Pi 5 (OurDAQ)

## Projektbeschreibung

Dieses Projekt (OurDAQ) zielt auf die Entwicklung eines prototypischen Messdatenerfassungssystems (DAQ) basierend auf [`Raspberry Pi 5`](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) und [`Digilent MCC DAQ HAT MCC 118`](https://mccdaq.github.io/daqhats/overview.html#mcc-118) ab. Das System dient als Grundlage für ein studentisches Messtechniklabor.

Das System bietet folgende Standard-Messroutinen:

- Multimeter-Funktionalität
- Oszilloskop-Funktionalität
- Netzteil-Funktionalität
- Funktionsgenerator-Funktionalität
- Diodenkennlinie-Funktionalität
- Filterkennlinie-Funktionalität

## Hardwareanforderungen

- [`Raspberry Pi 5`](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [`Digilent MCC DAQ HAT MCC 118`](https://mccdaq.github.io/daqhats/overview.html#mcc-118)
- Externe Peripherie:
  - DAC + OPV + Mosfet für Spannungsversorgung
  - Gehäuse mit geplanten Anschlüssen und Steckern

## Softwareanforderungen

- Linux System wie [`Raspberry Pi OS`](https://www.raspberrypi.com/software/) oder [`Ubuntu`](https://ubuntu.com/download/raspberry-pi)
- [`uv`](https://docs.astral.sh/uv/) Python-Paketemanager
- `python>=3.11`
- Und Folgende Python-Pakete:
  - `daqhats>=1.4.1.0`
  - `dash>=3.2.0`
  - `lgpio>=0.2.2.0`
  - `matplotlib>=3.10.3`
  - `notebook>=7.4.2`
  - `numpy>=2.2.5`
  - `pandas>=2.2.3`
  - `pyqtgraph>=0.13.7`
  - `spidev>=3.7`

## Installation

1. update und upgrade:

   ```bash
   sudo apt update
   sudo apt full-upgrade
   sudo reboot
   ```

2. Abhängigkeiten und Pakete von `Digilent MCC DAQ HAT MCC 118` installieren

   ```bash
   cd ~
   git clone https://github.com/mccdaq/daqhats.git
   ```

   ```bash
   cd ~/daqhats
   sudo ./install.sh
   ```

3. repository klonen:

   ```bash
   cd ~
   git clone https://github.com/MSY-Walter/OurDAQ.git
   ```

### Entwicklungsumgebung

1. `uv` installieren (Falls nicht vorhanden):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Abhängigkeiten und Pakete in der virtuellen Umgebung installieren:

   ```bash
   cd ~/OurDAQ
   uv sync
   ```

## Verwendung

Bestimmte Funktionalität öffnen:

```bash
cd ~/OurDAQ/src
uv run <Dateiname>
```

In Jupyter Lab (Jupyter Notebook) öffnen:

```bash
cd ~/OurDAQ/src
uv run jupyter lab --ip=0.0.0.0 --port=8888
```

## Projektstruktur

- `docs/`: Dokumentation
- `src/`: Quellcode-Verzeichnis
  - `Test/`: Programme zu testen (noch in Bearbeitung)
    - `Diodenkennlinie_test.py`: Diodenkennlinie darstellen (testen)
    - `Diodenkennlinie.ipynb`: Jupyter Notebook für Diodenkennlinie
    - `DMM_test.py`: Digitalmultimeter in Web (testen)
    - `Filterkennlinie_test.py`: Filterkennlinie darstellen (testen)
    - `Filterkennlinie.ipynb`: Jupyter Notebook für Filterkennlinie
    - `Funktionsgenerator_test.py`: Erzeugung der Signale mit AD9833 (optimiert)
  - `daqhats_utils.py`: Bibliothek für Netzteil-Funktionalität
  - `Dashboard_web.py`: Hauptmenü für alle Funktionalitäten in Web
  - `Diodenkennlinie.py`: Diodenkennlinie darstellen
  - `DMM_web.py`: Digitalmultimeter in Web
  - `Filterkennlinie.py`: Filterkennlinie darstellen
  - `Funktionsgenerator_web.py`: Erzeugung der Signale mit AD9833 in web
  - `Funktionsgenerator.py`: Erzeugung der Signale mit AD9833
  - `Netzteil_minus_web.py`: Netzteilfunktion (negativ) in Web
  - `Netzteil_minus.py`: Netzteilfunktion (negativ)
  - `Netzteil_plus_web.py`: Netzteilfunktion (positiv) in Web
  - `Netzteil_plus.py`: Netzteilfunktion (positiv)
  - `Oszilloskop_web.py`: Oszilloskop in Web
- `.gitignore`: Bei commit ignorieren
- `LICENSE`: MIT License
- `pyproject.toml`: Abhängigkeiten und Pakete
- `README.md`: Diese Datei
- `uv.lock`: Quelle von Abhängigkeiten und Pakete

## Link

[`MCC DAQ HAT Library for Raspberry Pi`](https://github.com/mccdaq/daqhats)

[`uv Introduction`](https://docs.astral.sh/uv/)

## Lizenz

Dieses Projekt steht unter [`MIT License`](LICENSE)
