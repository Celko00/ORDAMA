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

Karten Blueprint - Akten auf Karte anzeigen
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

karte_bp = Blueprint('karte', __name__, url_prefix='/api/karte')


def init_karte_blueprint(auth_manager, db_manager, akten_manager):
    """
    Endpunkte:
    - POST /api/karte/punkte   { ids?: [int], limit?: int, offset?: int }
    """

    @karte_bp.route('/punkte', methods=['POST'])
    @auth_manager.login_required
    def punkte():
        try:
            data = request.get_json(silent=True) or {}
            ids = data.get('ids')

            try:
                limit = int(data.get('limit', 2000))
                offset = int(data.get('offset', 0))
            except (ValueError, TypeError):
                limit = 2000
                offset = 0
            limit = max(1, min(limit, 5000))
            offset = max(0, offset)

            where_ids = ""
            params = []
            if isinstance(ids, list) and ids:
                try:
                    ids = [int(x) for x in ids]
                except Exception:
                    return jsonify({'error': 'Ungueltige Akten-IDs'}), 400
                ids = list(dict.fromkeys(ids))
                if len(ids) > 5000:
                    return jsonify({'error': 'Zu viele Akten-IDs auf einmal'}), 400
                platzhalter = ",".join(["?"] * len(ids))
                where_ids = f" AND r.id IN ({platzhalter})"
                params.extend(ids)

            # ── Lazy-Aufbau der Koordinaten (für bestehende Datenbanken) ───────
            # Nicht alles auf einmal berechnen (Performance), sondern:
            # - Bei Auswahl: genau diese IDs aktualisieren
            # - Sonst: die neuesten Einträge ohne Koordinaten (limitierte Anzahl)
            try:
                with db_manager.get_connection() as conn:
                    cur = conn.cursor()
                    if isinstance(ids, list) and ids:
                        platzhalter2 = ",".join(["?"] * len(ids))
                        cur.execute(
                            f"""
                            SELECT r.id, r.content, r.address
                            FROM records r
                            LEFT JOIN record_koordinaten k ON k.record_id = r.id
                            WHERE r.archived = 0
                              AND r.id IN ({platzhalter2})
                              AND k.record_id IS NULL
                            """,
                            ids,
                        )
                    else:
                        cur.execute(
                            """
                            SELECT r.id, r.content, r.address
                            FROM records r
                            LEFT JOIN record_koordinaten k ON k.record_id = r.id
                            WHERE r.archived = 0
                              AND k.record_id IS NULL
                            ORDER BY r.updated_at DESC
                            LIMIT 300
                            """
                        )
                    fehlende = cur.fetchall()
            except Exception:
                fehlende = []

            for row in fehlende:
                try:
                    # Bevorzugt Adresse nutzen, sonst Inhalt
                    quelle = row['address'] if row['address'] else row['content']
                    akten_manager.aktualisiere_koordinaten(int(row['id']), quelle or "")
                except Exception:
                    pass

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT
                        r.id,
                        r.number,
                        r.title,
                        r.address,
                        r.hashtags,
                        r.border_color,
                        r.updated_at,
                        k.plz,
                        k.ort,
                        k.lat,
                        k.lon
                    FROM records r
                    JOIN record_koordinaten k ON k.record_id = r.id
                    WHERE r.archived = 0
                      AND k.lat IS NOT NULL
                      AND k.lon IS NOT NULL
                      {where_ids}
                    ORDER BY r.updated_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*params, limit, offset),
                )
                rows = cursor.fetchall()

                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM records r
                    JOIN record_koordinaten k ON k.record_id = r.id
                    WHERE r.archived = 0
                      AND k.lat IS NOT NULL
                      AND k.lon IS NOT NULL
                      {where_ids}
                    """,
                    params,
                )
                total = cursor.fetchone()['total']

            punkte_liste = []
            for row in rows:
                punkte_liste.append({
                    'id': row['id'],
                    'number': row['number'],
                    'title': row['title'],
                    'address': row['address'] or '',
                    'hashtags': row['hashtags'] or '',
                    'border_color': row['border_color'] or '',
                    'updated_at': row['updated_at'],
                    'plz': row['plz'] or '',
                    'ort': row['ort'] or '',
                    'lat': row['lat'],
                    'lon': row['lon'],
                })

            ref = akten_manager.karten_dienst.hole_referenzorte()

            return jsonify({
                'success': True,
                'punkte': punkte_liste,
                'referenzorte': ref,
                'pagination': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'has_more': (offset + limit) < total
                }
            })

        except Exception as e:
            logger.exception("Kartenpunkte fehlgeschlagen")
            return jsonify({'error': f'Kartenpunkte fehlgeschlagen: {str(e)}'}), 500

    return karte_bp
