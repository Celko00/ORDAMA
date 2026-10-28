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

Archivierungs-Modul für ORDAMA
Automatische Archivierung von Akten basierend auf Alter und letzter Nutzung
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class ArchiveManager:
    """Verwaltet die automatische Archivierung von Akten"""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

    def get_archive_config(self):
        """Gibt die Archivierungskonfiguration zurück"""
        return self.config.get('archive', {})

    def should_archive_record(self, record, archive_config):
        """
        Prüft, ob eine Akte archiviert werden sollte basierend auf:
        - Alter der Akte (created_at)
        - Letzter Nutzung (updated_at)
        - Kriterien-Logik (UND/ODER)
        """
        if not archive_config.get('auto_archive', False):
            return False

        # Alter berechnen
        created_at = datetime.fromisoformat(record['created_at'])
        updated_at = datetime.fromisoformat(record['updated_at'])
        now = datetime.now()

        # Maximales Alter berechnen
        age_days = archive_config.get('age_days', 0)
        age_months = archive_config.get('age_months', 0)
        age_years = archive_config.get('age_years', 0)

        max_age = timedelta(days=age_days) + timedelta(days=age_months * 30) + timedelta(days=age_years * 365)

        # Maximale Inaktivität berechnen
        unused_days = archive_config.get('unused_days', 0)
        unused_months = archive_config.get('unused_months', 0)
        unused_years = archive_config.get('unused_years', 0)

        max_unused = timedelta(days=unused_days) + timedelta(days=unused_months * 30) + timedelta(days=unused_years * 365)

        # Kriterien-Logik (UND oder ODER)
        logic = archive_config.get('logic', 'and')

        # Prüfen ob Akte alt genug ist
        age_met = True
        if max_age > timedelta(0):
            age = now - created_at
            age_met = age >= max_age

        # Prüfen ob Akte lange nicht genutzt wurde
        unused_met = True
        if max_unused > timedelta(0):
            unused = now - updated_at
            unused_met = unused >= max_unused

        # Wenn keine Kriterien gesetzt sind, nicht archivieren
        if max_age == timedelta(0) and max_unused == timedelta(0):
            return False

        # Logik anwenden
        if logic == 'or':
            # ODER: eines der Kriterien reicht
            return age_met or unused_met
        else:
            # UND (Standard): beide Kriterien müssen zutreffen
            return age_met and unused_met

    def get_records_to_archive(self, archive_config):
        """Gibt alle Akten zurück, die archiviert werden sollten"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Alle nicht-archivierten Akten abrufen
            cursor.execute('''
                SELECT id, number, title, created_at, updated_at, status
                FROM records
                WHERE archived = 0
                ORDER BY created_at ASC
            ''')

            records = cursor.fetchall()

            # Filtern basierend auf Archivierungskriterien
            records_to_archive = []
            for record in records:
                if self.should_archive_record(record, archive_config):
                    records_to_archive.append(record)

            return records_to_archive

    def archive_record(self, record_id, user_id=None):
        """
        Archiviert eine einzelne Akte
        Setzt das archived-Flag auf 1
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Akte archivieren
                cursor.execute('''
                    UPDATE records
                    SET archived = 1,
                        archived_at = ?,
                        archived_by = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), user_id, record_id))

                conn.commit()

                logger.info(f"Akte {record_id} wurde archiviert")
                return True

        except Exception as e:
            logger.error(f"Fehler beim Archivieren von Akte {record_id}: {e}")
            return False

    def archive_records(self, record_ids, user_id=None):
        """
        Archiviert mehrere Akten auf einmal
        """
        success_count = 0
        error_count = 0

        for record_id in record_ids:
            if self.archive_record(record_id, user_id):
                success_count += 1
            else:
                error_count += 1

        logger.info(f"Archivierung abgeschlossen: {success_count} erfolgreich, {error_count} fehlerhaft")
        return {
            'success': success_count,
            'errors': error_count,
            'total': len(record_ids)
        }

    def run_auto_archive(self):
        """
        Führt die automatische Archivierung basierend auf der Konfiguration durch
        """
        archive_config = self.get_archive_config()

        if not archive_config.get('auto_archive', False):
            logger.info("Automatische Archivierung ist deaktiviert")
            return {
                'success': 0,
                'errors': 0,
                'total': 0,
                'message': 'Automatische Archivierung ist deaktiviert'
            }

        # Prüfen ob Intervall erreicht ist
        last_run = archive_config.get('last_run', '')
        run_interval = archive_config.get('run_interval', 'daily')

        if last_run:
            last_run_date = datetime.fromisoformat(last_run)
            now = datetime.now()

            # Intervall berechnen
            if run_interval == 'daily':
                if (now - last_run_date).days < 1:
                    return {
                        'success': 0,
                        'errors': 0,
                        'total': 0,
                        'message': 'Archivierung wurde heute bereits ausgeführt'
                    }
            elif run_interval == 'weekly':
                if (now - last_run_date).days < 7:
                    return {
                        'success': 0,
                        'errors': 0,
                        'total': 0,
                        'message': 'Archivierung wurde diese Woche bereits ausgeführt'
                    }
            elif run_interval == 'monthly':
                if (now - last_run_date).days < 30:
                    return {
                        'success': 0,
                        'errors': 0,
                        'total': 0,
                        'message': 'Archivierung wurde diesen Monat bereits ausgeführt'
                    }
            elif run_interval == 'yearly':
                if (now - last_run_date).days < 365:
                    return {
                        'success': 0,
                        'errors': 0,
                        'total': 0,
                        'message': 'Archivierung wurde dieses Jahr bereits ausgeführt'
                    }

        # Akten zum Archivieren finden
        records_to_archive = self.get_records_to_archive(archive_config)

        if not records_to_archive:
            logger.info("Keine Akten zum Archivieren gefunden")
            return {
                'success': 0,
                'errors': 0,
                'total': 0,
                'message': 'Keine Akten zum Archivieren gefunden'
            }

        # Akten archivieren
        record_ids = [record['id'] for record in records_to_archive]
        result = self.archive_records(record_ids)

        # last_run aktualisieren
        self.update_last_run()

        result['message'] = f'{result["success"]} Akten erfolgreich archiviert'
        return result

    def update_last_run(self):
        """Aktualisiert den last_run Zeitstempel in der Konfiguration"""
        archive_config = self.get_archive_config()
        archive_config['last_run'] = datetime.now().isoformat()

        # Konfiguration speichern (muss über den Config-Manager geschehen)
        # Hier nur Logik, das Speichern passiert in app.py oder admin_blueprint
        logger.info(f"last_run aktualisiert: {archive_config['last_run']}")

    def get_archive_stats(self):
        """Gibt Statistiken über archivierte und nicht-archivierte Akten zurück"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Gesamtzahl der Akten
            cursor.execute('SELECT COUNT(*) FROM records')
            total = cursor.fetchone()[0]

            # Nicht-archivierte Akten
            cursor.execute('SELECT COUNT(*) FROM records WHERE archived = 0')
            active = cursor.fetchone()[0]

            # Archivierte Akten
            cursor.execute('SELECT COUNT(*) FROM records WHERE archived = 1')
            archived = cursor.fetchone()[0]

            return {
                'total': total,
                'active': active,
                'archived': archived
            }
