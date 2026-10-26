"""
Assistent Blueprint - lokale Befehlserkennung für Akten
"""

import logging
import re
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from assistant_learning import AssistantLearningStore, _clean_text
from command_parser import CommandParser

logger = logging.getLogger(__name__)

assistant_bp = Blueprint('assistant', __name__, url_prefix='/api/assistant')

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEARNING_FILE = PROJECT_ROOT / 'Konfiguration' / 'assistant_learning.json'


def init_assistant_blueprint(auth_manager, db_manager, akten_manager):
    """Initialisiert den Assistenten Blueprint."""

    learning_store = AssistantLearningStore(LEARNING_FILE)
    parser = CommandParser(learning_store)

    def require_auth(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Nicht authentifiziert', 'session_expired': True}), 401

            user_id = session.get('user_id')

            # Session-Prüfung komplett deaktiviert - nur Flask Session Cookie prüfen
            # Admin-Logout funktioniert über separaten Endpunkt

            return f(*args, **kwargs)
        return decorated_function

    def _resolve_category_id(category_name):
        if not category_name:
            return None
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM categories WHERE name LIKE ? ORDER BY name LIMIT 1', (f'%{category_name}%',))
                row = cursor.fetchone()
                return row['id'] if row else None
        except Exception as exc:
            logger.warning("Kategorie konnte nicht aufgelöst werden: %s", exc)
            return None

    def _find_record(identifier):
        if not identifier:
            return None

        normalized_identifier = _clean_text(identifier)
        if not normalized_identifier:
            return None

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT r.*, c.name AS category_name
                FROM records r
                LEFT JOIN categories c ON r.category_id = c.id
                WHERE r.archived = 0
                  AND (
                    r.number = ?
                    OR lower(r.title) = lower(?)
                    OR r.number LIKE ?
                    OR lower(r.title) LIKE lower(?)
                    OR lower(r.content) LIKE lower(?)
                  )
                ORDER BY
                    CASE
                        WHEN r.number = ? THEN 1
                        WHEN lower(r.title) = lower(?) THEN 2
                        WHEN r.number LIKE ? THEN 3
                        WHEN lower(r.title) LIKE lower(?) THEN 4
                        ELSE 5
                    END,
                    r.updated_at DESC
                LIMIT 1
                ''',
                (
                    normalized_identifier,
                    normalized_identifier,
                    f'%{normalized_identifier}%',
                    f'%{normalized_identifier}%',
                    f'%{normalized_identifier.lower()}%',
                    normalized_identifier,
                    normalized_identifier,
                    f'%{normalized_identifier}%',
                    f'%{normalized_identifier}%'
                )
            )
            return cursor.fetchone()

    def _get_record_by_id(record_id):
        if not record_id:
            return None

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT r.*, c.name AS category_name
                FROM records r
                LEFT JOIN categories c ON r.category_id = c.id
                WHERE r.archived = 0 AND r.id = ?
                LIMIT 1
                ''',
                (record_id,)
            )
            return cursor.fetchone()

    def _format_date_for_message(iso_date):
        if not iso_date:
            return None
        try:
            return datetime.fromisoformat(iso_date).strftime('%d.%m.%Y')
        except Exception:
            return iso_date

    def _summarize_record_text(record):
        parts = [f'Akte "{record["title"]}"']
        if record['number']:
            parts.append(f'Nummer {record["number"]}')
        if record['status']:
            parts.append(f'Status {record["status"]}')
        if record['category_name']:
            parts.append(f'Kategorie {record["category_name"]}')
        if record['reminder_date']:
            parts.append(f'Termin {_format_date_for_message(record["reminder_date"])}')
        if record['address']:
            parts.append(f'Adresse {record["address"]}')

        content = (record['content'] or '').strip()
        if content:
            compact = re.sub(r'\s+', ' ', content)
            if len(compact) > 260:
                compact = compact[:257].rstrip() + '...'
            parts.append(f'Inhalt: {compact}')

        return '\n'.join(parts)

    def _build_record_preview(record, snippet=None, badge=None):
        if not record:
            return None

        preview_snippet = _clean_text(snippet)
        if not preview_snippet:
            preview_snippet = _clean_text(record.get('content') if hasattr(record, 'get') else record['content'])
        if preview_snippet and len(preview_snippet) > 180:
            preview_snippet = preview_snippet[:177].rstrip() + '...'

        reminder_date = None
        if hasattr(record, 'get'):
            reminder_date = record.get('reminder_date')
            category_name = record.get('category_name')
            status = record.get('status')
            title = record.get('title')
            number = record.get('number')
            record_id = record.get('id')
        else:
            reminder_date = record['reminder_date']
            category_name = record['category_name']
            status = record['status']
            title = record['title']
            number = record['number']
            record_id = record['id']

        return {
            'id': record_id,
            'number': number,
            'title': title,
            'snippet': preview_snippet,
            'status': status,
            'category': category_name,
            'reminder_date_label': _format_date_for_message(reminder_date),
            'action_badge': badge
        }

    @assistant_bp.route('/parse', methods=['POST'])
    @require_auth
    def parse_command():
        try:
            data = request.get_json()
            if not data or 'command' not in data:
                return jsonify({'error': 'Kein Befehl angegeben'}), 400

            parsed = parser.parse(data['command'])
            return jsonify({'success': True, 'parsed': parsed})
        except Exception as exc:
            logger.error("Fehler beim Parsen: %s", exc, exc_info=True)
            return jsonify({'error': str(exc)}), 500

    @assistant_bp.route('/feedback', methods=['POST'])
    @require_auth
    def assistant_feedback():
        try:
            data = request.get_json() or {}
            command_text = data.get('command', '')
            expected_command = data.get('expected_command')
            corrected_data = data.get('corrected_data') or {}
            is_correct = data.get('is_correct', True)

            if not command_text:
                return jsonify({'success': False, 'message': 'Kein Befehl für das Lernen angegeben'}), 400

            learning_store.record_feedback(command_text, expected_command, corrected_data, is_correct)
            return jsonify({
                'success': True,
                'message': 'Die Rückmeldung wurde gespeichert. Der Assistent kann ähnliche Formulierungen künftig besser erkennen.'
            })
        except Exception as exc:
            logger.error("Fehler beim Speichern des Feedbacks: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Speichern des Feedbacks: {exc}'}), 500

    @assistant_bp.route('/learning-data', methods=['GET'])
    @require_auth
    def get_learning_data():
        try:
            data = learning_store.data
            return jsonify({
                'success': True,
                'data': {
                    'blacklist': data.get('blacklist', []),
                    'feedback_examples': data.get('feedback_examples', []),
                    'positive_examples': data.get('positive_examples', []),
                    'action_aliases': data.get('action_aliases', {}),
                    'field_aliases': data.get('field_aliases', {}),
                    'field_synonyms': data.get('field_synonyms', {}),
                    'date_formats': data.get('date_formats', [])
                }
            })
        except Exception as exc:
            logger.error("Fehler beim Abrufen der Lern-Daten: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Abrufen der Lern-Daten: {exc}'}), 500

    @assistant_bp.route('/learning-data', methods=['POST'])
    @require_auth
    def add_learning_data():
        try:
            data = request.get_json() or {}
            entry_type = data.get('type')  # 'field_synonyms' or 'date_formats'
            field_name = data.get('field_name')  # For field_synonyms
            synonym = data.get('synonym')  # For field_synonyms
            date_format = data.get('date_format')  # For date_formats

            if entry_type == 'field_synonyms':
                if field_name and synonym:
                    learning_store.add_field_synonym(field_name, synonym)
                    return jsonify({'success': True, 'message': 'Synonym wurde hinzugefügt'})
                else:
                    return jsonify({'success': False, 'message': 'Feldname und Synonym erforderlich'}), 400
            else:
                return jsonify({'success': False, 'message': 'Ungültiger Typ angegeben'}), 400
        except Exception as exc:
            logger.error("Fehler beim Hinzufügen der Lern-Daten: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Hinzufügen der Lern-Daten: {exc}'}), 500

    @assistant_bp.route('/learning-data', methods=['DELETE'])
    @require_auth
    def clear_learning_data():
        try:
            data = request.get_json() or {}
            entry_type = data.get('type')  # 'blacklist', 'feedback_examples', 'positive_examples', 'action_aliases', 'field_aliases', 'field_synonyms', 'date_formats', or 'all'
            entry_index = data.get('index')  # Optional: specific index to delete
            field_name = data.get('field_name')  # For field_synonyms
            synonym = data.get('synonym')  # For field_synonyms
            date_format = data.get('date_format')  # For date_formats

            if entry_type == 'all':
                learning_store.data = {
                    'blacklist': [],
                    'feedback_examples': [],
                    'positive_examples': [],
                    'action_aliases': {},
                    'field_aliases': {},
                    'field_synonyms': learning_store._get_default_field_synonyms(),
                    'date_formats': learning_store._get_default_date_formats()
                }
                learning_store.save()
            elif entry_type == 'blacklist':
                if entry_index is not None:
                    # Delete specific blacklist entry
                    blacklist = list(learning_store.data.get('blacklist', []))
                    if 0 <= entry_index < len(blacklist):
                        blacklist.pop(entry_index)
                        learning_store.data['blacklist'] = blacklist
                else:
                    # Clear all blacklist entries
                    learning_store.data['blacklist'] = []
            elif entry_type in ['feedback_examples', 'positive_examples']:
                if entry_index is not None:
                    # Delete specific entry
                    entries = list(learning_store.data.get(entry_type, []))
                    if 0 <= entry_index < len(entries):
                        entries.pop(entry_index)
                        learning_store.data[entry_type] = entries
                else:
                    # Clear all entries of this type
                    learning_store.data[entry_type] = []
            elif entry_type in ['action_aliases', 'field_aliases']:
                if entry_index is not None:
                    # Delete specific alias
                    aliases = learning_store.data.get(entry_type, {})
                    command_type = data.get('command_type')
                    if command_type and command_type in aliases:
                        if 0 <= entry_index < len(aliases[command_type]):
                            aliases[command_type].pop(entry_index)
                            learning_store.data[entry_type] = aliases
                else:
                    # Clear all aliases of this type
                    learning_store.data[entry_type] = {}
            elif entry_type == 'field_synonyms':
                if field_name and synonym:
                    learning_store.remove_field_synonym(field_name, synonym)
                elif field_name:
                    # Clear all synonyms for this field
                    field_synonyms = learning_store.data.get('field_synonyms', {})
                    if field_name in field_synonyms:
                        field_synonyms[field_name] = []
                        learning_store.data['field_synonyms'] = field_synonyms
                        learning_store.save()
                else:
                    # Reset to defaults
                    learning_store.data['field_synonyms'] = learning_store._get_default_field_synonyms()
                    learning_store.save()
            else:
                return jsonify({'success': False, 'message': 'Ungültiger Typ angegeben'}), 400

            learning_store.save()
            return jsonify({'success': True, 'message': 'Lern-Daten wurden aktualisiert'})
        except Exception as exc:
            logger.error("Fehler beim Löschen der Lern-Daten: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Löschen der Lern-Daten: {exc}'}), 500

    @assistant_bp.route('/execute', methods=['POST'])
    @require_auth
    def execute_command():
        try:
            data = request.get_json()
            if not data or 'command' not in data:
                return jsonify({'success': False, 'message': 'Kein Befehl angegeben'}), 400

            command_text = data['command']
            user_id = session['user_id']

            logger.info("Assistent-Befehl: %s", command_text)

            parsed = parser.parse(command_text)
            logger.info("Geparster Befehl: %s", parsed)

            if parsed['command'] == 'blacklisted':
                return jsonify({
                    'success': False,
                    'message': parsed.get('message', 'Dieser Befehl wurde als falsch markiert. Bitte formuliere ihn anders.'),
                    'action': 'blacklisted'
                })

            if parsed['command'] == 'create_record':
                return _execute_create_record(parsed['data'], user_id)
            if parsed['command'] == 'update_record':
                return _execute_update_record(parsed['data'], user_id)
            if parsed['command'] == 'summarize_record':
                return _execute_summarize_record(parsed['data'])
            if parsed['command'] == 'search':
                return _execute_search(parsed['data'])
            if parsed['command'] == 'delete_record':
                return _execute_delete_record(parsed['data'], user_id)
            if parsed['command'] == 'archive_record':
                return _execute_archive_record(parsed['data'], user_id)
            if parsed['command'] == 'set_status':
                return _execute_set_status(parsed['data'], user_id)
            if parsed['command'] == 'set_color':
                return _execute_set_color(parsed['data'], user_id)
            if parsed['command'] == 'set_reminder':
                return _execute_set_reminder(parsed['data'], user_id)
            if parsed['command'] == 'list_records':
                return _execute_list_records()
            if parsed['command'] == 'add_note':
                return _execute_add_note(parsed['data'], user_id)
            if parsed['command'] == 'set_category':
                return _execute_set_category(parsed['data'], user_id)
            if parsed['command'] == 'help':
                return _execute_help()

            return jsonify({
                'success': False,
                'message': 'Befehl nicht erkannt'
            })
        except Exception as exc:
            logger.error("Fehler beim Ausführen des Assistenten-Befehls: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler: {str(exc)}'}), 500

    def _execute_create_record(data, user_id):
        try:
            title = _clean_text(data.get('title'))
            content = _clean_text(data.get('content'))
            address = _clean_text(data.get('address'))
            status = _clean_text(data.get('status'))
            category = _clean_text(data.get('category'))
            border_color = _clean_text(data.get('border_color'))
            city = _clean_text(data.get('city'))
            reminder_date = data.get('reminder_date')

            if not title:
                return jsonify({'success': False, 'message': 'Kein Titel für die Akte erkannt. Beispiele: "erstelle eine Akte mit dem Titel Markus Müller" oder "lege Akte Markus Müller an".'})

            category_id = _resolve_category_id(category)

            if city and address:
                address = f'{address}, {city}'
            elif city and not address:
                address = city

            result = akten_manager.create_akte(
                title=title,
                content=content or '',
                hashtags='',
                user_id=user_id,
                address=address,
                status=status or 'offen',
                category_id=category_id,
                border_color=border_color,
                reminder_date=reminder_date
            )

            record = _get_record_by_id(result['id'])

            message = f'Akte "{title}" wurde erstellt.'
            
            # Record success for learning
            learning_store.record_success(data.get('_original_command', ''), 'create_record', data)

            return jsonify({
                'success': True,
                'message': message,
                'record_id': result['id'],
                'record_number': result['number'],
                'action': 'record_created',
                'records': [_build_record_preview(record or result, badge='Erstellt')]
            })
        except Exception as exc:
            logger.error("Fehler beim Erstellen der Akte: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Erstellen der Akte: {str(exc)}'}), 500

    def _execute_update_record(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            updates = data.get('updates') or {}
            content_mode = data.get('content_mode', 'replace')

            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte zum Bearbeiten erkannt. Beispiel: "bearbeite Akte Markus Müller und setze den Termin auf 20.08.2026".'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            current = dict(record)
            title = _clean_text(updates.get('title')) or current.get('title')
            content_update = _clean_text(updates.get('content'))
            if content_update and content_mode == 'append' and current.get('content'):
                content = f'{current["content"].rstrip()}\n{content_update}'
            else:
                content = content_update if content_update is not None else current.get('content', '')

            address = _clean_text(updates.get('address')) or current.get('address')
            status = _clean_text(updates.get('status')) or current.get('status')
            category = _clean_text(updates.get('category'))
            border_color = _clean_text(updates.get('border_color')) or current.get('border_color')
            city = _clean_text(updates.get('city'))
            reminder_date = updates.get('reminder_date') or current.get('reminder_date')

            if city and address:
                address = f'{address}, {city}'
            elif city and not address:
                address = city

            category_id = current.get('category_id')
            if category:
                resolved_category_id = _resolve_category_id(category)
                if resolved_category_id is not None:
                    category_id = resolved_category_id

            akten_manager.update_akte(
                record_id=current['id'],
                title=title,
                content=content or '',
                hashtags=current.get('hashtags', ''),
                user_id=user_id,
                border_color=border_color,
                reminder_date=reminder_date,
                reminder_end_date=current.get('reminder_end_date'),
                reminder_repeat=current.get('reminder_repeat'),
                status=status,
                category_id=category_id,
                address=address,
                reminder_assigned_to=current.get('reminder_assigned_to')
            )

            updated_record = _get_record_by_id(current['id']) or current

            changes = []
            if updates.get('title'):
                changes.append('Titel')
            if updates.get('content'):
                changes.append('Inhalt')
            if updates.get('address') or updates.get('city'):
                changes.append('Adresse')
            if updates.get('status'):
                changes.append('Status')
            if updates.get('category'):
                changes.append('Kategorie')
            if updates.get('border_color'):
                changes.append('Farbe')
            if updates.get('reminder_date'):
                changes.append('Termin')

            change_text = ', '.join(changes) if changes else 'Daten'
            
            # Record success for learning
            learning_store.record_success(data.get('_original_command', ''), 'update_record', data)

            return jsonify({
                'success': True,
                'message': f'Akte "{title}" wurde aktualisiert. Geändert: {change_text}.',
                'record_id': current['id'],
                'record_number': current['number'],
                'action': 'record_updated',
                'records': [_build_record_preview(updated_record, badge='Aktualisiert')]
            })
        except Exception as exc:
            logger.error("Fehler beim Bearbeiten der Akte: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Bearbeiten der Akte: {str(exc)}'}), 500

    def _execute_summarize_record(data):
        try:
            identifier = _clean_text(data.get('identifier'))
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte für die Zusammenfassung erkannt.'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            summary = _summarize_record_text(record)
            return jsonify({
                'success': True,
                'message': summary,
                'record_id': record['id'],
                'record_number': record['number'],
                'action': 'record_summary',
                'records': [_build_record_preview(record, snippet=summary, badge='Zusammenfassung')]
            })
        except Exception as exc:
            logger.error("Fehler beim Zusammenfassen der Akte: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Zusammenfassen der Akte: {str(exc)}'}), 500

    def _execute_search(data):
        try:
            query = _clean_text(data.get('query'))
            if not query:
                return jsonify({'success': False, 'message': 'Keine Suchanfrage angegeben.'})

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT r.id, r.number, r.title, r.content, r.status, r.reminder_date, c.name AS category_name
                    FROM records r
                    LEFT JOIN categories c ON c.id = r.category_id
                    WHERE archived = 0
                      AND (r.title LIKE ? OR r.content LIKE ? OR r.number LIKE ?)
                    ORDER BY r.updated_at DESC
                    LIMIT 10
                    ''',
                    (f'%{query}%', f'%{query}%', f'%{query}%')
                )
                records = cursor.fetchall()

            results = []
            for row in records:
                snippet = _clean_text(row['content'] or '')
                if snippet and len(snippet) > 120:
                    snippet = snippet[:117].rstrip() + '...'
                results.append({
                    'id': row['id'],
                    'number': row['number'],
                    'title': row['title'],
                    'snippet': snippet,
                    'status': row['status'],
                    'category': row['category_name'],
                    'reminder_date_label': _format_date_for_message(row['reminder_date'])
                })

            # Record success for learning
            learning_store.record_success(data.get('_original_command', ''), 'search', data)
            
            return jsonify({
                'success': True,
                'message': f'{len(results)} Akten gefunden für "{query}".',
                'results': results,
                'records': results,
                'action': 'search_results'
            })
        except Exception as exc:
            logger.error("Fehler bei der Suche: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler bei der Suche: {str(exc)}'}), 500

    def _execute_delete_record(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte zum Löschen erkannt. Beispiel: "lösche Akte Markus Müller".'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            aktenzeichen = akten_manager.delete_akte(record['id'], user_id)
            
            return jsonify({
                'success': True,
                'message': f'Akte "{record["title"]}" ({aktenzeichen}) wurde gelöscht.',
                'action': 'record_deleted'
            })
        except Exception as exc:
            logger.error("Fehler beim Löschen der Akte: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Löschen der Akte: {str(exc)}'}), 500

    def _execute_archive_record(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte zum Archivieren erkannt. Beispiel: "archiviere Akte Markus Müller".'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE records SET archived = 1 WHERE id = ?', (record['id'],))
                conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Akte "{record["title"]}" wurde archiviert.',
                'action': 'record_archived'
            })
        except Exception as exc:
            logger.error("Fehler beim Archivieren der Akte: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Archivieren der Akte: {str(exc)}'}), 500

    def _execute_set_status(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            status = _clean_text(data.get('status'))
            
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte für den Status-Wechsel erkannt. Beispiel: "setze Status von Akte Müller auf erledigt".'})
            
            if not status:
                return jsonify({'success': False, 'message': 'Kein Status erkannt. Verfügbare Status: offen, erledigt, bearbeitung, neutral'})
            
            valid_statuses = ['offen', 'erledigt', 'bearbeitung', 'neutral']
            if status not in valid_statuses:
                return jsonify({'success': False, 'message': f'Ungültiger Status. Verfügbare: {", ".join(valid_statuses)}'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            akten_manager.update_akte(
                record_id=record['id'],
                title=record['title'],
                content=record.get('content', ''),
                hashtags=record.get('hashtags', ''),
                user_id=user_id,
                border_color=record.get('border_color'),
                reminder_date=record.get('reminder_date'),
                reminder_end_date=record.get('reminder_end_date'),
                reminder_repeat=record.get('reminder_repeat'),
                status=status,
                category_id=record.get('category_id'),
                address=record.get('address'),
                reminder_assigned_to=record.get('reminder_assigned_to')
            )
            
            
            return jsonify({
                'success': True,
                'message': f'Status von Akte "{record["title"]}" wurde auf "{status}" geändert.',
                'action': 'status_updated',
                'records': [_build_record_preview(_get_record_by_id(record['id']), badge='Status geändert')]
            })
        except Exception as exc:
            logger.error("Fehler beim Ändern des Status: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Ändern des Status: {str(exc)}'}), 500

    def _execute_set_color(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            color = _clean_text(data.get('color'))
            
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte für den Farb-Wechsel erkannt. Beispiel: "färbe Akte Müller rot".'})
            
            if not color:
                return jsonify({'success': False, 'message': 'Keine Farbe erkannt. Verfügbare Farben: rot, blau, gelb, grün, magenta'})
            
            valid_colors = ['', 'border-red', 'border-blue', 'border-yellow', 'border-green', 'border-magenta']
            if color not in valid_colors:
                return jsonify({'success': False, 'message': f'Ungültige Farbe. Verfügbare: rot, blau, gelb, grün, magenta'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            akten_manager.update_akte(
                record_id=record['id'],
                title=record['title'],
                content=record.get('content', ''),
                hashtags=record.get('hashtags', ''),
                user_id=user_id,
                border_color=color,
                reminder_date=record.get('reminder_date'),
                reminder_end_date=record.get('reminder_end_date'),
                reminder_repeat=record.get('reminder_repeat'),
                status=record.get('status'),
                category_id=record.get('category_id'),
                address=record.get('address'),
                reminder_assigned_to=record.get('reminder_assigned_to')
            )
            
            
            return jsonify({
                'success': True,
                'message': f'Rahmenfarbe von Akte "{record["title"]}" wurde geändert.',
                'action': 'color_updated',
                'records': [_build_record_preview(_get_record_by_id(record['id']), badge='Farbe geändert')]
            })
        except Exception as exc:
            logger.error("Fehler beim Ändern der Farbe: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Ändern der Farbe: {str(exc)}'}), 500

    def _execute_set_reminder(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            reminder_date = data.get('reminder_date')
            
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte für den Termin erkannt. Beispiel: "setze Termin für Akte Müller auf 20.08.2026".'})
            
            if not reminder_date:
                return jsonify({'success': False, 'message': 'Kein Datum erkannt. Beispiel: "am 20.08.2026" oder "20.08.2026"'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            akten_manager.update_akte(
                record_id=record['id'],
                title=record['title'],
                content=record.get('content', ''),
                hashtags=record.get('hashtags', ''),
                user_id=user_id,
                border_color=record.get('border_color'),
                reminder_date=reminder_date,
                reminder_end_date=record.get('reminder_end_date'),
                reminder_repeat=record.get('reminder_repeat'),
                status=record.get('status'),
                category_id=record.get('category_id'),
                address=record.get('address'),
                reminder_assigned_to=record.get('reminder_assigned_to')
            )
            
            formatted_date = _format_date_for_message(reminder_date)
            return jsonify({
                'success': True,
                'message': f'Termin für Akte "{record["title"]}" wurde auf {formatted_date} gesetzt.',
                'action': 'reminder_updated',
                'records': [_build_record_preview(_get_record_by_id(record['id']), badge='Termin gesetzt')]
            })
        except Exception as exc:
            logger.error("Fehler beim Setzen des Termins: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Setzen des Termins: {str(exc)}'}), 500

    def _execute_list_records():
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT r.id, r.number, r.title, r.content, r.status, r.reminder_date, c.name AS category_name
                    FROM records r
                    LEFT JOIN categories c ON c.id = r.category_id
                    WHERE archived = 0
                    ORDER BY r.updated_at DESC
                    LIMIT 20
                    '''
                )
                records = cursor.fetchall()

            results = []
            for row in records:
                snippet = _clean_text(row['content'] or '')
                if snippet and len(snippet) > 100:
                    snippet = snippet[:97].rstrip() + '...'
                results.append({
                    'id': row['id'],
                    'number': row['number'],
                    'title': row['title'],
                    'snippet': snippet,
                    'status': row['status'],
                    'category': row['category_name'],
                    'reminder_date_label': _format_date_for_message(row['reminder_date'])
                })

            return jsonify({
                'success': True,
                'message': f'{len(results)} Akten gefunden.',
                'results': results,
                'records': results,
                'action': 'list_records'
            })
        except Exception as exc:
            logger.error("Fehler beim Auflisten der Akten: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Auflisten der Akten: {str(exc)}'}), 500

    def _execute_add_note(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            note = _clean_text(data.get('note'))
            
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte für die Notiz erkannt. Beispiel: "notiere bei Akte Müller: Rückruf morgen".'})
            
            if not note:
                return jsonify({'success': False, 'message': 'Keine Notiz erkannt.'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            current_content = record.get('content', '') or ''
            new_content = f'{current_content}\n{note}' if current_content else note

            akten_manager.update_akte(
                record_id=record['id'],
                title=record['title'],
                content=new_content,
                hashtags=record.get('hashtags', ''),
                user_id=user_id,
                border_color=record.get('border_color'),
                reminder_date=record.get('reminder_date'),
                reminder_end_date=record.get('reminder_end_date'),
                reminder_repeat=record.get('reminder_repeat'),
                status=record.get('status'),
                category_id=record.get('category_id'),
                address=record.get('address'),
                reminder_assigned_to=record.get('reminder_assigned_to')
            )
            
            
            return jsonify({
                'success': True,
                'message': f'Notiz wurde zu Akte "{record["title"]}" hinzugefügt.',
                'action': 'note_added',
                'records': [_build_record_preview(_get_record_by_id(record['id']), badge='Notiz hinzugefügt')]
            })
        except Exception as exc:
            logger.error("Fehler beim Hinzufügen der Notiz: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Hinzufügen der Notiz: {str(exc)}'}), 500

    def _execute_set_category(data, user_id):
        try:
            identifier = _clean_text(data.get('identifier'))
            category = _clean_text(data.get('category'))
            
            if not identifier:
                return jsonify({'success': False, 'message': 'Es wurde keine Akte für die Kategorie erkannt. Beispiel: "ordne Akte Müller in Kategorie Kunden ein".'})
            
            if not category:
                return jsonify({'success': False, 'message': 'Keine Kategorie erkannt.'})

            record = _find_record(identifier)
            if not record:
                return jsonify({'success': False, 'message': f'Keine passende Akte für "{identifier}" gefunden.'})

            category_id = _resolve_category_id(category)
            if category_id is None:
                return jsonify({'success': False, 'message': f'Kategorie "{category}" nicht gefunden.'})

            akten_manager.update_akte(
                record_id=record['id'],
                title=record['title'],
                content=record.get('content', ''),
                hashtags=record.get('hashtags', ''),
                user_id=user_id,
                border_color=record.get('border_color'),
                reminder_date=record.get('reminder_date'),
                reminder_end_date=record.get('reminder_end_date'),
                reminder_repeat=record.get('reminder_repeat'),
                status=record.get('status'),
                category_id=category_id,
                address=record.get('address'),
                reminder_assigned_to=record.get('reminder_assigned_to')
            )
            
            
            return jsonify({
                'success': True,
                'message': f'Akte "{record["title"]}" wurde in Kategorie "{category}" einsortiert.',
                'action': 'category_updated',
                'records': [_build_record_preview(_get_record_by_id(record['id']), badge='Kategorie geändert')]
            })
        except Exception as exc:
            logger.error("Fehler beim Ändern der Kategorie: %s", exc, exc_info=True)
            return jsonify({'success': False, 'message': f'Fehler beim Ändern der Kategorie: {str(exc)}'}), 500


    def _execute_help():
        help_text = """
🤖 Verfügbare Befehle für den Assistenten:

📝 Akten erstellen:
• "erstelle eine Akte mit dem Titel Markus Müller und dem Inhalt heute Fußball"
• "lege Akte Markus Müller an"
• "mach mir eine Akte zu Markus Müller"

✏️ Akten bearbeiten:
• "bearbeite Akte Markus Müller und setze den Termin auf 20.08.2026"
• "ändere bei Akte Markus Müller den Inhalt auf Rückruf morgen"
• "ergänze bei Akte Müller: Anruf heute"

🔍 Suchen:
• "suche nach Markus Müller"
• "finde Akte Schmidt"

 Der Assistent lernt aus deinen Befehlen! Wenn er etwas nicht versteht, kannst du Feedback geben.
"""
        return jsonify({'success': True, 'message': help_text.strip()})

    return assistant_bp
