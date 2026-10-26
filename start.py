#!/usr/bin/env python3
"""
ORDAMA - Server Starter
"""

import os
import sys
import subprocess
import time
import argparse
from pathlib import Path

def neu_starten_mit_virtueller_umgebung():
    """Startet das Skript neu mit dem Virtual Environment, falls vorhanden"""
    base_dir = Path(__file__).parent
    venv_python = base_dir / "Virtual Environment" / "Scripts" / "python.exe"
    
    # Prüfen ob wir bereits im venv sind
    is_venv = sys.prefix != sys.base_prefix
    
    if not is_venv and venv_python.exists():
        print("Virtual Environment...")
        # Aktuelles Skript mit dem venv-Python neu starten
        result = subprocess.run([str(venv_python)] + sys.argv)
        sys.exit(result.returncode)

# Virtual Environment Prüfung am Anfang
neu_starten_mit_virtueller_umgebung()

# Backend zum Python-Pfad hinzufügen
backend_path = Path(__file__).parent / "Backend"
sys.path.insert(0, str(backend_path))

from app import ORDAMA

def main():
    """Startet den ORDAMA Server"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--delay', type=int, default=0, help='Verzögerung in Sekunden vor dem Start')
    args = parser.parse_args()

    if args.delay > 0:
        print(f"Warte {args.delay} Sekunden...")
        time.sleep(args.delay)

    try:
        # App erstellen und starten
        app = ORDAMA()
        app.run()
    except KeyboardInterrupt:
        print("\nServer wird beendet...")
    except Exception as e:
        print(f"Fehler beim Starten: {e}")
        input("Drücke Enter zum Beenden...")

if __name__ == '__main__':
    main()
