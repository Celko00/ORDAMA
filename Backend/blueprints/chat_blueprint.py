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

Chat Blueprint - Team-Chat für ORDAMA
"""

import logging
import os
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, session, Response, send_file
import sqlite3
import json
import time

# security_utils importieren
sys.path.insert(0, str(Path(__file__).parent.parent))
from security_utils import FileUploadValidator

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'}


def init_chat_blueprint(auth_manager, db_manager, config):
    """Initialisiert den Chat Blueprint."""

    def require_auth(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Nicht authentifiziert', 'session_expired': True}), 401
            return f(*args, **kwargs)
        return decorated_function

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    @chat_bp.route('/rooms', methods=['GET'])
    @require_auth
    def get_rooms():
        """Listet alle Chat-Räume auf"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT r.*, u.username as created_by_name,
                           (SELECT COUNT(*) FROM chat_messages WHERE room_id = r.id) as message_count,
                           (SELECT MAX(created_at) FROM chat_messages WHERE room_id = r.id) as last_message_at
                    FROM chat_rooms r
                    LEFT JOIN users u ON r.created_by = u.id
                    ORDER BY last_message_at DESC, r.created_at DESC
                ''')
                rooms = cursor.fetchall()
                return jsonify({
                    'success': True,
                    'rooms': [dict(row) for row in rooms]
                })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der Chat-Räume: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/rooms', methods=['POST'])
    @require_auth
    def create_room():
        """Erstellt einen neuen Chat-Raum"""
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            description = data.get('description', '').strip()
            user_id = session['user_id']

            if not name:
                return jsonify({'error': 'Raumname ist erforderlich'}), 400

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO chat_rooms (name, description, created_by)
                    VALUES (?, ?, ?)
                ''', (name, description, user_id))
                conn.commit()
                room_id = cursor.lastrowid

                # Ersteller automatisch als Mitglied hinzufügen
                cursor.execute('''
                    INSERT INTO chat_room_members (room_id, user_id)
                    VALUES (?, ?)
                ''', (room_id, user_id))
                conn.commit()

            return jsonify({
                'success': True,
                'room_id': room_id,
                'message': 'Chat-Raum erstellt'
            })
        except Exception as exc:
            logger.error("Fehler beim Erstellen des Chat-Raums: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/rooms/<int:room_id>', methods=['DELETE'])
    @require_auth
    def delete_room(room_id):
        """Löscht einen Chat-Raum"""
        try:
            user_id = session['user_id']
            
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # Prüfen ob Benutzer der Ersteller ist oder Admin
                cursor.execute('SELECT created_by FROM chat_rooms WHERE id = ?', (room_id,))
                room = cursor.fetchone()
                
                if not room:
                    return jsonify({'error': 'Chat-Raum nicht gefunden'}), 404
                
                cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                
                if room['created_by'] != user_id and (not user or user['role'] != 'admin'):
                    return jsonify({'error': 'Keine Berechtigung'}), 403
                
                cursor.execute('DELETE FROM chat_rooms WHERE id = ?', (room_id,))
                conn.commit()

            return jsonify({
                'success': True,
                'message': 'Chat-Raum gelöscht'
            })
        except Exception as exc:
            logger.error("Fehler beim Löschen des Chat-Raums: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/rooms/<int:room_id>/messages', methods=['GET'])
    @require_auth
    def get_messages(room_id):
        """Ruft Nachrichten für einen Chat-Raum ab"""
        try:
            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT m.*, u.username, u.signature
                    FROM chat_messages m
                    LEFT JOIN users u ON m.user_id = u.id
                    WHERE m.room_id = ?
                    ORDER BY m.created_at ASC
                    LIMIT ? OFFSET ?
                ''', (room_id, limit, offset))
                messages = cursor.fetchall()

            return jsonify({
                'success': True,
                'messages': [dict(row) for row in messages]
            })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der Nachrichten: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/rooms/<int:room_id>/messages', methods=['POST'])
    @require_auth
    def send_message(room_id):
        """Sendet eine Nachricht in einen Chat-Raum"""
        try:
            user_id = session['user_id']

            # Datei-Upload zuerst prüfen
            if 'file' in request.files:
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': 'Keine Datei ausgewählt'}), 400

                # File-Upload Validierung mit FileUploadValidator
                sanitized_filename = FileUploadValidator.sanitize_filename(file.filename)
                if not FileUploadValidator.is_allowed_extension(sanitized_filename):
                    return jsonify({'error': f'Dateityp nicht erlaubt: {file.filename}'}), 400

                # Datei-Größe prüfen (max 10MB für Chat)
                max_size_mb = 10
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                is_valid, errors = FileUploadValidator.validate_upload(
                    sanitized_filename,
                    file.content_type,
                    file_size,
                    max_size_mb
                )

                if not is_valid:
                    return jsonify({'error': ', '.join(errors)}), 400

                # Speicherort für Chat-Dateien
                base_dir = Path(config['paths'].get('data_base_dir', './Speicher'))
                if not base_dir.is_absolute():
                    base_dir = Path(__file__).resolve().parents[2] / base_dir
                chat_dir = base_dir / "Chat"
                chat_dir.mkdir(parents=True, exist_ok=True)

                filename = secure_filename(sanitized_filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                unique_filename = f"{timestamp}_{filename}"
                file_path = chat_dir / unique_filename
                file.save(str(file_path))

                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
                    user = cursor.fetchone()
                    username = user['username'] if user else 'Unbekannt'

                    cursor.execute('''
                        INSERT INTO chat_messages (room_id, user_id, username, message, message_type, file_path, file_name, file_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (room_id, user_id, username, f'Datei: {filename}', 'file', str(file_path), filename, file_size))
                    conn.commit()
                    message_id = cursor.lastrowid

                return jsonify({
                    'success': True,
                    'message_id': message_id,
                    'message': 'Datei hochgeladen'
                })

            # Textnachricht
            elif request.is_json:
                data = request.get_json()
                message = data.get('message', '').strip()
                message_type = data.get('message_type', 'text')

                if not message:
                    return jsonify({'error': 'Nachricht ist erforderlich'}), 400

                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
                    user = cursor.fetchone()
                    username = user['username'] if user else 'Unbekannt'

                    cursor.execute('''
                        INSERT INTO chat_messages (room_id, user_id, username, message, message_type)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (room_id, user_id, username, message, message_type))
                    conn.commit()
                    message_id = cursor.lastrowid

                return jsonify({
                    'success': True,
                    'message_id': message_id,
                    'message': 'Nachricht gesendet'
                })
            else:
                return jsonify({'error': 'Keine Nachricht oder Datei'}), 400

        except Exception as exc:
            logger.error("Fehler beim Senden der Nachricht: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/messages/<int:message_id>', methods=['DELETE'])
    @require_auth
    def delete_message(message_id):
        """Löscht eine Nachricht"""
        try:
            user_id = session['user_id']
            
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM chat_messages WHERE id = ?', (message_id,))
                message = cursor.fetchone()
                
                if not message:
                    return jsonify({'error': 'Nachricht nicht gefunden'}), 404
                
                cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                
                if message['user_id'] != user_id and (not user or user['role'] != 'admin'):
                    return jsonify({'error': 'Keine Berechtigung'}), 403
                
                cursor.execute('DELETE FROM chat_messages WHERE id = ?', (message_id,))
                conn.commit()

            return jsonify({
                'success': True,
                'message': 'Nachricht gelöscht'
            })
        except Exception as exc:
            logger.error("Fehler beim Löschen der Nachricht: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/file/<int:message_id>', methods=['GET'])
    @require_auth
    def get_chat_file(message_id):
        """Ruft eine Datei aus einer Chat-Nachricht ab"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Prüfen ob die Nachricht existiert und ob der Benutzer Zugriff hat
                cursor.execute('''
                    SELECT file_path, file_name, room_id, user_id
                    FROM chat_messages
                    WHERE id = ?
                ''', (message_id,))
                message = cursor.fetchone()

                if not message:
                    return jsonify({'error': 'Nachricht nicht gefunden'}), 404

                # Sender hat immer Zugriff auf eigene Dateien
                if message['user_id'] == user_id:
                    pass  # Zugriff erlaubt
                elif message['room_id']:
                    # Prüfe ob Benutzer Mitglied im Raum ist
                    # Fallback: Wenn keine Mitglieder existieren, erlaube Zugriff für alle (für alte Nachrichten)
                    cursor.execute('''
                        SELECT COUNT(*) as count FROM chat_room_members WHERE room_id = ?
                    ''', (message['room_id'],))
                    member_count = cursor.fetchone()['count']

                    if member_count > 0:
                        # Wenn Mitglieder existieren, prüfe Mitgliedschaft
                        cursor.execute('''
                            SELECT 1 FROM chat_room_members
                            WHERE room_id = ? AND user_id = ?
                        ''', (message['room_id'], user_id))
                        if not cursor.fetchone():
                            return jsonify({'error': 'Keine Berechtigung'}), 403
                    # Wenn keine Mitglieder existieren, Zugriff erlauben (alte Nachrichten)
                else:
                    return jsonify({'error': 'Keine Berechtigung'}), 403

                file_path = Path(message['file_path'])
                if not file_path.exists():
                    return jsonify({'error': 'Datei nicht gefunden'}), 404

                return send_file(file_path, as_attachment=False, download_name=message['file_name'])

        except Exception as exc:
            logger.error("Fehler beim Abrufen der Datei: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/private-file/<int:message_id>', methods=['GET'])
    @require_auth
    def get_private_chat_file(message_id):
        """Ruft eine Datei aus einer privaten Chat-Nachricht ab"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Prüfen ob die Nachricht existiert und ob der Benutzer Zugriff hat
                cursor.execute('''
                    SELECT file_path, file_name, sender_id, receiver_id
                    FROM private_messages
                    WHERE id = ?
                ''', (message_id,))
                message = cursor.fetchone()

                if not message:
                    logger.error("Nachricht nicht gefunden: %s", message_id)
                    return jsonify({'error': 'Nachricht nicht gefunden'}), 404

                # Prüfen ob Benutzer Zugriff hat (entweder Sender oder Empfänger)
                if message['sender_id'] != user_id and message['receiver_id'] != user_id:
                    logger.error("Keine Berechtigung: user_id=%s, sender_id=%s, receiver_id=%s", user_id, message['sender_id'], message['receiver_id'])
                    return jsonify({'error': 'Keine Berechtigung'}), 403

                file_path = Path(message['file_path'])
                logger.info("Datei-Pfad: %s", file_path)
                logger.info("Datei existiert: %s", file_path.exists())

                if not file_path.exists():
                    # Datei nicht gefunden - Nachricht in DB markieren oder löschen
                    logger.warning("Datei nicht gefunden, markiere Nachricht als ohne Datei: %s", message_id)
                    cursor.execute('''
                        UPDATE private_messages
                        SET file_path = NULL, file_name = NULL, file_size = NULL
                        WHERE id = ?
                    ''', (message_id,))
                    conn.commit()
                    return jsonify({'error': 'Datei nicht gefunden'}), 404

                return send_file(file_path, as_attachment=False, download_name=message['file_name'])

        except Exception as exc:
            logger.error("Fehler beim Abrufen der privaten Datei: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/rooms/<int:room_id>/info', methods=['GET'])
    @require_auth
    def get_room_info(room_id):
        """Ruft Informationen über einen Chat-Raum ab"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT r.*, u.username as created_by_name
                    FROM chat_rooms r
                    LEFT JOIN users u ON r.created_by = u.id
                    WHERE r.id = ?
                ''', (room_id,))
                room = cursor.fetchone()
                
                if not room:
                    return jsonify({'error': 'Chat-Raum nicht gefunden'}), 404

            return jsonify({
                'success': True,
                'room': dict(room)
            })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der Raum-Informationen: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    # ── Private Messages (1-zu-1) ─────────────────────────

    @chat_bp.route('/unread-counts', methods=['GET'])
    @require_auth
    def get_unread_counts():
        """Gibt die Anzahl ungelesener Nachrichten für jeden Benutzer zurück"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT sender_id as other_user_id, sender_username as other_username, COUNT(*) as unread_count
                    FROM private_messages
                    WHERE receiver_id = ? AND read_at IS NULL
                    GROUP BY sender_id, sender_username
                ''', (user_id,))
                unread_counts = cursor.fetchall()

            return jsonify({
                'success': True,
                'unread_counts': [dict(row) for row in unread_counts]
            })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der ungelesenen Nachrichten: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/conversations', methods=['GET'])
    @require_auth
    def get_conversations():
        """Listet alle Konversationen des aktuellen Benutzers"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT
                        CASE
                            WHEN sender_id = ? THEN receiver_id
                            ELSE sender_id
                        END as other_user_id,
                        CASE
                            WHEN sender_id = ? THEN receiver_username
                            ELSE sender_username
                        END as other_username,
                        MAX(created_at) as last_message_at,
                        (SELECT COUNT(*) FROM private_messages pm2
                         WHERE pm2.receiver_id = ?
                         AND pm2.sender_id = CASE
                            WHEN pm1.sender_id = ? THEN pm1.receiver_id
                            ELSE pm1.sender_id
                        END AND pm2.read_at IS NULL) as unread_count
                    FROM private_messages pm1
                    WHERE sender_id = ? OR receiver_id = ?
                    GROUP BY other_user_id, other_username
                    ORDER BY last_message_at DESC
                ''', (user_id, user_id, user_id, user_id, user_id, user_id))
                conversations = cursor.fetchall()

            return jsonify({
                'success': True,
                'conversations': [dict(row) for row in conversations]
            })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der Konversationen: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/conversations/<int:other_user_id>/messages', methods=['GET'])
    @require_auth
    def get_private_messages(other_user_id):
        """Ruft private Nachrichten zwischen zwei Benutzern ab"""
        try:
            user_id = session['user_id']
            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT m.*,
                           CASE
                               WHEN m.sender_id = ? THEN 1
                               ELSE 0
                           END as is_own
                    FROM private_messages m
                    WHERE (m.sender_id = ? AND m.receiver_id = ?)
                       OR (m.sender_id = ? AND m.receiver_id = ?)
                    ORDER BY m.created_at ASC
                    LIMIT ? OFFSET ?
                ''', (user_id, user_id, other_user_id, other_user_id, user_id, limit, offset))
                messages = cursor.fetchall()

                # Prüfen ob Dateien existieren und Pfade bereinigen
                for msg in messages:
                    if msg['file_path']:
                        file_path = Path(msg['file_path'])
                        if not file_path.exists():
                            # Datei nicht gefunden - Pfad in DB bereinigen
                            logger.warning("Datei nicht gefunden beim Laden, bereinige Nachricht: %s", msg['id'])
                            cursor.execute('''
                                UPDATE private_messages
                                SET file_path = NULL, file_name = NULL, file_size = NULL
                                WHERE id = ?
                            ''', (msg['id'],))
                            msg['file_path'] = None
                            msg['file_name'] = None
                            msg['file_size'] = None
                conn.commit()

            # Mark messages as read
            cursor.execute('''
                UPDATE private_messages
                SET read_at = CURRENT_TIMESTAMP
                WHERE receiver_id = ? AND sender_id = ? AND read_at IS NULL
            ''', (user_id, other_user_id))
            conn.commit()

            return jsonify({
                'success': True,
                'messages': [dict(row) for row in messages]
            })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der privaten Nachrichten: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/conversations/<int:other_user_id>/messages', methods=['POST'])
    @require_auth
    def send_private_message(other_user_id):
        """Sendet eine private Nachricht an einen anderen Benutzer"""
        try:
            user_id = session['user_id']

            # Get usernames
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
                sender = cursor.fetchone()
                cursor.execute('SELECT username FROM users WHERE id = ?', (other_user_id,))
                receiver = cursor.fetchone()

                if not sender or not receiver:
                    return jsonify({'error': 'Benutzer nicht gefunden'}), 404

                sender_username = sender['username']
                receiver_username = receiver['username']

            # Datei-Upload zuerst prüfen
            if 'file' in request.files:
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': 'Keine Datei ausgewählt'}), 400

                if not allowed_file(file.filename):
                    return jsonify({'error': 'Dateityp nicht erlaubt'}), 400

                # Speicherort für Chat-Dateien
                base_dir = Path(config['paths'].get('data_base_dir', './Speicher'))
                if not base_dir.is_absolute():
                    base_dir = Path(__file__).resolve().parents[2] / base_dir
                chat_dir = base_dir / "Chat"
                chat_dir.mkdir(parents=True, exist_ok=True)

                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                unique_filename = f"{timestamp}_{filename}"
                file_path = chat_dir / unique_filename
                file.save(str(file_path))

                file_size = os.path.getsize(file_path)

                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO private_messages (sender_id, receiver_id, sender_username, receiver_username, message, message_type, file_path, file_name, file_size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (user_id, other_user_id, sender_username, receiver_username, f'Datei: {filename}', 'file', str(file_path), filename, file_size))
                    conn.commit()
                    message_id = cursor.lastrowid

                return jsonify({
                    'success': True,
                    'message_id': message_id,
                    'message': 'Datei hochgeladen'
                })

            # Textnachricht
            elif request.is_json:
                data = request.get_json()
                message = data.get('message', '').strip()
                message_type = data.get('message_type', 'text')

                if not message:
                    return jsonify({'error': 'Nachricht ist erforderlich'}), 400

                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO private_messages (sender_id, receiver_id, sender_username, receiver_username, message, message_type)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, other_user_id, sender_username, receiver_username, message, message_type))
                    conn.commit()
                    message_id = cursor.lastrowid

                return jsonify({
                    'success': True,
                    'message_id': message_id,
                    'message': 'Nachricht gesendet'
                })
            else:
                return jsonify({'error': 'Keine Nachricht oder Datei'}), 400
                
        except Exception as exc:
            logger.error("Fehler beim Senden der privaten Nachricht: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/conversations/<int:other_user_id>/mark-read', methods=['POST'])
    @require_auth
    def mark_conversation_read(other_user_id):
        """Markiert alle Nachrichten einer Konversation als gelesen"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE private_messages
                    SET read_at = CURRENT_TIMESTAMP
                    WHERE receiver_id = ? AND sender_id = ? AND read_at IS NULL
                ''', (user_id, other_user_id))
                conn.commit()

            return jsonify({
                'success': True,
                'message': 'Konversation als gelesen markiert'
            })
        except Exception as exc:
            logger.error("Fehler beim Markieren als gelesen: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/conversations/<int:other_user_id>/messages/<int:message_id>', methods=['DELETE'])
    @require_auth
    def delete_private_message(other_user_id, message_id):
        """Löscht eine private Nachricht"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Prüfen ob die Nachricht existiert und ob der Benutzer Zugriff hat
                cursor.execute('''
                    SELECT sender_id, receiver_id
                    FROM private_messages
                    WHERE id = ?
                ''', (message_id,))
                message = cursor.fetchone()

                if not message:
                    return jsonify({'error': 'Nachricht nicht gefunden'}), 404

                # Prüfen ob Benutzer Zugriff hat (entweder Sender oder Empfänger)
                if message['sender_id'] != user_id and message['receiver_id'] != user_id:
                    return jsonify({'error': 'Keine Berechtigung'}), 403

                cursor.execute('DELETE FROM private_messages WHERE id = ?', (message_id,))
                conn.commit()

            return jsonify({
                'success': True,
                'message': 'Nachricht gelöscht'
            })
        except Exception as exc:
            logger.error("Fehler beim Löschen der privaten Nachricht: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @chat_bp.route('/conversations/<int:other_user_id>/clear', methods=['DELETE'])
    @require_auth
    def clear_private_conversation(other_user_id):
        """Löscht den kompletten Chatverlauf mit einem Benutzer"""
        try:
            user_id = session['user_id']

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM private_messages
                    WHERE (sender_id = ? AND receiver_id = ?)
                    OR (sender_id = ? AND receiver_id = ?)
                ''', (user_id, other_user_id, other_user_id, user_id))
                conn.commit()

            return jsonify({
                'success': True,
                'message': 'Chatverlauf gelöscht'
            })
        except Exception as exc:
            logger.error("Fehler beim Löschen des Chatverlaufs: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    # ── Server-Sent Events (SSE) for Real-time Updates ─────────────────────────

    @chat_bp.route('/stream')
    @require_auth
    def stream_updates():
        """SSE-Endpoint für Echtzeit-Updates"""
        user_id = session['user_id']
        
        def event_stream():
            last_check = time.time()
            while True:
                try:
                    current_time = time.time()
                    
                    # Check for new messages every 2 seconds
                    if current_time - last_check >= 2:
                        with db_manager.get_connection() as conn:
                            cursor = conn.cursor()
                            
                            # Check for new room messages
                            cursor.execute('''
                                SELECT room_id, COUNT(*) as count, MAX(created_at) as last_at
                                FROM chat_messages
                                WHERE created_at > ?
                                GROUP BY room_id
                            ''', (datetime.fromtimestamp(last_check),))
                            room_updates = cursor.fetchall()
                            
                            # Check for new private messages
                            cursor.execute('''
                                SELECT sender_id, COUNT(*) as count, MAX(created_at) as last_at
                                FROM private_messages
                                WHERE receiver_id = ? AND created_at > ?
                                GROUP BY sender_id
                            ''', (user_id, datetime.fromtimestamp(last_check)))
                            private_updates = cursor.fetchall()
                        
                        last_check = current_time
                        
                        # Send updates if any
                        if room_updates or private_updates:
                            data = {
                                'rooms': [dict(row) for row in room_updates],
                                'private': [dict(row) for row in private_updates]
                            }
                            yield f"data: {json.dumps(data)}\n\n"
                    
                    # Keep connection alive
                    yield ": keep-alive\n\n"
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error("SSE stream error: %s", e)
                    break
        
        return Response(
            event_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )

    return chat_bp
