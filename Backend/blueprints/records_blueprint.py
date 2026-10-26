"""
Records Blueprint - Akten-Management
"""

import logging
import json
import os
import sys
from pathlib import Path
from flask import Blueprint, request, jsonify, session, send_from_directory

# security_utils importieren
sys.path.insert(0, str(Path(__file__).parent.parent))
from security_utils import InputSanitizer, FileUploadValidator

logger = logging.getLogger(__name__)

records_bp = Blueprint('records', __name__, url_prefix='/api/records')


def validate_reminder_repeat(reminder_repeat):
    if not reminder_repeat:
        return True
    if isinstance(reminder_repeat, str):
        if reminder_repeat in ['weekly', 'monthly', 'yearly']:
            return True
        try:
            data = json.loads(reminder_repeat)
        except json.JSONDecodeError:
            return False
    else:
        data = reminder_repeat
    if not isinstance(data, dict) or 'type' not in data:
        return False
    if data['type'] == 'weekly':
        return 'weekday' in data and isinstance(data['weekday'], int) and 0 <= data['weekday'] <= 6
    if data['type'] == 'weekly_interval':
        return (
            'interval' in data and isinstance(data['interval'], int) and 1 <= data['interval'] <= 5 and
            'weekday' in data and isinstance(data['weekday'], int) and 0 <= data['weekday'] <= 6
        )
    if data['type'] == 'monthly_interval':
        return (
            'interval' in data and isinstance(data['interval'], int) and 1 <= data['interval'] <= 12 and
            (
                'mode' not in data or data['mode'] == 'date' or (
                    data['mode'] == 'weekday' and
                    'nth' in data and (
                        data['nth'] == 'last' or
                        (isinstance(data['nth'], int) and 1 <= data['nth'] <= 5)
                    ) and
                    'weekday' in data and isinstance(data['weekday'], int) and 0 <= data['weekday'] <= 6
                )
            )
        )
    if data['type'] == 'yearly_interval':
        return 'interval' in data and isinstance(data['interval'], int) and 1 <= data['interval'] <= 10
    if data['type'] == 'monthly':
        return True
    if data['type'] == 'monthly_nth_weekday':
        return (
            'nth' in data and (
                data['nth'] == 'last' or
                (isinstance(data['nth'], int) and 1 <= data['nth'] <= 5)
            ) and
            'weekday' in data and isinstance(data['weekday'], int) and 0 <= data['weekday'] <= 6
        )
    if data['type'] == 'monthly_last_weekday':
        return 'weekday' in data and isinstance(data['weekday'], int) and 0 <= data['weekday'] <= 6
    if data['type'] == 'yearly':
        return True
    return False


def normalize_reminder_assigned_to(reminder_assigned_to, current_user_id, is_admin=False):
    if reminder_assigned_to in [None, '', False]:
        return None

    try:
        reminder_assigned_to = int(reminder_assigned_to)
    except (TypeError, ValueError):
        raise ValueError('Ungültige Termin-Sichtbarkeit')

    if not is_admin and reminder_assigned_to != int(current_user_id):
        raise ValueError('Private Termine können nur für den aktuellen Benutzer gesetzt werden')

    return reminder_assigned_to


