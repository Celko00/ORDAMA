#!/usr/bin/env python3
"""
ORDAMA - Dokumentenmanagement-System
Copyright (C) 2026 Marcel Kohl

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Cloudflare Tunnel Auto-Installer
Installiert und konfiguriert cloudflared automatisch auf Windows und Linux
"""

import os
import sys
import platform
import subprocess
import json
import urllib.request
import zipfile
import tarfile
import shutil
from pathlib import Path

class CloudflareTunnelInstaller:
    def __init__(self):
        self.system = platform.system()
        self.machine = platform.machine()
        self.base_dir = Path(__file__).parent.parent.parent
        self.config_dir = self.base_dir / "Konfiguration"
        self.config_file = self.config_dir / "cloudflare_tunnel.json"
        
        # cloudflared Version
        self.version = "2024.9.1"
        
    def get_download_url(self):
        """Gibt die Download-URL für das aktuelle System zurück"""
        base_url = f"https://github.com/cloudflare/cloudflared/releases/download/{self.version}"
        
        if self.system == "Windows":
            if self.machine == "AMD64":
                return f"{base_url}/cloudflared-windows-amd64.exe"
            elif self.machine == "ARM64":
                return f"{base_url}/cloudflared-windows-arm64.exe"
        elif self.system == "Linux":
            if self.machine == "x86_64":
                return f"{base_url}/cloudflared-linux-amd64"
            elif self.machine == "aarch64":
                return f"{base_url}/cloudflared-linux-arm64"
            elif self.machine == "armv7l":
                return f"{base_url}/cloudflared-linux-arm"
        
        raise Exception(f"Unsupported platform: {self.system} {self.machine}")
    
    def get_install_dir(self):
        """Gibt das Installationsverzeichnis zurück"""
        if self.system == "Windows":
            return Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "cloudflared"
        else:
            return Path("/usr/local/bin")
    
    def download_cloudflared(self):
        """Lädt cloudflared herunter"""
        print(f"📥 Lade cloudflared {self.version} herunter...")
        
        url = self.get_download_url()
        install_dir = self.get_install_dir()
        install_dir.mkdir(parents=True, exist_ok=True)
        
        if self.system == "Windows":
            binary_path = install_dir / "cloudflared.exe"
            urllib.request.urlretrieve(url, binary_path)
        else:
            temp_path = install_dir / "cloudflared_temp"
            urllib.request.urlretrieve(url, temp_path)
            binary_path = install_dir / "cloudflared"
            shutil.move(temp_path, binary_path)
            os.chmod(binary_path, 0o755)
        
        print(f"✅ cloudflared installiert: {binary_path}")
        return binary_path
    
    def install_windows_service(self, binary_path):
        """Installiert cloudflared als Windows Service"""
        print("🔧 Installiere Windows Service...")
        
        try:
            # cloudflared service install verwenden
            cmd = [
                str(binary_path),
                "service",
                "install"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Windows Service installiert")
                
                # Konfigurationsdatei erstellen
                self.create_config()
                
                # Service starten
                subprocess.run([str(binary_path), "service", "start"], capture_output=True)
                print("✅ Windows Service gestartet")
                return True
            else:
                print(f"❌ Fehler bei Service-Installation: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Fehler: {e}")
            return False
    
    def install_linux_service(self, binary_path):
        """Installiert cloudflared als systemd Service"""
        print("🔧 Installiere systemd Service...")
        
        try:
            # systemd Service-Datei erstellen
            service_content = f"""[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
ExecStart={binary_path} tunnel run --config {self.config_dir / "cloudflared.yml"}
WorkingDirectory={self.base_dir}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
            
            service_file = Path("/etc/systemd/system/cloudflared.service")
            with open(service_file, 'w') as f:
                f.write(service_content)
            
            # systemd neu laden
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            
            # Service aktivieren
            subprocess.run(["systemctl", "enable", "cloudflared"], check=True)
            
            print("✅ systemd Service installiert")
            
            # Konfigurationsdatei erstellen
            self.create_config()
            
            # Service starten
            subprocess.run(["systemctl", "start", "cloudflared"], check=True)
            print("✅ systemd Service gestartet")
            return True
            
        except Exception as e:
            print(f"❌ Fehler: {e}")
            return False
    
    def create_config(self):
        """Erstellt cloudflared Konfiguration"""
        config_file = self.config_dir / "cloudflared.yml"
        
        if config_file.exists():
            print(f"⚠️  Konfiguration existiert bereits: {config_file}")
            return
        
        print(f"📝 Erstelle Konfiguration: {config_file}")
        
        # Standard-Konfiguration
        config_content = f"""# Cloudflare Tunnel Konfiguration
# Diese Datei wird automatisch generiert

# Tunnel-ID (muss noch konfiguriert werden)
# tunnel: <tunnel-id>

# Credentials-Datei (muss noch konfiguriert werden)
# credentials-file: {self.config_dir / "<tunnel-id>.json"}

ingress:
  # Beispiel: ORDAMA Server
  - hostname: dein-domain.de
    service: http://localhost:8081
  # Fallback für nicht konfigurierte Hosts
  - service: http_status:404
"""
        
        with open(config_file, 'w') as f:
            f.write(config_content)
        
        print(f"✅ Konfiguration erstellt: {config_file}")
        print("⚠️  Bitte Tunnel-ID und Credentials konfigurieren!")
    
    def save_config(self, tunnel_id, tunnel_token, hostname, port=8081):
        """Speichert Tunnel-Konfiguration"""
        config = {
            "tunnel_id": tunnel_id,
            "tunnel_token": tunnel_token,
            "hostname": hostname,
            "port": port
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Konfiguration gespeichert: {self.config_file}")
    
    def load_config(self):
        """Lädt Tunnel-Konfiguration"""
        if not self.config_file.exists():
            return None
        
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def install(self):
        """Haupt-Installationsroutine"""
        print("=" * 60)
        print("Cloudflare Tunnel Auto-Installer")
        print("=" * 60)
        print(f"System: {self.system} {self.machine}")
        print(f"Version: {self.version}")
        print()
        
        try:
            # cloudflared herunterladen
            binary_path = self.download_cloudflared()
            
            # Service installieren
            if self.system == "Windows":
                success = self.install_windows_service(binary_path)
            else:
                success = self.install_linux_service(binary_path)
            
            if success:
                print()
                print("=" * 60)
                print("✅ Installation erfolgreich!")
                print("=" * 60)
                print()
                print("Nächste Schritte:")
                print("1. Cloudflare Tunnel erstellen: https://dash.cloudflare.com/")
                print("2. Tunnel-ID und Token in der Konfiguration eintragen")
                print("3. Service neustarten")
                print()
                if self.system == "Windows":
                    print("Windows Service Befehle:")
                    print("  Start: sc start cloudflared")
                    print("  Stop: sc stop cloudflared")
                    print("  Status: sc query cloudflared")
                else:
                    print("Linux Service Befehle:")
                    print("  Start: sudo systemctl start cloudflared")
                    print("  Stop: sudo systemctl stop cloudflared")
                    print("  Status: sudo systemctl status cloudflared")
                    print("  Logs: sudo journalctl -u cloudflared -f")
            else:
                print()
                print("❌ Installation fehlgeschlagen")
                return False
                
        except Exception as e:
            print(f"❌ Fehler: {e}")
            return False
        
        return True

def main():
    installer = CloudflareTunnelInstaller()
    installer.install()

if __name__ == "__main__":
    main()
