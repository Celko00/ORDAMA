"""
Admin Blueprint - Admin-Funktionen (Settings, IP-Whitelist, Server-Steuerung)
"""

import logging
import json
import threading
import os
import sys
import subprocess
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app, send_from_directory

# security_utils importieren
from security_utils import InputSanitizer

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api')


def init_admin_blueprint(auth_manager, db_manager, config, base_dir, audit_logger, backup_manager=None, update_manager=None, current_version="1.0.0", ocr_manager=None, image_backup_manager=None):
    """Initialisiert das Admin Blueprint mit den Managern"""
    
    # LearningSystem importieren
    from learning_system import LearningSystem
    learning_system = LearningSystem(db_manager)

    @admin_bp.route('/admin/get-all-active-ips', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_all_active_ips():
        """Gibt alle IPs aller aktiven Sessions zurück"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT ip_address 
                    FROM user_sessions 
                    WHERE ip_address IS NOT NULL AND ip_address != ''
                    AND last_activity > datetime('now', 'localtime', '-30 minutes')
                ''')
                ips = [row['ip_address'] for row in cursor.fetchall()]
            
            # Aktuelle IP des Users immer hinzufügen (falls nicht schon vorhanden)
            client_ip = request.remote_addr
            cf_connecting_ip = request.headers.get('CF-Connecting-IP')
            if cf_connecting_ip:
                client_ip = cf_connecting_ip
            elif request.headers.get('X-Forwarded-For'):
                forwarded_ips = request.headers.get('X-Forwarded-For').split(',')
                client_ip = forwarded_ips[0].strip()
            
            if client_ip and client_ip not in ips:
                ips.append(client_ip)
            
            return jsonify({'ips': ips})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen aller aktiven IPs: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/admin/get-current-ip', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_current_ip():
        """Gibt die aktuelle IP-Adresse des eingeloggten Users zurück"""
        try:
            # Client IP ermitteln (wie in app.py check_ip_whitelist)
            client_ip = request.remote_addr
            
            # Prüfe CF-Connecting-IP Header (Cloudflare-spezifisch)
            cf_connecting_ip = request.headers.get('CF-Connecting-IP')
            if cf_connecting_ip:
                client_ip = cf_connecting_ip
            elif request.headers.get('X-Forwarded-For'):
                # Fallback auf X-Forwarded-For
                forwarded_ips = request.headers.get('X-Forwarded-For').split(',')
                client_ip = forwarded_ips[0].strip()
            
            return jsonify({'ip': client_ip})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der aktuellen IP: {e}")
            return jsonify({'error': str(e)}), 500
    @auth_manager.login_required
    @auth_manager.admin_required
    def check_update():
        return jsonify({
            'current_version': current_version,
            'success': True
        })

    @admin_bp.route('/admin/update/upload', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def upload_update():
        if not update_manager:
            return jsonify({'error': 'UpdateManager nicht verfügbar'}), 500
        
        if 'file' not in request.files:
            return jsonify({'error': 'Keine Datei hochgeladen'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Keine Datei ausgewählt'}), 400
        
        # Temporär speichern
        temp_path = Path(base_dir) / "temp_update_package.zip"
        file.save(str(temp_path))
        
        # Validieren
        if not update_manager.pruefe_update_datei(temp_path):
            if temp_path.exists():
                os.remove(temp_path)
            return jsonify({'error': 'Ungültiges Update-Paket (Backend/app.py fehlt)'}), 400
        
        # Entpacken
        success = update_manager.update_paket_entpacken(temp_path)
        if temp_path.exists():
            os.remove(temp_path)
            
        if success:
            return jsonify({'success': True, 'message': 'Update-Paket bereit zur Installation'})
        else:
            return jsonify({'error': 'Fehler beim Entpacken des Updates'}), 500

    @admin_bp.route('/admin/update/install', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def install_update():
        if not update_manager:
            return jsonify({'error': 'UpdateManager nicht verfügbar'}), 500
        
        # Wir führen die Installation in einem separaten Thread aus, 
        # damit wir dem Browser sofort eine Antwort schicken können, 
        # bevor der Server durch Dateiänderungen neu startet.
        def deferred_install():
            import time
            import platform
            import subprocess
            time.sleep(1) # Kurze Pause, damit der Response gesendet werden kann
            
            result = update_manager.update_installieren()
            
            if result.get('success'):
                logger.info("Update-Installation erfolgreich. Starte Server neu...")
                
                # Server-Neustart-Logik (kopiert von /api/server/restart)
                time.sleep(1)
                try:
                    is_windows = platform.system() == "Windows"
                    python_exe = sys.executable
                    
                    if is_windows:
                        venv_python = base_dir / "Virtual Environment" / "Scripts" / "python.exe"
                        if not venv_python.exists():
                            venv_python = base_dir / "Virtual Environment" / "python.exe"
                        if venv_python.exists():
                            python_exe = str(venv_python)
                        subprocess.Popen([python_exe, str(base_dir / "start.py"), "--delay", "2"], 
                                        creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=str(base_dir))
                    else:
                        venv_dir = base_dir / "venv_linux"
                        venv_python = venv_dir / "bin" / "python3"
                        if not venv_python.exists():
                            venv_python = venv_dir / "bin" / "python"
                        if venv_python.exists():
                            python_exe = str(venv_python)

                        start_script = base_dir / "start.py"
                        if start_script.exists():
                            with open(os.devnull, 'w') as devnull:
                                subprocess.Popen([python_exe, str(start_script), "--delay", "2"],
                                               cwd=str(base_dir),
                                               stdout=devnull,
                                               stderr=devnull,
                                               start_new_session=True)
                        else:
                            logger.error("start.py nicht gefunden!")
                            os._exit(1)
                    
                    logger.info("Server-Neustart nach Update initiiert. Beende aktuellen Prozess.")
                    os._exit(0)
                except Exception as e:
                    logger.error(f"Fehler beim Server-Neustart nach Update: {e}")
                    os._exit(1)
            else:
                logger.error(f"Update-Installation fehlgeschlagen: {result.get('error')}")

        thread = threading.Thread(target=deferred_install)
        thread.start()
        
        audit_logger.log_action(session.get('username', 'unknown'), 'UPDATE', 'Software-Update Installation gestartet')
        return jsonify({
            'success': True, 
            'message': 'Update-Installation wurde gestartet. Das Programm wird im Hintergrund aktualisiert und startet automatisch neu.'
        })

    @admin_bp.route('/admin/update/export', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def export_update():
        """Exportiert das aktuelle System als Update-Paket"""
        try:
            import zipfile
            from datetime import datetime
            
            # Version aus Backend/app.py auslesen
            version = "1.0.0"
            app_py_path = base_dir / "Backend" / "app.py"
            try:
                with open(app_py_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines):
                    if 'VERSION =' in line:
                        version = line.split('=')[1].strip().replace('"', '').replace("'", "")
                        break
            except Exception as e:
                logger.warning(f"Version konnte nicht ausgelesen werden: {e}")

            # Dateiname mit Timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"ORDAMA_Update_v{version}_{timestamp}.zip"
            zip_path = base_dir / zip_name
            
            # Pfade, die NICHT im Update enthalten sein sollen
            ausgeschlossene_pfade = [
                "Speicher",
                "Konfiguration",
                "Logs",
                "Backups",
                "Virtual Environment",
                "venv_linux",
                "temp_update",
                "__pycache__",
                ".trae",
                ".git",
                ".uploads"
            ]

            logger.info(f"Erstelle Update-Paket: {zip_name}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(base_dir):
                    rel_root = os.path.relpath(root, base_dir)
                    
                    # Prüfen auf Ausschluss
                    if rel_root != ".":
                        teile = Path(rel_root).parts
                        if any(t in ausgeschlossene_pfade for t in teile):
                            continue
                    
                    # Spezial-Ausschluss für Root-Verzeichnisse
                    if any(rel_root.startswith(ex) for ex in ausgeschlossene_pfade):
                        continue

                    for file in files:
                        rel_file_path = os.path.join(rel_root, file) if rel_root != "." else file
                        
                        if any(ex in rel_file_path for ex in ausgeschlossene_pfade):
                            continue
                        
                        if file.endswith('.pyc') or file.endswith('.zip') or file.endswith('.log'):
                            continue

                        full_path = Path(root) / file
                        zipf.write(full_path, rel_file_path)

            logger.info(f"Update-Paket erfolgreich erstellt: {zip_path}")
            
            audit_logger.log_action(session.get('username', 'unknown'), 'UPDATE', f'Update-Paket exportiert: {zip_name}')
            
            return jsonify({
                'success': True, 
                'message': 'Update-Paket erfolgreich erstellt',
                'filename': zip_name,
                'version': version
            })
            
        except Exception as e:
            logger.error(f"Fehler beim Exportieren des Updates: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/admin/update/download/<filename>', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def download_update(filename):
        """Lädt ein exportiertes Update-Paket herunter"""
        try:
            # Sicherheitsprüfung: Nur .zip Dateien erlauben
            if not filename.endswith('.zip'):
                return jsonify({'error': 'Ungültiger Dateityp'}), 400
            
            # Pfad zur Datei
            file_path = base_dir / filename
            
            if not file_path.exists():
                return jsonify({'error': 'Datei nicht gefunden'}), 404
            
            return send_from_directory(str(base_dir), filename, as_attachment=True)
            
        except Exception as e:
            logger.error(f"Fehler beim Download des Updates: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/admin/backup/now', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def run_backup():
        # Altes Backup-System deaktiviert - leitet zu Image-Backup weiter
        if not image_backup_manager:
            return jsonify({'error': 'ImageBackupManager nicht verfügbar'}), 500
        
        result = image_backup_manager.create_backup()
        if result['success']:
            keep_count = config.get('backup', {}).get('keep_count', 10)
            image_backup_manager.cleanup_old_backups(keep_count=keep_count)
            user_name = session.get('username', 'unknown')
            audit_logger.log_action(user_name, 'BACKUP', 'Manuelles Image-Backup erstellt')
            return jsonify(result)
        else:
            return jsonify(result), 500
    
    @admin_bp.route('/admin/backup/snapshots', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def list_snapshots():
        # Altes Backup-System deaktiviert - leitet zu Image-Backup-Liste weiter
        if not image_backup_manager:
            return jsonify({'error': 'ImageBackupManager nicht verfügbar'}), 500
        
        backups = image_backup_manager.list_backups()
        return jsonify({'success': True, 'snapshots': backups})
    
    @admin_bp.route('/admin/backup/restore', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def restore_snapshot():
        if not backup_manager:
            return jsonify({'error': 'BackupManager nicht verfügbar'}), 500
        
        data = request.get_json()
        timestamp = data.get('timestamp')
        overwrite = data.get('overwrite', True)
        
        if not timestamp:
            return jsonify({'error': 'Timestamp erforderlich'}), 400
        
        # Alle Datenbankverbindungen schließen vor dem Restore
        logger.info(f"Schließe alle Datenbankverbindungen vor Restore")
        db_manager.close_all_connections()
        
        # Kurze Pause, damit alle Verbindungen sicher geschlossen sind
        import time
        time.sleep(0.5)
        
        # Führe das Restore SYNCHRON durch (ohne temporäres Skript!)
        logger.info(f"Starte Restore von Snapshot {timestamp}")
        result = backup_manager.restore_snapshot(timestamp, overwrite=overwrite)
        
        if result['success']:
            audit_logger.log_action(session.get('username', 'unknown'), 'RESTORE', f'Snapshot {timestamp} wiederhergestellt')
            logger.info(f"Restore erfolgreich! Server muss neu gestartet werden!")
            return jsonify({
                'success': True, 
                'message': 'Snapshot erfolgreich wiederhergestellt! Bitte Server manuell neu starten!'
            })
        else:
            logger.error(f"Restore fehlgeschlagen: {result.get('error')}")
            return jsonify(result), 500

    # --- Image Backup System Endpoints ---
    
    @admin_bp.route('/admin/image-backup/create', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def create_image_backup():
        if not image_backup_manager:
            return jsonify({'error': 'ImageBackupManager nicht verfügbar'}), 500
        
        result = image_backup_manager.create_backup()
        if result['success']:
            keep_count = config.get('backup', {}).get('keep_count', 10)
            image_backup_manager.cleanup_old_backups(keep_count=keep_count)
            user_name = session.get('username', 'unknown')
            audit_logger.log_action(user_name, 'BACKUP', f'Image-Backup erstellt: {result["filename"]}')
            return jsonify(result)
        else:
            return jsonify(result), 500
    
    @admin_bp.route('/admin/image-backup/list', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def list_image_backups():
        if not image_backup_manager:
            return jsonify({'error': 'ImageBackupManager nicht verfügbar'}), 500
        
        backups = image_backup_manager.list_backups()
        return jsonify({'success': True, 'backups': backups})
    
    @admin_bp.route('/admin/image-backup/restore', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def restore_image_backup():
        if not image_backup_manager:
            return jsonify({'error': 'ImageBackupManager nicht verfügbar'}), 500
        
        data = request.get_json()
        filename = data.get('filename')
        overwrite = data.get('overwrite', True)
        
        if not filename:
            return jsonify({'error': 'Filename erforderlich'}), 400
        
        # Führe das Restore durch
        logger.info(f"Starte Image-Backup Restore von {filename}")
        result = image_backup_manager.restore_backup(filename, overwrite=overwrite)
        
        if result['success']:
            audit_logger.log_action(session.get('username', 'unknown'), 'RESTORE', f'Image-Backup wiederhergestellt: {filename}')
            logger.info(f"Image-Backup Restore erfolgreich!")
            return jsonify(result)
        else:
            logger.error(f"Image-Backup Restore fehlgeschlagen: {result.get('error')}")
            return jsonify(result), 500
    
    @admin_bp.route('/admin/image-backup/verify', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def verify_image_backup():
        if not image_backup_manager:
            return jsonify({'error': 'ImageBackupManager nicht verfügbar'}), 500
        
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'error': 'Filename erforderlich'}), 400
        
        result = image_backup_manager.verify_backup(filename)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
    
    @admin_bp.route('/admin/image-backup/download/<filename>', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def download_image_backup(filename):
        """Lädt ein Image-Backup herunter"""
        try:
            # Sicherheitsprüfung: Nur .zip Dateien erlauben
            if not filename.endswith('.zip'):
                return jsonify({'error': 'Ungültiger Dateityp'}), 400
            
            # Pfad zur Datei
            backup_dir = Path(base_dir) / config['paths'].get('backup_dir', './Backups')
            file_path = backup_dir / filename
            
            if not file_path.exists():
                return jsonify({'error': 'Datei nicht gefunden'}), 404
            
            return send_from_directory(str(backup_dir), filename, as_attachment=True)
            
        except Exception as e:
            logger.error(f"Fehler beim Download des Image-Backups: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/admin/browse-folders', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def browse_folders():
        """Listet Verzeichnisse für den Datei-Browser auf"""
        try:
            current_path_str = request.args.get('path', '')
            
            if not current_path_str:
                # Root-Drives auf Windows oder / auf Linux
                if sys.platform == 'win32':
                    import ctypes
                    drives = []
                    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                        if bitmask & 1:
                            drives.append(f"{letter}:\\")
                        bitmask >>= 1
                    return jsonify({'current': '', 'folders': drives, 'is_root': True})
                else:
                    current_path = Path('/')
            else:
                current_path = Path(current_path_str)

            if not current_path.exists():
                return jsonify({'error': 'Pfad existiert nicht'}), 404

            folders = []
            try:
                for item in current_path.iterdir():
                    try:
                        if item.is_dir():
                            folders.append(item.name)
                    except (PermissionError, OSError):
                        continue # Überspringe Ordner ohne Zugriff
            except PermissionError:
                return jsonify({'error': 'Keine Berechtigung für diesen Ordner'}), 403

            # Parent bestimmen
            parent = None
            if current_path.parent != current_path:
                parent = str(current_path.parent.absolute())
            elif sys.platform == 'win32':
                # Wenn wir im Root eines Laufwerks sind (C:\), ist der Parent die Laufwerksliste ('')
                parent = ''

            return jsonify({
                'current': str(current_path.absolute()),
                'parent': parent,
                'folders': sorted(folders),
                'is_root': False
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # --- Logbuch Endpunkte ---

    @admin_bp.route('/admin/audit-logs', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_audit_logs():
        try:
            content = audit_logger.get_log_content()
            return jsonify({'logs': content})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # --- Settings Endpunkte ---
    
    @admin_bp.route('/view-settings', methods=['GET'])
    @auth_manager.login_required
    def get_view_settings():
        try:
            settings = db_manager.get_all_settings()
            return jsonify({
                'default_filter': settings.get('default_filter', ''),
                'default_sort': settings.get('default_sort', 'created_desc')
            })
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Ansichtseinstellungen: {e}")
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/settings', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_settings():
        try:
            settings = db_manager.get_all_settings()
            
            # Konfiguration neu laden aus settings.json für aktuelle Werte
            from pathlib import Path
            import json
            config_file = Path(__file__).parent.parent.parent / "Konfiguration" / "settings.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    current_config = json.load(f)
            else:
                current_config = config
            
            # Server-Einstellungen aus Konfiguration hinzufügen
            # SECRET_KEY jetzt vollständig zurückgeben zum Testen
            security_config = current_config['security'].copy()
            
            # Gewichte für Ähnlichkeitssuche laden
            user_id = session.get('user_id')
            similarity_weights = learning_system.get_similarity_weights(user_id)

            return jsonify({
                'settings': settings,
                'server': current_config['server'],
                'server_name': settings.get('server_name', ''),
                'security': security_config,
                'upload': current_config['upload'],
                'paths': current_config['paths'],
                'backup': current_config.get('backup', {
                    'interval': 'daily',
                    'time': '00:00',
                    'keep_count': 5,
                    'last_backup': None,
                    'backup_on_startup': False
                }),
                'ocr': current_config.get('ocr', {
                    'enabled': True,
                    'lang': 'deu+eng',
                    'oem': '3',
                    'psm': '6',
                    'dpi': 300,
                    'page_delay_seconds': 0.5,
                    'job_delay_seconds': 1.0,
                    'schedule_mode': 'always',
                    'schedule_start': '20:00',
                    'schedule_end': '06:00',
                    'preprocessing': {
                        'enabled': True,
                        'denoise': True,
                        'sharpen': True,
                        'binarize': False,
                        'deskew': True,
                        'contrast_enhance': True
                    }
                }),
                'search': current_config.get('search', {
                    'similarity_limit': 20,
                    'duplicate_candidate_limit': 100,
                    'similarity_candidate_limit': 200
                }),
                'session': current_config.get('session', {
                    'permanent': True
                }),
                'network': current_config.get('network', {
                    'request_limit_enabled': False,
                    'max_requests_per_minute': 100
                }),
                'archive': current_config.get('archive', {
                    'enabled': False,
                    'auto_archive': False,
                    'age_days': 365,
                    'age_months': 0,
                    'age_years': 0,
                    'unused_days': 180,
                    'unused_months': 0,
                    'unused_years': 0,
                    'run_interval': 'daily',
                    'last_run': ''
                }),
                'similarity_weights': similarity_weights,
                'duplicate_threshold': float(settings.get('duplicate_threshold', '0.7'))
            })
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Einstellungen: {e}")
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/settings', methods=['PUT'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def update_settings():
        try:
            data = request.get_json()
            logger.info(f"Einstellungs-Update empfangen: {json.dumps(data, indent=2)}")

            # Server-Einstellungen auch in Konfigurationsdatei speichern
            config_changed = False
            if 'server' in data:
                for key in ['host', 'port', 'plz_validation_enabled']:
                    if key in data['server']:
                        config['server'][key] = data['server'][key]
                        config_changed = True
                
                # allow_external basierend auf host setzen
                if 'host' in data['server']:
                    config['server']['allow_external'] = (data['server']['host'] == '0.0.0.0')
                    config_changed = True

            if 'upload' in data:
                if 'max_file_size_mb' in data['upload']:
                    config['upload']['max_file_size_mb'] = data['upload']['max_file_size_mb']
                    config_changed = True
                    # Auch im aktuellen App-Kontext aktualisieren
                    current_app.config['MAX_CONTENT_LENGTH'] = data['upload']['max_file_size_mb'] * 1024 * 1024

            if 'security' in data:
                if 'secret_key' in data:
                    # SECRET_KEY speichern wenn nicht leer
                    new_secret_key = data['security']['secret_key']
                    if new_secret_key and new_secret_key != '***' and new_secret_key != 'Wird automatisch generiert':
                        config['security']['secret_key'] = new_secret_key
                        config_changed = True
                        logger.info(f"SECRET_KEY wurde aktualisiert: {new_secret_key[:10]}...")
                    # Wenn leer, nichts tun (vorhandener SECRET_KEY bleibt erhalten)
                if 'max_login_attempts' in data['security']:
                    config['security']['max_login_attempts'] = data['security']['max_login_attempts']
                    config_changed = True
                if 'rate_limit_window_minutes' in data['security']:
                    config['security']['rate_limit_window_minutes'] = data['security']['rate_limit_window_minutes']
                    config_changed = True
                if 'ip_whitelist_mode' in data['security']:
                    config['security']['ip_whitelist_mode'] = data['security']['ip_whitelist_mode']
                    config_changed = True
                    logger.info(f"IP-Whitelist-Modus wurde aktualisiert: {data['security']['ip_whitelist_mode']}")
                if 'cloudflare_ips' in data['security']:
                    config['security']['cloudflare_ips'] = data['security']['cloudflare_ips']
                    config_changed = True
                    logger.info(f"Cloudflare IPs wurden aktualisiert: {len(data['security']['cloudflare_ips'])} Einträge")
                if 'custom_ips' in data['security']:
                    config['security']['custom_ips'] = data['security']['custom_ips']
                    config_changed = True
                    logger.info(f"Custom IPs wurden aktualisiert: {len(data['security']['custom_ips'])} Einträge")

            if 'paths' in data:
                for key in ['data_base_dir', 'attachments_dir', 'backup_dir']:
                    if key in data['paths']:
                        config['paths'][key] = data['paths'][key]
                        config_changed = True
            
            # Gewichtungen für Ähnlichkeitssuche speichern
            if 'similarity_weights' in data:
                try:
                    user_id = session.get('user_id')
                    learning_system.update_similarity_weights(user_id, data['similarity_weights'])
                    logger.info(f"Gewichtungen für Ähnlichkeitssuche aktualisiert für user_id={user_id}")
                except Exception as e:
                    logger.error(f"Fehler beim Speichern der Gewichtungen: {e}")

            if 'backup' in data:
                if 'backup' not in config: config['backup'] = {}
                for key in ['interval', 'time', 'keep_count', 'backup_on_startup']:
                    if key in data['backup']:
                        config['backup'][key] = data['backup'][key]
                        config_changed = True
            
            if 'search' in data:
                if 'search' not in config: config['search'] = {}
                for key in ['similarity_limit', 'duplicate_candidate_limit', 'similarity_candidate_limit']:
                    if key in data['search']:
                        config['search'][key] = data['search'][key]
                        config_changed = True
                        logger.info(f"Search setting {key} updated to {data['search'][key]}")
            
            if 'network' in data:
                if 'network' not in config: config['network'] = {}
                for key in ['request_limit_enabled', 'max_requests_per_minute', 'block_duration_seconds']:
                    if key in data['network']:
                        config['network'][key] = data['network'][key]
                        config_changed = True
                        logger.info(f"Network setting {key} updated to {data['network'][key]}")

            if 'archive' in data:
                if 'archive' not in config: config['archive'] = {}
                for key in ['enabled', 'auto_archive', 'age_days', 'age_months', 'age_years', 'unused_days', 'unused_months', 'unused_years', 'run_interval']:
                    if key in data['archive']:
                        config['archive'][key] = data['archive'][key]
                        config_changed = True
                        logger.info(f"Archive setting {key} updated to {data['archive'][key]}")
            
            if 'similarity' in data and 'limit' in data['similarity']:
                # Altes Format für Kompatibilität
                if 'search' not in config: config['search'] = {}
                config['search']['similarity_limit'] = data['similarity']['limit']
                config_changed = True
            
            if 'ocr' in data:
                if 'ocr' not in config: config['ocr'] = {}
                for key in ['enabled', 'lang', 'oem', 'psm', 'dpi', 'page_delay_seconds', 'job_delay_seconds', 'schedule_mode', 'schedule_start', 'schedule_end']:
                    if key in data['ocr']:
                        config['ocr'][key] = data['ocr'][key]
                        config_changed = True
                # Vorverarbeitungs-Einstellungen speichern
                if 'preprocessing' in data['ocr']:
                    if 'preprocessing' not in config['ocr']: config['ocr']['preprocessing'] = {}
                    for key in ['enabled', 'denoise', 'sharpen', 'binarize', 'deskew', 'contrast_enhance']:
                        if key in data['ocr']['preprocessing']:
                            config['ocr']['preprocessing'][key] = data['ocr']['preprocessing'][key]
                            config_changed = True

            if 'duplicate_threshold' in data:
                db_manager.set_setting('duplicate_threshold', str(data['duplicate_threshold']))

            if 'session' in data:
                if 'session' not in config: config['session'] = {}
                for key in ['permanent']:
                    if key in data['session']:
                        config['session'][key] = data['session'][key]
                        config_changed = True

            # Server-/Firmennamen speichern
            if 'server_name' in data:
                db_manager.set_setting('server_name', str(data['server_name']))

            if config_changed:
                config_file = base_dir / "Konfiguration" / "settings.json"
                config_file.parent.mkdir(parents=True, exist_ok=True)
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                
                # OCR-Manager Konfiguration neu laden, wenn OCR-Einstellungen geändert wurden
                if 'ocr' in data and ocr_manager:
                    try:
                        ocr_manager.reload_config(config)
                        logger.info("OCR-Manager Konfiguration neu geladen")
                    except Exception as e:
                        logger.error(f"Fehler beim Neuladen der OCR-Konfiguration: {e}")

            # Andere Einstellungen in Datenbank speichern
            for key, value in data.items():
                if key in ['server', 'upload', 'security', 'paths', 'backup', 'ocr', 'session', 'network', 'archive']:
                    continue  # Diese wurden bereits in Konfigurationsdatei gespeichert
                # Wenn value ein dict ist, als JSON-String speichern
                if isinstance(value, dict):
                    db_manager.set_setting(key, json.dumps(value))
                else:
                    db_manager.set_setting(key, str(value))
            return jsonify({'success': True, 'message': 'Einstellungen gespeichert'})
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Einstellungen: {e}")
            return jsonify({'error': str(e)}), 500

    # --- Stats Endpunkt ---
    
    @admin_bp.route('/stats')
    @auth_manager.login_required
    @auth_manager.require_permission('can_view_stats')
    def dashboard_stats():
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Prüfen ob Admin - dann erweiterte Statistiken
                is_admin = session.get('role') == 'admin'
                
                if is_admin:
                    # Admin-Statistiken: Benutzer
                    cursor.execute("SELECT COUNT(*) FROM users")
                    total_users = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM users WHERE active = 1")
                    active_users = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
                    admin_users = cursor.fetchone()[0]
                    
                    # Akten-Statistiken
                    cursor.execute("SELECT COUNT(*) FROM records WHERE archived = 0")
                    total_records = cursor.fetchone()[0]
                    
                    # Dateianhänge zählen
                    cursor.execute("SELECT COUNT(*) FROM attachments")
                    total_attachments = cursor.fetchone()[0]
                    
                    return jsonify({
                        'totalUsers': total_users,
                        'activeUsers': active_users,
                        'adminUsers': admin_users,
                        'totalRecords': total_records,
                        'totalAttachments': total_attachments
                    })
                else:
                    # Normale Benutzer-Statistiken: Akten und Dateianhänge
                    cursor.execute("SELECT COUNT(*) FROM records WHERE archived = 0")
                    total = cursor.fetchone()[0]
                    
                    # Dateianhänge zählen
                    cursor.execute("SELECT COUNT(*) FROM attachments")
                    attachments = cursor.fetchone()[0]
                    
                    return jsonify({
                        'totalRecords': total,
                        'totalAttachments': attachments
                    })
                
        except Exception as e:
            return jsonify({'error': f'Statistik fehlgeschlagen: {str(e)}'}), 500

    # --- Server Steuerung ---
    
    @admin_bp.route('/server/restart', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def server_restart():
        """Server wird nach kurzer Verzoegerung neugestartet"""
        def restart():
            import time
            import platform
            time.sleep(1)
            # Neustart Prozess
            try:
                # Auf Windows CREATE_NEW_CONSOLE nutzen, damit ein neues Fenster aufgeht
                # Auf anderen Systemen einfach Popen
                is_windows = platform.system() == "Windows"
                # Finde korrektes Python-Interpreter (inklusive VENV)
                python_exe = sys.executable
                
                if is_windows:
                    # Windows: Virtual Environment
                    venv_python = base_dir / "Virtual Environment" / "Scripts" / "python.exe"
                    if not venv_python.exists():
                        venv_python = base_dir / "Virtual Environment" / "python.exe"
                    if venv_python.exists():
                        python_exe = str(venv_python)
                    # Windows: Original-Code beibehalten
                    subprocess.Popen([python_exe, str(base_dir / "start.py"), "--delay", "2"], 
                                    creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=str(base_dir))
                else:
                    # Linux/macOS: Nutze start.py (wie Windows) für Konsistenz
                    # Finde venv-Python
                    venv_dir = base_dir / "venv_linux"
                    venv_python = venv_dir / "bin" / "python3"
                    if not venv_python.exists():
                        venv_python = venv_dir / "bin" / "python"
                    if venv_python.exists():
                        python_exe = str(venv_python)

                    # start.py aufrufen mit Delay für sauberen Neustart
                    start_script = base_dir / "start.py"
                    if start_script.exists():
                        # Im Hintergrund starten mit start_new_session für Detachment
                        # Ausgabe nach /dev/null umleiten um den Prozess zu entkoppeln
                        with open(os.devnull, 'w') as devnull:
                            subprocess.Popen([python_exe, str(start_script), "--delay", "2"],
                                           cwd=str(base_dir),
                                           stdout=devnull,
                                           stderr=devnull,
                                           start_new_session=True)
                    else:
                        logger.error("start.py nicht gefunden!")
                        os._exit(1)
                
                logger.info("Server-Neustart initiiert. Beende aktuellen Prozess.")
                os._exit(0)
            except Exception as e:
                logger.error(f"Fehler beim Server-Neustart: {e}")
                os._exit(1)
        
        threading.Thread(target=restart).start()
        return jsonify({'success': True, 'message': 'Server wird neu gestartet...'})
    
    @admin_bp.route('/server/stop', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def server_stop():
        """Server wird sauber beendet"""
        def stop():
            import time
            time.sleep(0.5)
            # Shutdown-Funktion muss von außen bereitgestellt werden
            logger.info("Server wird beendet...")
            os._exit(0)
        
        threading.Thread(target=stop).start()
        return jsonify({'success': True, 'message': 'Server wird beendet...'})

    # --- Karten-Orte Management Endpunkte ---

    @admin_bp.route('/karte/referenzorte', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_referenzorte():
        """Lädt alle Referenzorte aus ref.json"""
        try:
            ref_pfad = Path(base_dir) / "Konfiguration" / "karte" / "ref.json"
            if not ref_pfad.exists():
                return jsonify({'orte': {}})
            
            with open(ref_pfad, 'r', encoding='utf-8') as f:
                orte = json.load(f)
            
            return jsonify({'orte': orte})
        except Exception as e:
            logger.error(f"Fehler beim Laden der Referenzorte: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/karte/referenzorte', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def add_referenzort():
        """Fügt einen neuen Referenzort hinzu"""
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            lat = data.get('lat')
            lon = data.get('lon')
            level = data.get('level', 2)

            if not name:
                return jsonify({'error': 'Name erforderlich'}), 400
            if lat is None or lon is None:
                return jsonify({'error': 'Koordinaten (lat, lon) erforderlich'}), 400

            try:
                lat = float(lat)
                lon = float(lon)
                level = int(level)
            except (ValueError, TypeError):
                return jsonify({'error': 'Ungültige Koordinaten oder Level'}), 400

            # Validierung der Koordinaten
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                return jsonify({'error': 'Koordinaten außerhalb des gültigen Bereichs'}), 400

            ref_pfad = Path(base_dir) / "Konfiguration" / "karte" / "ref.json"
            ref_pfad.parent.mkdir(parents=True, exist_ok=True)

            # Bestehende Daten laden
            if ref_pfad.exists():
                with open(ref_pfad, 'r', encoding='utf-8') as f:
                    orte = json.load(f)
            else:
                orte = {}

            # Ort hinzufügen oder aktualisieren
            orte[name] = {
                'lat': lat,
                'lon': lon,
                'level': level
            }

            # Speichern
            with open(ref_pfad, 'w', encoding='utf-8') as f:
                json.dump(orte, f, indent=4, ensure_ascii=False)

            audit_logger.log_action(session.get('username', 'unknown'), 'KARTE', f'Referenzort "{name}" hinzugefügt')
            return jsonify({'success': True, 'message': f'Ort "{name}" hinzugefügt'})
        except Exception as e:
            logger.error(f"Fehler beim Hinzufügen des Referenzortes: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/karte/referenzorte/<name>', methods=['DELETE'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def delete_referenzort(name):
        """Löscht einen Referenzort"""
        try:
            ref_pfad = Path(base_dir) / "Konfiguration" / "karte" / "ref.json"
            if not ref_pfad.exists():
                return jsonify({'error': 'ref.json nicht gefunden'}), 404

            with open(ref_pfad, 'r', encoding='utf-8') as f:
                orte = json.load(f)

            if name not in orte:
                return jsonify({'error': 'Ort nicht gefunden'}), 404

            del orte[name]

            with open(ref_pfad, 'w', encoding='utf-8') as f:
                json.dump(orte, f, indent=4, ensure_ascii=False)

            audit_logger.log_action(session.get('username', 'unknown'), 'KARTE', f'Referenzort "{name}" gelöscht')
            return jsonify({'success': True, 'message': f'Ort "{name}" gelöscht'})
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Referenzortes: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/karte/referenzorte/import', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def import_referenzorte():
        """Importiert eine komplette Liste von Referenzorten (ersetzt ref.json)"""
        try:
            data = request.get_json()
            orte = data.get('orte', {})

            if not isinstance(orte, dict):
                return jsonify({'error': 'orte muss ein Objekt sein'}), 400

            # Validierung der Struktur
            for name, coords in orte.items():
                if not isinstance(coords, dict):
                    return jsonify({'error': f'Ungültige Daten für Ort "{name}"'}), 400
                if 'lat' not in coords or 'lon' not in coords:
                    return jsonify({'error': f'Fehlende Koordinaten für Ort "{name}"'}), 400
                try:
                    lat = float(coords['lat'])
                    lon = float(coords['lon'])
                    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                        return jsonify({'error': f'Ungültige Koordinaten für Ort "{name}"'}), 400
                except (ValueError, TypeError):
                    return jsonify({'error': f'Ungültige Koordinaten für Ort "{name}"'}), 400

            ref_pfad = Path(base_dir) / "Konfiguration" / "karte" / "ref.json"
            ref_pfad.parent.mkdir(parents=True, exist_ok=True)

            with open(ref_pfad, 'w', encoding='utf-8') as f:
                json.dump(orte, f, indent=4, ensure_ascii=False)

            audit_logger.log_action(session.get('username', 'unknown'), 'KARTE', f'Referenzorte importiert ({len(orte)} Orte)')
            return jsonify({'success': True, 'message': f'{len(orte)} Orte importiert'})
        except Exception as e:
            logger.error(f"Fehler beim Importieren der Referenzorte: {e}")
            return jsonify({'error': str(e)}), 500

    # API-Endpunkte für intelligente Ähnlichkeitssuche und Lernsystem
    
    @admin_bp.route('/learning/similarity-weights', methods=['GET'])
    @auth_manager.login_required
    def get_similarity_weights():
        """Lädt die aktuellen Gewichtungen für Ähnlichkeitssuche"""
        try:
            user_id = session.get('user_id')
            weights = learning_system.get_similarity_weights(user_id)
            return jsonify({'success': True, 'weights': weights})
        except Exception as e:
            logger.error(f"Fehler beim Laden der Gewichtungen: {e}")
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/learning/similarity-weights', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def update_similarity_weights():
        """Aktualisiert die Gewichtungen für Ähnlichkeitssuche"""
        try:
            user_id = session.get('user_id')
            data = request.get_json()
            
            logger.info(f"Empfange Gewichtungs-Update: user_id={user_id}, data={data}")
            
            weights = data.get('weights', {})
            
            # Validierung
            valid_keys = ['title', 'content', 'address', 'hashtags', 'category', 
                          'border_color', 'status', 'attachments', 'ocr_text', 
                          'creation_date', 'update_date']
            
            for key in weights:
                if key not in valid_keys:
                    logger.error(f"Ungültiger Gewichtungs-Key: {key}")
                    return jsonify({'error': f'Ungültiger Gewichtungs-Key: {key}'}), 400
                if not isinstance(weights[key], (int, float)):
                    logger.error(f"Gewichtung für {key} muss eine Zahl sein, ist {type(weights[key])}")
                    return jsonify({'error': f'Gewichtung für {key} muss eine Zahl sein'}), 400
                if weights[key] < 0 or weights[key] > 2.0:
                    logger.error(f"Gewichtung für {key} muss zwischen 0 und 2.0 liegen, ist {weights[key]}")
                    return jsonify({'error': f'Gewichtung für {key} muss zwischen 0 und 2.0 liegen'}), 400
            
            # Gewichtungen aktualisieren (NULL user_id = globale Konfiguration)
            is_global = data.get('global', False)
            target_user_id = None if is_global else user_id
            
            logger.info(f"Aktualisiere Gewichtungen: target_user_id={target_user_id}, is_global={is_global}, weights={weights}")
            
            learning_system.update_similarity_weights(target_user_id, weights)
            
            audit_logger.log_action(session.get('username', 'unknown'), 'LEARNING', 
                                   f'Gewichtungen aktualisiert (global={is_global})')
            
            logger.info("Gewichtungen erfolgreich aktualisiert")
            return jsonify({'success': True, 'message': 'Gewichtungen aktualisiert'})
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Gewichtungen: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/learning/learn-from-clicks', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def learn_from_clicks():
        """Löst Lernprozess aus basierend auf Klickdaten"""
        try:
            data = request.get_json()
            days = data.get('days', 30)
            user_id = session.get('user_id')
            
            learning_system.learn_from_clicks(user_id, days)
            
            audit_logger.log_action(session.get('username', 'unknown'), 'LEARNING', 
                                   f'Lernprozess gestartet (letzte {days} Tage)')
            
            return jsonify({'success': True, 'message': f'Lernprozess abgeschlossen (letzte {days} Tage)'})
        except Exception as e:
            logger.error(f"Fehler beim Lernprozess: {e}")
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/learning/statistics', methods=['GET'])
    @auth_manager.login_required
    def get_learning_statistics():
        """Lädt Lern-Statistiken"""
        try:
            user_id = session.get('user_id')
            stats = learning_system.get_learning_statistics(user_id)
            return jsonify({'success': True, 'statistics': stats})
        except Exception as e:
            logger.error(f"Fehler beim Laden der Lern-Statistiken: {e}")
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/learning/log-search', methods=['POST'])
    @auth_manager.login_required
    def log_search():
        """Protokolliert eine Suchanfrage (für Frontend-Tracking)"""
        try:
            user_id = session.get('user_id')
            data = request.get_json()
            search_type = data.get('search_type', 'unknown')
            query_params = data.get('query_params', {})
            result_count = data.get('result_count', 0)
            
            search_log_id = learning_system.log_search(user_id, search_type, query_params, result_count)
            
            return jsonify({'success': True, 'search_log_id': search_log_id})
        except Exception as e:
            logger.error(f"Fehler beim Protokollieren der Suche: {e}")
            return jsonify({'error': str(e)}), 500
    
    @admin_bp.route('/learning/log-result-click', methods=['POST'])
    @auth_manager.login_required
    def log_result_click():
        """Protokolliert einen Klick auf ein Suchergebnis"""
        try:
            data = request.get_json()
            search_log_id = data.get('search_log_id')
            record_id = data.get('record_id')
            click_position = data.get('click_position', 0)
            
            if not search_log_id or not record_id:
                return jsonify({'error': 'search_log_id und record_id erforderlich'}), 400
            
            learning_system.log_result_click(search_log_id, record_id, click_position)
            
            return jsonify({'success': True, 'message': 'Klick protokolliert'})
        except Exception as e:
            logger.error(f"Fehler beim Protokollieren des Klicks: {e}")
            return jsonify({'error': str(e)}), 500

    @admin_bp.route('/log/toast', methods=['POST'])
    def log_toast():
        """Protokolliert Toast-Meldungen vom Frontend im Audit-Log"""
        try:
            data = request.get_json()
            msg = data.get('message', '')
            toast_type = data.get('type', 'info')
            username = session.get('username', 'anonymous')
            
            audit_logger.log_action(username, f'TOAST_{toast_type.upper()}', msg)
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Fehler beim Protokollieren des Toast: {e}")
            return jsonify({'error': str(e)}), 500

    return admin_bp