def init_records_blueprint(app, auth_manager, db_manager, akten_manager, sperr_manager, audit_logger, ocr_manager=None, config=None):
    """Initialisiert das Records Blueprint mit den Managern"""
    
    @records_bp.route('', methods=['GET'])
    @auth_manager.login_required
    def list_records():
        try:
            search = request.args.get('search', '')
            filter_type = request.args.get('filter', 'all')
            search_type = request.args.get('search_type', 'all')
            
            # Pagination mit konsistenten Limits
            try:
                limit = int(request.args.get('limit', 50))
                offset = int(request.args.get('offset', 0))
            except (ValueError, TypeError):
                limit = 50
                offset = 0
            
            # Validierung: sinnvolle Limits
            limit = max(1, min(limit, 500))  # Min 1, Max 500 pro Anfrage
            offset = max(0, offset)
            
            category_id = request.args.get('category_id', type=int)
            border_color = request.args.get('border_color', type=str)

            result = akten_manager.list_akten(
                search, filter_type, search_type, limit, offset, category_id, border_color,
                viewer_user_id=session['user_id'],
                is_admin=session.get('role') == 'admin'
            )
            return jsonify(result)

        except Exception as e:
            return jsonify({'error': f'Aktenliste fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/stats', methods=['GET'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_view_stats')
    def get_stats():
        try:
            # Erweiterte Statistiken laden
            is_admin = session.get('role') == 'admin'
            stats = akten_manager.get_dashboard_stats(is_admin)
            return jsonify({'success': True, 'stats': stats})
        except Exception as e:
            return jsonify({'error': f'Statistik konnte nicht geladen werden: {str(e)}'}), 500
    
    @records_bp.route('/check-duplicates', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def check_duplicates():
        """Prüft auf ähnliche Akten vor der Erstellung"""
        try:
            data = request.get_json()
            title = InputSanitizer.sanitize_text(data.get('title', '').strip())
            content = InputSanitizer.sanitize_text(data.get('content', ''))
            address = InputSanitizer.sanitize_text(data.get('address', ''))
            hashtags = InputSanitizer.sanitize_text(data.get('hashtags', ''))

            if not title:
                return jsonify({'error': 'Titel ist erforderlich'}), 400
            
            # Dublettenerkennung durchführen
            duplicate_check = akten_manager.check_for_duplicates(
                title=title,
                content=content,
                address=address,
                hashtags=hashtags,
                user_id=session['user_id']
            )
            
            return jsonify({'success': True, 'duplicate_check': duplicate_check})
            
        except Exception as e:
            logger.error(f"Fehler bei Dublettenprüfung: {e}", exc_info=True)
            return jsonify({'error': f'Dublettenprüfung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/check-plz', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def check_plz():
        """Prüft ob die Postleitzahl in der Adresse im System vorhanden ist"""
        try:
            # Prüfen ob PLZ-Validierung aktiviert ist
            plz_validation_enabled = config.get('server', {}).get('plz_validation_enabled', True) if config else True
            if not plz_validation_enabled:
                # PLZ-Validierung deaktiviert - immer erfolgreich
                return jsonify({'success': True, 'plz_valid': True, 'validation_disabled': True})
            
            data = request.get_json()
            address = InputSanitizer.sanitize_text(data.get('address', ''))
            
            # PLZ-Validierung durchführen
            plz_valid, plz_warning = akten_manager.check_plz_valid(address)
            
            if not plz_valid:
                # PLZ nicht gefunden - Warnung zurückgeben
                return jsonify({
                    'success': False,
                    'warning': 'plz_invalid',
                    'message': plz_warning
                })
            
            # PLZ gültig oder keine PLZ angegeben
            return jsonify({'success': True, 'plz_valid': True})
            
        except Exception as e:
            logger.error(f"Fehler bei PLZ-Prüfung: {e}", exc_info=True)
            return jsonify({'error': f'PLZ-Prüfung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def create_record():
        try:
            data = request.get_json()
            title = InputSanitizer.sanitize_text(data.get('title', '').strip())
            content = InputSanitizer.sanitize_text(data.get('content', ''))
            address = InputSanitizer.sanitize_text(data.get('address', ''))
            hashtags = InputSanitizer.sanitize_text(data.get('hashtags', ''))
            force_create = data.get('force_create', False)  # Überspringt Dublettenprüfung wenn True
            
            # Check permissions for each field
            border_color = data.get('border_color', '') if auth_manager.check_permission('can_set_border_color') else ''
            status = data.get('status', 'neutral') if auth_manager.check_permission('can_set_status') else 'neutral'
            reminder_date = data.get('reminder_date') if auth_manager.check_permission('can_set_reminder') else None
            reminder_end_date = data.get('reminder_end_date') if auth_manager.check_permission('can_set_reminder') else None
            reminder_repeat = data.get('reminder_repeat') if auth_manager.check_permission('can_set_reminder') else None
            reminder_assigned_to = None
            category_id = data.get('category_id') if auth_manager.check_permission('can_set_category') else None
            hashtags = data.get('hashtags', '') if auth_manager.check_permission('can_set_note') else ''

            if auth_manager.check_permission('can_set_reminder'):
                reminder_assigned_to = normalize_reminder_assigned_to(
                    data.get('reminder_assigned_to'),
                    session['user_id'],
                    session.get('role') == 'admin'
                )
            
            if not title:
                return jsonify({'error': 'Titel ist erforderlich'}), 400
            if not validate_reminder_repeat(reminder_repeat):
                return jsonify({'error': 'Ungültige Wiederholungsdaten'}), 400
            
            # PLZ-Validierung durchführen (wenn nicht erzwungen und Validierung aktiviert)
            plz_validation_enabled = config.get('server', {}).get('plz_validation_enabled', True)
            if not force_create and address and plz_validation_enabled:
                plz_valid, plz_warning = akten_manager.check_plz_valid(address)
                if not plz_valid:
                    # PLZ nicht gefunden - Warnung zurückgeben
                    return jsonify({
                        'success': False,
                        'warning': 'plz_invalid',
                        'message': plz_warning
                    })
            
            # Dublettenerkennung durchführen (wenn nicht erzwungen)
            if not force_create:
                duplicate_check = akten_manager.check_for_duplicates(
                    title=title,
                    content=content,
                    address=address,
                    hashtags=hashtags,
                    user_id=session['user_id']
                )
                
                if duplicate_check.get('has_duplicates'):
                    # Dubletten gefunden - Warnung zurückgeben
                    return jsonify({
                        'success': False,
                        'warning': 'duplicate_found',
                        'duplicate_check': duplicate_check,
                        'message': f"Es wurden {len(duplicate_check['duplicates'])} ähnliche Akten gefunden. Möchten Sie trotzdem fortfahren?"
                    })
            
            record = akten_manager.create_akte(
                title, content, hashtags, session['user_id'], border_color, reminder_date, reminder_end_date, reminder_repeat, status, category_id, address, reminder_assigned_to
            )
            
            # Audit Log
            audit_logger.log_action(session['username'], "ERSTELLT", f"Akte #{record['number']}: {title}")
            
            return jsonify({'success': True, 'record': record})
            
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'Aktenerstellung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>', methods=['GET', 'PUT'])
    @auth_manager.login_required
    def get_or_update_record(record_id):
        try:
            if request.method == 'PUT':
                if not auth_manager.check_permission('can_write'):
                    return jsonify({'error': 'Keine Schreibberechtigung'}), 403
                
                # Pruefen ob Akte gesperrt ist
                if sperr_manager.is_record_locked(record_id, session['user_id']):
                    return jsonify({'error': 'Akte ist gesperrt'}), 423
                
                try:
                    data = request.get_json()
                    title = InputSanitizer.sanitize_text(data.get('title', '').strip())
                    content = InputSanitizer.sanitize_text(data.get('content', ''))
                    address = InputSanitizer.sanitize_text(data.get('address', ''))
                    force_create = data.get('force_create', False)  # Überspringt PLZ-Validierung wenn True

                    # Alte Daten holen fuer Log
                    old_record = akten_manager.get_akte(record_id, viewer_user_id=None, is_admin=True)
                    
                    # Use old values if no permission
                    border_color = data.get('border_color', '') if auth_manager.check_permission('can_set_border_color') else old_record.get('border_color', '')
                    status = data.get('status') if auth_manager.check_permission('can_set_status') else old_record.get('status', 'neutral')
                    reminder_date = data.get('reminder_date') if auth_manager.check_permission('can_set_reminder') else old_record.get('reminder_date')
                    reminder_end_date = data.get('reminder_end_date') if auth_manager.check_permission('can_set_reminder') else old_record.get('reminder_end_date')
                    reminder_repeat = data.get('reminder_repeat') if auth_manager.check_permission('can_set_reminder') else old_record.get('reminder_repeat')
                    reminder_assigned_to = old_record.get('reminder_assigned_to')
                    category_id = data.get('category_id') if auth_manager.check_permission('can_set_category') else old_record.get('category_id')
                    hashtags = data.get('hashtags', '') if auth_manager.check_permission('can_set_note') else old_record.get('hashtags', '')

                    if auth_manager.check_permission('can_set_reminder'):
                        can_manage_private_reminder = (
                            old_record.get('reminder_assigned_to') in [None, session['user_id']] or
                            session.get('role') == 'admin'
                        )
                        if can_manage_private_reminder:
                            reminder_assigned_to = normalize_reminder_assigned_to(
                                data.get('reminder_assigned_to'),
                                session['user_id'],
                                session.get('role') == 'admin'
                            )
                        else:
                            reminder_date = old_record.get('reminder_date')
                            reminder_end_date = old_record.get('reminder_end_date')
                            reminder_repeat = old_record.get('reminder_repeat')
                            reminder_assigned_to = old_record.get('reminder_assigned_to')
                    
                    if not title:
                        return jsonify({'error': 'Titel ist erforderlich'}), 400
                    if not validate_reminder_repeat(reminder_repeat):
                        return jsonify({'error': 'Ungültige Wiederholungsdaten'}), 400
                    
                    # PLZ-Validierung durchführen (bei Adressänderung, wenn nicht erzwungen)
                    if not force_create and address:
                        plz_valid, plz_warning = akten_manager.check_plz_valid(address)
                        if not plz_valid:
                            # PLZ nicht gefunden - Warnung zurückgeben
                            return jsonify({
                                'success': False,
                                'warning': 'plz_invalid',
                                'message': plz_warning
                            })
                    
                    akten_manager.update_akte(
                        record_id, title, content, hashtags, session['user_id'], border_color, reminder_date, reminder_end_date, reminder_repeat, status, category_id, address, reminder_assigned_to
                    )
                    
                    # Audit Log
                    audit_logger.log_action(session['username'], "BEARBEITET", f"Akte #{old_record['number']}: {title}")
                    
                    return jsonify({'success': True})
                except ValueError as e:
                    return jsonify({'error': str(e)}), 400
                except Exception as e:
                    logger.error(f"PUT-Fehler: {e}")
                    return jsonify({'error': f'Aktualisierung fehlgeschlagen: {str(e)}'}), 500
            
            # GET: Akte zurueckgeben
            record = akten_manager.get_akte(
                record_id,
                viewer_user_id=session['user_id'],
                is_admin=session.get('role') == 'admin'
            )
            if not record:
                return jsonify({'error': 'Akte nicht gefunden'}), 404
            
            # Lock-Info anhaengen fuer Frontend-Anzeige
            record['lock_info'] = sperr_manager.get_lock_info(record_id)
            return jsonify(record)
            
        except Exception as e:
            return jsonify({'error': f'Aktenabruf fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>', methods=['DELETE'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_delete')
    def delete_record(record_id):
        try:
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                return jsonify({'error': 'Akte ist gesperrt'}), 423
            
            # Daten holen fuer Log
            try:
                record = akten_manager.get_akte(record_id, viewer_user_id=None, is_admin=True)
            except Exception as e:
                logger.error(f"Fehler beim Abrufen der Akte für Log: {e}")
                record = {'title': 'Unbekannt'}
            
            aktenzeichen = akten_manager.delete_akte(record_id, session['user_id'])
            
            # Audit Log
            try:
                audit_logger.log_action(session['username'], "GELÖSCHT", f"Akte #{aktenzeichen}: {record['title']}")
            except Exception as e:
                logger.error(f"Fehler beim Audit Log: {e}")
            
            return jsonify({'success': True, 'message': f'Akte {aktenzeichen} geloescht'})
            
        except ValueError as e:
            logger.error(f"Wertfehler beim Löschen der Akte {record_id}: {e}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Akte {record_id}: {e}", exc_info=True)
            return jsonify({'error': f'Loeschung fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/massen-loeschen', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_delete')
    def delete_records_bulk():
        """
        Löscht mehrere Akten in einem Request.
        Body: { "ids": [1,2,3] }
        """
        try:
            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400

            # Validiere + limitiere (Performance / Missbrauchsschutz)
            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            # Deduplizieren (Reihenfolge beibehalten)
            ids = list(dict.fromkeys(ids))
            if len(ids) > 200:
                return jsonify({'error': 'Zu viele Akten auf einmal (max. 200)'}), 400

            # Lock-Prüfung in einem Query (Performance)
            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            result = akten_manager.loesche_akten_mehrere(ids, session['user_id'])
            geloescht = result.get('aktenzeichen', [])
            
            # Audit Log
            if geloescht:
                audit_logger.log_action(session['username'], "MASSEN-DELETE", f"{len(geloescht)} Akten gelöscht: {', '.join(geloescht)}")
            
            return jsonify({
                'success': True,
                'deleted_count': len(geloescht),
                'deleted_numbers': geloescht,
                'dateisystem_fehler': result.get('dateisystem_fehler', [])
            })

        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'Massen-Loeschung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/massen-status', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def update_status_bulk():
        """
        Aktualisiert den Status mehrerer Akten.
        Body: { "ids": [1,2,3], "status": "offen" }
        """
        try:
            if not auth_manager.check_permission('can_set_status'):
                return jsonify({'error': 'Keine Berechtigung zum Ändern des Status'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])
            new_status = data.get('status')

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400
            if new_status not in ['neutral', 'offen', 'erledigt', 'bearbeitung']:
                return jsonify({'error': 'Ungültiger Status'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            updated_count = akten_manager.update_status_mehrere(ids, new_status, session['user_id'])
            return jsonify({'success': True, 'updated_count': updated_count})

        except Exception as e:
            return jsonify({'error': f'Massen-Status-Update fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/massen-farbe', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def update_color_bulk():
        """
        Aktualisiert die Rahmenfarbe mehrerer Akten.
        Body: { "ids": [1,2,3], "color": "border-red" }
        """
        try:
            if not auth_manager.check_permission('can_set_border_color'):
                return jsonify({'error': 'Keine Berechtigung zum Ändern der Rahmenfarbe'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])
            new_color = data.get('color', '')

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400
            
            # Validiere Farbe (leerer String ist erlaubt für Standard)
            valid_colors = ['', 'border-red', 'border-blue', 'border-yellow', 'border-green', 'border-magenta']
            if new_color not in valid_colors:
                return jsonify({'error': 'Ungültige Farbe'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            updated_count = akten_manager.update_farbe_mehrere(ids, new_color, session['user_id'])
            return jsonify({'success': True, 'updated_count': updated_count})

        except Exception as e:
            return jsonify({'error': f'Massen-Farben-Update fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/massen-termin', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def update_reminder_bulk():
        """
        Aktualisiert den Termin mehrerer Akten.
        Body: { "ids": [1,2,3], "reminder_date": "2025-01-01", "reminder_end_date": null, "reminder_repeat": null }
        """
        try:
            if not auth_manager.check_permission('can_set_reminder'):
                return jsonify({'error': 'Keine Berechtigung zum Ändern von Terminen'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])
            reminder_date = data.get('reminder_date')
            reminder_end_date = data.get('reminder_end_date')
            reminder_repeat = data.get('reminder_repeat')
            reminder_assigned_to = normalize_reminder_assigned_to(
                data.get('reminder_assigned_to'),
                session['user_id'],
                session.get('role') == 'admin'
            )

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            if not validate_reminder_repeat(reminder_repeat):
                return jsonify({'error': 'Ungültige Wiederholungsdaten'}), 400
            
            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            updated_count = akten_manager.update_termin_mehrere(
                ids, reminder_date, reminder_end_date, reminder_repeat, reminder_assigned_to, session['user_id']
            )
            return jsonify({'success': True, 'updated_count': updated_count})

        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'Massen-Termin-Update fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/massen-note', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def update_note_bulk():
        """
        Aktualisiert den Vermerk (hashtags) mehrerer Akten.
        Body: { "ids": [1,2,3], "note": "neuer Vermerk" }
        """
        try:
            if not auth_manager.check_permission('can_set_note'):
                return jsonify({'error': 'Keine Berechtigung zum Ändern von Vermerken'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])
            note = data.get('note', '')

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            updated_count = akten_manager.update_note_mehrere(ids, note, session['user_id'])
            return jsonify({'success': True, 'updated_count': updated_count})

        except Exception as e:
            logger.error(f'Massen-Vermerk-Update fehlgeschlagen: {str(e)}', exc_info=True)
            return jsonify({'error': f'Massen-Vermerk-Update fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/massen-erinnerung', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def create_reminders_bulk():
        """
        Erstellt Erinnerungn für mehrere Akten.
        Body: { "ids": [1,2,3], "reminder_date": "2025-01-01", "assigned_to": null, "note": null }
        """
        try:
            if not auth_manager.check_permission('can_set_erinnerung'):
                return jsonify({'error': 'Keine Berechtigung zum Setzen von Erinnerungn'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])
            reminder_date = data.get('reminder_date')
            assigned_to = data.get('assigned_to')
            note = data.get('note')

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400
            if not reminder_date:
                return jsonify({'error': 'Kein Datum angegeben'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            db_manager.create_reminders_bulk(ids, reminder_date, session['user_id'], assigned_to, note)
            return jsonify({'success': True})

        except Exception as e:
            return jsonify({'error': f'Massen-Erinnerung-Erstellung fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/massen-termin-loeschen', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def delete_termine_bulk():
        """
        Löscht alle Kalender-Termine für mehrere Akten.
        Body: { "ids": [1,2,3] }
        """
        try:
            if not auth_manager.check_permission('can_delete_termine'):
                return jsonify({'error': 'Keine Berechtigung zum Löschen von Terminen'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            deleted_count = db_manager.delete_termine_bulk(ids)
            return jsonify({'success': True, 'deleted_count': deleted_count})

        except Exception as e:
            return jsonify({'error': f'Massen-Termin-Löschung fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/massen-erinnerung-loeschen', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def delete_erinnerungn_bulk():
        """
        Löscht alle Erinnerungn für mehrere Akten.
        Body: { "ids": [1,2,3] }
        """
        try:
            if not auth_manager.check_permission('can_delete_erinnerung'):
                return jsonify({'error': 'Keine Berechtigung zum Löschen von Erinnerungn'}), 403

            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])

            if not isinstance(ids, list) or not ids:
                return jsonify({'error': 'Keine Akten-IDs angegeben'}), 400

            try:
                ids = [int(x) for x in ids]
            except Exception:
                return jsonify({'error': 'Ungueltige Akten-IDs'}), 400

            gesperrt = sperr_manager.get_locked_record_ids(ids, session['user_id'])
            if gesperrt:
                return jsonify({'error': f'Akte {gesperrt[0]} ist gesperrt'}), 423

            deleted_count = db_manager.delete_erinnerungn_bulk(ids)
            return jsonify({'success': True, 'deleted_count': deleted_count})

        except Exception as e:
            return jsonify({'error': f'Massen-Erinnerung-Löschung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/files', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_upload')
    def upload_file(record_id):
        try:
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                return jsonify({'error': 'Akte ist gesperrt'}), 423

            if 'file' not in request.files:
                return jsonify({'error': 'Keine Datei hochgeladen'}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'Keine Datei ausgewählt'}), 400

            # File-Upload Validierung
            sanitized_filename = FileUploadValidator.sanitize_filename(file.filename)
            if not FileUploadValidator.is_allowed_extension(sanitized_filename):
                return jsonify({'error': f'Dateityp nicht erlaubt: {file.filename}'}), 400

            # Datei-Größe prüfen (max 50MB aus Konfiguration)
            max_size_mb = config.get('upload', {}).get('max_file_size_mb', 50)
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

            # Datei-Name im request object aktualisieren
            file.filename = sanitized_filename

            result = akten_manager.upload_file(record_id, file, session['user_id'])
            return jsonify(result)
            
        except Exception as e:
            return jsonify({'error': f'Upload fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/reorder-attachments', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def reorder_attachments(record_id):
        try:
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                return jsonify({'error': 'Akte ist gesperrt'}), 423
            
            data = request.get_json()
            filenames = data.get('filenames', [])
            
            if not isinstance(filenames, list):
                return jsonify({'error': 'Ungültiges Format für Dateiliste'}), 400
            
            akten_manager.reorder_attachments(record_id, filenames, session['user_id'])
            return jsonify({'success': True})
            
        except Exception as e:
            return jsonify({'error': f'Reordering fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/files/<filename>/rename', methods=['POST'])
    @auth_manager.login_required
    def rename_record_file(record_id, filename):
        try:
            if not auth_manager.check_permission('can_write'):
                return jsonify({'error': 'Keine Schreibberechtigung'}), 403
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                return jsonify({'error': 'Akte ist gesperrt'}), 423
            
            data = request.get_json()
            new_filename = data.get('new_filename')
            if not new_filename:
                return jsonify({'error': 'Neuer Dateiname fehlt'}), 400
                
            akten_manager.rename_attachment(record_id, filename, new_filename, session['user_id'])
            return jsonify({'success': True, 'message': 'Datei umbenannt'})
            
        except Exception as e:
            return jsonify({'error': f'Umbenennen fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/<int:record_id>/files/<filename>/ocr/retry', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def retry_ocr_for_file(record_id, filename):
        try:
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                return jsonify({'error': 'Akte ist gesperrt'}), 423
            if ocr_manager is None:
                return jsonify({'error': 'OCR ist nicht initialisiert'}), 503

            result = ocr_manager.enqueue_attachment_by_record_and_filename(record_id, filename, force=True)
            return jsonify({'success': True, 'ocr': result})
        except Exception as e:
            return jsonify({'error': f'OCR-Neustart fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/clipboard', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_upload')
    def upload_from_clipboard(record_id):
        """Importiert Inhalte aus der Zwischenablage (Bilder oder Text)"""
        try:
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                return jsonify({'error': 'Akte ist gesperrt'}), 423

            data = request.get_json()
            content_type = data.get('type')  # 'image' oder 'text'
            content = data.get('content')
            filename = data.get('filename')

            if not content_type or not content:
                return jsonify({'error': 'Keine Inhaltstyp oder Inhalt übergeben'}), 400

            import base64
            from io import BytesIO
            from datetime import datetime

            if content_type == 'image':
                # Base64-Bild dekodieren
                try:
                    # Header entfernen (z.B. "data:image/png;base64,")
                    if ',' in content:
                        content = content.split(',')[1]
                    image_data = base64.b64decode(content)
                except Exception as e:
                    return jsonify({'error': f'Ungültiges Bildformat: {str(e)}'}), 400

                # Dateinamen generieren falls nicht angegeben
                if not filename:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f'clipboard_{timestamp}.jpg'

                # Prüfen ob Dateiendung erlaubt
                sanitized_filename = FileUploadValidator.sanitize_filename(filename)
                if not FileUploadValidator.is_allowed_extension(sanitized_filename):
                    # Falls keine Endung, .jpg hinzufügen
                    if not sanitized_filename.endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                        sanitized_filename += '.jpg'

                # Datei-Größe prüfen
                max_size_mb = config.get('upload', {}).get('max_file_size_mb', 50)
                if len(image_data) > max_size_mb * 1024 * 1024:
                    return jsonify({'error': f'Bild zu groß (max {max_size_mb}MB)'}), 400

                # Mock File-Objekt erstellen
                class MockFile:
                    def __init__(self, filename, content):
                        self.filename = filename
                        self.content = content
                    
                    def save(self, path):
                        with open(path, 'wb') as f:
                            f.write(self.content)
                    
                    def seek(self, pos, whence=0):
                        pass
                    
                    def tell(self):
                        return len(self.content)

                mock_file = MockFile(sanitized_filename, image_data)
                result = akten_manager.upload_file(record_id, mock_file, session['user_id'])
                return jsonify(result)

            elif content_type == 'text':
                # Text als Markdown-Datei speichern
                if not filename:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f'clipboard_{timestamp}.md'
                else:
                    # Sicherstellen dass .md Endung
                    if not filename.endswith('.md'):
                        filename += '.md'

                sanitized_filename = FileUploadValidator.sanitize_filename(filename)

                # Mock File-Objekt für Text erstellen
                class TextFile:
                    def __init__(self, filename, text_content):
                        self.filename = filename
                        self.content = text_content.encode('utf-8')
                    
                    def save(self, path):
                        with open(path, 'wb') as f:
                            f.write(self.content)
                    
                    def seek(self, pos, whence=0):
                        pass
                    
                    def tell(self):
                        return len(self.content)

                text_file = TextFile(sanitized_filename, content)
                result = akten_manager.upload_file(record_id, text_file, session['user_id'])
                return jsonify(result)

            else:
                return jsonify({'error': f'Unbekannter Inhaltstyp: {content_type}'}), 400

        except Exception as e:
            logger.error(f"Clipboard-Import Fehler: {e}", exc_info=True)
            return jsonify({'error': f'Clipboard-Import fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/ocr/queue', methods=['GET'])
    @auth_manager.login_required
    def list_ocr_queue():
        """Listet alle OCR-Scans in der Warteschlange (pending/running)"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        ao.attachment_id,
                        ao.record_id,
                        ao.status,
                        ao.progress,
                        ao.pages_done,
                        ao.pages_total,
                        ao.updated_at,
                        a.filename,
                        r.number as record_number,
                        r.title as record_title
                    FROM attachment_ocr ao
                    JOIN attachments a ON a.id = ao.attachment_id
                    JOIN records r ON r.id = ao.record_id
                    WHERE ao.status IN ('pending', 'running')
                    ORDER BY ao.status DESC, ao.updated_at ASC
                ''')
                queue_scans = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'queue_scans': queue_scans})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der OCR-Warteschlange: {e}")
            return jsonify({'error': f'Fehler beim Abrufen: {str(e)}'}), 500

    @records_bp.route('/ocr/failed', methods=['GET'])
    @auth_manager.login_required
    def list_failed_ocr_scans():
        """Listet alle fehlgeschlagenen OCR-Scans mit Fehl-Anzahl"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        ao.attachment_id,
                        ao.record_id,
                        ao.failure_count,
                        ao.error_message,
                        ao.updated_at,
                        a.filename,
                        r.number as record_number,
                        r.title as record_title
                    FROM attachment_ocr ao
                    JOIN attachments a ON a.id = ao.attachment_id
                    JOIN records r ON r.id = ao.record_id
                    WHERE ao.status = 'error'
                    ORDER BY ao.failure_count DESC, ao.updated_at DESC
                ''')
                failed_scans = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'failed_scans': failed_scans})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen fehlgeschlagener OCR-Scans: {e}")
            return jsonify({'error': f'Fehler beim Abrufen: {str(e)}'}), 500

    @records_bp.route('/ocr/failed/requeue', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def requeue_failed_ocr_scans():
        """Stellt fehlgeschlagene OCR-Scans in die Warteschlange"""
        try:
            if ocr_manager is None:
                return jsonify({'error': 'OCR ist nicht initialisiert'}), 503

            data = request.get_json()
            attachment_ids = data.get('attachment_ids', [])

            if not attachment_ids:
                return jsonify({'error': 'Keine attachment_ids angegeben'}), 400

            results = []
            for attachment_id in attachment_ids:
                try:
                    with db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT record_id, filename
                            FROM attachments
                            WHERE id = ?
                        ''', (attachment_id,))
                        row = cursor.fetchone()
                        if not row:
                            results.append({'attachment_id': attachment_id, 'success': False, 'error': 'Anhang nicht gefunden'})
                            continue

                        result = ocr_manager.enqueue_attachment(attachment_id, force=True)
                        results.append({'attachment_id': attachment_id, 'success': True, 'queued': result.get('queued')})
                except Exception as e:
                    results.append({'attachment_id': attachment_id, 'success': False, 'error': str(e)})

            return jsonify({'success': True, 'results': results})
        except Exception as e:
            logger.error(f"Fehler beim Neu-Einreihen von OCR-Scans: {e}")
            return jsonify({'error': f'Fehler: {str(e)}'}), 500

    @records_bp.route('/ocr/failed/delete', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_delete')
    def delete_failed_ocr_scans():
        """Löscht fehlgeschlagene OCR-Einträge (nicht die Dateien)"""
        try:
            data = request.get_json()
            attachment_ids = data.get('attachment_ids', [])

            if not attachment_ids:
                return jsonify({'error': 'Keine attachment_ids angegeben'}), 400

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(attachment_ids))
                cursor.execute(f'''
                    DELETE FROM ocr_jobs
                    WHERE attachment_id IN ({placeholders})
                ''', attachment_ids)
                cursor.execute(f'''
                    DELETE FROM attachment_ocr
                    WHERE attachment_id IN ({placeholders})
                ''', attachment_ids)
                conn.commit()

            return jsonify({'success': True, 'deleted_count': len(attachment_ids)})
        except Exception as e:
            logger.error(f"Fehler beim Löschen von OCR-Einträgen: {e}")
            return jsonify({'error': f'Fehler: {str(e)}'}), 500

    @records_bp.route('/<int:record_id>/files/<filename>', methods=['GET', 'DELETE'])
    @auth_manager.login_required
    def download_or_delete_file(record_id, filename):
        try:
            if request.method == 'DELETE':
                if not auth_manager.check_permission('can_delete'):
                    return jsonify({'error': 'Keine Loeschberechtigung'}), 403
                if sperr_manager.is_record_locked(record_id, session['user_id']):
                    return jsonify({'error': 'Akte ist gesperrt'}), 423
                
                result = akten_manager.delete_file(record_id, filename, session['user_id'])
                return jsonify({'success': True, 'deleted': result})
            else:
                directory, filename = akten_manager.download_file(record_id, filename)
                # Pruefen ob Download erzwungen werden soll (vom Download-Button)
                force_download = request.args.get('download', '0') == '1'
                
                # Download-Berechtigung pruefen
                if force_download and not auth_manager.check_permission('can_download'):
                    return jsonify({'error': 'Keine Download-Berechtigung'}), 403

                return send_from_directory(
                    directory, 
                    filename, 
                    as_attachment=force_download,
                    conditional=True  # Wichtig fuer Byte-Range Streaming (Videos)
                )
            
        except Exception as e:
            return jsonify({'error': f'Dateizugriff fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/lock', methods=['POST'])
    @auth_manager.login_required
    def lock_record(record_id):
        try:
            if sperr_manager.is_record_locked(record_id, session['user_id']):
                # Return lock info so frontend can show who has locked it
                lock_info = sperr_manager.get_lock_info(record_id)
                return jsonify({'error': 'Akte ist bereits gesperrt', 'lock_info': lock_info}), 423
            
            sperr_manager.lock_record(record_id, session['user_id'])
            return jsonify({'success': True, 'message': 'Akte gesperrt'})
            
        except Exception as e:
            return jsonify({'error': f'Sperrung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/unlock', methods=['POST'])
    @auth_manager.login_required
    def unlock_record(record_id):
        try:
            if not sperr_manager.can_unlock_record(record_id, session['user_id']):
                return jsonify({'error': 'Sie können diese Akte nicht entsperren'}), 403
            
            sperr_manager.unlock_record(record_id, session['user_id'])
            return jsonify({'success': True, 'message': 'Akte entsperrt'})
            
        except Exception as e:
            return jsonify({'error': f'Entsperrung fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/lock-info', methods=['GET'])
    @auth_manager.login_required
    def record_lock_info(record_id):
        info = sperr_manager.get_lock_info(record_id)
        return jsonify({'locked': info is not None, 'lock_info': info})
    
    @records_bp.route('/<int:record_id>/heartbeat', methods=['POST'])
    @auth_manager.login_required
    def heartbeat_lock(record_id):
        """Verlaengert Lock-Sperre"""
        try:
            success = sperr_manager.extend_lock(record_id, session['user_id'])
            return jsonify({'success': success})
        except Exception as e:
            return jsonify({'error': f'Heartbeat fehlgeschlagen: {str(e)}'}), 500
    
    @records_bp.route('/cleanup-locks', methods=['POST'])
    @auth_manager.login_required
    def cleanup_locks():
        sperr_manager.cleanup_expired_locks()
        return jsonify({'success': True})
    
    @records_bp.route('/similar', methods=['GET'])
    @auth_manager.login_required
    def find_similar_records():
        """Findet ähnliche Akten basierend auf Text-Ähnlichkeit"""
        try:
            search_query = request.args.get('search_query', '')
            reference_record_id = request.args.get('reference_record_id', type=int)
            limit = int(request.args.get('limit', config.get('search', {}).get('similarity_limit', '20') if config else '20'))
            offset = int(request.args.get('offset', 0))
            min_similarity = float(request.args.get('min_similarity', 0.01))
            
            # Limit maximieren
            limit = min(limit, 100)
            
            result = akten_manager.find_similar_records(
                search_query=search_query if search_query else None,
                reference_record_id=reference_record_id,
                limit=limit,
                offset=offset,
                min_similarity=min_similarity,
                viewer_user_id=session['user_id'],
                is_admin=session.get('role') == 'admin'
            )
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Fehler bei Ähnlichkeitssuche: {e}", exc_info=True)
            return jsonify({'error': f'Ähnlichkeitssuche fehlgeschlagen: {str(e)}'}), 500
    
    # Reminder (Erinnerung) Endpoints
    @records_bp.route('/reminders', methods=['GET'])
    @auth_manager.login_required
    def get_reminders():
        try:
            today_only = request.args.get('today_only', 'false').lower() == 'true'
            all_reminders = request.args.get('all', 'false').lower() == 'true'
            include_completed = request.args.get('include_completed', 'false').lower() == 'true'
            
            if all_reminders:
                reminders = db_manager.get_all_reminders(today_only=today_only, include_completed=include_completed)
            else:
                reminders = db_manager.get_reminders_for_user(session['user_id'], today_only=today_only)
                
            return jsonify({'success': True, 'reminders': reminders})
        except Exception as e:
            return jsonify({'error': f'Erinnerungn konnten nicht geladen werden: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/reminders', methods=['GET'])
    @auth_manager.login_required
    def get_record_reminders(record_id):
        try:
            reminders = db_manager.get_reminders_for_record(record_id)
            return jsonify({'success': True, 'reminders': reminders})
        except Exception as e:
            return jsonify({'error': f'Erinnerungn für Akte konnten nicht geladen werden: {str(e)}'}), 500
    
    @records_bp.route('/<int:record_id>/reminders', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def create_record_reminder(record_id):
        try:
            data = request.get_json()
            reminder_date = data.get('reminder_date')
            assigned_to = data.get('assigned_to')
            note = data.get('note')
            
            if not reminder_date:
                return jsonify({'error': 'Datum ist erforderlich'}), 400
            
            # Check if there's already an active (non-completed) reminder for this record
            existing_reminders = db_manager.get_reminders_for_record(record_id)
            active_reminders = [r for r in existing_reminders if r.get('completed', 0) == 0]
            if len(active_reminders) > 0:
                return jsonify({'error': 'Es existiert bereits eine aktive Erinnerung für diese Akte'}), 400
            
            reminder_id = db_manager.create_reminder(
                record_id=record_id,
                reminder_date=reminder_date,
                created_by=session['user_id'],
                assigned_to=assigned_to,
                note=note
            )
            
            # Audit Log
            record = akten_manager.get_akte(record_id)
            audit_logger.log_action(session['username'], "ERINNERUNG ERSTELLT", f"Akte #{record['number']}: {record['title']}")
            
            return jsonify({'success': True, 'reminder_id': reminder_id})
        except Exception as e:
            return jsonify({'error': f'Erinnerung konnte nicht erstellt werden: {str(e)}'}), 500
    
    @records_bp.route('/reminders/<int:reminder_id>', methods=['PUT'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def update_reminder(reminder_id):
        try:
            data = request.get_json()
            reminder_date = data.get('reminder_date')
            assigned_to = data.get('assigned_to')
            note = data.get('note')
            completed = data.get('completed')
            
            success = db_manager.update_reminder(
                reminder_id=reminder_id,
                reminder_date=reminder_date,
                assigned_to=assigned_to,
                note=note,
                completed=completed
            )
            
            if success:
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Erinnerung nicht gefunden'}), 404
        except Exception as e:
            return jsonify({'error': f'Erinnerung konnte nicht aktualisiert werden: {str(e)}'}), 500
    
    @records_bp.route('/users', methods=['GET'])
    @auth_manager.login_required
    def list_all_users():
        """Gibt alle aktiven Benutzer zurück (für Erinnerungn-Zuweisung und Chat)"""
        try:
            users = db_manager.list_users()
            # Nur aktive Benutzer und ohne Passwort-Hashes
            active_users = [u for u in users if u.get('active', 1) == 1]
            for u in active_users:
                u.pop('password_hash', None)
                # is_online als Boolean zurückgeben (Standard 0 wenn nicht vorhanden)
                is_online_value = u.get('is_online')
                if is_online_value is None:
                    is_online_value = 0
                u['is_online'] = bool(int(is_online_value))
            return jsonify({'success': True, 'users': active_users})
        except Exception as e:
            return jsonify({'error': f'Benutzerliste konnte nicht geladen werden: {str(e)}'}), 500
    
    @records_bp.route('/reminders/<int:reminder_id>', methods=['DELETE'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def delete_reminder(reminder_id):
        try:
            success = db_manager.delete_reminder(reminder_id)
            if success:
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Erinnerung nicht gefunden'}), 404
        except Exception as e:
            return jsonify({'error': f'Erinnerung konnte nicht gelöscht werden: {str(e)}'}), 500

    # ── Archiv-Endpoints ────────────────────────────────────────────────────

    @records_bp.route('/archive', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def archive_records():
        """Verschiebt mehrere Akten ins Archiv"""
        try:
            data = request.get_json()
            record_ids = data.get('record_ids', [])
            archive_reason = data.get('archive_reason', None)
            user_id = session.get('user_id')

            if not record_ids:
                return jsonify({'error': 'Keine Akten IDs übergeben'}), 400

            result = akten_manager.archive_records(record_ids, user_id, archive_reason)

            if result.get('success'):
                return jsonify(result)
            else:
                return jsonify({'error': result.get('error', 'Archivierung fehlgeschlagen')}), 400
        except Exception as e:
            logger.error(f"Fehler bei Archivierung: {e}", exc_info=True)
            return jsonify({'error': f'Archivierung fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/restore', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def restore_records():
        """Stellt mehrere Akten aus dem Archiv wieder her"""
        try:
            data = request.get_json()
            record_ids = data.get('record_ids', [])
            user_id = session.get('user_id')

            if not record_ids:
                return jsonify({'error': 'Keine Akten IDs übergeben'}), 400

            result = akten_manager.restore_records(record_ids, user_id)

            if result.get('success'):
                return jsonify(result)
            else:
                return jsonify({'error': result.get('error', 'Wiederherstellung fehlgeschlagen')}), 400
        except Exception as e:
            logger.error(f"Fehler bei Wiederherstellung: {e}", exc_info=True)
            return jsonify({'error': f'Wiederherstellung fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/archived', methods=['GET'])
    @auth_manager.login_required
    def list_archived_records():
        """Listet archivierte Akten"""
        try:
            search = request.args.get('search', '')
            filter_type = request.args.get('filter', 'all')
            search_type = request.args.get('search_type', 'all')
            limit = int(request.args.get('limit', 50))
            offset = int(request.args.get('offset', 0))
            category_id = request.args.get('category_id')
            border_color = request.args.get('border_color')
            user_id = session.get('user_id')
            is_admin = session.get('role') == 'admin'

            if category_id:
                category_id = int(category_id)

            result = akten_manager.list_archived_records(
                search=search,
                filter_type=filter_type,
                search_type=search_type,
                limit=limit,
                offset=offset,
                category_id=category_id,
                border_color=border_color,
                viewer_user_id=user_id,
                is_admin=is_admin
            )

            return jsonify(result)
        except Exception as e:
            logger.error(f"Fehler beim Laden archivierter Akten: {e}", exc_info=True)
            return jsonify({'error': f'Laden archivierter Akten fehlgeschlagen: {str(e)}'}), 500

    @records_bp.route('/<int:record_id>/archive-metadata', methods=['GET'])
    @auth_manager.login_required
    def get_archive_metadata(record_id):
        """Holt Archiv-Metadaten für eine Akte"""
        try:
            metadata = akten_manager.get_archive_metadata(record_id)
            if metadata:
                return jsonify({'success': True, 'metadata': metadata})
            else:
                return jsonify({'error': 'Archiv-Metadaten nicht gefunden'}), 404
        except Exception as e:
            logger.error(f"Fehler beim Laden Archiv-Metadaten: {e}", exc_info=True)
            return jsonify({'error': f'Laden Archiv-Metadaten fehlgeschlagen: {str(e)}'}), 500

    return records_bp
