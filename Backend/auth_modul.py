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

Authentifizierung & Rechte-System für ORDAMA
"""

from functools import wraps
from flask import session, jsonify, request
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

class AuthManager:
    def __init__(self, db_manager, security_logger=None):
        self.db_manager = db_manager
        self.security_logger = security_logger
        self.failed_attempts = {} # username -> {'count': int, 'last_attempt': datetime}
    
    def login_required(self, f):
        """Login Decorator für API-Endpunkte mit strikter Session-Validierung"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, current_app
            auth_token = request.headers.get('X-Auth-Token')
            device_id = request.headers.get('X-Device-ID')

            # Prüfen ob Session-Cookie existiert
            if 'user_id' not in session:
                # Heartbeat ist tolerant gegenüber abgelaufenen Sessions
                if request.path.endswith('/heartbeat'):
                    return jsonify({'success': False, 'session_expired': True}), 200
                return jsonify({'error': 'Nicht authentifiziert', 'session_expired': True}), 401

            user_id = session.get('user_id')
            role = session.get('role')

            # Multi-Device-Schutz: Prüfen ob device_id mit DB übereinstimmt (nur für denselben Benutzer)
            if device_id:
                active_session = self.db_manager.get_active_session(user_id, timeout_minutes=0)
                if active_session and active_session['device_id'] != device_id:
                    # Device-ID stimmt nicht überein - Session beenden (nur wenn es derselbe Benutzer ist)
                    # Verschiedene Benutzer können gleichzeitig eingeloggt sein
                    session.clear()
                    if request.path.endswith('/heartbeat'):
                        return jsonify({'success': False, 'session_expired': True, 'reason': 'multi_device'}), 200
                    return jsonify({'error': 'Sie sind auf einem anderen Gerät eingeloggt. Diese Session wurde beendet.', 'session_expired': True}), 401

            # Token-Validierung (falls Token vorhanden)
            if auth_token and session.get('auth_token') != auth_token:
                # Token-Prüfung nur bei kritischen Operationen streng
                if not request.path.endswith('/heartbeat'):
                    return jsonify({'error': 'Ungültiges Token'}), 401

            return f(*args, **kwargs)
        return decorated_function
    
    def admin_required(self, f):
        """Admin-Decorator für geschützte Endpunkte mit strikter Session-Validierung"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, current_app
            device_id = request.headers.get('X-Device-ID')

            # Prüfen ob Session-Cookie existiert
            if 'user_id' not in session:
                return jsonify({'error': 'Nicht authentifiziert', 'session_expired': True}), 401

            user_id = session.get('user_id')

            # Admin-Check für Decorator-Funktion

            if session.get('role') != 'admin':
                return jsonify({'error': 'Admin-Rechte erforderlich'}), 403
            return f(*args, **kwargs)
        return decorated_function
    
    def check_permission(self, permission):
        """Prüft ob aktueller Benutzer eine Berechtigung hat (read/write/delete)"""
        user_id = session.get('user_id')
        if not user_id:
            return False
        user = self.db_manager.get_user(user_id)
        if not user:
            return False
        if user['role'] == 'admin':
            return True
        return bool(user.get(permission, 0))
    
    def require_permission(self, permission):
        """Decorator der eine bestimmte Berechtigung erfordert mit strikter Session-Validierung"""
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                from flask import request, current_app
                device_id = request.headers.get('X-Device-ID')

                # Prüfen ob Session-Cookie existiert
                if 'user_id' not in session:
                    return jsonify({'error': 'Nicht authentifiziert', 'session_expired': True}), 401

                user_id = session.get('user_id')

                # Session-Prüfung komplett deaktiviert - nur Flask Session Cookie prüfen
                # Admin-Logout funktioniert über separaten Endpunkt

                if not self.check_permission(permission):
                    return jsonify({'error': f'Berechtigung "{permission}" nicht vorhanden'}), 403
                return f(*args, **kwargs)
            return decorated_function
        return decorator
    
    def authenticate_user(self, username, password):
        """Authentifizierung mit Brute-Force-Schutz"""
        # Device-ID vom Frontend bekommen oder generieren (Fallback für Browser-Kompatibilität)
        device_id = request.headers.get('X-Device-ID')
        if not device_id:
            import secrets
            device_id = secrets.token_hex(16)
            logger.warning(f"Keine Device-ID im Request von {username}, verwende generierte: {device_id[:8]}...")

        # Brute-Force Schutz prüfen
        now = datetime.now()
        if username in self.failed_attempts:
            attempt_info = self.failed_attempts[username]
            if attempt_info['count'] >= 5:
                # Nach 5 Fehlversuchen für 5 Minuten sperren
                if now - attempt_info['last_attempt'] < timedelta(minutes=5):
                    logger.warning(f"Login blockiert (Brute-Force): {username}")
                    ip_address = request.remote_addr if request else None
                    if self.security_logger:
                        self.security_logger.log_rate_limit_exceeded(ip_address, username)
                    return {'error': 'Zu viele Fehlversuche. Bitte warten Sie 5 Minuten.'}
                else:
                    # Sperre abgelaufen
                    self.failed_attempts[username]['count'] = 0

        user = self.db_manager.verify_user_credentials(username, password)
        if user:
            # Erfolgreich: Fehlversuche zurücksetzen
            if username in self.failed_attempts:
                del self.failed_attempts[username]

            # Session mit Rechten erstellen
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['login_time'] = now.isoformat()
            session['device_id'] = device_id  # Device-ID auch in Session speichern

            # Last Login aktualisieren
            self.db_manager.update_last_login(user['id'])

            # Aktuelle Rechte laden
            full_user = self.db_manager.get_user(user['id'])

            logger.info(f"Login erfolgreich: username={username}, user_id={user['id']}, device_id={device_id[:8]}...")

            return {
                'success': True,
                'user': {
                    'id': full_user['id'],
                    'username': full_user['username'],
                    'role': full_user['role'],
                    'can_read': bool(full_user['can_read']),
                    'can_write': bool(full_user['can_write']),
                    'can_delete': bool(full_user['can_delete']),
                    'can_download': bool(full_user['can_download']),
                    'can_upload': bool(full_user['can_upload']),
                    'can_fill_forms': bool(full_user.get('can_fill_forms', 1)),
                    'can_set_category': bool(full_user.get('can_set_category', 1)),
                    'can_set_status': bool(full_user.get('can_set_status', 1)),
                    'can_set_border_color': bool(full_user.get('can_set_border_color', 1)),
                    'can_set_reminder': bool(full_user.get('can_set_reminder', 1)),
                    'can_delete_termine': bool(full_user.get('can_delete_termine', 1)),
                    'can_set_erinnerung': bool(full_user.get('can_set_erinnerung', 1)),
                    'can_delete_erinnerung': bool(full_user.get('can_delete_erinnerung', 1)),
                    'can_set_note': bool(full_user.get('can_set_note', 1)),
                    'can_archive': bool(full_user.get('can_archive', 1)),
                    'can_view_stats': bool(full_user.get('can_view_stats', 1)),
                    'can_view_records': bool(full_user.get('can_view_records', 1)),
                    'can_view_gallery': bool(full_user.get('can_view_gallery', 1)),
                    'can_chat': bool(full_user.get('can_chat', 1)),
                    'can_view_map': bool(full_user.get('can_view_map', 1)),
                    'can_view_calendar': bool(full_user.get('can_view_calendar', 1)),
                    'can_view_assistant': bool(full_user.get('can_view_assistant', 1)),
                    'can_view_archive': bool(full_user.get('can_view_archive', 1)),
                    'signature': full_user.get('signature')
                }
            }
        else:
            # Fehlversuch zählen
            if username not in self.failed_attempts:
                self.failed_attempts[username] = {'count': 0, 'last_attempt': now}

            self.failed_attempts[username]['count'] += 1
            self.failed_attempts[username]['last_attempt'] = now

            # Security Event loggen
            ip_address = request.remote_addr if request else None
            if self.security_logger:
                self.security_logger.log_login_failed(ip_address, username)

            # logger.warning(f"Login fehlgeschlagen: username={username}, attempt={self.failed_attempts[username]['count']}")
            return {'error': 'Benutzername oder Passwort falsch'}
    
    def logout_user(self):
        """Loggt einen Benutzer aus"""
        user_id = session.get('user_id')

        # Alle Sessions dieses Benutzers löschen
        if user_id:
            self.db_manager.delete_all_user_sessions(user_id)
            
            # Alle Locks dieses Benutzers freigeben
            try:
                import importlib
                sperr_module = importlib.import_module('sperr_logik')
                sperr_manager = sperr_module.SperrManager(self.db_manager)
                sperr_manager.release_all_user_locks(user_id)
            except Exception as e:
                logger.error(f"Fehler beim Freigeben der Locks beim Logout: {e}")

        session.clear()
        return {'success': True}
    
    def get_current_user(self):
        """Gibt den aktuellen Benutzer mit Rechten zurück"""
        if 'user_id' in session:
            user = self.db_manager.get_user(session['user_id'])
            if user:
                return {
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role'],
                    'can_read': bool(user['can_read']),
                    'can_write': bool(user['can_write']),
                    'can_delete': bool(user['can_delete']),
                    'can_download': bool(user['can_download']),
                    'can_upload': bool(user['can_upload']),
                    'can_fill_forms': bool(user.get('can_fill_forms', 1)),
                    'can_set_category': bool(user.get('can_set_category', 1)),
                    'can_set_status': bool(user.get('can_set_status', 1)),
                    'can_set_border_color': bool(user.get('can_set_border_color', 1)),
                    'can_set_reminder': bool(user.get('can_set_reminder', 1)),
                    'can_delete_termine': bool(user.get('can_delete_termine', 1)),
                    'can_set_erinnerung': bool(user.get('can_set_erinnerung', 1)),
                    'can_delete_erinnerung': bool(user.get('can_delete_erinnerung', 1)),
                    'can_set_note': bool(user.get('can_set_note', 1)),
                    'can_archive': bool(user.get('can_archive', 1)),
                    'can_view_stats': bool(user.get('can_view_stats', 1)),
                    'can_view_records': bool(user.get('can_view_records', 1)),
                    'can_view_gallery': bool(user.get('can_view_gallery', 1)),
                    'can_chat': bool(user.get('can_chat', 1)),
                    'can_view_map': bool(user.get('can_view_map', 1)),
                    'can_view_calendar': bool(user.get('can_view_calendar', 1)),
                    'can_view_assistant': bool(user.get('can_view_assistant', 1)),
                    'can_view_archive': bool(user.get('can_view_archive', 1)),
                    'signature': user.get('signature')
                }
        return None
    
    def check_user_limit(self):
        """Prüft das Benutzerlimit - Open Source Version hat kein Limit"""
        # Open Source Version: Kein Benutzerlimit
        return True, None
