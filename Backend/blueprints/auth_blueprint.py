"""
Auth Blueprint - Authentifizierung und User-Management
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from functools import wraps
import os
import json
import sys
from pathlib import Path

# security_utils importieren
sys.path.insert(0, str(Path(__file__).parent.parent))
from security_utils import InputSanitizer

logger = logging.getLogger(__name__)

# Direktes File-Logging für Debug-Zwecke
DEBUG_LOG_FILE = os.path.join(os.path.dirname(__file__), '..', 'ordama_debug.log')
LOGIN_STATUS_FILE = os.path.join(os.path.dirname(__file__), '..', 'login_status.json')

def debug_log(message):
    """Schreibt Debug-Meldungen direkt in eine Datei"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp} - {message}\n")
    print(f"DEBUG: {message}")

def get_login_status():
    """Liest den Login-Status aus der JSON-Datei"""
    try:
        if os.path.exists(LOGIN_STATUS_FILE):
            with open(LOGIN_STATUS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Fehler beim Lesen des Login-Status: {e}")
        return {}

def set_login_status(user_id, username, logged_in=True):
    """Setzt den Login-Status in der JSON-Datei"""
    try:
        status = get_login_status()
        if logged_in:
            status[str(user_id)] = {
                'username': username,
                'logged_in': True,
                'timestamp': datetime.now().isoformat()
            }
        else:
            status.pop(str(user_id), None)
        with open(LOGIN_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        logger.error(f"Fehler beim Setzen des Login-Status: {e}")

def is_user_logged_in(user_id):
    """Prüft ob ein Benutzer eingeloggt ist (mit Zeitstempel-Validierung)"""
    status = get_login_status()
    user_status = status.get(str(user_id))

    if not user_status or not user_status.get('logged_in', False):
        return False

    # Zeitstempel prüfen - wenn älter als 24 Stunden, automatisch zurücksetzen
    try:
        timestamp = user_status.get('timestamp')
        if timestamp:
            login_time = datetime.fromisoformat(timestamp)
            # Wenn Login älter als 24 Stunden ist, als abgelaufen betrachten
            if datetime.now() - login_time > timedelta(hours=24):
                logger.info(f"Login-Status für user_id={user_id} abgelaufen (24 Stunden), wird zurückgesetzt")
                set_login_status(user_id, None, False)
                return False
    except Exception as e:
        logger.error(f"Fehler beim Validieren des Login-Zeitstempels: {e}")

    return True

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def init_auth_blueprint(auth_manager, db_manager, config):
    """Initialisiert das Auth Blueprint mit den Managern"""
    
    @auth_bp.route('/login', methods=['POST'])
    def login():
        try:
            data = request.get_json()
            username = InputSanitizer.sanitize_text(data.get('username', '').strip())
            password = data.get('password', '')

            if not username or not password:
                return jsonify({'error': 'Benutzername und Passwort erforderlich'}), 400

            # Rate-Limit prüfen
            ip_address = request.remote_addr
            max_attempts = config['security'].get('max_login_attempts', 5)
            window_minutes = config['security'].get('rate_limit_window_minutes', 15)
            allowed, failed_count, wait_seconds = db_manager.check_login_rate_limit(username, ip_address, max_attempts, window_minutes)

            if not allowed:
                # logger.warning(f"Rate-Limit überschritten für username={username}, ip={ip_address}")
                wait_minutes = (wait_seconds + 59) // 60  # Aufrunden auf ganze Minuten

                # Security Log für Rate-Limit Überschreitung
                db_manager.add_security_log(
                    event_type='rate_limit_exceeded',
                    severity='danger',
                    message=f'Rate-Limit überschritten: {failed_count} fehlgeschlagene Versuche für {username} von IP {ip_address}',
                    ip_address=ip_address,
                    username=username
                )

                return jsonify({'error': f'Zu viele fehlgeschlagene Login-Versuche. Bitte {wait_minutes} Minute(n) warten.', 'waitSeconds': wait_seconds}), 429

            result = auth_manager.authenticate_user(username, password)

            # Login-Versuch aufzeichnen
            success = 'error' not in result
            db_manager.record_login_attempt(username, ip_address, success)

            if 'error' in result:
                remaining_attempts = max_attempts - failed_count - 1
                return jsonify({'error': result['error'], 'remainingAttempts': remaining_attempts}), 401

            # Device-ID aus Request holen (muss vorhanden sein für zuverlässiges Session-Management)
            device_id = session.get('device_id') or request.headers.get('X-Device-ID')
            if not device_id:
                # Fallback: Keine Warnung, nur generieren für Browser-Kompatibilität
                import secrets
                device_id = secrets.token_hex(16)

            # Prüfen ob Benutzer eine aktive Session hat (kein Timeout - Session läuft nur ab wenn Admin beendet)
            if True:
                active_session = db_manager.get_active_session(result['user']['id'], timeout_minutes=0)
                if active_session:
                    # Wenn es die gleiche device_id ist, Login erlauben (erneutes Login vom selben Gerät/Browser)
                    if active_session['device_id'] == device_id:
                        # Session NICHT löschen, nur Flask-Session aktualisieren
                        # DB-Session bleibt bestehen
                        session_needs_creation = False
                    else:
                        # Verschiedene device_id → wirklich anderes Gerät - Login erlauben und alte Session beenden
                        # Alle alten Sessions löschen und neue erstellen
                        db_manager.delete_all_user_sessions(result['user']['id'])
                        session_needs_creation = True
                else:
                    # Keine aktive Session - neue Session erstellen
                    session_needs_creation = True
            else:
                # Admins: Multi-Device-Schutz deaktiviert, aber alte Sessions trotzdem bereinigen
                db_manager.delete_all_user_sessions(result['user']['id'])
                session_needs_creation = True

            # Einfache Session-basierte Authentifizierung (keine Tokens mehr)
            # Erst NACH der Multi-Device-Prüfung setzen, um fehlgeschlagene Login-Versuche nicht als Session zu zählen
            session['user_id'] = result['user']['id']
            session['username'] = username
            session['device_id'] = device_id  # Device-ID in Flask-Session speichern

            # Login-Status setzen (file-basiert)
            set_login_status(result['user']['id'], username, True)

            # Online-Status in Datenbank setzen
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET is_online = 1 WHERE id = ?', (result['user']['id'],))
                conn.commit()

            # Nur Session in Datenbank erstellen wenn nötig (für Admins oder erste Login)
            if session_needs_creation:
                # Alle alten Sessions löschen und neue erstellen
                db_manager.delete_all_user_sessions(result['user']['id'])
                # Client IP ermitteln
                client_ip = request.remote_addr
                cf_connecting_ip = request.headers.get('CF-Connecting-IP')
                if cf_connecting_ip:
                    client_ip = cf_connecting_ip
                elif request.headers.get('X-Forwarded-For'):
                    forwarded_ips = request.headers.get('X-Forwarded-For').split(',')
                    client_ip = forwarded_ips[0].strip()
                # Neue Session in Datenbank erstellen (für Heartbeat/Lock-Management)
                db_manager.create_user_session(result['user']['id'], device_id, client_ip)

            logger.info(f"Login erfolgreich: {username}")

            # Keine Tokens mehr zurückgeben - nur Session-Cookies
            result['device_id'] = device_id

            # Zusätzliche Header für Browser-Kompatibilität
            response = jsonify(result)
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

            return response

        except Exception as e:
            logger.error(f"Fehler beim Login: {e}")
            return jsonify({'error': f'Login fehlgeschlagen: {str(e)}'}), 500
    
    @auth_bp.route('/logout', methods=['POST'])
    @auth_manager.login_required
    def logout():
        try:
            user_id = session.get('user_id')

            # Alle Sessions dieses Benutzers löschen und Login-Status zurücksetzen (file-basiert)
            if user_id:
                db_manager.delete_all_user_sessions(user_id)
                set_login_status(user_id, None, False)
                
                # Online-Status in Datenbank zurücksetzen
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('UPDATE users SET is_online = 0 WHERE id = ?', (user_id,))
                    conn.commit()
                
                logger.info(f"Logout erfolgreich: user_id={user_id}")

            return jsonify(auth_manager.logout_user())
        except Exception as e:
            logger.error(f"Fehler beim Logout: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auth_bp.route('/me', methods=['GET'])
    @auth_manager.login_required
    def get_current_user_info():
        user = auth_manager.get_current_user()
        # Auch hier wird durch login_required die strikte Session-Validierung durchgeführt
        return jsonify({'user': user})
    
    @auth_bp.route('/heartbeat', methods=['POST'])
    @auth_manager.login_required
    def heartbeat():
        """Heartbeat-Endpoint für aktive Sessions - prüft ob Nutzer noch online ist"""
        try:
            user_id = session.get('user_id')

            # Prüfen ob Login vom Admin zurückgesetzt wurde (login_status.json)
            if not is_user_logged_in(user_id):
                logger.info(f"Benutzer user_id={user_id} wurde vom Administrator ausgeloggt")
                return jsonify({'success': False, 'session_expired': True}), 200
            device_id = request.headers.get('X-Device-ID')
            if not user_id:
                return jsonify({'error': 'Keine Session'}), 401

            # Device-ID muss vorhanden sein für Session-Validierung
            if not device_id:
                return jsonify({'error': 'Device-ID fehlt'}), 400

            # Strikte Validierung wird bereits durch login_required durchgeführt
            # Hier nur noch die Aktivität aktualisieren
            db_manager.update_user_session_activity(user_id)
            
            # Online-Status in Datenbank aktualisieren
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET is_online = 1 WHERE id = ?', (user_id,))
                conn.commit()
            
            # Locks dieses Benutzers verlängern
            import importlib
            sperr_module = importlib.import_module('sperr_logik')
            sperr_manager = sperr_module.SperrManager(db_manager)
            sperr_manager.extend_user_locks(user_id)
            
            return jsonify({'success': True, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            logger.error(f"Fehler beim Heartbeat: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auth_bp.route('/admin/reset-login-status/<int:user_id>', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def reset_login_status(user_id):
        """Setzt den Login-Status eines Benutzers zurück (nur Admin)"""
        try:
            # Alle Sessions des Benutzers löschen
            db_manager.delete_all_user_sessions(user_id)
            
            # Alle Locks des Benutzers freigeben
            try:
                import importlib
                sperr_module = importlib.import_module('sperr_logik')
                sperr_manager = sperr_module.SperrManager(db_manager)
                released_count = sperr_manager.release_all_user_locks(user_id)
                logger.info(f"Admin-Reset: {released_count} Locks für Benutzer {user_id} freigegeben")
            except Exception as e:
                logger.error(f"Fehler beim Freigeben der Locks beim Admin-Reset: {e}")
            
            # Login-Status zurücksetzen
            set_login_status(user_id, None, False)
            
            logger.info(f"Login-Status zurückgesetzt für user_id={user_id} durch Admin {session.get('username')}")
            return jsonify({'success': True, 'message': f'Login-Status für Benutzer {user_id} zurückgesetzt'})
        except Exception as e:
            logger.error(f"Fehler beim Zurücksetzen des Login-Status: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auth_bp.route('/admin/online-status', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_online_status():
        """Gibt den Online-Status aller Benutzer zurück (nur Admin)"""
        try:
            users = db_manager.list_users()
            
            # Online-Status aus Datenbank verwenden (konsistent mit Chat)
            online_users = []
            for user in users:
                online_users.append({
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role'],
                    'is_online': bool(user.get('is_online', 0)),
                    'last_seen': None  # Datenbank speichert keinen last_seen für is_online
                })
            
            return jsonify({'online_users': online_users})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Online-Status: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auth_bp.route('/set-online-status', methods=['POST'])
    @auth_manager.login_required
    def set_online_status():
        """Setzt den Online-Status des aktuellen Benutzers (online oder offline)"""
        try:
            user_id = session.get('user_id')
            username = session.get('username')
            if not user_id:
                return jsonify({'error': 'Keine Session'}), 401
            
            data = request.get_json()
            is_online = data.get('is_online', True)
            
            set_login_status(user_id, username, logged_in=is_online)
            
            logger.info(f"Online-Status gesetzt für user_id={user_id}, username={username}, is_online={is_online}")
            return jsonify({'success': True, 'is_online': is_online})
        except Exception as e:
            logger.error(f"Fehler beim Setzen des Online-Status: {e}")
            return jsonify({'error': str(e)}), 500

    @auth_bp.route('/security-logs', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def get_security_logs():
        """Ruft Security Logs ab (nur Admin)"""
        try:
            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)
            event_type = request.args.get('event_type', None)
            logs = db_manager.get_security_logs(limit=limit, offset=offset, event_type=event_type)
            return jsonify({'logs': logs})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Security Logs: {e}")
            return jsonify({'error': str(e)}), 500

    return auth_bp


def create_user_blueprint(auth_manager, db_manager, config, ip_whitelist_decorator, security_logger=None):
    """Erstellt User-Management Blueprint"""

    user_bp = Blueprint('users', __name__, url_prefix='/api/users')

    # Hilfsfunktion für optionalen IP-Whitelist Decorator
    def apply_ip_whitelist(f):
        if ip_whitelist_decorator:
            return ip_whitelist_decorator(f)
        return f

    @user_bp.route('/me/preferences', methods=['GET'])
    @auth_manager.login_required
    def get_my_preferences():
        try:
            prefs = db_manager.get_user_preferences(session['user_id'])
            return jsonify({'preferences': prefs})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Benutzereinstellungen: {e}")
            return jsonify({'error': str(e)}), 500

    @user_bp.route('/me/preferences', methods=['PUT'])
    @auth_manager.login_required
    def save_my_preferences():
        try:
            data = request.get_json() or {}
            preferences = data.get('preferences')
            if not isinstance(preferences, dict):
                return jsonify({'error': 'preferences-Objekt erforderlich'}), 400
            saved = db_manager.set_user_preferences(session['user_id'], preferences)
            return jsonify({'success': True, 'preferences': saved})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Benutzereinstellungen: {e}")
            return jsonify({'error': str(e)}), 500
    
    @user_bp.route('', methods=['GET'])
    @user_bp.route('/', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.admin_required
    @apply_ip_whitelist
    def list_users():
        try:
            users = db_manager.list_users()
            # Passwort-Hashes nicht an Frontend senden
            for u in users:
                u.pop('password_hash', None)
            return jsonify({'users': users})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @user_bp.route('', methods=['POST'])
    @user_bp.route('/', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    @apply_ip_whitelist
    def create_user():
        try:
            # Benutzerlimit prüfen
            allowed, limit_msg = auth_manager.check_user_limit()
            if not allowed:
                return jsonify({'error': limit_msg}), 403

            data = request.get_json()
            username = data.get('username', '').strip()
            password = data.get('password', '')
            role = data.get('role', 'user')
            can_read = 1 if data.get('can_read', True) else 0
            can_write = 1 if data.get('can_write', True) else 0
            can_delete = 1 if data.get('can_delete', False) else 0
            can_download = 1 if data.get('can_download', True) else 0
            can_upload = 1 if data.get('can_upload', True) else 0
            can_fill_forms = 1 if data.get('can_fill_forms', True) else 0
            can_set_category = 1 if data.get('can_set_category', True) else 0
            can_set_status = 1 if data.get('can_set_status', True) else 0
            can_set_border_color = 1 if data.get('can_set_border_color', True) else 0
            can_set_reminder = 1 if data.get('can_set_reminder', True) else 0
            can_delete_termine = 1 if data.get('can_delete_termine', True) else 0
            can_set_erinnerung = 1 if data.get('can_set_erinnerung', True) else 0
            can_delete_erinnerung = 1 if data.get('can_delete_erinnerung', True) else 0
            can_set_note = 1 if data.get('can_set_note', True) else 0
            can_archive = 1 if data.get('can_archive', True) else 0
            can_view_stats = 1 if data.get('can_view_stats', True) else 0
            can_view_records = 1 if data.get('can_view_records', True) else 0
            can_view_gallery = 1 if data.get('can_view_gallery', True) else 0
            can_chat = 1 if data.get('can_chat', True) else 0
            can_view_map = 1 if data.get('can_view_map', True) else 0
            can_view_calendar = 1 if data.get('can_view_calendar', True) else 0
            can_view_assistant = 1 if data.get('can_view_assistant', True) else 0
            can_view_archive = 1 if data.get('can_view_archive', True) else 0

            if not username or not password:
                return jsonify({'error': 'Benutzername und Passwort erforderlich'}), 400
            
            # Passwort-Länge prüfen mit Fallback auf 8 falls config nicht verfügbar
            password_min_length = 8
            if config and 'security' in config:
                password_min_length = config['security'].get('password_min_length', 8)
            
            if len(password) < password_min_length:
                return jsonify({'error': f"Passwort muss mindestens {password_min_length} Zeichen haben"}), 400

            user_id = db_manager.create_user(username, password, role, can_read, can_write, can_delete, can_download, can_upload, can_fill_forms,
                                              can_set_category, can_set_status, can_set_border_color, can_set_reminder, can_delete_termine,
                                              can_set_erinnerung, can_delete_erinnerung, can_set_note, can_archive, can_view_stats,
                                              can_view_records, can_view_gallery, can_chat, can_view_map, can_view_calendar, can_view_assistant, can_view_archive)
            
            # Neue Nutzer starten mit aktuellen Standard-Auswahlfeldern (optional)
            try:
                db_manager.set_user_preferences(user_id, db_manager.get_default_user_preferences())
            except Exception as e:
                logger.warning(f"Konnte User Preferences nicht setzen für Benutzer {username}: {e}")

            # Security Event loggen
            if security_logger:
                current_user = session.get('username')
                ip_address = request.remote_addr if request else None
                security_logger.log_user_created(username, current_user, ip_address)

            return jsonify({'success': True, 'user_id': user_id})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Benutzers: {e}", exc_info=True)
            return jsonify({'error': f'Benutzererstellung fehlgeschlagen: {str(e)}'}), 500
    
    @user_bp.route('/<int:user_id>', methods=['PUT'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def update_user(user_id):
        try:
            data = request.get_json()
            fields = {}
            if 'username' in data:
                fields['username'] = data['username']
            if 'role' in data:
                fields['role'] = data['role']
            if 'active' in data:
                fields['active'] = 1 if data['active'] else 0
            if 'can_read' in data:
                fields['can_read'] = 1 if data['can_read'] else 0
            if 'can_write' in data:
                fields['can_write'] = 1 if data['can_write'] else 0
            if 'can_download' in data:
                fields['can_download'] = 1 if data['can_download'] else 0
            if 'can_delete' in data:
                fields['can_delete'] = 1 if data['can_delete'] else 0
            if 'can_upload' in data:
                fields['can_upload'] = 1 if data['can_upload'] else 0
            if 'can_fill_forms' in data:
                fields['can_fill_forms'] = 1 if data['can_fill_forms'] else 0
            if 'can_set_category' in data:
                fields['can_set_category'] = 1 if data['can_set_category'] else 0
            if 'can_set_status' in data:
                fields['can_set_status'] = 1 if data['can_set_status'] else 0
            if 'can_set_border_color' in data:
                fields['can_set_border_color'] = 1 if data['can_set_border_color'] else 0
            if 'can_set_reminder' in data:
                fields['can_set_reminder'] = 1 if data['can_set_reminder'] else 0
            if 'can_delete_termine' in data:
                fields['can_delete_termine'] = 1 if data['can_delete_termine'] else 0
            if 'can_set_erinnerung' in data:
                fields['can_set_erinnerung'] = 1 if data['can_set_erinnerung'] else 0
            if 'can_delete_erinnerung' in data:
                fields['can_delete_erinnerung'] = 1 if data['can_delete_erinnerung'] else 0
            if 'can_set_note' in data:
                fields['can_set_note'] = 1 if data['can_set_note'] else 0
            if 'can_archive' in data:
                fields['can_archive'] = 1 if data['can_archive'] else 0
            if 'can_view_stats' in data:
                fields['can_view_stats'] = 1 if data['can_view_stats'] else 0
            if 'can_view_records' in data:
                fields['can_view_records'] = 1 if data['can_view_records'] else 0
            if 'can_view_gallery' in data:
                fields['can_view_gallery'] = 1 if data['can_view_gallery'] else 0
            if 'can_chat' in data:
                fields['can_chat'] = 1 if data['can_chat'] else 0
            if 'can_view_map' in data:
                fields['can_view_map'] = 1 if data['can_view_map'] else 0
            if 'can_view_calendar' in data:
                fields['can_view_calendar'] = 1 if data['can_view_calendar'] else 0
            if 'can_view_assistant' in data:
                fields['can_view_assistant'] = 1 if data['can_view_assistant'] else 0
            if 'can_view_archive' in data:
                fields['can_view_archive'] = 1 if data['can_view_archive'] else 0

            db_manager.update_user(user_id, **fields)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @user_bp.route('/<int:user_id>/signature', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.admin_required
    def upload_signature(user_id):
        try:
            data = request.get_json()
            signature_base64 = data.get('signature')
            if not signature_base64:
                return jsonify({'error': 'Keine Signatur-Daten empfangen'}), 400
            
            db_manager.update_user(user_id, signature=signature_base64)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @user_bp.route('/<int:user_id>/password', methods=['PUT'])
    @auth_manager.login_required
    def change_user_password(user_id):
        try:
            # Eigenes Passwort oder Admin kann alles aendern
            if session['user_id'] != user_id and session.get('role') != 'admin':
                return jsonify({'error': 'Nicht berechtigt'}), 403

            # Username vor Änderung holen
            user = db_manager.get_user_by_id(user_id)
            username = user['username'] if user else 'Unbekannt'

            data = request.get_json()
            new_password = data.get('new_password', '')
            if not new_password:
                return jsonify({'error': 'Neues Passwort erforderlich'}), 400
            if len(new_password) < config['security'].get('password_min_length', 8):
                return jsonify({'error': f'Passwort zu kurz (min. {config["security"]["password_min_length"]})'}), 400

            db_manager.change_password(user_id, new_password)

            # Security Event loggen
            if security_logger:
                current_user = session.get('username')
                ip_address = request.remote_addr if request else None
                security_logger.log_password_changed(username, current_user, ip_address)

            return jsonify({'success': True, 'message': 'Passwort geaendert'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @user_bp.route('/<int:user_id>', methods=['DELETE'])
    @auth_manager.login_required
    @auth_manager.admin_required
    @apply_ip_whitelist
    def delete_user(user_id):
        try:
            # Username vor Löschung holen
            user = db_manager.get_user_by_id(user_id)
            username = user['username'] if user else 'Unbekannt'

            db_manager.delete_user(user_id)

            # Security Event loggen
            if security_logger:
                current_user = session.get('username')
                ip_address = request.remote_addr if request else None
                security_logger.log_user_deleted(username, current_user, ip_address)

            return jsonify({'success': True})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return user_bp
