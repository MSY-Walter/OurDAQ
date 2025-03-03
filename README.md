# 📊 Datenerfassungssystem auf Raspberry Pi 4

## 📋 Projektbeschreibung

Dieses Projekt zielt auf die Entwicklung eines prototypischen Messdatenerfassungssystems (DAQ) basierend auf Raspberry Pi 4 und Digilent MCC DAQ HATs ab. Das System bietet oszilloskop- und netzteilähnliche Funktionen und dient als Grundlage für ein studentisches Messtechniklabor.

## 💻 Hardwareanforderungen

- Raspberry Pi 4
- Digilent MCC DAQ HAT (MCC 118/128, 152)
- Externe Peripherie:
  - DAC + OPV + Mosfet für Spannungsversorgung
  - Gehäuse mit geplanten Anschlüssen und Steckern

## 🛠️ Softwareanforderungen

- Python 3.8+
- Jupyter Notebook
- Folgende Python-Pakete:
  - numpy
  - matplotlib
  - ipykernel
  - ipython
  - ipywidgets

### Entwicklungsumgebung

1. Virtuelle Umgebung erstellen:

   ```bash
   python -m venv .venv
   ```

2. Umgebung aktivieren:

   ```bash
   # Windows
   .venv\Scripts\activate
   # Linux/MacOS
   source .venv/bin/activate
   ```

3. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

## ⚙️ Installation

1. Raspberry Pi OS installieren
2. Python und notwendige Pakete installieren:

   ```bash
   sudo apt update
   sudo apt install python3 python3-pip
   pip install -r requirements.txt
   ```

3. Repository klonen:

   ```bash
   git clone https://github.com/MSY-Walter/Projektarbeit
   ```

## 🚀 Verwendung

Das System bietet folgende Standard-Messroutinen:

- Multimeter-Funktionalität
- Oszilloskop-Funktionalität
- Netzteil-Funktionalität

## 📂 Projektstruktur

```
.
├── docs/                              # Dokumentation
├── src/                               # Quellcode-Verzeichnis
│   ├── Dashboard.ipynb                # Haupt-Dashboard für Messungen
│   ├── Messdaten_Generator.py         # Modul zur Datengenerierung 
│   └── Messdaten_Visualisierung.ipynb # Messdaten in Jupyter-Notebook ploten                           
├── LICENSE                            # Zertifikat                            
├── README.md                          # Diese Datei
└── requirements.txt                   # Python-Pakete
```

## 🤝 Beitrag leisten

## 📜 Lizenz

Dieses Projekt steht unter [MIT License](LICENSE)
