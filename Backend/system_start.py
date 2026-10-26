import os
import sys
import subprocess
import time
import platform
import socket
from pathlib import Path

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def find_free_port(start_port):
    port = start_port
    while is_port_in_use(port):
        print(f"⚠️ Port {port} belegt, probiere {port + 1}...")
        port += 1
    return port

def start_server():
    # Da dieses Skript in /Backend/ liegt, ist das Hauptverzeichnis eine Ebene höher
    base_dir = Path(__file__).parent.parent
    backend_app = base_dir / "Backend" / "app.py"
    requirements_file = base_dir / "Backend" / "requirements.txt"
    
    print("ORDAMA Launcher")
    print("===============")
    
    # OS detection
    is_windows = platform.system() == "Windows"
    
    # Environment setup
    if is_windows:
        venv_python = base_dir / "Virtual Environment" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = base_dir / "Virtual Environment" / "python.exe"
    else:
        # Linux / macOS
        venv_dir = base_dir / "venv_linux"
        # Try python3 first, then python
        venv_python = venv_dir / "bin" / "python3"
        if not venv_python.exists():
            venv_python = venv_dir / "bin" / "python"
        
        if not venv_dir.exists():
            print("Erstelle Linux-Virtual-Environment...")
            try:
                subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
            except subprocess.CalledProcessError:
                print("\n❌ FEHLER: Konnte Virtual Environment nicht erstellen.")
                print("Grund: Das Python-Modul 'venv' fehlt wahrscheinlich.")
                print("LÖSUNG: Bitte installiere es mit folgendem Befehl im Terminal:")
                print("      sudo apt update && sudo apt install python3-venv")
                print("\nDas Programm wird jetzt beendet.")
                return False
            
            if venv_dir.exists():
                print("Installiere Abhängigkeiten in venv...")
                if not install_dependencies(venv_python, requirements_file, base_dir):
                    return False
        else:
            # Falls venv existiert, prüfen ob Flask bereit ist
            print("Prüfe System-Abhängigkeiten...")
            flask_check = subprocess.run([str(venv_python), "-c", "import flask"], capture_output=True)
            if flask_check.returncode != 0:
                print("⚠️ Flask wurde nicht gefunden. Starte automatische Reparatur...")
                if not install_dependencies(venv_python, requirements_file, base_dir):
                    print("\n❌ FEHLER: Die automatische Reparatur ist fehlgeschlagen.")
                    print("LÖSUNG: Löschen Sie den Ordner 'venv_linux' manuell und starten Sie das Programm neu.")
                    return False
                print("✅ Reparatur erfolgreich.")

    python_exe = str(venv_python) if venv_python.exists() else sys.executable
    backend_app_abs = backend_app.absolute()
    
    # Port-Suche
    target_port = find_free_port(8080)
    
    print(f"Starte Backend auf Port {target_port} mit: {python_exe}")
    
    # Environment-Variablen für Tesseract vorbereiten
    env = os.environ.copy()
    if not is_windows:
        tesseract_dir = base_dir / "Tesseract" / "linux"
        lib_dir = tesseract_dir / "lib"
        if lib_dir.exists():
            # Füge den lib-Ordner zum LD_LIBRARY_PATH hinzu
            if "LD_LIBRARY_PATH" in env:
                env["LD_LIBRARY_PATH"] = f"{str(lib_dir)}:{env['LD_LIBRARY_PATH']}"
            else:
                env["LD_LIBRARY_PATH"] = str(lib_dir)
    
    try:
        server_process = subprocess.Popen(
            [python_exe, str(backend_app_abs), f"--port={target_port}"], 
            cwd=str(base_dir),
            start_new_session=not is_windows,
            env=env
        )
    except Exception as e:
        print(f"❌ Schwerwiegender Fehler beim Starten des Prozesses: {e}")
        return False

    print("Warte auf Serverstart...")
    time.sleep(3)
    
    # Prüfen ob der Prozess noch läuft (nicht sofort abgestürzt ist)
    time.sleep(1) # Kurze Pause vor dem Check
    if server_process.poll() is not None:
        print("\n❌ FEHLER: Der Backend-Server konnte nicht gestart werden.")
        print(f"Mögliche Ursache: Port {target_port} wurde während des Starts belegt oder interner App-Fehler.")
        return False

    print("\nORDAMA läuft!")
    print(f"Erreichbar unter: http://localhost:{target_port}")
    print("Schließen Sie dieses Fenster zum Beenden des Servers.")
    
    try:
        server_process.wait()
    except KeyboardInterrupt:
        server_process.terminate()
        print("\nServer beendet.")
    return True

def install_dependencies(venv_python, requirements_file, base_dir):
    """Hilfsfunktion zur Installation der Abhängigkeiten"""
    try:
        # Erst pip sicherstellen
        subprocess.run([str(venv_python), "-m", "ensurepip", "--upgrade"], capture_output=True)
        
        # Online-Installation
        print("🌐 Installiere Abhängigkeiten aus dem Internet...")
        result = subprocess.run([
            str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)
        ])
        
        if result.returncode == 0:
            return True
            
        print("❌ Installation fehlgeschlagen.")
        return False
    except Exception as e:
        print(f"❌ Fehler bei der Installation: {e}")
        return False

if __name__ == "__main__":
    if not start_server():
        print("\nStartvorgang abgebrochen.")
        input("Drücken Sie Enter zum Beenden...")
        sys.exit(1)
