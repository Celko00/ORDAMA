#!/bin/bash
# ORDAMA Linux Installer
# Dieses Skript integriert ORDAMA in dein Linux-System

# Root-Verzeichnis ist eine Ebene höher
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP_TEMPLATE="$BASE_DIR/Backend/ORDAMA.desktop"
DESKTOP_FINAL="$BASE_DIR/ORDAMA.desktop"
ICON_SOURCE="$BASE_DIR/Benutzeroberflaeche/start.png"
APP_DIR="$HOME/.local/share/applications"

echo "🔧 Integriere ORDAMA in das System..."

# Sicherstellen, dass Skripte ausführbar sind
chmod +x "$BASE_DIR/ORDAMA_starten.sh"

# .desktop Datei aus Template erstellen und Pfade setzen
cp "$DESKTOP_TEMPLATE" "$DESKTOP_FINAL"
sed -i "s|Exec=.*|Exec=$BASE_DIR/ORDAMA_starten.sh|g" "$DESKTOP_FINAL"
sed -i "s|Icon=.*|Icon=$ICON_SOURCE|g" "$DESKTOP_FINAL"

# In das lokale App-Verzeichnis kopieren
mkdir -p "$APP_DIR"
cp "$DESKTOP_FINAL" "$APP_DIR/"

# Desktop-Datenbank aktualisieren
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APP_DIR"
fi

echo "✅ Fertig! ORDAMA sollte nun in deinem Anwendungsmenü erscheinen."
echo "Du kannst das Programm jetzt einfach über dein Startmenü suchen und starten."
