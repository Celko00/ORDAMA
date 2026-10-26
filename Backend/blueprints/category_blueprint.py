"""
Category Blueprint - Kategorien-Management
"""

import logging
from flask import Blueprint, request, jsonify, session

logger = logging.getLogger(__name__)

category_bp = Blueprint('category', __name__, url_prefix='/api/categories')

def init_category_blueprint(auth_manager, db_manager, audit_logger):
    """Initialisiert das Category Blueprint"""
    
    @category_bp.route('', methods=['GET'])
    @auth_manager.login_required
    def list_categories():
        try:
            # Benötigt db_manager Zugriff
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, color FROM categories ORDER BY name")
                categories = [dict(r) for r in cursor.fetchall()]
            return jsonify({'success': True, 'categories': categories})
        except Exception as e:
            return jsonify({'error': f'Kategorien konnten nicht geladen werden: {str(e)}'}), 500

    @category_bp.route('', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def create_category():
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            color = data.get('color', '')
            
            if not name:
                return jsonify({'error': 'Name ist erforderlich'}), 400
                
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO categories (name, color, created_by) VALUES (?, ?, ?)", 
                               (name, color, session['user_id']))
                cat_id = cursor.lastrowid
                conn.commit()
            
            # Audit Log
            audit_logger.log_action(session['username'], "KATEGORIE+", f"Kategorie erstellt: {name}")
            
            return jsonify({'success': True, 'category': {'id': cat_id, 'name': name, 'color': color}})
        except Exception as e:
            return jsonify({'error': f'Kategorie konnte nicht erstellt werden: {str(e)}'}), 500

    @category_bp.route('/<int:cat_id>', methods=['PUT'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def update_category(cat_id):
        try:
            data = request.get_json()
            name = data.get('name', '').strip()
            
            if not name:
                return jsonify({'error': 'Name ist erforderlich'}), 400
            
            # Altes Name holen fuer Log
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
                old_cat = cursor.fetchone()
                if not old_cat: return jsonify({'error': 'Nicht gefunden'}), 404
                
                cursor.execute("UPDATE categories SET name = ? WHERE id = ?", (name, cat_id))
                conn.commit()
            
            # Audit Log
            audit_logger.log_action(session['username'], "KATEGORIE~", f"Kategorie umbenannt: {old_cat['name']} -> {name}")
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': f'Update fehlgeschlagen: {str(e)}'}), 500

    @category_bp.route('/<int:cat_id>', methods=['DELETE'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def delete_category(cat_id):
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
                cat = cursor.fetchone()
                if not cat: return jsonify({'error': 'Nicht gefunden'}), 404
                
                cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
                conn.commit()
            
            # Audit Log
            audit_logger.log_action(session['username'], "KATEGORIE-", f"Kategorie gelöscht: {cat['name']}")
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': f'Löschen fehlgeschlagen: {str(e)}'}), 500

    @category_bp.route('/move', methods=['POST'])
    @auth_manager.login_required
    @auth_manager.require_permission('can_write')
    def move_records():
        try:
            if not auth_manager.check_permission('can_set_category'):
                return jsonify({'error': 'Keine Berechtigung zum Ändern von Kategorien'}), 403

            data = request.get_json()
            record_ids = data.get('record_ids', [])
            category_id = data.get('category_id') # Kann None sein
            
            if not record_ids:
                return jsonify({'error': 'Keine Akten ausgewählt'}), 400

            try:
                record_ids = [int(x) for x in record_ids]
            except (TypeError, ValueError):
                return jsonify({'error': 'Ungültige Akten-IDs'}), 400

            if len(record_ids) > 200:
                return jsonify({'error': 'Zu viele Akten auf einmal (max. 200)'}), 400

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ', '.join(['?'] * len(record_ids))
                cursor.execute(f"UPDATE records SET category_id = ? WHERE id IN ({placeholders})",
                               [category_id] + record_ids)
                count = cursor.rowcount
                conn.commit()
                # Cache invalidieren
                db_manager.invalidate_records_cache()
                db_manager.invalidate_cache('stats:')

            audit_logger.log_action(session['username'], "KATEGORIE-VERSCHIEBUNG", f"{count} Akten verschoben")
            
            return jsonify({'success': True, 'count': count})
        except Exception as e:
            return jsonify({'error': f'Akten konnten nicht verschoben werden: {str(e)}'}), 500