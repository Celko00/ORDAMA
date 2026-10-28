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

ORDAMA Backend - Modulare Blueprint-Struktur
"""

import os
import json
import logging
import logging.handlers
import threading
import signal
import sys
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from colorama import init, Fore, Style

# Colorama für Windows-Konsole initialisieren
init(autoreset=True)

# Logging konfigurieren mit Rotation
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Logs Ordner erstellen
logs_dir = Path(__file__).parent.parent / "Logs"
logs_dir.mkdir(parents=True, exist_ok=True)

# File Handler mit Rotation (max 5MB, 3 Backups)
file_handler = logging.handlers.RotatingFileHandler(
    logs_dir / 'ordama_log.log',
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Custom Colored Formatter für Console
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.colors = {
            'DEBUG': Fore.CYAN,
            'INFO': Fore.GREEN,
            'WARNING': Fore.YELLOW,
            'ERROR': Fore.RED,
            'CRITICAL': Fore.RED + Style.BRIGHT,
        }
    
    def format(self, record):
        levelname = record.levelname
        if levelname in self.colors:
            record.levelname = f"{self.colors[levelname]}{levelname}{Style.RESET_ALL}"
        return super().format(record)

# Console Handler mit Colored Formatter
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger.addHandler(file_handler)
logger.addHandler(console_handler)

from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from flask_compress import Compress

from rate_limiter import RateLimitMiddleware
from database import DatabaseManager
from akten_logic import AktenManager
from backup_logic import BackupManager
from backup_image import ImageBackupManager
from update_logic import UpdateManager
from sperr_logik import SperrManager
from system.mod.db_schutz import setze_datenbank_schutz
from auth_modul import AuthManager
from audit_logger import AuditLogger
from system.mod.formular_logik import FormularManager
from security_events import SecurityEventLogger
from ocr_logic import OCRManager
from security_utils import CSRFProtection, InputSanitizer, FileUploadValidator
from archive_logic import ArchiveManager

# Blueprints importieren
from blueprints.auth_blueprint import init_auth_blueprint, create_user_blueprint
from blueprints.records_blueprint import init_records_blueprint
from blueprints.admin_blueprint import init_admin_blueprint
from blueprints.karte_blueprint import init_karte_blueprint
from blueprints.category_blueprint import init_category_blueprint, category_bp
from blueprints.formular_blueprint import init_formular_blueprint, formular_bp
from blueprints.gallery_blueprint import init_gallery_blueprint
from blueprints.assistant_blueprint import init_assistant_blueprint
from blueprints.chat_blueprint import init_chat_blueprint

class ORDAMA:
    VERSION = "1.1.2"
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.config_dir = self.base_dir / "Konfiguration"
        logger.info(f"ORDAMA initialisiert. Base Dir: {self.base_dir.absolute()}")
        self.config = self.load_config()
        self.app = self.create_app()
        
    def load_config(self):
        """Lädt Konfiguration aus settings.json"""
        config_file = self.base_dir / "Konfiguration" / "settings.json"
        config = self.get_default_config()
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        
        # Port-Übersteuerung durch Befehlszeilenargument (falls vorhanden)
        if len(sys.argv) > 1:
            try:
                for arg in sys.argv[1:]:
                    if arg.startswith('--port='):
                        config['server']['port'] = int(arg.split('=')[1])
                        logger.info(f"Port durch Argument übersteuert: {config['server']['port']}")
            except Exception as e:
                logger.error(f"Fehler beim Parsen der Argumente: {e}")
                
        return config
    
    def get_default_config(self):
        """Standardkonfiguration"""
        return {
            "server": {
                "host": "127.0.0.1", 
                "port": 8080, 
                "debug": True,
                "allow_external": False,
                "auto_restart": False
            },
            "database": {"name": "ordama.db"},
            "security": {
                "ip_whitelist": []
            },
            "upload": {"max_file_size_mb": 50},
            "paths": {
                "data_base_dir": "./Speicher", 
                "backup_dir": "./Backups"
            },
            "session": {
                "permanent": True
            },
            "network": {
                "request_limit_enabled": False,
                "max_requests_per_minute": 100,
                "block_duration_seconds": 60,
                "description": "Schützt vor Überlastung durch zu viele Anfragen pro Benutzer"
            },
            "ocr": {
                "enabled": True,
                "lang": "deu+eng",
                "poll_interval_seconds": 2.5,
                "render_scale": 2.0,
                "tesseract_cmd": "tesseract",
                "page_delay_seconds": 0.5,
                "job_delay_seconds": 1.0,
                "oem": "3",
                "psm": "6",
                "dpi": 300,
                "preprocessing": {
                    "enabled": True,
                    "denoise": True,
                    "sharpen": True,
                    "binarize": False,
                    "deskew": True,
                    "contrast_enhance": True,
                    "denoise_strength": 3,
                    "sharpen_strength": 2.0,
                    "binarize_threshold": 127,
                    "contrast_factor": 1.5
                }
            },
            "backup": {
                "interval": "daily",
                "time": "00:00",
                "keep_count": 5,
                "last_backup": None
            },
            "network": {
                "request_limit_enabled": False,
                "max_requests_per_minute": 100,
                "description": "Schützt vor Überlastung durch zu viele Anfragen pro Benutzer"
            },
            "archive": {
                "enabled": False,
                "auto_archive": False,
                "age_days": 365,
                "age_months": 0,
                "age_years": 0,
                "unused_days": 180,
                "unused_months": 0,
                "unused_years": 0,
                "run_interval": "daily",
                "last_run": "",
                "description": "Automatische Archivierung von Akten basierend auf Alter und letzter Nutzung"
            }
        }
    
    def check_auto_backup(self):
        """Prüft ob ein automatisches Backup fällig ist"""
        try:
            interval = self.config.get('backup', {}).get('interval', 'daily')
            if interval == 'none':
                return

            last_backup_str = self.config.get('backup', {}).get('last_backup')
            now = datetime.now()
            backup_time_str = self.config.get('backup', {}).get('time', '00:00').strip()
            if not backup_time_str:
                backup_time_str = '00:00'
            backup_hour, backup_minute = map(int, backup_time_str.split(':'))
            
            should_backup = False
            # Aktuelle Zeit und Backup-Zeit berechnen
            current_time = now.replace(second=0, microsecond=0)
            backup_today = now.replace(hour=backup_hour, minute=backup_minute, second=0, microsecond=0)
            
            if not last_backup_str:
                # Kein Backup bisher - backup, wenn aktuelle Zeit >= Backup-Zeit
                should_backup = current_time >= backup_today
            else:
                last_backup = datetime.fromisoformat(last_backup_str)
                last_backup_date = last_backup.date()
                today = now.date()
                
                if interval == 'daily':
                    # Backup, wenn letzte Backup vor der heutigen Backup-Zeit war und aktuelle Zeit >= Backup-Zeit
                    if (last_backup < backup_today) and (current_time >= backup_today):
                        should_backup = True
                elif interval == 'weekly':
                    # Backup, wenn letzte Backup vor der heutigen Backup-Zeit vor mehr als einer Woche war
                    if last_backup < backup_today - timedelta(days=7) and current_time >= backup_today:
                        should_backup = True
                elif interval == 'monthly':
                    # Backup, wenn letzte Backup in einem anderen Monat war
                    if (last_backup.year != today.year or last_backup.month != today.month) and current_time >= backup_today:
                        should_backup = True
            
            if should_backup:
                logger.info(f"Automatisches Image-Backup fällig (Intervall: {interval}, Zeit: {backup_time_str})...")
                
                # Zuerst Datenbank-Wartung (VACUUM/ANALYZE)
                self.db_manager.run_maintenance()
                
                result = self.image_backup_manager.create_backup()
                if result['success']:
                    keep_count = self.config.get('backup', {}).get('keep_count', 10)
                    self.image_backup_manager.cleanup_old_backups(keep_count=keep_count)
                    
                    # Konfig aktualisieren
                    self.config['backup']['last_backup'] = now.isoformat()
                    config_file = self.base_dir / "Konfiguration" / "settings.json"
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(self.config, f, indent=4, ensure_ascii=False)
                    logger.info("Automatisches Image-Backup erfolgreich abgeschlossen.")
                else:
                    logger.error(f"Automatisches Image-Backup fehlgeschlagen: {result.get('error')}")

        except Exception as e:
            logger.error(f"Fehler bei automatischer Backup-Prüfung: {e}")

    def start_backup_timer(self):
        """Startet einen Timer, der regelmäßig prüft, ob ein Backup fällig ist (alle 60 Sekunden)"""
        def timer_loop():
            while True:
                try:
                    self.check_auto_backup()
                except Exception as e:
                    logger.error(f"Fehler im Backup-Timer: {e}")
                # Warte 60 Sekunden bis zur nächsten Prüfung
                import time
                time.sleep(60)

        # Starte Timer in eigenem Thread
        self.backup_timer_thread = threading.Thread(target=timer_loop, daemon=True)
        self.backup_timer_thread.start()

        # Cleanup-Task für inaktive Sessions und Locks
        def cleanup_loop():
            while True:
                try:
                    # Kein Session-Timeout mehr - keine Sessions löschen
                    # Nur Locks bereinigen
                    self.db_manager.cleanup_inactive_sessions_and_locks(timeout_minutes=0)
                except Exception as e:
                    logger.error(f"Fehler im Cleanup-Task: {e}")
                # Warte 60 Sekunden bis zur nächsten Prüfung
                import time
                time.sleep(60)

        # Starte Cleanup in eigenem Thread
        self.cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        # Archive-Task für automatische Archivierung
        def archive_loop():
            while True:
                try:
                    self.check_auto_archive()
                except Exception as e:
                    logger.error(f"Fehler im Archive-Timer: {e}")
                # Warte 60 Sekunden bis zur nächsten Prüfung
                import time
                time.sleep(60)

        # Starte Archive in eigenem Thread
        self.archive_thread = threading.Thread(target=archive_loop, daemon=True)
        self.archive_thread.start()

    def check_auto_archive(self):
        """Prüft ob eine automatische Archivierung fällig ist"""
        try:
            if not self.config.get('archive', {}).get('auto_archive', False):
                return

            result = self.archive_manager.run_auto_archive()

            if result['total'] > 0:
                logger.info(f"Automatische Archivierung: {result['message']}")

                # Konfig aktualisieren
                self.config['archive']['last_run'] = datetime.now().isoformat()
                config_file = self.base_dir / "Konfiguration" / "settings.json"
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Fehler bei automatischer Archivierung: {e}")

    def create_app(self):
        """Erstellt Flask Anwendung mit Blueprint-Struktur"""
        app = Flask(__name__, 
                   static_folder=str(self.base_dir / "Benutzeroberflaeche"),
                   static_url_path="/")
        
        # CORS für Frontend mit konfigurierten Origins
        port = self.config['server']['port']
        cors_config = self.config.get('cors', {
            'allowed_origins': [f'http://localhost:{port}', f'http://127.0.0.1:{port}'],
            'allow_credentials': True
        })
        CORS(app, origins=cors_config['allowed_origins'], supports_credentials=cors_config.get('allow_credentials', True))
        
        # gzip Komprimierung aktivieren
        Compress(app)
        
        # Rate Limiting Middleware (für Schutz vor Überlastung)
        network_config = self.config.get('network', {
            'request_limit_enabled': False,
            'max_requests_per_minute': 100
        })
        rate_limit_config = {
            'enabled': network_config.get('request_limit_enabled', False),
            'rate_limit_per_minute': network_config.get('max_requests_per_minute', 100),
            'block_duration_seconds': network_config.get('block_duration_seconds', 60)
        }
        rate_limiter = RateLimitMiddleware(app)
        rate_limiter.configure(rate_limit_config)
        app.wsgi_app = rate_limiter
        
        # Security Headers
        @app.after_request
        def add_security_headers(response):
            # Verhindert Clickjacking
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            # Verhindert MIME-Type Sniffing
            response.headers['X-Content-Type-Options'] = 'nosniff'
            # Aktiviert XSS-Schutz
            response.headers['X-XSS-Protection'] = '1; mode=block'
            # Referrer Policy
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            # Content Security Policy (relaxed für lokale Entwicklung)
            response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: *"
            return response
        
        # Konfiguration
        # SECRET_KEY aus Konfiguration oder Umgebungsvariable laden
        secret_key = os.environ.get('ORDAMA_SECRET_KEY')
        if not secret_key:
            secret_key = self.config['security'].get('secret_key', '')

            if not secret_key:
                # Wenn kein SECRET_KEY vorhanden, Fehler werfen
                logger.error("Kein SECRET_KEY in Konfiguration gefunden. Bitte fügen Sie einen SECRET_KEY in settings.json hinzu.")
                raise ValueError("SECRET_KEY ist erforderlich für die Session-Sicherheit")
            else:
                logger.info("SECRET_KEY aus Konfiguration geladen")
        
        # Pfad auflösen (unterstützt absolut und relativ)
        def resolve_path(p_str):
            p = Path(p_str)
            return p if p.is_absolute() else self.base_dir / p

        data_base_dir = resolve_path(self.config['paths'].get('data_base_dir', './Speicher'))
        data_dir = data_base_dir / "Datenbank"
        akten_dir = data_base_dir / "Akten"
        vorlagen_dir = data_base_dir / "Formularvorlagen"
        backup_dir = resolve_path(self.config['paths'].get('backup_dir', './Backups'))

        is_production = True
        session_cookie_secure = is_production
        
        # Session-Konfiguration aus settings.json laden
        session_config = self.config.get('session', {})
        session_permanent = session_config.get('permanent', True)
        
        # Session-Lifetime immer auf 100 Jahre setzen (kein Session-Timeout)
        session_lifetime = timedelta(days=36500)  # 100 Jahre = praktisch keine Ablaufzeit
        
        app.config.update({
            'SECRET_KEY': secret_key,
            'SESSION_PERMANENT': session_permanent,
            'PERMANENT_SESSION_LIFETIME': session_lifetime,
            'SESSION_COOKIE_SECURE': False,  # Für lokale Entwicklung und Brave-Kompatibilität auf False
            'SESSION_COOKIE_HTTPONLY': False,  # Für Brave-Kompatibilität auf False
            'SESSION_COOKIE_SAMESITE': None,  # Für Brave-Kompatibilität auf None
            'SESSION_COOKIE_DOMAIN': None,  # Cookie-Domain automatisch bestimmen
            'SESSION_COOKIE_PATH': '/',  # Cookie für gesamten Pfad verfügbar
            'SESSION_REFRESH_EACH_REQUEST': True,  # Cookie bei jeder Anfrage erneuern
            'MAX_CONTENT_LENGTH': self.config['upload']['max_file_size_mb'] * 1024 * 1024,
            'DATA_BASE_DIR': data_base_dir,
            'DATA_DIR': data_dir,
            'AKTEN_DIR': akten_dir,
            'VORLAGEN_DIR': vorlagen_dir,
            'BACKUP_DIR': backup_dir
        })
        
        # Flask Entwicklungsserver-Warnung unterdrücken
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        
        # Verzeichnisse erstellen (müssen vor DB-Initialisierung existieren)
        data_dir.mkdir(parents=True, exist_ok=True)
        akten_dir.mkdir(parents=True, exist_ok=True)
        vorlagen_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Prüfe, ob eine ausstehende Restore-Instruktion existiert
        restore_instruction_file = backup_dir / "restore_instruction.json"
        if restore_instruction_file.exists():
            logger.info("Ausstehende Restore-Instruktion gefunden - führe Wiederherstellung durch...")
            try:
                with open(restore_instruction_file, 'r', encoding='utf-8') as f:
                    restore_instruction = json.load(f)
                
                temp_restore_dir = Path(restore_instruction['temp_restore_dir'])
                data_dir = Path(restore_instruction['data_dir'])
                akten_dir = Path(restore_instruction['akten_dir'])
                data_base_dir = Path(restore_instruction['data_base_dir'])
                base_dir = Path(restore_instruction['base_dir'])
                
                logger.info(f"Temporäres Restore-Verzeichnis: {temp_restore_dir}")
                
                # Datenbankdateien wiederherstellen
                temp_db_dir = temp_restore_dir / "Datenbank"
                if temp_db_dir.exists():
                    for db_file in temp_db_dir.glob("*"):
                        dest_path = data_dir / db_file.name
                        if dest_path.exists():
                            dest_path.unlink()
                        shutil.move(str(db_file), str(dest_path))
                        logger.info(f"Datenbankdatei wiederhergestellt: {db_file.name}")
                
                # Andere Verzeichnisse wiederherstellen
                mappings = [
                    (temp_restore_dir / "Akten", akten_dir),
                    (temp_restore_dir / "Formularvorlagen", data_base_dir / "Formularvorlagen"),
                    (temp_restore_dir / "Chat", data_base_dir / "Chat"),
                    (temp_restore_dir / "Konfiguration", base_dir / "Konfiguration"),
                ]
                
                for temp_src, actual_dest in mappings:
                    if temp_src.exists():
                        if actual_dest.exists():
                            shutil.rmtree(actual_dest)
                        shutil.move(str(temp_src), str(actual_dest))
                        logger.info(f"Verzeichnis wiederhergestellt: {actual_dest.name}")
                
                # Archiv wiederherstellen
                temp_archive_dir = temp_restore_dir / "Archiv"
                if temp_archive_dir.exists():
                    actual_archive_dir = akten_dir / "Archiv"
                    if actual_archive_dir.exists():
                        shutil.rmtree(actual_archive_dir)
                    shutil.move(str(temp_archive_dir), str(actual_archive_dir))
                    logger.info("Archiv wiederhergestellt")
                
                # Temporäres Verzeichnis aufräumen
                shutil.rmtree(temp_restore_dir)
                logger.info(f"Temporäres Verzeichnis gelöscht: {temp_restore_dir}")
                
                # Instruktionsdatei löschen
                restore_instruction_file.unlink()
                logger.info("Restore-Instruktion gelöscht - Wiederherstellung abgeschlossen")
                
            except Exception as e:
                logger.error(f"Fehler bei der automatischen Wiederherstellung: {e}")
                # Instruktion nicht löschen, damit es beim nächsten Start erneut versucht wird

        # Module initialisieren
        self.db_manager = DatabaseManager(self.base_dir, self.config)
        self.akten_manager = AktenManager(self.base_dir, self.config, self.db_manager)
        self.security_logger = SecurityEventLogger(self.db_manager)
        self.backup_manager = BackupManager(self.base_dir, self.config, self.security_logger)
        self.image_backup_manager = ImageBackupManager(self.base_dir, self.config, self.db_manager, None, self.security_logger)
        self.update_manager = UpdateManager(self.base_dir)
        self.sperr_manager = SperrManager(self.db_manager)
        self.auth_manager = AuthManager(self.db_manager, self.security_logger)
        self.audit_logger = AuditLogger(self.base_dir)
        self.formular_manager = FormularManager(self.base_dir, self.db_manager, self.akten_manager, vorlagen_dir)
        self.ocr_manager = OCRManager(self.base_dir, self.config, self.db_manager)
        self.archive_manager = ArchiveManager(self.db_manager, self.config)
        self.akten_manager.set_ocr_manager(self.ocr_manager)
        # Update image backup manager with OCR manager after initialization
        self.image_backup_manager.ocr_manager = self.ocr_manager

        # Security Logger an Rate Limiter übergeben
        if hasattr(app, 'wsgi_app') and hasattr(app.wsgi_app, 'set_security_logger'):
            app.wsgi_app.set_security_logger(self.security_logger)
            logger.info("Security Logger an Rate Limiter übergeben")
        else:
            logger.warning("Konnte Security Logger nicht an Rate Limiter übergeben - Methode nicht gefunden")

        # Zeige Backup-Info beim Serverstart
        backups = self.image_backup_manager.list_backups()
        if backups:
            last_backup = backups[0].get('created_at', 'Unbekannt')
            logger.info(f"Backup-Info: Es existieren {len(backups)} Image-Backups, letzter Backup: {last_backup}")
        else:
            logger.info("Backup-Info: Keine Image-Backups vorhanden")

        # Prüfe, ob Backup bei Start durchgeführt werden soll
        backup_on_startup = self.config.get('backup', {}).get('backup_on_startup', False)
        if backup_on_startup:
            logger.info("Image-Backup bei Programmstart aktiv - führe Backup durch...")
            self.db_manager.run_maintenance()
            result = self.image_backup_manager.create_backup()
            if result['success']:
                keep_count = self.config.get('backup', {}).get('keep_count', 10)
                self.image_backup_manager.cleanup_old_backups(keep_count=keep_count)
                self.config['backup']['last_backup'] = datetime.now().isoformat()
                config_file = self.base_dir / "Konfiguration" / "settings.json"
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                logger.info("Start-Image-Backup erfolgreich abgeschlossen.")
            else:
                logger.error(f"Start-Image-Backup fehlgeschlagen: {result.get('error')}")

        # Datenbank initialisieren
        self.db_manager.initialize_database()

        # System-Start Security Event loggen
        self.security_logger.log_system_start()

        # Alte Security Logs bereinigen (älter als 30 Tage)
        self.security_logger.clear_old_logs(days=30)

        # OCR-Worker starten
        self.ocr_manager.start()

        # Automatisches Backup-Timer starten
        self.start_backup_timer()

        # IP-Whitelist Middleware
        @app.before_request
        def check_ip_whitelist():
            import ipaddress
            
            # Erlaube statische Dateien und die Hauptseite
            if (request.path == '/' or
                request.path.endswith(('.html', '.css', '.js', '.png', '.ico', '.jpg', '.jpeg')) or
                request.path.startswith('/static')):
                return
            
            # Erlaube Health-Check Endpunkte
            if request.path in ['/api/health', '/api/auth/heartbeat']:
                return
            
            # Whitelist-Modus aus Konfiguration holen
            whitelist_mode = self.config.get('security', {}).get('ip_whitelist_mode', 'none')
            
            # Wenn Modus 'none' ist, keine Einschränkung
            if whitelist_mode == 'none':
                return
            
            # Whitelist basierend auf Modus aus Konfiguration holen
            if whitelist_mode == 'cloudflare':
                whitelist = self.config.get('security', {}).get('cloudflare_ips', [])
                # Nur loggen wenn sich die Whitelist geändert hat (Rate Limiting)
                if not hasattr(self, '_last_cloudflare_count') or self._last_cloudflare_count != len(whitelist):
                    logger.info(f"IP-Whitelist Modus: cloudflare, {len(whitelist)} Einträge")
                    self._last_cloudflare_count = len(whitelist)
            elif whitelist_mode == 'custom':
                whitelist = self.config.get('security', {}).get('custom_ips', [])
                # Nur loggen wenn sich die Whitelist geändert hat (Rate Limiting)
                if not hasattr(self, '_last_custom_count') or self._last_custom_count != len(whitelist):
                    logger.info(f"IP-Whitelist Modus: custom, {len(whitelist)} Einträge")
                    self._last_custom_count = len(whitelist)
            else:
                whitelist = []
                logger.info(f"IP-Whitelist Modus: {whitelist_mode}")
            
            # Wenn Whitelist leer oder None ist, keine Einschränkung
            if not whitelist or len(whitelist) == 0:
                logger.info("Whitelist ist leer - keine Einschränkung")
                return
            
            # Prüfen ob Whitelist nur leere Strings enthält
            non_empty_whitelist = [w for w in whitelist if w and w.strip()]
            if not non_empty_whitelist:
                logger.info("Whelist enthält nur leere Strings - keine Einschränkung")
                return
            
            # Client IP ermitteln
            # Für Cloudflare Tunnel: CF-Connecting-IP enthält die Cloudflare IP
            # X-Forwarded-For enthält [client_ip, cloudflare_ip] (wird von Cloudflare Tunnel nicht immer gesetzt)
            client_ip = request.remote_addr
            
            # Prüfe CF-Connecting-IP Header (Cloudflare-spezifisch)
            cf_connecting_ip = request.headers.get('CF-Connecting-IP')
            if cf_connecting_ip:
                client_ip = cf_connecting_ip
                logger.info(f"Cloudflare IP aus CF-Connecting-IP: {client_ip}")
            elif request.headers.get('X-Forwarded-For'):
                # Fallback auf X-Forwarded-For
                forwarded_ips = request.headers.get('X-Forwarded-For').split(',')
                client_ip = forwarded_ips[0].strip()
                logger.info(f"IP aus X-Forwarded-For: {client_ip}")
            
            # Rate Limiting für detaillierte IP-Logs (nur alle 10 Sekunden oder bei IP-Wechsel)
            if not hasattr(self, '_last_ip_log_time'):
                self._last_ip_log_time = {}
            if not hasattr(self, '_last_logged_ip'):
                self._last_logged_ip = {}
            
            current_time = datetime.now()
            should_log_ip = (client_ip not in self._last_logged_ip or 
                            current_time - self._last_ip_log_time.get(client_ip, datetime.min) > timedelta(seconds=10))
            
            if should_log_ip:
                logger.info(f"Client IP: {client_ip}, Remote Addr: {request.remote_addr}, CF-Connecting-IP: {request.headers.get('CF-Connecting-IP', 'N/A')}, X-Forwarded-For: {request.headers.get('X-Forwarded-For', 'N/A')}")
                self._last_logged_ip[client_ip] = True
                self._last_ip_log_time[client_ip] = current_time
            
            # Localhost immer erlauben
            if client_ip in ['127.0.0.1', '::1', 'localhost']:
                return
            
            # Prüfen ob Client IP in Whitelist ist (unterstützt CIDR)
            try:
                client_ip_obj = ipaddress.ip_address(client_ip)
                for allowed in non_empty_whitelist:
                    if not allowed or allowed.strip() == '':
                        continue
                    # Port entfernen falls vorhanden (z.B. 192.168.0.1:8080 -> 192.168.0.1)
                    allowed_ip = allowed.strip().split(':')[0]
                    try:
                        if '/' in allowed_ip:
                            # CIDR Range
                            if client_ip_obj in ipaddress.ip_network(allowed_ip, strict=False):
                                return
                        else:
                            # Einzelne IP
                            if client_ip == allowed_ip:
                                return
                    except ValueError:
                        # Ungültiges Format überspringen
                        continue
                
                # IP nicht in Whitelist - Rate Limiting für Warnungen
                if not hasattr(self, '_last_rejection_log_time'):
                    self._last_rejection_log_time = {}
                
                should_log_rejection = (client_ip not in self._last_rejection_log_time or 
                                      current_time - self._last_rejection_log_time.get(client_ip, datetime.min) > timedelta(seconds=30))
                
                if should_log_rejection:
                    logger.warning(f"Zugriff von nicht erlaubter IP abgelehnt: {client_ip} (Modus: {whitelist_mode})")
                    self._last_rejection_log_time[client_ip] = current_time
                
                return jsonify({
                    'error': 'Zugriff verweigert',
                    'message': f'Ihre IP-Adresse ({client_ip}) ist nicht in der Whitelist.'
                }), 403
            except ValueError:
                # Ungültige Client IP - aus Sicherheitsgründen ablehnen
                logger.warning(f"Ungültige Client IP: {client_ip}")
                return jsonify({
                    'error': 'Zugriff verweigert',
                    'message': 'Ungültige IP-Adresse'
                }), 403
        
        # Zugriffs-Logging Middleware (für Admin-Überwachung)
        @app.before_request
        def log_request():
            # Logge nur API-Requests (keine statischen Dateien)
            if request.path.startswith('/api/') and not request.path.endswith(('.html', '.css', '.js')):
                try:
                    # Technische Endpoints ausschließen (Health-Checks, Heartbeat, etc.)
                    excluded_endpoints = ['/api/health', '/api/auth/heartbeat', '/api/auth/me']
                    if request.path in excluded_endpoints:
                        return
                    
                    # Benutzer ermitteln (falls eingeloggt)
                    user_name = "Gast"
                    if 'user_id' in session:
                        user_id = session.get('user_id')
                        user = self.db_manager.get_user_by_id(user_id)
                        if user:
                            user_name = user['username']
                    # Bei Login-Request Benutzernamen aus Request-Body holen
                    elif request.path == '/api/auth/login' and request.method == 'POST':
                        try:
                            data = request.get_json()
                            if data and 'username' in data:
                                user_name = data['username']
                        except (ValueError, TypeError):
                            pass
                    
                    # IP-Adresse ermitteln
                    ip_address = request.remote_addr or "Unbekannt"
                    
                    # Zugriffs-Log schreiben
                    self.audit_logger.log_access(
                        user_name=user_name,
                        endpoint=request.path,
                        method=request.method,
                        ip_address=ip_address
                    )
                except Exception as e:
                    # Logging-Fehler sollten die Anwendung nicht blockieren
                    pass

        # Blueprints registrieren
        self.register_blueprints(app)
        
        # Hauptroute für Frontend
        @app.route('/')
        def index():
            """Hauptseite - liefert das Frontend"""
            return send_from_directory(str(self.base_dir / "Benutzeroberflaeche"), "index.html")

        @app.route('/viewer')
        def viewer():
            """Dedizierte Viewer-Seite für Anhänge (mit Download-Schutz)"""
            return send_from_directory(str(self.base_dir / "Benutzeroberflaeche"), "viewer.html")
        
        @app.route('/api/health')
        def health_check():
            """Health Check Endpoint für Offline-Erkennung"""
            return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

        @app.route('/api/server-name')
        def get_server_name():
            """Öfflicher Endpunkt für den Servernamen (für Login-Screen)"""
            server_name = self.db_manager.get_setting('server_name')
            return jsonify({'server_name': server_name or ''})

        @app.route('/api/csrf-token')
        def get_csrf_token():
            """Liefert ein CSRF-Token für den Frontend-Gebrauch"""
            return jsonify({'csrf_token': CSRFProtection.get_token()})

        @app.after_request
        def add_security_headers(response):
            # Sicherheits-Header hinzufügen
            # X-Frame-Options: SAMEORIGIN erlaubt das Einbetten in Iframes auf der gleichen Domain
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            # CSP-Header für lokale Netzwerke und PDF-Vorschau optimiert
            # Wir erlauben http: und https: sowie 'self' für alle Quellen
            csp = (
                "default-src 'self' http:; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' http:; "
                "style-src 'self' 'unsafe-inline' http:; "
                "img-src 'self' data: http:; "
                "frame-src 'self' data: blob:; "
                "object-src 'self' data: blob:; "
                "media-src 'self' data: blob: http:; "
                "connect-src 'self' http:; "
                "frame-ancestors 'self';"
            )
            response.headers['Content-Security-Policy'] = csp
            
            return response
        
        return app
    
    def register_blueprints(self, app):
        """Registriert alle Blueprints"""
        # Auth Blueprint
        auth_bp = init_auth_blueprint(self.auth_manager, self.db_manager, self.config)
        app.register_blueprint(auth_bp)
        
        # User Blueprint
        user_bp = create_user_blueprint(self.auth_manager, self.db_manager, self.config, None, self.security_logger)
        app.register_blueprint(user_bp)
        
        # Records Blueprint
        records_bp = init_records_blueprint(
            app,
            self.auth_manager,
            self.db_manager,
            self.akten_manager,
            self.sperr_manager,
            self.audit_logger,
            self.ocr_manager,
            self.config
        )
        app.register_blueprint(records_bp)
        
        # Admin Blueprint
        admin_bp = init_admin_blueprint(
            self.auth_manager,
            self.db_manager,
            self.config,
            self.base_dir,
            self.audit_logger,
            self.backup_manager,
            self.update_manager,
            self.VERSION,
            self.ocr_manager,
            self.image_backup_manager
        )
        app.register_blueprint(admin_bp)

        # Tunnel Blueprint
        from blueprints.tunnel_blueprint import init_tunnel_blueprint
        tunnel_bp = init_tunnel_blueprint(self.base_dir, self.config_dir)
        app.register_blueprint(tunnel_bp)

        # Karte Blueprint
        karte_bp = init_karte_blueprint(self.auth_manager, self.db_manager, self.akten_manager)
        app.register_blueprint(karte_bp)

        # Category Blueprint
        init_category_blueprint(self.auth_manager, self.db_manager, self.audit_logger)
        app.register_blueprint(category_bp)

        # Formular Blueprint
        init_formular_blueprint(app, self.auth_manager, self.formular_manager, self.audit_logger)
        app.register_blueprint(formular_bp)

        # Gallery Blueprint
        gallery_bp = init_gallery_blueprint(
            app,
            self.auth_manager,
            self.db_manager,
            self.base_dir,
            self.config
        )
        app.register_blueprint(gallery_bp)

        # Assistant Blueprint
        assistant_bp = init_assistant_blueprint(
            self.auth_manager,
            self.db_manager,
            self.akten_manager
        )
        app.register_blueprint(assistant_bp)

        # Chat Blueprint
        chat_bp = init_chat_blueprint(
            self.auth_manager,
            self.db_manager,
            self.config
        )
        app.register_blueprint(chat_bp)

    def shutdown_server(self, signum=None, frame=None):
        """Herunterfahren des Servers vorbereiten"""
        if signum:
            logger.info(f"Signal {signum} empfangen. Fahre herunter...")
        else:
            logger.info("Server wird heruntergefahren...")
            
        # Datenbank schützen (Header-Manipulation)
        try:
            if hasattr(self, 'ocr_manager') and self.ocr_manager:
                self.ocr_manager.stop()
            db_path = str(self.db_manager.db_path)
            if setze_datenbank_schutz(db_path, aktivieren=True):
                logger.info("Datenbank erfolgreich geschützt.")
        except Exception as e:
            logger.error(f"Fehler beim Schützen der Datenbank beim Beenden: {e}")
            
        sys.exit(0)
    
    def run(self):
        """Startet den Server mit sauberem Shutdown bei Fenster-Schliessen"""
        import signal
        import sys
        
        def signal_handler(sig, frame):
            print('\nServer wird beendet...')
            self.shutdown_server()
        
        # Signal-Handler registrieren
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Linux-spezifisch: SIGHUP behandeln (Server schließt wenn Konsole geschlossen wird)
        # Nur auf Unix/Linux Systemen anwenden
        import platform
        if platform.system() != 'Windows':
            try:
                signal.signal(signal.SIGHUP, signal_handler)
                logger.info("SIGHUP-Signal wird behandelt - Server schließt bei Konsole-Schließung")
            except Exception as e:
                logger.warning(f"SIGHUP-Handler konnte nicht gesetzt werden: {e}")
        
        # Windows-spezifisch: CTRL_CLOSE_EVENT (Konsolenfenster geschlossen)
        import sys
        if sys.platform == 'win32':
            try:
                import ctypes
                from ctypes import wintypes
                import atexit
                
                kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                
                def ctrl_handler(sig):
                    print('\nKonsolenfenster wird geschlossen...')
                    self.shutdown_server()
                    return True
                
                handler = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)(ctrl_handler)
                kernel32.SetConsoleCtrlHandler(handler, True)
                
                # Registriere Notfall-Exit
                atexit.register(self.shutdown_server)
                
            except Exception as e:
                print(f"Windows-Handler konnte nicht registriert werden: {e}")
                pass
        
        # Host basierend auf Einstellung
        host = self.config['server'].get('host', '127.0.0.1')
        port = self.config['server'].get('port', 8080)
        
        # Falls allow_external explizit gesetzt ist, aber host noch 127.0.0.1 ist
        if self.config['server'].get('allow_external', False) and host == '127.0.0.1':
            host = '0.0.0.0'
        
        print("ORDAMA Server")
        print(f"Server: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
        
        # Lokale IP-Adresse für Netzwerkzugriff anzeigen
        try:
            import socket
            # Lokale IP ermitteln (nicht localhost)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Verbindung zu Google DNS für IP-Ermittlung
            local_ip = s.getsockname()[0]
            s.close()

            if local_ip != "127.0.0.1" and local_ip != host:
                print(f"Lokale IP: http://{local_ip}:{self.config['server']['port']}")
                # Netzwerk-Info Event loggen
                self.security_logger.log_server_started(local_ip, self.config['server']['port'])
        except Exception:
            pass  # Bei Fehlern einfach keine lokale IP anzeigen
        
        if self.config['server'].get('allow_external', False):
            print("Server ist extern erreichbar!")
        
        try:
            self.app.run(
                host=host,
                port=self.config['server']['port'],
                use_reloader=False,
                threaded=True
            )
        except KeyboardInterrupt:
            self.shutdown_server()
        except Exception as e:
            print(f"Server Fehler: {e}")
            self.shutdown_server()

if __name__ == '__main__':
    app = ORDAMA()
    app.run()
