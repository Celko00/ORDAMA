"""
Aktenlogik-Modul für ORDAMA
"""

import os
import shutil
import re
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

from karten_logik import KartenDienst
from learning_system import LearningSystem
from search_logic import SearchLogic
from duplicate_detection import DuplicateDetector
from storage_manager import StorageManager
from plz_validator import PLZValidator

class AktenManager:
    def __init__(self, base_dir, config, db_manager):
        self.base_dir = Path(base_dir)
        self.config = config
        self.db_manager = db_manager
        self.ocr_manager = None
        self.learning_system = LearningSystem(db_manager)
        
        # Neue Module initialisieren
        self.search_logic = SearchLogic(db_manager)
        self.duplicate_detector = DuplicateDetector(db_manager)
        self.storage_manager = StorageManager(base_dir, config)
        self.plz_validator = PLZValidator(base_dir)
        
        # Pfad auflösen (absolut oder relativ zum base_dir)
        self.akten_dir = self.storage_manager.get_akten_dir()
            
        self.karten_dienst = KartenDienst(self.base_dir)

    def _calculate_storage_info(self):
        """Berechnet Speicherplatz-Informationen mit Caching"""
        return self.storage_manager.calculate_storage_info()

    def set_ocr_manager(self, ocr_manager):
        """Registriert den OCR-Manager nach der Initialisierung"""
        self.ocr_manager = ocr_manager

    def parse_search_query(self, search):
        """
        Parst Suchabfrage und erkennt UND/ODER-Operatoren
        Wortreihenfolge-unabhängig: Alle Wörter werden automatisch als AND behandeln
        """
        return self.search_logic.parse_search_query(search)

    def build_search_conditions(self, parsed_search, search_type, query_prefix=''):
        """
        Baut SQL-Suchbedingungen basierend auf geparster Suchabfrage
        Wortreihenfolge-unabhängig für alle Suchtypen
        """
        return self.search_logic.build_search_conditions(parsed_search, search_type, query_prefix)

    def matches_search_pattern(self, text, parsed_search):
        """
        Prüft, ob ein Text mit der geparsten Suchabfrage übereinstimmt
        Für Dateianhang-Suche
        """
        return self.search_logic.matches_search_pattern(text, parsed_search)

    def build_like_conditions_for_column(self, parsed_search, column_name):
        """Baut LIKE-Bedingungen für ein beliebiges Textfeld"""
        return self.search_logic.build_like_conditions_for_column(parsed_search, column_name)

    def get_ocr_matching_record_ids(self, parsed_search):
        """Findet OCR-Treffer für die globale Suche"""
        return self.search_logic.get_ocr_matching_record_ids(parsed_search)

    def get_ocr_match_details(self, parsed_search):
        """Liefert OCR-Treffer gruppiert nach Akte inklusive Dateiname und Textauszug"""
        return self.search_logic.get_ocr_match_details(parsed_search)
        
    def check_for_duplicates(self, title, content, address, user_id, hashtags=None, min_similarity=None):
        """Prüft auf ähnliche Akten (Dubletten) basierend auf Titel und Textinhalten (Inhalt/Adresse/Hashtags)"""
        return self.duplicate_detector.check_for_duplicates(title, content, address, user_id, hashtags, min_similarity)
    
    def check_plz_valid(self, address):
        """
        Prüft ob die Postleitzahl in der Adresse im System vorhanden ist
        
        Args:
            address: Die zu prüfende Adresse
            
        Returns:
            Tuple (is_valid, warning_message)
            - is_valid: True wenn PLZ gültig oder keine PLZ vorhanden
            - warning_message: None wenn gültig, sonst Warnmeldung für Benutzer
        """
        return self.plz_validator.pruefe_adresse(address)
    
    def create_akte(self, title, content, hashtags, user_id, border_color=None, reminder_date=None, reminder_end_date=None, reminder_repeat=None, status='offen', category_id=None, address=None, reminder_assigned_to=None):
        """Erstellt eine neue Akte mit Ordnerstruktur"""
        # Aktennummer generieren
        number = self.db_manager.get_next_record_number(user_id)
        
        try:
            # Username holen
            username = None
            with self.db_manager.get_connection() as conn_temp:
                cursor_temp = conn_temp.cursor()
                cursor_temp.execute("SELECT username FROM users WHERE id = ?", (user_id,))
                user_row = cursor_temp.fetchone()
                if user_row:
                    username = user_row['username']
            
            # Akte in Datenbank erstellen
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO records (number, title, content, address, hashtags, border_color, status, created_by, created_by_name, updated_by, updated_by_name, reminder_date, reminder_end_date, reminder_repeat, category_id, reminder_assigned_to)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (number, title, content, address, hashtags, border_color, status, user_id, username, user_id, username, reminder_date, reminder_end_date, reminder_repeat, category_id, reminder_assigned_to))
                
                record_id = cursor.lastrowid
                conn.commit()

            # Cache invalidieren
            self.db_manager.invalidate_records_cache()
            self.db_manager.invalidate_cache('stats:')  # Statistiken invalidieren

            # Koordinaten (bevorzugt aus Adressfeld, sonst aus Inhalt)
            self.aktualisiere_koordinaten(record_id, address if address else content)
            
            # Ordnerstruktur erstellen: Akten/Aktennummer/
            akte_dir = self.akten_dir / number
            akte_dir.mkdir(parents=True, exist_ok=True)
            
            return {
                'id': record_id,
                'number': number,
                'title': title,
                'content': content,
                'hashtags': hashtags,
                'category_id': category_id,
                'created_by': user_id,
                'created_by_name': username,
                'attachments': [],
                'locked': False
            }
            
        except Exception as e:
            # Bei Fehler: Ordner löschen falls erstellt
            akte_dir = self.akten_dir / number
            if akte_dir.exists():
                shutil.rmtree(str(akte_dir))
            raise e
    
    def update_akte(self, record_id, title, content, hashtags, user_id, border_color=None, reminder_date=None, reminder_end_date=None, reminder_repeat=None, status=None, category_id=None, address=None, reminder_assigned_to=None):
        """Aktualisiert eine bestehende Akte"""
        try:
            # Username holen
            username = None
            with self.db_manager.get_connection() as conn_temp:
                cursor_temp = conn_temp.cursor()
                cursor_temp.execute("SELECT username FROM users WHERE id = ?", (user_id,))
                user_row = cursor_temp.fetchone()
                if user_row:
                    username = user_row['username']
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE records 
                    SET title = ?, content = ?, address = ?, hashtags = ?, border_color = ?, 
                        status = COALESCE(?, status),
                        category_id = ?,
                        updated_by = ?, updated_by_name = ?, updated_at = CURRENT_TIMESTAMP, 
                        reminder_date = ?, reminder_end_date = ?, reminder_repeat = ?, reminder_assigned_to = ?
                    WHERE id = ?
                ''', (title, content, address, hashtags, border_color, status, category_id, user_id, username, reminder_date, reminder_end_date, reminder_repeat, reminder_assigned_to, record_id))
                conn.commit()

            # Cache invalidieren
            self.db_manager.invalidate_records_cache()
            self.db_manager.invalidate_cache('stats:')  # Statistiken invalidieren

            # Koordinaten (bevorzugt aus Adressfeld, sonst aus Inhalt)
            self.aktualisiere_koordinaten(record_id, address if address else content)
            return True
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Akte: {e}")
            raise e

    def aktualisiere_koordinaten(self, record_id, content):
        """
        Extrahiert PLZ/Ort aus der Akte und schreibt/aktualisiert record_koordinaten.
        Wenn keine PLZ gefunden wird, wird ein evtl. vorhandener Eintrag entfernt.
        """
        try:
            extrakt = self.karten_dienst.extrahiere_plz_ort(content or "")
            if not extrakt:
                with self.db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM record_koordinaten WHERE record_id = ?", (record_id,))
                    conn.commit()
                return

            plz, ort = extrakt
            coords = self.karten_dienst.finde_koordinaten(plz, ort)
            if not coords:
                # PLZ vorhanden, aber keine Koordinaten → Eintrag entfernen (damit Karte nur valide Punkte zeigt)
                with self.db_manager.get_connection() as conn:
                    conn.execute("DELETE FROM record_koordinaten WHERE record_id = ?", (record_id,))
                    conn.commit()
                return

            lat, lon = coords
            with self.db_manager.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO record_koordinaten (record_id, plz, ort, lat, lon, aktualisiert_am)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) DO UPDATE SET
                        plz=excluded.plz,
                        ort=excluded.ort,
                        lat=excluded.lat,
                        lon=excluded.lon,
                        aktualisiert_am=excluded.aktualisiert_am
                    """,
                    (record_id, plz, ort, float(lat), float(lon), datetime.now().isoformat()),
                )
                conn.commit()
        except Exception as e:
            # Nicht hart fehlschlagen lassen – Akte soll trotzdem speicherbar sein
            logger.warning(f"Koordinaten konnten nicht aktualisiert werden (record_id={record_id}): {e}")
    
    def delete_akte(self, record_id, user_id):
        """Löscht eine Akte (archiviert) und den Ordner"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT number FROM records WHERE id = ? AND archived = 0", (record_id,))
            record = cursor.fetchone()
            
            if not record:
                raise ValueError("Akte nicht gefunden")
            
            aktenzeichen = record['number']
            
            # Zuerst abhängige Datensätze löschen (FOREIGN KEY Constraints)
            # Reminders löschen
            cursor.execute("DELETE FROM reminders WHERE record_id = ?", (record_id,))
            # Attachments löschen (OCR wird durch CASCADE gelöscht)
            cursor.execute("DELETE FROM attachments WHERE record_id = ?", (record_id,))
            # Record Locks löschen
            cursor.execute("DELETE FROM record_locks WHERE record_id = ?", (record_id,))
            # Koordinaten löschen
            cursor.execute("DELETE FROM record_koordinaten WHERE record_id = ?", (record_id,))
            
            # Akte vollständig löschen (nicht archivieren) für Nummern-Wiederverwendung
            cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
            
            # Nummer aus used_numbers entfernen, damit sie wiederverwendet werden kann
            cursor.execute("DELETE FROM used_numbers WHERE number = ?", (int(aktenzeichen),))
            
            conn.commit()
        
        # Cache invalidieren
        self.db_manager.invalidate_records_cache()
        
        # Ordner löschen
        akte_dir = self.akten_dir / aktenzeichen
        if akte_dir.exists():
            shutil.rmtree(str(akte_dir))
        
        return aktenzeichen

    def loesche_akten_mehrere(self, record_ids, user_id):
        """
        Löscht mehrere Akten in einem Durchlauf (für Performance).
        - DB-Löschung erfolgt in EINER Transaktion.
        - Ordner im Dateisystem werden nach Commit entfernt.
        """
        if not record_ids:
            return {'aktenzeichen': [], 'dateisystem_fehler': []}

        # Deduplizieren (Reihenfolge beibehalten)
        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            cursor.execute(
                f"SELECT id, number FROM records WHERE id IN ({platzhalter})",
                eindeutige_ids
            )
            rows = cursor.fetchall()

            if len(rows) != len(eindeutige_ids):
                raise ValueError("Eine oder mehrere Akten wurden nicht gefunden")

            aktenzeichen_liste = [row['number'] for row in rows]

            # Abhängige Datensätze löschen
            cursor.execute(f"DELETE FROM reminders WHERE record_id IN ({platzhalter})", eindeutige_ids)
            cursor.execute(f"DELETE FROM attachments WHERE record_id IN ({platzhalter})", eindeutige_ids)
            cursor.execute(f"DELETE FROM record_locks WHERE record_id IN ({platzhalter})", eindeutige_ids)
            cursor.execute(f"DELETE FROM record_koordinaten WHERE record_id IN ({platzhalter})", eindeutige_ids)

            # Akten selbst löschen
            cursor.execute(f"DELETE FROM records WHERE id IN ({platzhalter})", eindeutige_ids)

            # Nummern aus used_numbers entfernen, damit sie wiederverwendet werden können
            platzhalter_nummern = ','.join(['?'] * len(aktenzeichen_liste))
            # Konvertiere zu Integer für used_numbers Tabelle
            aktenzeichen_int = [int(az) for az in aktenzeichen_liste]
            cursor.execute(
                f"DELETE FROM used_numbers WHERE number IN ({platzhalter_nummern})",
                aktenzeichen_int
            )

            conn.commit()

        # Cache invalidieren
        self.db_manager.invalidate_records_cache()
        self.db_manager.invalidate_cache('stats:')

        # Dateisystem: Aktenordner entfernen (nach Commit)
        dateisystem_fehler = []
        for aktenzeichen in aktenzeichen_liste:
            akte_dir = self.akten_dir / aktenzeichen
            if akte_dir.exists():
                try:
                    shutil.rmtree(str(akte_dir))
                except Exception as e:
                    logger.error(f"Aktenordner konnte nicht gelöscht werden ({aktenzeichen}): {e}")
                    dateisystem_fehler.append({'aktenzeichen': aktenzeichen, 'fehler': str(e)})

        return {'aktenzeichen': aktenzeichen_liste, 'dateisystem_fehler': dateisystem_fehler}
    
    def update_status_mehrere(self, record_ids, new_status, user_id):
        """
        Aktualisiert den Status mehrerer Akten in einem Durchlauf.
        """
        if not record_ids:
            return 0
            
        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            
            cursor.execute(
                f"UPDATE records SET status = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({platzhalter}) AND archived = 0",
                [new_status, user_id] + eindeutige_ids
            )
            conn.commit()
            # Cache invalidieren
            self.db_manager.invalidate_records_cache()
            self.db_manager.invalidate_cache('stats:')
            return cursor.rowcount

    def get_dashboard_stats(self, is_admin=False):
        """
        Liefert erweiterte Statistiken für das Dashboard:
        - Basis-Counts (Gesamt, Angepinnt, Anhänge)
        - Admin-Counts (Benutzer)
        - Status-Verteilung
        - Kategorie-Verteilung
        - Erstellungs-Trend (letzte 12 Monate)
        - Speicherplatz-Informationen
        """
        # Cache-Check für Statistiken (5 Minuten TTL)
        cache_key = f"stats:dashboard:{is_admin}"
        cached_stats = self.db_manager.cache.get(cache_key)
        if cached_stats:
            return cached_stats
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Basis-Statistiken
            cursor.execute("SELECT COUNT(*) FROM records WHERE archived = 0")
            total_records = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM records WHERE archived = 1")
            archived_records = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM attachments")
            total_attachments = cursor.fetchone()[0]
            
            res = {
                'totalRecords': total_records,
                'archivedRecords': archived_records,
                'totalAttachments': total_attachments
            }
            
            if is_admin:
                cursor.execute("SELECT COUNT(*) FROM users")
                res['totalUsers'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
                res['adminUsers'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM categories")
                res['totalCategories'] = cursor.fetchone()[0]
            
            # 2. Status-Verteilung (optimiert mit Index)
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM records 
                WHERE archived = 0 
                GROUP BY status
            """)
            status_dist = {row['status']: row['count'] for row in cursor.fetchall()}
            res['status_distribution'] = status_dist
            
            # 3. Kategorie-Verteilung (optimiert mit Index)
            cursor.execute("""
                SELECT c.name, COUNT(r.id) as count
                FROM categories c
                LEFT JOIN records r ON r.category_id = c.id AND r.archived = 0
                GROUP BY c.id, c.name
                ORDER BY count DESC
            """)
            cat_dist = {row['name']: row['count'] for row in cursor.fetchall()}
            res['category_distribution'] = cat_dist
            
            # 4. Farb-Verteilung
            cursor.execute("""
                SELECT border_color, COUNT(*) as count
                FROM records
                WHERE archived = 0
                GROUP BY border_color
            """)
            color_dist = {row['border_color'] or '': row['count'] for row in cursor.fetchall()}
            res['color_distribution'] = color_dist
            
            # 5. Anhang-Typen (PDF vs Bilder vs Rest) – aggregiert in SQL
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN lower(filename) LIKE '%.pdf' THEN 1 ELSE 0 END) as pdf,
                    SUM(CASE WHEN lower(filename) LIKE '%.jpg'
                              OR lower(filename) LIKE '%.jpeg'
                              OR lower(filename) LIKE '%.png'
                              OR lower(filename) LIKE '%.gif'
                              OR lower(filename) LIKE '%.webp' THEN 1 ELSE 0 END) as image,
                    COUNT(*) as total
                FROM attachments
            """)
            att_row = cursor.fetchone()
            pdf_count = att_row['pdf'] or 0
            image_count = att_row['image'] or 0
            total_att = att_row['total'] or 0
            res['attachment_types'] = {
                'pdf': pdf_count,
                'image': image_count,
                'other': max(0, total_att - pdf_count - image_count)
            }
            
            # 6. Erstellungs-Trend (letzte 12 Monate)
            cursor.execute("""
                SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
                FROM records
                WHERE archived = 0
                AND created_at >= date('now', '-12 months')
                GROUP BY month
                ORDER BY month ASC
            """)
            trend_data = {row['month']: row['count'] for row in cursor.fetchall()}
            
            labels = []
            values = []
            for i in range(11, -1, -1):
                month_date = datetime.now() - timedelta(days=i*30)
                month_key = month_date.strftime('%Y-%m')
                labels.append(month_date.strftime('%m/%y'))
                values.append(trend_data.get(month_key, 0))

            res['creation_trend'] = {
                'labels': labels,
                'values': values
            }

            # 7. Archivierungs-Trend (letzte 12 Monate)
            cursor.execute("""
                SELECT strftime('%Y-%m', am.archived_at) as month, COUNT(*) as count
                FROM archive_metadata am
                WHERE am.archived_at IS NOT NULL
                AND am.archived_at >= date('now', '-12 months')
                GROUP BY month
                ORDER BY month ASC
            """)
            archive_trend_data = {row['month']: row['count'] for row in cursor.fetchall()}
            
            archive_labels = []
            archive_values = []
            for i in range(11, -1, -1):
                month_date = datetime.now() - timedelta(days=i*30)
                month_key = month_date.strftime('%Y-%m')
                archive_labels.append(month_date.strftime('%m/%y'))
                archive_values.append(archive_trend_data.get(month_key, 0))

            res['archive_trend'] = {
                'labels': archive_labels,
                'values': archive_values
            }

            # 8. Speicherplatz-Informationen (mit Caching)
            res['storage'] = self._calculate_storage_info()
            
            # Statistiken cachen (5 Minuten TTL)
            self.db_manager.cache.set(cache_key, res, ttl=300)
            
            return res

    def get_kalender_statistik(self, year=None):
        """
        Berechnet die Anzahl der Termine pro Monat für ein Jahr.
        Optimiert: Die Berechnung erfolgt direkt in der Datenbank.
        """
        if not year:
            year = datetime.now().year
            
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Einmalige Termine zählen
            cursor.execute("""
                SELECT strftime('%m', reminder_date) as month, COUNT(*) as count
                FROM records 
                WHERE reminder_date IS NOT NULL 
                AND strftime('%Y', reminder_date) = ?
                AND (reminder_repeat IS NULL OR reminder_repeat = '')
                GROUP BY month
            """, (str(year),))
            once_results = {row['month']: row['count'] for row in cursor.fetchall()}
            
            # Monatliche/Wiederkehrende Termine sind komplexer in SQL (SQLite), 
            # daher rufen wir hier nur die Datensätze ab die Wiederholungen haben 
            # und verarbeiten sie kurz im Python (da es meist viel weniger sind).
            cursor.execute("""
                SELECT reminder_date, reminder_repeat
                FROM records 
                WHERE reminder_date IS NOT NULL 
                AND reminder_repeat IS NOT NULL AND reminder_repeat != ''
            """)
            repeat_records = cursor.fetchall()
            
        # Ergebnisse zusammenführen
        month_counts = [0] * 12
        
        # Einmalige hinzufügen
        for m_str, count in once_results.items():
            month_counts[int(m_str) - 1] += count
            
        # Wiederkehrende hinzufügen
        for record in repeat_records:
            try:
                # Vereinfachte Logik für Wiederholungen im Backend
                # (Entspricht der Logik im Frontend, aber effizienter da weniger Daten übertragen werden)
                start_date = datetime.strptime(record['reminder_date'][:10], '%Y-%m-%d')
                repeat = record['reminder_repeat']
                
                for m in range(12):
                    # Letzter Tag des Monats
                    if m == 11:
                        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
                    else:
                        last_day = datetime(year, m + 2, 1) - timedelta(days=1)
                    
                    if repeat == 'daily':
                        # Jeden Tag im Monat (wenn gestartet)
                        first_day_of_month = datetime(year, m + 1, 1)
                        if start_date <= last_day:
                            days_in_month = last_day.day
                            if start_date > first_day_of_month:
                                days_in_month -= (start_date - first_day_of_month).days
                            month_counts[m] += max(0, days_in_month)
                    elif repeat == 'weekly':
                        # Einmal pro Woche
                        # Hier vereinfacht: ca 4.3 Wochen pro Monat
                        if start_date <= last_day:
                            month_counts[m] += 4
                    elif repeat == 'monthly':
                        # Einmal pro Monat
                        if start_date <= last_day:
                            month_counts[m] += 1
                    elif repeat == 'yearly':
                        # Einmal pro Jahr
                        if start_date.month == (m + 1) and start_date.year <= year:
                            month_counts[m] += 1
            except (ValueError, TypeError, AttributeError):
                continue
                
        return month_counts

    def update_farbe_mehrere(self, record_ids, new_color, user_id):
        """
        Aktualisiert die Rahmenfarbe mehrerer Akten in einem Durchlauf.
        Die Neusortierung (updated_at) wird hier bewusst ausgelassen.
        """
        if not record_ids:
            return 0
            
        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))

            cursor.execute(
                f"UPDATE records SET border_color = ?, updated_by = ? WHERE id IN ({platzhalter}) AND archived = 0",
                [new_color, user_id] + eindeutige_ids
            )
            count = cursor.rowcount
            conn.commit()
            # Cache invalidieren
            self.db_manager.invalidate_records_cache()
            self.db_manager.invalidate_cache('stats:')
            logger.info(f"Farbe aktualisiert: {count} Akten, neue Farbe: {new_color}, IDs: {eindeutige_ids}")
            return count

    def update_termin_mehrere(self, record_ids, reminder_date, reminder_end_date, reminder_repeat, reminder_assigned_to, user_id):
        """
        Aktualisiert den Termin mehrerer Akten in einem Durchlauf.
        """
        if not record_ids:
            return 0
            
        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            
            cursor.execute(
                f"UPDATE records SET reminder_date = ?, reminder_end_date = ?, reminder_repeat = ?, reminder_assigned_to = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({platzhalter}) AND archived = 0",
                [reminder_date, reminder_end_date, reminder_repeat, reminder_assigned_to, user_id] + eindeutige_ids
            )
            count = cursor.rowcount
            conn.commit()
            # Cache invalidieren
            self.db_manager.invalidate_records_cache()
            self.db_manager.invalidate_cache('stats:')
            return count

    def update_note_mehrere(self, record_ids, new_note, user_id):
        """
        Aktualisiert den Vermerk (hashtags) mehrerer Akten in einem Durchlauf.
        """
        if not record_ids:
            return 0
            
        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            
            cursor.execute(
                f"UPDATE records SET hashtags = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({platzhalter}) AND archived = 0",
                [new_note, user_id] + eindeutige_ids
            )
            count = cursor.rowcount
            conn.commit()
            # Cache invalidieren
            self.db_manager.invalidate_records_cache()
            self.db_manager.invalidate_cache('stats:')

            # FTS5-Tabelle aktualisieren
            for record_id in eindeutige_ids:
                cursor.execute('DELETE FROM records_fts WHERE rowid = ?', (record_id,))
                cursor.execute('''
                    INSERT INTO records_fts(rowid, id, title, content, address, hashtags)
                    SELECT id, id, COALESCE(title, ''), COALESCE(content, ''), COALESCE(address, ''), COALESCE(hashtags, '')
                    FROM records WHERE id = ?
                ''', (record_id,))
            
            conn.commit()
            
            # Cache invalidieren
            self.db_manager.cache.clear()
            
            return count

    def _can_view_private_reminder(self, record_dict, viewer_user_id=None, is_admin=False):
        assigned_to = record_dict.get('reminder_assigned_to')
        if not assigned_to:
            return True
        if is_admin:
            return True
        return viewer_user_id is not None and int(assigned_to) == int(viewer_user_id)

    def _apply_reminder_visibility(self, record_dict, viewer_user_id=None, is_admin=False):
        can_view = self._can_view_private_reminder(record_dict, viewer_user_id, is_admin)
        record_dict['reminder_is_private'] = bool(record_dict.get('reminder_assigned_to'))
        record_dict['reminder_hidden'] = not can_view and bool(record_dict.get('reminder_assigned_to'))

        if not can_view:
            record_dict['reminder_date'] = None
            record_dict['reminder_end_date'] = None
            record_dict['reminder_repeat'] = None
            record_dict['reminder_assigned_to'] = None

        return record_dict

    # ── Kategorien (Ablage) ─────────────────────────
    
    def list_categories(self, user_id=None):
        """Listet alle Kategorien auf"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM categories ORDER BY name ASC"
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def create_category(self, name, color, user_id):
        """Erstellt eine neue Kategorie"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO categories (name, color, created_by) VALUES (?, ?, ?)",
                (name, color, user_id)
            )
            cat_id = cursor.lastrowid
            conn.commit()
            return {'id': cat_id, 'name': name, 'color': color}

    def update_category(self, cat_id, name, color):
        """Aktualisiert eine Kategorie"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE categories SET name = ?, color = ? WHERE id = ?",
                (name, color, cat_id)
            )
            conn.commit()
            return True

    def delete_category(self, cat_id):
        """Löscht eine Kategorie und entfernt sie von allen Akten"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # Aktenverknüpfung auf NULL setzen
            cursor.execute("UPDATE records SET category_id = NULL WHERE category_id = ?", (cat_id,))
            cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            conn.commit()
            return True

    def verschiebe_akten_in_kategorie(self, record_ids, category_id, user_id):
        """Verschiebt mehrere Akten in eine Kategorie"""
        if not record_ids:
            return 0
        
        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            
            cursor.execute(
                f"UPDATE records SET category_id = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({platzhalter}) AND archived = 0",
                [category_id, user_id] + eindeutige_ids
            )
            conn.commit()
            return cursor.rowcount

    def get_akte(self, record_id, viewer_user_id=None, is_admin=False):
        """Holt eine spezifische Akte"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT r.*, COALESCE(r.created_by_name, u.username) as created_by_name,
                       l.user_id as locked_by, l.expires_at as lock_expires
                FROM records r
                LEFT JOIN users u ON r.created_by = u.id
                LEFT JOIN record_locks l ON r.id = l.record_id AND l.expires_at > datetime('now')
                WHERE r.id = ? AND r.archived = 0
            ''', (record_id,))
            
            record = cursor.fetchone()
            if record:
                record_dict = dict(record)
                record_dict['attachments'] = self.get_attachments(record['id'])
                record_dict['locked'] = record['locked_by'] is not None
                return self._apply_reminder_visibility(record_dict, viewer_user_id, is_admin)
            return None
    
    def list_akten(self, search='', filter_type='all', search_type='all', limit=50, offset=0, category_id=None, border_color=None, viewer_user_id=None, is_admin=False):
        """Listet Akten mit Filteroptionen und erweiterter Suche - mit Pagination für Performance"""
        # Cache-Check für einfache Abfragen ohne Suche
        cache_key = f"records:{filter_type}:{category_id}:{border_color}:{viewer_user_id}:{is_admin}:{limit}:{offset}"
        if not search:
            cached_result = self.db_manager.cache.get(cache_key)
            if cached_result:
                return cached_result
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Suchabfrage parsen
            parsed_search = self.parse_search_query(search)
            ocr_match_ids = self.get_ocr_matching_record_ids(parsed_search) if (search and search_type == 'ocr') else set()
            ocr_match_details = self.get_ocr_match_details(parsed_search) if (search and search_type == 'ocr') else {}

            # Bei Anhänge- oder OCR-Suche: Alle Akten laden und erst im Python-Code filtern
            # weil Anhänge im Dateisystem liegen, nicht in der Datenbank
            if search and search_type in ['attachments', 'ocr']:
                # Alle Filter-Bedingungen sammeln
                filter_conds = []
                filter_params = []
                
                if category_id is not None:
                    filter_conds.append('r.category_id = ?')
                    filter_params.append(category_id)
                
                if border_color is not None:
                    if border_color == '':
                        filter_conds.append('(r.border_color IS NULL OR r.border_color = "")')
                    else:
                        filter_conds.append('r.border_color = ?')
                        filter_params.append(border_color)
                
                if filter_type != 'all':
                    if filter_type == 'status_offen': filter_conds.append('r.status = "offen"')
                    elif filter_type == 'status_neutral': filter_conds.append('r.status = "neutral"')
                    elif filter_type == 'status_erledigt': filter_conds.append('r.status = "erledigt"')
                    elif filter_type == 'status_bearbeitung': filter_conds.append('r.status = "bearbeitung"')
                    elif filter_type == 'recent': filter_conds.append('r.created_at >= datetime("now", "-7 days")')
                    elif filter_type == 'recent30': filter_conds.append('r.created_at >= datetime("now", "-30 days")')
                    elif filter_type == 'recent365': filter_conds.append('r.created_at >= datetime("now", "-365 days")')
                    elif filter_type == 'has_termine': filter_conds.append('r.reminder_date IS NOT NULL')
                    elif filter_type == 'has_my_termine': 
                        if is_admin:
                            filter_conds.append('r.reminder_date IS NOT NULL')
                        else:
                            filter_conds.append('(r.reminder_date IS NOT NULL AND (r.reminder_assigned_to IS NULL OR r.reminder_assigned_to = ?))')
                            filter_params.append(viewer_user_id)
                    elif filter_type == 'expired_termine': filter_conds.append('r.reminder_date < date("now")')
                    elif filter_type == 'has_reminders': filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0)')
                    elif filter_type == 'has_my_reminders':
                        if is_admin:
                            filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0)')
                        else:
                            filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0 AND assigned_to = ?)')
                            filter_params.append(viewer_user_id)
                    elif filter_type == 'expired_erinnerungen': filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0 AND reminder_date < date("now"))')

                if filter_conds:
                    where_clause = f"WHERE r.archived = 0 AND ({' AND '.join(filter_conds)})"
                else:
                    where_clause = "WHERE r.archived = 0"

                # Hauptabfrage
                query = f'''
                    SELECT r.*, COALESCE(r.created_by_name, u.username) as created_by_name,
                           l.user_id as locked_by, l.expires_at as lock_expires
                    FROM records r
                    LEFT JOIN users u ON r.created_by = u.id
                    LEFT JOIN record_locks l ON r.id = l.record_id AND l.expires_at > datetime('now')
                    {where_clause}
                    ORDER BY r.updated_at DESC
                '''
                cursor.execute(query, filter_params)
                records = cursor.fetchall()
            else:
                # Normale Suche: Suchfilter in SQL anwenden
                filter_conds = []
                filter_params = []
                
                if category_id is not None:
                    filter_conds.append('r.category_id = ?')
                    filter_params.append(category_id)
                
                if border_color is not None:
                    if border_color == '':
                        filter_conds.append('(r.border_color IS NULL OR r.border_color = "")')
                    else:
                        filter_conds.append('r.border_color = ?')
                        filter_params.append(border_color)

                if search and parsed_search:
                    search_condition, search_params = self.build_search_conditions(parsed_search, search_type, 'r.')
                    filter_conds.append(search_condition)
                    filter_params.extend(search_params)

                if filter_type != 'all':
                    if filter_type == 'status_offen': filter_conds.append('r.status = "offen"')
                    elif filter_type == 'status_neutral': filter_conds.append('r.status = "neutral"')
                    elif filter_type == 'status_erledigt': filter_conds.append('r.status = "erledigt"')
                    elif filter_type == 'status_bearbeitung': filter_conds.append('r.status = "bearbeitung"')
                    elif filter_type == 'recent': filter_conds.append('r.created_at >= datetime("now", "-7 days")')
                    elif filter_type == 'recent30': filter_conds.append('r.created_at >= datetime("now", "-30 days")')
                    elif filter_type == 'recent365': filter_conds.append('r.created_at >= datetime("now", "-365 days")')
                    elif filter_type == 'has_termine': filter_conds.append('r.reminder_date IS NOT NULL')
                    elif filter_type == 'has_my_termine': 
                        if is_admin:
                            filter_conds.append('r.reminder_date IS NOT NULL')
                        else:
                            filter_conds.append('(r.reminder_date IS NOT NULL AND (r.reminder_assigned_to IS NULL OR r.reminder_assigned_to = ?))')
                            filter_params.append(viewer_user_id)
                    elif filter_type == 'expired_termine': filter_conds.append('r.reminder_date < date("now")')
                    elif filter_type == 'has_reminders': filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0)')
                    elif filter_type == 'has_my_reminders':
                        if is_admin:
                            filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0)')
                        else:
                            filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0 AND assigned_to = ?)')
                            filter_params.append(viewer_user_id)
                    elif filter_type == 'expired_erinnerungen': filter_conds.append('EXISTS (SELECT 1 FROM reminders WHERE record_id = r.id AND completed = 0 AND reminder_date < date("now"))')

                if filter_conds:
                    where_clause = f"WHERE r.archived = 0 AND ({' AND '.join(filter_conds)})"
                else:
                    where_clause = "WHERE r.archived = 0"

                # Gesamtanzahl ermitteln
                count_query = f"SELECT COUNT(*) as total FROM records r {where_clause}"
                cursor.execute(count_query, filter_params)
                total_count = cursor.fetchone()['total']

                # Hauptabfrage mit Attachment-Count (Performance-Optimierung: N+1 Query Problem behoben)
                query = f'''
                    SELECT r.*, COALESCE(r.created_by_name, u.username) as created_by_name,
                           l.user_id as locked_by, l.expires_at as lock_expires,
                           COALESCE(ac.count, 0) as attachment_count
                    FROM records r
                    LEFT JOIN users u ON r.created_by = u.id
                    LEFT JOIN record_locks l ON r.id = l.record_id AND l.expires_at > datetime('now')
                    LEFT JOIN (SELECT record_id, COUNT(*) as count FROM attachments GROUP BY record_id) ac ON r.id = ac.record_id
                    {where_clause}
                    ORDER BY r.updated_at DESC LIMIT ? OFFSET ?
                '''
                params = filter_params + [limit, offset]
                cursor.execute(query, params)
                records = cursor.fetchall()
            
            # Anhänge zählen (Performance-Optimierung: attachment_count bereits in Hauptquery enthalten)
            result = []
            for record in records:
                record_dict = dict(record)

                # Zusätzliche Filterung für Dateianhang-Suche (falls nötig)
                # Bei 'attachments' Dateinamen/lesbare Textdateien durchsuchen,
                # bei 'ocr' nur OCR-Treffer berücksichtigen
                # Performance-Optimierung: Nur Anhänge laden wenn wirklich benötigt für Suche
                if search and search_type in ['attachments', 'ocr'] and parsed_search:
                    matched_attachments = []

                    if search_type == 'ocr':
                        if record['id'] not in ocr_match_ids:
                            continue
                        matched_attachments = list(ocr_match_details.get(record['id'], []))
                        attachments = self.get_attachments(record['id'])
                        record_dict['attachment_count'] = len(attachments)
                        if not matched_attachments:
                            continue
                        record_dict['search_matches'] = matched_attachments
                    else:
                        attachment_matches = False
                        attachments = self.get_attachments(record['id'])
                        record_dict['attachment_count'] = len(attachments)

                        for attachment in attachments:
                            # Suche im Dateinamen mit erweiterter Suche
                            if self.matches_search_pattern(attachment['filename'], parsed_search):
                                attachment_matches = True
                                if not any(m['filename'] == attachment['filename'] for m in matched_attachments):
                                    matched_attachments.append({
                                        'type': 'filename',
                                        'filename': attachment['filename'],
                                        'snippet': 'Treffer im Dateinamen'
                                    })
                                continue

                            # Suche im Dateiinhalt (für Textdateien)
                            try:
                                attachment_path = self.akten_dir / record['number'] / attachment['filename']
                                if attachment_path.exists():
                                    text_extensions = ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.log', '.rtf', '.tex']
                                    if any(attachment_path.suffix.lower() == ext for ext in text_extensions):
                                        try:
                                            with open(attachment_path, 'r', encoding='utf-8', errors='ignore') as f:
                                                content = f.read()
                                                if self.matches_search_pattern(content, parsed_search):
                                                    attachment_matches = True
                                                    if not any(m['filename'] == attachment['filename'] for m in matched_attachments):
                                                        matched_attachments.append({
                                                            'type': 'text',
                                                            'filename': attachment['filename'],
                                                            'snippet': self._build_search_excerpt(content, parsed_search)
                                                        })
                                        except Exception:
                                            continue
                            except Exception:
                                continue

                        if not attachment_matches:
                            continue
                        if matched_attachments:
                            record_dict['search_matches'] = matched_attachments

                    # Bei 'attachments' muss ein Anhang übereinstimmen
                    if search_type == 'attachments' and not matched_attachments:
                        continue

                record_dict['locked'] = record['locked_by'] is not None
                record_dict = self._apply_reminder_visibility(record_dict, viewer_user_id, is_admin)
                result.append(record_dict)

            if search and search_type in ['attachments', 'ocr']:
                total_count = len(result)
                result = result[offset:offset + limit]
            
            # Pagination-Info zurückgeben
            result_data = {
                'records': result,
                'pagination': {
                    'total': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_more': offset + limit < total_count
                }
            }
            
            # Cache für einfache Abfragen ohne Suche
            if not search:
                self.db_manager.cache.set(cache_key, result_data, ttl=60)  # 1 Minute Cache
            
            return result_data
    
    def get_attachments(self, record_id_or_number):
        """Lädt Anhänge aus der Datenbank, sortiert nach order_index"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Falls eine Nummer (String) übergeben wurde, erst ID holen
                if isinstance(record_id_or_number, str):
                    cursor.execute("SELECT id FROM records WHERE number = ?", (record_id_or_number,))
                    row = cursor.fetchone()
                    if not row:
                        return []
                    record_id = row['id']
                else:
                    record_id = record_id_or_number

                cursor.execute('''
                    SELECT
                        a.id,
                        a.filename,
                        a.file_size as size,
                        a.uploaded_at as modified,
                        a.order_index,
                        o.status as ocr_status,
                        o.progress as ocr_progress,
                        o.pages_done as ocr_pages_done,
                        o.pages_total as ocr_pages_total,
                        o.has_text as ocr_has_text,
                        o.error_message as ocr_error_message
                    FROM attachments a
                    LEFT JOIN attachment_ocr o ON o.attachment_id = a.id
                    WHERE a.record_id = ?
                    ORDER BY a.order_index ASC, a.uploaded_at DESC
                ''', (record_id,))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Anhänge aus DB: {e}")
            return []

    def reorder_attachments(self, record_id, filenames_order, user_id):
        """Speichert eine neue Reihenfolge für Anhänge"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Alle Dateinamen in einem Rutsch aktualisieren
                for index, filename in enumerate(filenames_order):
                    cursor.execute('''
                        UPDATE attachments 
                        SET order_index = ? 
                        WHERE record_id = ? AND filename = ?
                    ''', (index, record_id, filename))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Fehler beim Reordering der Anhänge: {e}")
            raise e

    def rename_attachment(self, record_id, old_filename, new_filename, user_id):
        """Benennt einen Anhang in der Datenbank und im Dateisystem um"""
        try:
            # Aktennummer holen
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT number FROM records WHERE id = ? AND archived = 0", (record_id,))
                record = cursor.fetchone()
                
                if not record:
                    raise ValueError(f"Akte mit ID {record_id} nicht gefunden")
                
                aktenzeichen = record['number']
                
                # Dateinamen säubern (Path Traversal verhindern)
                new_filename = re.sub(r'[\\/*?:"<>|]', '_', new_filename)
                new_filename = os.path.basename(new_filename)
                
                if not new_filename:
                    raise ValueError("Ungültiger Dateiname")

                # Prüfen ob der alte Dateiname existiert
                cursor.execute("SELECT filename FROM attachments WHERE record_id = ? AND filename = ?", (record_id, old_filename))
                if not cursor.fetchone():
                    raise ValueError(f"Datei {old_filename} nicht gefunden")
                
                # Prüfen ob der neue Dateiname bereits existiert
                cursor.execute("SELECT filename FROM attachments WHERE record_id = ? AND filename = ?", (record_id, new_filename))
                if cursor.fetchone():
                    raise ValueError(f"Eine Datei mit dem Namen {new_filename} existiert bereits")

                # Dateisystem: Umbenennen
                akte_dir = self.akten_dir / aktenzeichen
                old_path = akte_dir / old_filename
                new_path = akte_dir / new_filename
                
                if not old_path.exists():
                    raise FileNotFoundError(f"Datei im Dateisystem nicht gefunden: {old_filename}")
                
                os.rename(str(old_path), str(new_path))

                # Datenbank: Umbenennen
                cursor.execute('''
                    UPDATE attachments 
                    SET filename = ? 
                    WHERE record_id = ? AND filename = ?
                ''', (new_filename, record_id, old_filename))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Fehler beim Umbenennen des Anhangs: {e}")
            raise e

    def get_attachment_count(self, record_id):
        """Lädt nur die Anzahl der Anhänge aus der Datenbank (Performance-Optimierung für Listenansicht)"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) as count
                    FROM attachments
                    WHERE record_id = ?
                ''', (record_id,))
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Fehler beim Zählen der Anhänge: {e}")
            return 0
    
    def upload_file(self, record_id, file, user_id):
        """Lädt eine Datei hoch und speichert sie im Aktenordner und in der Datenbank"""
        try:
            # Aktennummer holen
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT number FROM records WHERE id = ? AND archived = 0", (record_id,))
                record = cursor.fetchone()
                
                if not record:
                    raise ValueError(f"Akte mit ID {record_id} nicht gefunden")
                
                aktenzeichen = record['number']
            
            # Datei speichern
            akte_dir = self.akten_dir / aktenzeichen
            akte_dir.mkdir(parents=True, exist_ok=True)
            
            # Prüfen ob Datei bereits existiert
            original_filename = file.filename
            file_path = akte_dir / original_filename
            if file_path.exists():
                # Zeitstempel hinzufügen um Duplikate zu vermeiden
                name_parts = original_filename.rsplit('.', 1)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                if len(name_parts) == 2:
                    new_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                else:
                    new_filename = f"{original_filename}_{timestamp}"
                file_path = akte_dir / new_filename
            else:
                new_filename = original_filename
            
            # Datei speichern
            file.save(str(file_path))
            
            # Dateiberechtigungen setzen (für Cross-Platform-Kompatibilität)
            if os.name != 'nt':  # Nicht Windows (also Linux/macOS)
                try:
                    os.chmod(str(file_path), 0o666)  # Lesen/Schreiben für alle
                    # Auch den Aktenordner selbst entsprechend setzen
                    os.chmod(str(akte_dir), 0o777)
                except Exception as perm_error:
                    logger.warning(f"Konnte Dateiberechtigungen nicht setzen: {perm_error}")
            else:
                # Windows: Versuche, Read-Only-Attribut zu entfernen, falls vorhanden
                try:
                    os.chmod(str(file_path), 0o777)
                except Exception as perm_error:
                    logger.warning(f"Konnte Dateiberechtigungen nicht setzen: {perm_error}")
            
            # MIME-Typ bestimmen
            mime_type = "application/octet-stream"  # Default
            if file_path.suffix.lower() in ['.jpg', '.jpeg']:
                mime_type = "image/jpeg"
            elif file_path.suffix.lower() == '.png':
                mime_type = "image/png"
            elif file_path.suffix.lower() == '.gif':
                mime_type = "image/gif"
            elif file_path.suffix.lower() == '.pdf':
                mime_type = "application/pdf"
            elif file_path.suffix.lower() in ['.txt', '.md']:
                mime_type = "text/plain"
            elif file_path.suffix.lower() in ['.mp3', '.wav']:
                mime_type = "audio/mpeg"
            elif file_path.suffix.lower() == '.mp4':
                mime_type = "video/mp4"
            
            # In Datenbank speichern
            attachment_id = None
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Nächsten order_index bestimmen
                cursor.execute("SELECT MAX(order_index) as max_idx FROM attachments WHERE record_id = ?", (record_id,))
                max_row = cursor.fetchone()
                next_idx = (max_row['max_idx'] + 1) if (max_row and max_row['max_idx'] is not None) else 0

                cursor.execute('''
                    INSERT INTO attachments (
                        record_id, filename, original_filename, 
                        file_size, mime_type, uploaded_by, order_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record_id,
                    new_filename,
                    original_filename,
                    file_path.stat().st_size,
                    mime_type,
                    user_id,
                    next_idx
                ))
                attachment_id = cursor.lastrowid
                conn.commit()

            # Bild-Hashes berechnen und speichern (für Ähnlichkeitssuche)
            if mime_type.startswith('image/') and attachment_id:
                try:
                    from PIL import Image
                    import imagehash
                    import numpy as np
                    import json
                    import cv2
                    
                    img = Image.open(file_path)
                    img = img.convert('RGB')
                    
                    # Verschiedene Hash-Algorithmen für bessere Erkennung
                    phash = str(imagehash.phash(img))
                    dhash = str(imagehash.dhash(img))
                    whash = str(imagehash.whash(img))
                    
                    # Farb-Histogramm
                    img_small = img.resize((100, 100))
                    histogram = img_small.histogram()
                    histogram_normalized = np.array(histogram) / np.sum(histogram)
                    histogram_json = json.dumps(histogram_normalized.tolist())
                    
                    # OpenCV für erweiterte Analyse
                    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    
                    # HSV-Farbraum für bessere Farberkennung
                    hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
                    hsv_histogram = cv2.calcHist([hsv], [0, 1, 2], None, [50, 50, 50], [0, 180, 0, 256, 0, 256])
                    hsv_histogram = cv2.normalize(hsv_histogram, hsv_histogram).flatten()
                    hsv_json = json.dumps(hsv_histogram.tolist())
                    
                    # Kanten-Erkennung (Canny)
                    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                    edges = cv2.Canny(gray, 100, 200)
                    edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
                    
                    # Dominante Farben (HSV-basiert)
                    h, s, v = cv2.split(hsv)
                    dominant_hue = np.argmax(np.bincount(h.flatten()))
                    dominant_colors = []
                    if 0 <= dominant_hue < 10 or 170 <= dominant_hue <= 180:
                        dominant_colors.append('rot')
                    elif 10 <= dominant_hue < 25:
                        dominant_colors.append('orange')
                    elif 25 <= dominant_hue < 35:
                        dominant_colors.append('gelb')
                    elif 35 <= dominant_hue < 85:
                        dominant_colors.append('grün')
                    elif 85 <= dominant_hue < 125:
                        dominant_colors.append('cyan')
                    elif 125 <= dominant_hue < 155:
                        dominant_colors.append('blau')
                    elif 155 <= dominant_hue < 170:
                        dominant_colors.append('lila')
                    
                    if np.mean(v) > 200:
                        dominant_colors.append('hell')
                    elif np.mean(v) < 50:
                        dominant_colors.append('dunkel')
                    
                    colors_json = json.dumps(dominant_colors)
                    
                    # Hashes in Datenbank speichern
                    with self.db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO attachment_hashes (
                                attachment_id, record_id, phash, dhash, whash, 
                                color_histogram, dominant_colors, hsv_histogram, edge_density
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            attachment_id,
                            record_id,
                            phash,
                            dhash,
                            whash,
                            histogram_json,
                            colors_json,
                            hsv_json,
                            float(edge_density)
                        ))
                        conn.commit()
                        
                    logger.info(f"Bild-Hashes für Attachment {attachment_id} berechnet")
                except Exception as hash_error:
                    logger.warning(f"Konnte Bild-Hashes nicht berechnen: {hash_error}")

            ocr_result = {'queued': False, 'status': 'not_configured'}
            if self.ocr_manager and attachment_id:
                try:
                    ocr_result = self.ocr_manager.enqueue_attachment(attachment_id)
                except Exception as ocr_error:
                    logger.warning(f"OCR-Job konnte nicht erstellt werden: {ocr_error}")
                    ocr_result = {'queued': False, 'status': 'error', 'error': str(ocr_error)}
            
            return {
                'success': True,
                'filename': new_filename,
                'size': file_path.stat().st_size,
                'ocr': ocr_result
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Upload der Datei: {e}")
            raise e
    
    def delete_file(self, record_id, filename, user_id):
        """Löscht eine Datei aus dem Aktenordner und aus der Datenbank"""
        try:
            # Aktennummer und Attachment-ID holen
            attachment_id = None
            aktenzeichen = None
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT number FROM records WHERE id = ? AND archived = 0", (record_id,))
                record = cursor.fetchone()
                
                if not record:
                    raise ValueError(f"Akte mit ID {record_id} nicht gefunden")
                
                aktenzeichen = record['number']
                cursor.execute(
                    "SELECT id FROM attachments WHERE record_id = ? AND filename = ?",
                    (record_id, filename)
                )
                attachment_row = cursor.fetchone()
                if not attachment_row:
                    # Vielleicht stimmt der Dateiname nicht genau? Lass uns mal alle Attachments der Akte anzeigen
                    cursor.execute("SELECT filename FROM attachments WHERE record_id = ?", (record_id,))
                    all_files = [row['filename'] for row in cursor.fetchall()]
                    raise ValueError(f"Datei {filename} ist in der Akte nicht registriert. Vorhandene Dateien: {all_files}")
                attachment_id = attachment_row['id']
                logger.info(f"Gefundenes Attachment: ID={attachment_id}, record_id={record_id}, filename={filename}")
            
            # Datei löschen
            file_path = self.akten_dir / aktenzeichen / filename
            logger.info(f"Versuche Datei zu löschen: {file_path}")

            if file_path.exists():
                try:
                    # Versuche, die Dateiberechtigungen zu ändern, falls sie Read-Only ist
                    if os.name == 'nt':
                        # Windows: Versuche, Read-Only Attribut zu entfernen
                        try:
                            os.chmod(str(file_path), 0o777)
                        except Exception:
                            pass  # Ignoriere Fehler bei der Berechtigungänderung
                    else:
                        # Linux: Setze Berechtigungen auf 777, um sicherzustellen, dass sie gelöscht werden kann
                        try:
                            os.chmod(str(file_path), 0o777)
                        except Exception:
                            pass
                    
                    # Versuche, die Datei zu löschen
                    file_path.unlink()
                    logger.info(f"Datei {filename} aus Akte {aktenzeichen} erfolgreich gelöscht")
                except PermissionError as delete_error:
                    logger.error(f"Datei {filename} ist noch in Benutzung: {delete_error}")
                    raise Exception(
                        f"Datei {filename} ist aktuell noch geöffnet oder wird verarbeitet. "
                        "Bitte Viewer/Vorschau schließen und erneut versuchen."
                    )
                except Exception as delete_error:
                    logger.error(f"Fehler beim Löschen der Datei {filename}: {delete_error}")
                    raise Exception(f"Konnte Datei {filename} nicht löschen: {delete_error}")
            else:
                logger.warning(
                    f"Datei {filename} nicht mehr im Dateisystem gefunden; "
                    "Datenbankeintrag wird trotzdem entfernt."
                )

            # Zuerst alle abhängigen Datensätze löschen, dann das Attachment selbst in einer Transaktion
            with self.db_manager.get_connection() as conn:
                try:
                    conn.execute('BEGIN TRANSACTION')
                    cursor = conn.cursor()
                    
                    # List all tables that might reference attachments
                    tables_to_check = ['ocr_jobs', 'attachment_ocr', 'attachment_ocr_fts']
                    
                    # First, check what actually references this attachment
                    for table in tables_to_check:
                        try:
                            if table == 'attachment_ocr_fts':
                                # For FTS, use rowid
                                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE attachment_id = ?", (attachment_id,))
                            else:
                                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE attachment_id = ?", (attachment_id,))
                            count = cursor.fetchone()[0]
                            if count > 0:
                                logger.info(f"Gefunden: {count} Einträge in {table} für Attachment {attachment_id}")
                                if table == 'attachment_ocr_fts':
                                    # For FTS5, delete by rowid which is attachment_id
                                    cursor.execute(f"DELETE FROM {table} WHERE attachment_id = ?", (attachment_id,))
                                else:
                                    cursor.execute(f"DELETE FROM {table} WHERE attachment_id = ?", (attachment_id,))
                                logger.info(f"Gelöscht: {cursor.rowcount} Einträge aus {table}")
                        except Exception as table_err:
                            logger.warning(f"Konnte Tabelle {table} nicht prüfen/löschen: {table_err}")
                    
                    # Jetzt das Attachment selbst löschen
                    cursor.execute("DELETE FROM attachments WHERE record_id = ? AND filename = ?", (record_id, filename))
                    logger.info(f"Gelöscht: {cursor.rowcount} Einträge aus attachments für {filename}")
                    
                    conn.commit()
                    logger.info(f"Datenbankeintrag für {filename} erfolgreich gelöscht (Transaktion abgeschlossen)")
                except Exception as db_error:
                    conn.rollback()
                    logger.error(f"Fehler bei Datenbank-Transaktion: {db_error}", exc_info=True)
                    # Letzter Versuch: Direktes Löschen mit deaktivierten FKs
                    try:
                        conn.execute('PRAGMA foreign_keys = OFF')
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM attachments WHERE record_id = ? AND filename = ?", (record_id, filename))
                        conn.commit()
                        logger.info(f"Letzter Versuch erfolgreich: Datenbankeintrag für {filename} gelöscht")
                    except Exception as last_err:
                        logger.error(f"Auch letzter Versuch fehlgeschlagen: {last_err}", exc_info=True)
                        raise Exception(f"Fehler bei Datenbank-Transaktion: {db_error}")

            if file_path.exists():
                logger.error(f"FEHLER: Datei {filename} existiert noch nach dem Löschen!")
                raise Exception(f"Datei {filename} konnte nicht gelöscht werden - existiert noch")

            logger.info(f"Verifiziert: Anhang {filename} wurde vollständig entfernt")
            return True
                
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Datei: {e}", exc_info=True)
            raise e
    
    def download_file(self, record_id, filename):
        """Bereitet Datei zum Download vor"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT number FROM records WHERE id = ? AND archived = 0", (record_id,))
                record = cursor.fetchone()
                
                if not record:
                    raise ValueError(f"Akte mit ID {record_id} nicht gefunden")
                
                aktenzeichen = record['number']
            
            file_path = self.akten_dir / aktenzeichen / filename
            if not file_path.exists():
                raise ValueError(f"Datei {filename} nicht gefunden in Akte {aktenzeichen}")
            
            return str(self.akten_dir / aktenzeichen), filename
            
        except Exception as e:
            logger.error(f"Fehler beim Vorbereiten des Downloads: {e}")
            raise e
    
    def extract_keywords(self, text):
        """Extrahiert Keywords aus Text für Ähnlichkeitssuche"""
        return self.search_logic.extract_keywords(text)
    
    def extract_record_metadata(self, record_data):
        """Extrahiert Metadaten aus einer Akte für Ähnlichkeitssuche mit verbesserten Gewichtungen"""
        weighted_keywords = {}
        
        # Hilfsfunktion für Wort-Häufigkeit mit exponentieller Gewichtung
        def add_keywords_with_frequency(text, base_weight):
            if not text:
                return
            keywords = list(self.extract_keywords(text))
            for keyword in keywords:
                frequency = keywords.count(keyword)
                # Exponentielle Gewichtung: häufige Wörter werden stärker gewichtet
                weight = base_weight * (1 + (frequency - 1) * 0.5)
                weighted_keywords[keyword] = weighted_keywords.get(keyword, 0) + weight
        
        # Titel - höchste Gewichtung (sehr wichtig für Ähnlichkeit)
        if record_data.get('title'):
            add_keywords_with_frequency(record_data['title'], 5.0)
        
        # Inhalt - sehr hohe Gewichtung
        if record_data.get('content'):
            add_keywords_with_frequency(record_data['content'], 3.0)
        
        # OCR-Texte - sehr hohe Gewichtung (oft der wichtigste Indikator)
        if record_data.get('ocr_texts'):
            for ocr_text in record_data['ocr_texts']:
                if ocr_text:
                    add_keywords_with_frequency(ocr_text, 4.0)
        
        # Kategorie - hohe Gewichtung
        if record_data.get('category_name'):
            add_keywords_with_frequency(record_data['category_name'], 2.5)
        
        # Adresse - hohe Gewichtung
        if record_data.get('address'):
            add_keywords_with_frequency(record_data['address'], 2.0)
        
        # Dateinamen - mittlere Gewichtung
        if record_data.get('filenames'):
            for filename in record_data['filenames']:
                if filename:
                    clean_filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                    add_keywords_with_frequency(clean_filename, 1.5)
        
        # Hashtags - mittlere Gewichtung
        if record_data.get('hashtags'):
            add_keywords_with_frequency(record_data['hashtags'], 1.5)
        
        # Rahmenfarbe - niedrige Gewichtung
        if record_data.get('border_color'):
            add_keywords_with_frequency(record_data['border_color'], 0.5)
        
        # Status - niedrige Gewichtung
        if record_data.get('status'):
            add_keywords_with_frequency(record_data['status'], 0.5)
        
        return weighted_keywords
    
    def calculate_text_similarity(self, record1_data, record2_data):
        """Berechnet Text-Ähnlichkeit basierend auf gewichteten Keywords mit Vollständigkeits-Faktor"""
        if not record1_data or not record2_data:
            return 0
        
        weighted_keywords1 = self.extract_record_metadata(record1_data)
        weighted_keywords2 = self.extract_record_metadata(record2_data)
        
        if not weighted_keywords1 or not weighted_keywords2:
            return 0
        
        # Gemeinsame Keywords finden
        common_keywords = set(weighted_keywords1.keys()) & set(weighted_keywords2.keys())
        
        if not common_keywords:
            return 0
        
        # Gewichtete Ähnlichkeit berechnen
        # Für jedes gemeinsame Keyword: min(weight1, weight2) als Beitrag
        intersection_weight = sum(min(weighted_keywords1[k], weighted_keywords2[k]) for k in common_keywords)
        
        # Gesamtgewicht für Normalisierung (Summe aller Gewichte in beiden Sets)
        total_weight1 = sum(weighted_keywords1.values())
        total_weight2 = sum(weighted_keywords2.values())
        
        # Normalisierung: Maximum der Gesamtgewichte (statt Durchschnitt)
        # Dies verhindert, dass zwei leere Akten mit gleichem Titel als 100% ähnlich gelten
        normalization = max(total_weight1, total_weight2)
        
        if normalization == 0:
            return 0
        
        similarity = intersection_weight / normalization
        
        # Vollständigkeits-Faktor: Wenn eine Akte viel mehr Inhalt hat als die andere,
        # reduziert dies die Ähnlichkeit
        completeness_factor = min(total_weight1, total_weight2) / max(total_weight1, total_weight2)
        
        # Kombinierter Score mit Vollständigkeits-Faktor (0.7 Gewichtung für Ähnlichkeit, 0.3 für Vollständigkeit)
        final_similarity = (similarity * 0.7) + (completeness_factor * 0.3)
        
        logger.info(f"Ähnlichkeit berechnet: {final_similarity:.3f} (Gemeinsame Keywords: {len(common_keywords)}, Intersection-Weight: {intersection_weight:.2f}, Normalization: {normalization:.2f}, Vollständigkeits-Faktor: {completeness_factor:.2f})")
        
        return final_similarity
    
    def find_similar_records(self, search_query=None, reference_record_id=None, limit=50, offset=0, min_similarity=0.1, viewer_user_id=None, is_admin=False):
        """Findet ähnliche Akten basierend auf genauen Treffern und deren Keywords mit intelligenten Gewichtungen"""
        try:
            logger.info(f"Ähnlichkeitssuche gestartet: search_query={search_query}, reference_record_id={reference_record_id}, min_similarity={min_similarity}")
            
            if not search_query and not reference_record_id:
                return {'success': False, 'error': 'Kein Suchbegriff oder Referenz-Akte angegeben'}
            
            # Gewichtungen aus LearningSystem laden
            weights = self.learning_system.get_similarity_weights(viewer_user_id)
            logger.info(f"Gewichtungen geladen: {weights}")
            
            # Suchprotokollierung
            search_log_id = self.learning_system.log_search(
                viewer_user_id or 0, 
                'similarity', 
                {'search_query': search_query, 'reference_record_id': reference_record_id},
                0
            )
            
            # Schritt 1: Zuerst genaue Treffer finden (verbesserte Suche mit allen Wörtern)
            search_results = []
            
            if search_query:
                # Suchbegriff in einzelne Wörter zerlegen
                search_words = self.extract_keywords(search_query)
                
                if search_words:
                    with self.db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        
                        # Für jedes Wort eine LIKE-Bedingung erstellen (AND-Logik)
                        conditions = []
                        params = []
                        for word in search_words:
                            pattern = f'%{word}%'
                            conditions.append('(title LIKE ? OR content LIKE ? OR number LIKE ? OR hashtags LIKE ? OR address LIKE ?)')
                            params.extend([pattern, pattern, pattern, pattern, pattern])
                        
                        query = f"""
                            SELECT id, title, content, number, category_id, border_color, status, address, hashtags,
                                   created_at, updated_at, created_by, updated_by
                            FROM records
                            WHERE archived = 0
                            AND {' AND '.join(conditions)}
                        """
                        cursor.execute(query, params)
                        search_results = [dict(row) for row in cursor.fetchall()]
            
            elif reference_record_id:
                # Hole die Referenz-Akte
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, title, content, number, category_id, border_color, status, address, hashtags, created_at, updated_at, created_by, updated_by FROM records WHERE id = ? AND archived = 0", (reference_record_id,))
                    ref_record = cursor.fetchone()
                    if ref_record:
                        search_results = [dict(ref_record)]
            
            if not search_results:
                logger.info("Keine initialen Suchergebnisse gefunden")
                return {'success': True, 'records': [], 'pagination': {'total': 0, 'limit': limit, 'offset': offset}}
            
            logger.info(f"Initiale Suchergebnisse (genaue Treffer): {len(search_results)}")
            
            # Schritt 2: OCR-Texte und Dateinamen für Suchergebnisse laden
            ocr_texts_by_record = {}
            filenames_by_record = {}
            
            record_ids = [r['id'] for r in search_results]
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # OCR-Texte laden
                if record_ids:
                    placeholders = ','.join('?' * len(record_ids))
                    cursor.execute(f"SELECT record_id, ocr_text FROM attachment_ocr WHERE record_id IN ({placeholders}) AND ocr_text IS NOT NULL AND ocr_text != ''", record_ids)
                    for row in cursor.fetchall():
                        record_id = row['record_id']
                        if record_id not in ocr_texts_by_record:
                            ocr_texts_by_record[record_id] = []
                        ocr_texts_by_record[record_id].append(row['ocr_text'])
                    
                    # Dateinamen laden
                    cursor.execute(f"SELECT record_id, filename FROM attachments WHERE record_id IN ({placeholders})", record_ids)
                    for row in cursor.fetchall():
                        record_id = row['record_id']
                        if record_id not in filenames_by_record:
                            filenames_by_record[record_id] = []
                        filenames_by_record[record_id].append(row['filename'])
            
            # Schritt 3: Kategorienamen für Suchergebnisse laden
            category_ids = [r['category_id'] for r in search_results if r['category_id']]
            categories = {}
            if category_ids:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    placeholders = ','.join('?' * len(set(category_ids)))
                    cursor.execute(f"SELECT id, name FROM categories WHERE id IN ({placeholders})", list(set(category_ids)))
                    categories = {row['id']: row['name'] for row in cursor.fetchall()}
            
            # Schritt 4: Metadaten für Suchergebnisse ergänzen und Keywords extrahieren
            all_search_keywords = set()
            for record in search_results:
                record['ocr_texts'] = ocr_texts_by_record.get(record['id'], [])
                record['filenames'] = filenames_by_record.get(record['id'], [])
                record['category_name'] = categories.get(record['category_id'], '')
                
                # Keywords aus diesem genauen Treffer extrahieren
                weighted_keywords = self.extract_record_metadata(record)
                all_search_keywords.update(weighted_keywords.keys())
            
            logger.info(f"Keywords aus genauen Treffern: {all_search_keywords}")
            
            if not all_search_keywords:
                logger.info("Keine Keywords aus genauen Treffern gefunden")
                return {'success': True, 'records': [], 'pagination': {'total': 0, 'limit': limit, 'offset': offset}}
            
            # Schritt 5: FTS5-basierte Vorfilterung für Performance bei großen Datenmengen
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Prüfen ob FTS5-Tabelle existiert
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records_fts'")
                fts_exists = cursor.fetchone() is not None
                
                if fts_exists and all_search_keywords:
                    # FTS5-Suche für schnelle Vorfilterung (konfigurierbares Limit)
                    # Extrahiere relevante Keywords für FTS5-Suche mit OR-Logik
                    keyword_list = list(all_search_keywords)[:10]  # Max 10 Keywords
                    candidate_limit = int(self.db_manager.get_setting('similarity_candidate_limit', '200'))
                    if keyword_list:
                        # OR-Logik für FTS5: Jedes Keyword einzeln suchen
                        fts_queries = [k for k in keyword_list if len(k) >= 3]
                        if fts_queries:
                            # FTS5 mit OR-Logik (jedes Wort einzeln suchen)
                            # Keywords in Anführungszeichen setzen, um Sonderzeichen zu escapen
                            fts_query = ' OR '.join(f'"{k}"' for k in fts_queries)
                            cursor.execute("""
                                SELECT r.id, r.title, r.content, r.number, r.category_id, r.border_color, r.status, r.address, r.hashtags,
                                       r.created_at, r.updated_at, r.created_by, r.updated_by
                                FROM records_fts fts
                                JOIN records r ON fts.id = r.id
                                WHERE records_fts MATCH ?
                                AND r.archived = 0
                                LIMIT ?
                            """, (fts_query, candidate_limit))
                            other_records = [dict(row) for row in cursor.fetchall()]
                        else:
                            other_records = []
                    else:
                        other_records = []
                else:
                    # Fallback: Nur die letzten X Akten prüfen bei großen Datenmengen
                    candidate_limit = int(self.db_manager.get_setting('similarity_candidate_limit', '2000'))
                    if is_admin:
                        query = """
                            SELECT id, title, content, number, category_id, border_color, status, address, hashtags,
                                   created_at, updated_at, created_by, updated_by
                            FROM records
                            WHERE archived = 0
                            ORDER BY id DESC
                            LIMIT ?
                        """
                        cursor.execute(query, (candidate_limit,))
                    else:
                        query = """
                            SELECT id, title, content, number, category_id, border_color, status, address, hashtags,
                                   created_at, updated_at, created_by, updated_by
                            FROM records
                            WHERE archived = 0 AND (created_by = ? OR updated_by = ?)
                            ORDER BY id DESC
                            LIMIT ?
                        """
                        cursor.execute(query, (viewer_user_id, viewer_user_id, candidate_limit))
                    
                    other_records = [dict(row) for row in cursor.fetchall()]
            
            logger.info(f"Zu durchsuchende Akten: {len(other_records)}")
            
            # Schritt 6: OCR-Texte und Dateinamen für andere Akten laden
            other_record_ids = [r['id'] for r in other_records]
            ocr_texts_by_other = {}
            filenames_by_other = {}
            
            if other_record_ids:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # OCR-Texte laden
                    placeholders = ','.join('?' * len(other_record_ids))
                    cursor.execute(f"SELECT record_id, ocr_text FROM attachment_ocr WHERE record_id IN ({placeholders}) AND ocr_text IS NOT NULL AND ocr_text != ''", other_record_ids)
                    for row in cursor.fetchall():
                        record_id = row['record_id']
                        if record_id not in ocr_texts_by_other:
                            ocr_texts_by_other[record_id] = []
                        ocr_texts_by_other[record_id].append(row['ocr_text'])
                    
                    # Dateinamen laden
                    cursor.execute(f"SELECT record_id, filename FROM attachments WHERE record_id IN ({placeholders})", other_record_ids)
                    for row in cursor.fetchall():
                        record_id = row['record_id']
                        if record_id not in filenames_by_other:
                            filenames_by_other[record_id] = []
                        filenames_by_other[record_id].append(row['filename'])
            
            # Schritt 7: Metadaten für andere Akten ergänzen
            for record in other_records:
                record['ocr_texts'] = ocr_texts_by_other.get(record['id'], [])
                record['filenames'] = filenames_by_other.get(record['id'], [])
                record['category_name'] = categories.get(record['category_id'], '')
            
            # Schritt 8: Ähnlichkeit berechnen - genaue Treffer und ähnliche Akten mit gewichteter Berechnung
            similar_records = []
            search_result_ids = set(r['id'] for r in search_results)
            
            # Zuerst die genauen Treffer mit höchster Ähnlichkeit aufnehmen
            for record in search_results:
                record['similarity_score'] = 999  # Höchste Priorität für genaue Treffer
                similar_records.append((999, record))
            
            # Dann ähnliche Akten finden mit intelligenter Ähnlichkeitsberechnung
            for record in other_records:
                # Überspringe wenn es einer der genauen Treffer ist
                if record['id'] in search_result_ids:
                    continue
                
                # Intelligente Ähnlichkeitsberechnung mit LearningSystem
                similarity_score = 0
                
                # Für jeden genauen Treffer die Ähnlichkeit berechnen
                for search_record in search_results:
                    # Anhänge-Anzahl hinzufügen
                    search_record['attachment_count'] = len(search_record.get('filenames', []))
                    record['attachment_count'] = len(record.get('filenames', []))
                    
                    # OCR-Text zusammenfassen
                    search_record['ocr_text'] = ' '.join(search_record.get('ocr_texts', []))
                    record['ocr_text'] = ' '.join(record.get('ocr_texts', []))
                    
                    # Ähnlichkeit mit LearningSystem berechnen
                    current_similarity = self.learning_system.calculate_similarity_score(
                        record, search_record, weights
                    )
                    similarity_score = max(similarity_score, current_similarity)
                
                # Nur Akten mit signifikanter Ähnlichkeit aufnehmen
                if similarity_score >= min_similarity:
                    record['similarity_score'] = similarity_score
                    similar_records.append((similarity_score, record))
            
            # Schritt 9: Nach Ähnlichkeit sortieren (genaue Treffer zuerst, dann ähnliche nach gewichteter Ähnlichkeit)
            similar_records.sort(key=lambda x: x[0], reverse=True)
            
            # Schritt 10: Paginierung anwenden
            offset = min(offset, len(similar_records))
            paginated_results = [item[1] for item in similar_records[offset:offset + limit]]
            
            logger.info(f"Ähnlichkeitssuche abgeschlossen: {len(similar_records)} ähnliche Akten gefunden, zeige {len(paginated_results)}")
            
            # Suchprotokollierung aktualisieren mit result_count
            if search_log_id:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('UPDATE search_logs SET result_count = ? WHERE id = ?', (len(similar_records), search_log_id))
                    conn.commit()

            return {
                'success': True,
                'records': paginated_results,
                'pagination': {
                    'total': len(similar_records),
                    'limit': limit,
                    'offset': offset
                }
            }
        except Exception as e:
            logger.error(f"Fehler bei Ähnlichkeitssuche: {e}")
            return {'success': False, 'error': str(e)}

    # ── Archiv-Funktionen ────────────────────────────────────────────────

    def archive_records(self, record_ids, user_id, archive_reason=None):
        """
        Verschiebt mehrere Akten ins Archiv
        - Setzt archived=1 in records Tabelle
        - Erstellt Eintrag in archive_metadata
        - Verschiebt Ordner im Dateisystem (optional, für Performance behalten wir Ordner)
        """
        if not record_ids:
            return {'success': False, 'error': 'Keine Akten IDs übergeben'}

        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))

        # Username holen
        username = None
        with self.db_manager.get_connection() as conn_temp:
            cursor_temp = conn_temp.cursor()
            cursor_temp.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user_row = cursor_temp.fetchone()
            if user_row:
                username = user_row['username']

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))

            # Prüfen ob alle Akten existieren und nicht bereits archiviert sind
            cursor.execute(
                f"SELECT id, number FROM records WHERE id IN ({platzhalter}) AND archived = 0",
                eindeutige_ids
            )
            rows = cursor.fetchall()

            if len(rows) != len(eindeutige_ids):
                return {'success': False, 'error': 'Eine oder mehrere Akten wurden nicht gefunden oder sind bereits archiviert'}

            # Akten archivieren
            cursor.execute(
                f"UPDATE records SET archived = 1, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({platzhalter})",
                [user_id] + eindeutige_ids
            )

            # Archive-Metadaten erstellen
            for row in rows:
                record_id = row['id']
                record_number = row['number']
                original_folder_path = str(self.akten_dir / record_number)

                cursor.execute('''
                    INSERT OR REPLACE INTO archive_metadata
                    (record_id, archived_at, archived_by, archived_by_name, archive_reason, original_folder_path)
                    VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                ''', (record_id, user_id, username, archive_reason, original_folder_path))

            conn.commit()

        # Cache invalidieren
        self.db_manager.invalidate_records_cache()

        return {
            'success': True,
            'archived_count': len(eindeutige_ids),
            'record_ids': eindeutige_ids
        }

    def restore_records(self, record_ids, user_id):
        """
        Stellt mehrere Akten aus dem Archiv wieder her
        - Setzt archived=0 in records Tabelle
        - Löscht Eintrag aus archive_metadata
        """
        if not record_ids:
            return {'success': False, 'error': 'Keine Akten IDs übergeben'}

        eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            platzhalter = ','.join(['?'] * len(eindeutige_ids))

            # Prüfen ob alle Akten archiviert sind
            cursor.execute(
                f"SELECT id FROM records WHERE id IN ({platzhalter}) AND archived = 1",
                eindeutige_ids
            )
            rows = cursor.fetchall()

            if len(rows) != len(eindeutige_ids):
                return {'success': False, 'error': 'Eine oder mehrere Akten wurden nicht im Archiv gefunden'}

            # Akten wiederherstellen
            cursor.execute(
                f"UPDATE records SET archived = 0, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({platzhalter})",
                [user_id] + eindeutige_ids
            )

            # Archive-Metadaten löschen
            cursor.execute(
                f"DELETE FROM archive_metadata WHERE record_id IN ({platzhalter})",
                eindeutige_ids
            )

            conn.commit()

        # Cache invalidieren
        self.db_manager.invalidate_records_cache()

        return {
            'success': True,
            'restored_count': len(eindeutige_ids),
            'record_ids': eindeutige_ids
        }

    def list_archived_records(self, search='', filter_type='all', search_type='all', limit=50, offset=0, category_id=None, border_color=None, viewer_user_id=None, is_admin=False):
        """Listet archivierte Akten mit Filteroptionen (ähnlich wie list_akten aber mit archived=1)"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Basis-Query für archivierte Akten
            base_query = '''
                SELECT r.*, COALESCE(r.created_by_name, u.username) as created_by_name,
                       l.user_id as locked_by, l.expires_at as lock_expires
                FROM records r
                LEFT JOIN users u ON r.created_by = u.id
                LEFT JOIN record_locks l ON r.id = l.record_id AND l.expires_at > datetime('now')
                WHERE r.archived = 1
            '''
            params = []

            # Filter hinzufügen
            if category_id:
                base_query += " AND r.category_id = ?"
                params.append(category_id)

            if border_color:
                base_query += " AND r.border_color = ?"
                params.append(border_color)

            # Suche hinzufügen
            if search:
                parsed_search = self.parse_search_query(search)
                conditions = self.build_search_conditions(parsed_search, search_type, 'r.')
                if conditions:
                    base_query += f" AND ({conditions})"
                    params.extend(parsed_search['terms'])

            # Sortierung
            base_query += " ORDER BY r.updated_at DESC"

            # Pagination
            base_query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(base_query, params)
            rows = cursor.fetchall()

            records = []
            for row in rows:
                record_dict = dict(row)
                record_dict['attachments'] = self.get_attachments(row['id'])
                record_dict['locked'] = row['locked_by'] is not None
                record_dict = self._apply_reminder_visibility(record_dict, viewer_user_id, is_admin)
                records.append(record_dict)

            # Gesamtzahl ermitteln
            count_query = "SELECT COUNT(*) FROM records WHERE archived = 1"
            count_params = []
            if category_id:
                count_query += " AND category_id = ?"
                count_params.append(category_id)
            if border_color:
                count_query += " AND border_color = ?"
                count_params.append(border_color)
            if search:
                parsed_search = self.parse_search_query(search)
                conditions = self.build_search_conditions(parsed_search, search_type)
                if conditions:
                    count_query += f" AND ({conditions})"
                    count_params.extend(parsed_search['terms'])

            cursor.execute(count_query, count_params)
            total = cursor.fetchone()[0]

            return {
                'records': records,
                'pagination': {
                    'total': total,
                    'limit': limit,
                    'offset': offset
                }
            }

    def get_archive_metadata(self, record_id):
        """Holt Archiv-Metadaten für eine Akte"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM archive_metadata WHERE record_id = ?
            ''', (record_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
