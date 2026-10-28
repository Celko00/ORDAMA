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

Tunnel Blueprint - Cloudflare Tunnel Management
"""

import logging
import json
import subprocess
import platform
from pathlib import Path
from flask import Blueprint, request, jsonify, session

logger = logging.getLogger(__name__)

def init_tunnel_blueprint(base_dir, config_dir):
    """Initialisiert den Tunnel Blueprint"""
    tunnel_bp = Blueprint('tunnel', __name__)
    
    config_file = config_dir / "cloudflare_tunnel.json"
    
    @tunnel_bp.route('/config', methods=['GET'])
    def get_tunnel_config():
        """Holt die aktuelle Tunnel-Konfiguration"""
        try:
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                return jsonify({'success': True, 'config': config})
            else:
                return jsonify({'success': True, 'config': None})
        except Exception as e:
            logger.error(f"Fehler beim Laden der Tunnel-Konfiguration: {e}")
            return jsonify({'error': str(e)}), 500
    
    @tunnel_bp.route('/config', methods=['POST'])
    def save_tunnel_config():
        """Speichert die Tunnel-Konfiguration"""
        try:
            data = request.get_json()
            
            config = {
                'tunnel_id': data.get('tunnel_id'),
                'tunnel_token': data.get('tunnel_token'),
                'hostname': data.get('hostname'),
                'port': data.get('port', 8081)
            }
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # cloudflared Konfigurationsdatei aktualisieren
            update_cloudflared_config(config, config_dir)
            
            return jsonify({'success': True, 'message': 'Konfiguration gespeichert'})
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Tunnel-Konfiguration: {e}")
            return jsonify({'error': str(e)}), 500
    
    @tunnel_bp.route('/status', methods=['GET'])
    def get_tunnel_status():
        """Prüft den Status des cloudflared Services"""
        try:
            system = platform.system()
            
            if system == "Windows":
                # Windows Service Status prüfen
                try:
                    result = subprocess.run(['sc', 'query', 'cloudflared'], 
                                          capture_output=True, text=True)
                    if 'RUNNING' in result.stdout:
                        status = 'running'
                    elif 'STOPPED' in result.stdout:
                        status = 'stopped'
                    else:
                        status = 'unknown'
                except:
                    status = 'not_installed'
            else:
                # Linux systemd Status prüfen
                try:
                    result = subprocess.run(['systemctl', 'is-active', 'cloudflared'],
                                          capture_output=True, text=True)
                    status = result.stdout.strip()
                    if status == 'active':
                        status = 'running'
                    elif status == 'inactive':
                        status = 'stopped'
                    else:
                        status = 'unknown'
                except:
                    status = 'not_installed'
            
            return jsonify({'success': True, 'status': status})
        except Exception as e:
            logger.error(f"Fehler beim Prüfen des Tunnel-Status: {e}")
            return jsonify({'error': str(e)}), 500
    
    @tunnel_bp.route('/start', methods=['POST'])
    def start_tunnel():
        """Startet den cloudflared Service"""
        try:
            system = platform.system()
            
            if system == "Windows":
                subprocess.run(['sc', 'start', 'cloudflared'], check=True)
            else:
                subprocess.run(['systemctl', 'start', 'cloudflared'], check=True)
            
            return jsonify({'success': True, 'message': 'Tunnel gestartet'})
        except Exception as e:
            logger.error(f"Fehler beim Starten des Tunnels: {e}")
            return jsonify({'error': str(e)}), 500
    
    @tunnel_bp.route('/stop', methods=['POST'])
    def stop_tunnel():
        """Stoppt den cloudflared Service"""
        try:
            system = platform.system()
            
            if system == "Windows":
                subprocess.run(['sc', 'stop', 'cloudflared'], check=True)
            else:
                subprocess.run(['systemctl', 'stop', 'cloudflared'], check=True)
            
            return jsonify({'success': True, 'message': 'Tunnel gestoppt'})
        except Exception as e:
            logger.error(f"Fehler beim Stoppen des Tunnels: {e}")
            return jsonify({'error': str(e)}), 500
    
    @tunnel_bp.route('/restart', methods=['POST'])
    def restart_tunnel():
        """Startet den cloudflared Service neu"""
        try:
            system = platform.system()
            
            if system == "Windows":
                subprocess.run(['sc', 'stop', 'cloudflared'], check=True)
                subprocess.run(['sc', 'start', 'cloudflared'], check=True)
            else:
                subprocess.run(['systemctl', 'restart', 'cloudflared'], check=True)
            
            return jsonify({'success': True, 'message': 'Tunnel neu gestartet'})
        except Exception as e:
            logger.error(f"Fehler beim Neustarten des Tunnels: {e}")
            return jsonify({'error': str(e)}), 500
    
    return tunnel_bp

def update_cloudflared_config(config, config_dir):
    """Aktualisiert die cloudflared.yml Konfigurationsdatei"""
    config_file = config_dir / "cloudflared.yml"
    
    if not config.get('tunnel_id'):
        return
    
    config_content = f"""# Cloudflare Tunnel Konfiguration
# Automatisch generiert von ORDAMA

tunnel: {config['tunnel_id']}
credentials-file: {config_dir / f"{config['tunnel_id']}.json"}

ingress:
  - hostname: {config['hostname']}
    service: http://localhost:{config['port']}
  - service: http_status:404
"""
    
    with open(config_file, 'w') as f:
        f.write(config_content)
