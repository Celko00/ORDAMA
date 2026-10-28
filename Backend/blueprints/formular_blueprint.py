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

Formular Blueprint - API für Formulare
"""

import logging
from flask import Blueprint, request, jsonify, session

logger = logging.getLogger(__name__)

formular_bp = Blueprint('formular', __name__, url_prefix='/api/formulare')

def init_formular_blueprint(app, auth_manager, formular_manager, audit_logger):
    """Initialisiert das Formular Blueprint"""
    
    @formular_bp.route('/vorlagen', methods=['GET'])
    @auth_manager.login_required
    def list_vorlagen():
        try:
            vorlagen = formular_manager.hole_vorlagen()
            return jsonify({'success': True, 'vorlagen': vorlagen})
        except Exception as e:
            return jsonify({'error': f'Vorlagen konnten nicht geladen werden: {str(e)}'}), 500

    @formular_bp.route('/vorlagen', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def create_vorlage():
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            structure = data.get('structure')
            template_id = data.get('id')
            next_number = data.get('next_number')
            
            if not name or not structure:
                return jsonify({'error': 'Name und Struktur sind erforderlich'}), 400
                
            # Falls next_number mitgeschickt wurde, in die Struktur legen
            if next_number is not None:
                if isinstance(structure, dict):
                    structure['next_number'] = int(next_number)

            if template_id:
                # Update bestehende Vorlage
                formular_manager.update_vorlage(template_id, name, structure)
                audit_logger.log_action(session['username'], "FORMULAR-VORLAGE-AKTUALISIERT", f"Vorlage: {name}")
                return jsonify({'success': True})
            else:
                # Neue Vorlage
                vorlage = formular_manager.erstelle_vorlage(name, structure, session['user_id'])
                audit_logger.log_action(session['username'], "FORMULAR-VORLAGE-ERSTELLT", f"Vorlage: {name}")
                return jsonify({'success': True, 'vorlage': vorlage})
        except Exception as e:
            return jsonify({'error': f'Vorlage konnte nicht gespeichert werden: {str(e)}'}), 500

    @formular_bp.route('/vorlagen/<int:template_id>', methods=['DELETE'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_delete')
    def delete_vorlage(template_id):
        try:
            formular_manager.loesche_vorlage(template_id)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': f'Vorlage konnte nicht gelöscht werden: {str(e)}'}), 500

    @formular_bp.route('/ausfuellen', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_fill_forms')
    def fill_form():
        try:
            data = request.get_json()
            record_id = data.get('record_id')
            template_id = data.get('template_id')
            form_data = data.get('data')
            
            if not record_id or not template_id or not form_data:
                return jsonify({'error': 'Akte, Vorlage und Daten sind erforderlich'}), 400
                
            result = formular_manager.speichere_ausgefuelltes_formular(record_id, template_id, form_data, session['user_id'])
            
            # Audit Log
            audit_logger.log_action(session['username'], "FORMULAR-AUSGEFÜLLT", f"Akte ID: {record_id}, Vorlage ID: {template_id}")
            
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': f'Formular konnte nicht gespeichert werden: {str(e)}'}), 500

    @formular_bp.route('/ausfuellen-pdf', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_fill_forms')
    def fill_form_pdf():
        try:
            if 'file' not in request.files:
                return jsonify({'error': 'Keine PDF-Datei empfangen'}), 400
            
            pdf_file = request.files['file']
            record_id = request.form.get('record_id')
            template_id = request.form.get('template_id')
            
            if not record_id or not pdf_file:
                return jsonify({'error': 'Akte ID und PDF sind erforderlich'}), 400
                
            # template_id validieren und umwandeln
            template_id_val = None
            if template_id and str(template_id).isdigit():
                template_id_val = int(template_id)
                
            result = formular_manager.speichere_pdf_anhang(record_id, pdf_file, session['user_id'], template_id_val)
            
            # Audit Log
            audit_logger.log_action(session['username'], "FORMULAR-PDF-GESPEICHERT", f"Akte ID: {record_id}, Template ID: {template_id}")
            
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': f'PDF konnte nicht gespeichert werden: {str(e)}'}), 500
