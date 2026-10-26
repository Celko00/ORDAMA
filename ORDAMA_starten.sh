#!/bin/bash
# ORDAMA Linux Launcher
# Dieses Skript startet ORDAMA unter Linux

# In das Verzeichnis des Skripts wechseln
cd "$(dirname "$0")"

echo "ORDAMA wird gestartet..."

# Prüfen ob Python 3 installiert ist
if ! command -v python3 &> /dev/null
then
    echo "❌ Fehler: python3 wurde nicht gefunden."
    echo "Bitte installieren Sie Python 3 (z.B. sudo apt install python3)"
    read -p "Drücken Sie Enter zum Beenden..."
    exit 1
fi

# Start-Skript ausführen (liegt nun im Backend-Ordner)
python3 Backend/system_start.py

# Falls python3 fehlschlägt, versuche es mit python
if [ $? -ne 0 ]; then
    echo "Versuche es mit 'python'..."
    python Backend/system_start.py
fi

if [ $? -ne 0 ]; then
    echo "❌ Fehler beim Starten von ORDAMA."
    read -p "Drücken Sie Enter zum Beenden..."
    exit 1
fi
