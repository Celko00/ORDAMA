"""
Datenbank-Modul für ORDAMA
"""

import sqlite3
import bcrypt
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
import os
import threading
from threading import Lock

from system.mod.db_schutz import setze_datenbank_schutz
from cache_manager import CacheManager
from schema_manager import SchemaManager

logger = logging.getLogger(__name__)

# Konstanten für Datenbank-Konfiguration
BUSY_TIMEOUT_MS = 10000  # 10 Sekunden (für höhere Concurrency)
MMAP_SIZE_BYTES = 536870912  # 512MB (für bessere Performance bei großen Datenbanken)
RECORD_START_NUMBER = 1000
RECORD_MAX_POOL = 100000000
OCR_ERROR_MESSAGE_MAX_LENGTH = 1000

class DatabaseManager:
    def __init__(self, base_dir, config):
        self.base_dir = Path(base_dir)
        self.config = config
        
        # Cache für häufige Abfragen
        self.cache_manager = CacheManager()
        self.cache = self.cache_manager.cache  # Für Abwärtskompatibilität
        
        # Schema Manager für Tabellen und Migrationen
        self.schema_manager = SchemaManager(self.get_connection)
        
        # Connection Pool für wiederverwendbare Verbindungen
        self._connection_pool = {}
        self._pool_lock = Lock()
        self._max_pool_size = 50  # Max 50 Verbindungen im Pool (für 100+ Nutzer)
        
        # Pfad auflösen (absolut oder relativ zum base_dir)
        data_base_dir_str = config['paths'].get('data_base_dir', './Speicher')
        data_base_dir = Path(data_base_dir_str)
        if not data_base_dir.is_absolute():
            data_base_dir = self.base_dir / data_base_dir
            
        self.pool_db_path = data_base_dir / "Datenbank" / config['database']['name']
    
    def invalidate_records_cache(self):
        """Invalidiert alle Cache-Einträge die mit Akten zu tun haben"""
        self.cache_manager.invalidate_records_cache()
    
    def invalidate_user_cache(self, user_id=None):
        """Invalidiert User-spezifische Cache-Einträge"""
        self.cache_manager.invalidate_user_cache(user_id)
    
    def invalidate_cache(self, pattern):
        """Allgemeine Cache-Invalidierung"""
        self.cache_manager.invalidate_pattern(pattern)

    def analyze_query_performance(self, query, params=None):
        """Analysiert eine Query mit EXPLAIN QUERY PLAN für Performance-Optimierung"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"EXPLAIN QUERY PLAN {query}", params or [])
                plan = cursor.fetchall()
                return plan
            except Exception as e:
                logger.warning(f"Query-Analyse fehlgeschlagen: {e}")
                return None
    
    def optimize_database_queries(self):
        """Führt EXPLAIN QUERY PLAN auf wichtigen Abfragen aus und protokolliert Ergebnisse"""
        important_queries = [
            # Akten-Liste Abfrage
            """
            SELECT r.*, COALESCE(r.created_by_name, u.username) as created_by_name
            FROM records r
            LEFT JOIN users u ON r.created_by = u.id
            WHERE r.archived = 0
            ORDER BY r.updated_at DESC
            LIMIT 50 OFFSET 0
            """,
            # Statistik-Abfrage
            """
            SELECT status, COUNT(*) as count 
            FROM records 
            WHERE archived = 0 
            GROUP BY status
            """,
            # Kategorie-Abfrage
            """
            SELECT c.name, COUNT(r.id) as count
            FROM categories c
            LEFT JOIN records r ON r.category_id = c.id AND r.archived = 0
            GROUP BY c.id, c.name
            ORDER BY count DESC
            """,
            # Karte-Abfrage
            """
            SELECT r.id, r.number, r.title, r.address, r.hashtags, r.border_color, r.updated_at,
                   k.plz, k.ort, k.lat, k.lon
            FROM records r
            LEFT JOIN record_koordinaten k ON r.id = k.record_id
            WHERE r.archived = 0 AND k.lat IS NOT NULL AND k.lon IS NOT NULL
            ORDER BY r.updated_at DESC
            LIMIT 100
            """
        ]
        
        for i, query in enumerate(important_queries):
            plan = self.analyze_query_performance(query)
            if plan:
                logger.info(f"Query-Plan {i+1}: {plan}")
                # Prüfen ob TABLE SCAN statt INDEX SCAN verwendet wird
                for row in plan:
                    if row and 'detail' in row and 'SCAN' in str(row['detail']):
                        logger.warning(f"Performance-Warnung: Table Scan detected in Query {i+1}")


    def get_connection(self):
        """Datenbankverbindung mit Connection Pooling und Performance-Optimierungen"""
        # Vor dem Verbinden sicherstellen, dass der Header korrekt ist (Entsperren)
        setze_datenbank_schutz(str(self.pool_db_path), aktivieren=False)
        
        # Versuchen, eine Verbindung aus dem Pool zu holen
        thread_id = id(threading.current_thread())
        
        with self._pool_lock:
            # Prüfen ob für diesen Thread bereits eine Verbindung existiert
            if thread_id in self._connection_pool:
                conn = self._connection_pool[thread_id]
                try:
                    # Verbindung prüfen - ob noch gültig
                    conn.execute('SELECT 1')
                    return conn
                except sqlite3.Error:
                    # Verbindung ist ungültig, aus Pool entfernen
                    del self._connection_pool[thread_id]
            
            # Neue Verbindung erstellen
            conn = sqlite3.connect(str(self.pool_db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            
            # Performance-Optimierungen mit PRAGMAs
            cursor = conn.cursor()
            try:
                # WAL-Modus für bessere Concurrency (erlaubt gleichzeitige Lese-/Schreibzugriffe)
                cursor.execute('PRAGMA journal_mode=WAL')
                # Synchronous=NORMAL für bessere Performance bei akzeptablem Sicherheitslevel
                cursor.execute('PRAGMA synchronous=NORMAL')
                # Cache-Size erhöhen (default 2000 pages) - 128MB für große Datenbanken
                cursor.execute('PRAGMA cache_size=-131072')  # 128MB negativ = KB
                # Temp Store in Memory für schnellere temporäre Operationen
                cursor.execute('PRAGMA temp_store=MEMORY')
                # Foreign Keys aktivieren
                cursor.execute('PRAGMA foreign_keys=ON')
                # Locking Mode optimieren
                cursor.execute('PRAGMA locking_mode=NORMAL')
                # Page Size optimieren (default 4096)
                cursor.execute('PRAGMA page_size=4096')
                # Auto-Vacuum deaktivieren für bessere Performance (manuell VACUUM verwenden)
                cursor.execute('PRAGMA auto_vacuum=NONE')
                # MMap Size erhöhen für bessere Performance bei großen Datenbanken
                cursor.execute(f'PRAGMA mmap_size={MMAP_SIZE_BYTES}')  # 512MB
                # Busy Timeout erhöhen für bessere Concurrency bei vielen Nutzern
                cursor.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT_MS}')  # 10 Sekunden
                # WAL Auto-Checkpoint optimieren (weniger häufige Checkpoints)
                cursor.execute('PRAGMA wal_autocheckpoint=1000')  # Alle 1000 Seiten
            except Exception as e:
                logger.warning(f"Einige PRAGMAs konnten nicht gesetzt werden: {e}")
            
            # Verbindung zum Pool hinzügen (wenn Pool nicht voll)
            if len(self._connection_pool) < self._max_pool_size:
                self._connection_pool[thread_id] = conn
            
            return conn
    
    def close_all_connections(self):
        """Schließt alle offenen Datenbankverbindungen im Pool und führt WAL-Checkpoint durch"""
        with self._pool_lock:
            for thread_id, conn in list(self._connection_pool.items()):
                try:
                    # WAL-Checkpoint ausführen, um Änderungen in Hauptdatei zu schreiben
                    cursor = conn.cursor()
                    try:
                        cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                        conn.commit()
                    except Exception as e:
                        logger.warning(f"WAL-Checkpoint fehlgeschlagen: {e}")
                    
                    conn.close()
                    logger.info(f"Verbindung für Thread {thread_id} geschlossen")
                except Exception as e:
                    logger.warning(f"Fehler beim Schließen der Verbindung für Thread {thread_id}: {e}")
            self._connection_pool.clear()
            logger.info("Alle Datenbankverbindungen geschlossen")

    def initialize_database(self):
        """Initialisiert die Datenbank mit allen Tabellen"""
        self.schema_manager.initialize_database()
        
        # Admin-Benutzer erstellen oder aktualisieren (bleibt in database.py)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, password_hash FROM users WHERE username = 'admin'")
            admin_user = cursor.fetchone()
            
            if admin_user is None:
                admin_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, can_read, can_write, can_delete, can_download, can_upload)
                    VALUES (?, ?, 'admin', 1, 1, 1, 1, 1)
                ''', ('admin', admin_hash))
                logger.info("Admin-Benutzer erstellt")
            else:
                if not admin_user['password_hash'].startswith('$2b$'):
                    admin_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    cursor.execute('UPDATE users SET password_hash = ? WHERE username = "admin"', (admin_hash,))
                    logger.info("Admin-Passwort auf bcrypt aktualisiert")
                
                cursor.execute('''
                    UPDATE users SET role = 'admin', can_read = 1, can_write = 1, can_delete = 1, can_download = 1, can_upload = 1
                    WHERE username = 'admin'
                ''')
            
            # Standardwerte für Berechtigungen sicherstellen
            cursor.execute("UPDATE users SET can_read = 1 WHERE can_read IS NULL")
            cursor.execute("UPDATE users SET can_write = 1 WHERE can_write IS NULL")
            cursor.execute("UPDATE users SET can_download = 1 WHERE can_download IS NULL")
            cursor.execute("UPDATE users SET can_upload = 1 WHERE can_upload IS NULL")
            cursor.execute("UPDATE users SET can_delete_termine = 1 WHERE can_delete_termine IS NULL")
            cursor.execute("UPDATE users SET can_delete_erinnerung = 1 WHERE can_delete_erinnerung IS NULL")
            cursor.execute("UPDATE users SET can_view_records = 1 WHERE can_view_records IS NULL")
            cursor.execute("UPDATE users SET can_view_gallery = 1 WHERE can_view_gallery IS NULL")
            cursor.execute("UPDATE users SET can_chat = 1 WHERE can_chat IS NULL")
            cursor.execute("UPDATE users SET can_view_map = 1 WHERE can_view_map IS NULL")
            cursor.execute("UPDATE users SET can_view_calendar = 1 WHERE can_view_calendar IS NULL")
            cursor.execute("UPDATE users SET can_archive = 1 WHERE can_archive IS NULL")
            cursor.execute("UPDATE users SET can_view_archive = 1 WHERE can_view_archive IS NULL")

            conn.commit()

    def run_maintenance(self):
        """Führt Datenbank-Wartung aus (VACUUM und ANALYZE)"""
        try:
            with self.get_connection() as conn:
                conn.execute("VACUUM")
                conn.execute("ANALYZE")
                logger.info("Datenbank-Wartung (VACUUM/ANALYZE) erfolgreich durchgeführt.")
                return True
        except Exception as e:
            logger.error(f"Fehler bei Datenbank-Wartung: {e}")
            return False
    
    def get_next_record_number(self, user_id):
        """Generiert die kleinste freie Nummer aus dem Pool (1-100.000.000)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Kleinstmögliche freie Nummer finden
            start_number = RECORD_START_NUMBER
            max_pool = RECORD_MAX_POOL
            
            # Optimierung: Prüfen ob Lücken zwischen RECORD_START_NUMBER und der höchsten verwendeten Nummer existieren
            cursor.execute('SELECT MAX(number) as max_used FROM used_numbers')
            result = cursor.fetchone()
            max_used = result['max_used'] if result and result['max_used'] else start_number - 1
            
            # Wenn keine Nummern verwendet sind, mit RECORD_START_NUMBER beginnen
            if max_used < start_number:
                next_number = start_number
            else:
                # Kleinstmögliche freie Nummer finden
                # Methode: Wir suchen die kleinste Nummer ab RECORD_START_NUMBER die nicht in used_numbers ist
                cursor.execute('''
                    SELECT MIN(n) as next_free
                    FROM (
                        SELECT number + 1 as n
                        FROM used_numbers
                        WHERE number >= ?
                        AND number + 1 NOT IN (SELECT number FROM used_numbers)
                        AND number + 1 <= ?
                        UNION
                        SELECT ? as n
                        WHERE ? NOT IN (SELECT number FROM used_numbers)
                    )
                    WHERE n IS NOT NULL
                    ORDER BY n ASC
                    LIMIT 1
                ''', (start_number, max_pool, start_number, start_number))
                
                result = cursor.fetchone()
                if result and result['next_free']:
                    next_number = result['next_free']
                else:
                    # Keine Lücke gefunden, nächste nach der höchsten verwenden
                    next_number = max_used + 1
                    if next_number > max_pool:
                        raise Exception("Nummern-Pool erschöpft (9 Millionen Nummern erreicht)")
            
            # Nummer als verwendet markieren
            cursor.execute('''
                INSERT INTO used_numbers (number, used_at, used_by)
                VALUES (?, datetime('now'), ?)
            ''', (next_number, user_id))
            
            conn.commit()
            return str(next_number)
    
    def mark_reservation_used(self, number, user_id):
        """Nicht mehr benötigt - Nummer wird direkt bei Vergabe als verwendet markiert"""
        # Diese Funktion wird für Kompatibilität behalten, tut aber nichts mehr
        pass
    
    def verify_user_credentials(self, username, password):
        """Überprüft Benutzeranmeldedaten mit bcrypt"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, password_hash, role, active, can_read, can_write, can_delete, can_download, can_upload
                FROM users WHERE username = ? AND active = 1
            ''', (username,))
            
            user = cursor.fetchone()
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                return dict(user)
            return None
    
    def update_last_login(self, user_id):
        """Aktualisiert den letzten Login eines Benutzers"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET last_login = ? WHERE id = ?
            ''', (datetime.now().isoformat(), user_id))
            conn.commit()
    
    def get_user_by_token(self, token):
        """Sucht Benutzer anhand des Tokens in user_sessions"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.* FROM users u
                JOIN user_sessions s ON u.id = s.user_id
                WHERE s.device_id = ? AND s.last_activity > datetime('now', '-5 minutes')
            ''', (token,))
            user = cursor.fetchone()
            return dict(user) if user else None
    
    # --- User-Verwaltung ---
    
    def list_users(self):
        """Listet alle Benutzer auf"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, role, active, created_at, last_login,
                       can_read, can_write, can_delete, can_download, can_upload, can_fill_forms,
                       can_set_category, can_set_status, can_set_border_color, can_set_reminder, can_delete_termine,
                       can_set_erinnerung, can_delete_erinnerung, can_set_note, can_archive,
                       can_view_stats, can_view_records, can_view_gallery, can_chat, can_view_map, can_view_calendar, can_view_assistant, can_view_archive, signature, is_online
                FROM users ORDER BY username
            ''')
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_user(self, user_id):
        """Holt einen einzelnen Benutzer"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, role, active, created_at, last_login,
                       can_read, can_write, can_delete, can_download, can_upload, can_fill_forms,
                       can_set_category, can_set_status, can_set_border_color, can_set_reminder, can_delete_termine,
                       can_set_erinnerung, can_delete_erinnerung, can_set_note, can_archive,
                       can_view_stats, can_view_records, can_view_gallery, can_chat, can_view_map, can_view_calendar, can_view_assistant, can_view_archive, signature
                FROM users WHERE id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id):
        """Alias für get_user - holt einen einzelnen Benutzer anhand der ID"""
        return self.get_user(user_id)
    
    def create_user(self, username, password, role='user', can_read=1, can_write=1, can_delete=0, can_download=1, can_upload=1, can_fill_forms=1,
                    can_set_category=1, can_set_status=1, can_set_border_color=1, can_set_reminder=1, can_delete_termine=1,
                    can_set_erinnerung=1, can_delete_erinnerung=1, can_set_note=1, can_archive=1,
                    can_view_stats=1, can_view_records=1, can_view_gallery=1, can_chat=1, can_view_map=1, can_view_calendar=1, can_view_assistant=1, can_view_archive=1):
        """Erstellt einen neuen Benutzer mit bcrypt"""
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, active, can_read, can_write, can_delete, can_download, can_upload,
                                       can_fill_forms, can_set_category, can_set_status, can_set_border_color, can_set_reminder, can_delete_termine,
                                       can_set_erinnerung, can_delete_erinnerung, can_set_note, can_archive,
                                       can_view_stats, can_view_records, can_view_gallery, can_chat, can_view_map, can_view_calendar, can_view_assistant, can_view_archive,
                                       signature, logged_in)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (username, password_hash, role, 1, can_read, can_write, can_delete, can_download, can_upload,
                      can_fill_forms, can_set_category, can_set_status, can_set_border_color, can_set_reminder, can_delete_termine,
                      can_set_erinnerung, can_delete_erinnerung, can_set_note, can_archive,
                      can_view_stats, can_view_records, can_view_gallery, can_chat, can_view_map, can_view_calendar, can_view_assistant, can_view_archive,
                      None, 0))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                raise ValueError(f"Benutzername '{username}' existiert bereits")
    
    def update_user(self, user_id, **fields):
        """Aktualisiert Benutzerdaten"""
        allowed = ['username', 'role', 'active', 'can_read', 'can_write', 'can_delete', 'can_download', 'can_upload', 'can_fill_forms',
                   'can_set_category', 'can_set_status', 'can_set_border_color', 'can_set_reminder', 'can_delete_termine',
                   'can_set_erinnerung', 'can_delete_erinnerung', 'can_set_note', 'can_archive',
                   'can_view_stats', 'can_view_records', 'can_view_gallery', 'can_chat', 'can_view_map', 'can_view_calendar', 'can_view_assistant', 'can_view_archive', 'signature']
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [user_id]
            cursor.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return cursor.rowcount > 0
    
    # ── Settings Methoden ───────────────────────────────────
    def get_setting(self, key, default=None):
        """Holt einen Setting-Wert"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else default

    def set_setting(self, key, value):
        """Setzt einen Setting-Wert"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
            ''', (key, value))
            conn.commit()

    def get_all_settings(self):
        """Gibt alle Settings zurück"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value, updated_at FROM settings ORDER BY key')
            rows = cursor.fetchall()
            return {r['key']: r['value'] for r in rows}

    # ── User Preferences (Filter/Sortierung/Anzeige) ──
    def get_default_user_preferences(self):
        """Standard-Auswahl für neue Nutzer (Admin-Ansichts-Einstellungen + HTML-Defaults)"""
        settings = self.get_all_settings()
        default_filter = settings.get('default_filter') or 'recent30'
        default_sort = settings.get('default_sort') or 'created_desc'
        return {
            'records': {
                'filter': default_filter,
                'sort': default_sort,
                'categoryId': '',
                'searchType': 'all'
            },
            'gallery': {
                'filter': 'all',
                'sort': 'newest',
                'categoryId': '',
                'searchType': 'all'
            },
            'ui': {}
        }

    def get_user_preferences(self, user_id):
        """Holt nutzerspezifische Preferences; legt bei Bedarf Standards an"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT preferences FROM user_preferences WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                try:
                    prefs = json.loads(row['preferences'] or '{}')
                    if isinstance(prefs, dict) and prefs:
                        return prefs
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Ungültige Preferences für user_id={user_id}, setze Defaults")

        defaults = self.get_default_user_preferences()
        self.set_user_preferences(user_id, defaults)
        return defaults

    def set_user_preferences(self, user_id, preferences):
        """Speichert nutzerspezifische Preferences (JSON)"""
        if not isinstance(preferences, dict):
            raise ValueError('Preferences müssen ein Objekt sein')
        payload = json.dumps(preferences, ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_preferences (user_id, preferences, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences = excluded.preferences,
                    updated_at = datetime('now')
            ''', (user_id, payload))
            conn.commit()
        return preferences

    def create_user_session(self, user_id, device_id, ip_address=None):
        """Erstellt eine neue Session für einen Benutzer"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_sessions (user_id, device_id, ip_address, created_at, last_activity)
                VALUES (?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            ''', (user_id, device_id, ip_address))
            conn.commit()

            # Verifizieren dass die Session erstellt wurde
            cursor.execute('SELECT * FROM user_sessions WHERE user_id = ?', (user_id,))
            sessions = cursor.fetchall()

    def delete_user_session(self, user_id, device_id):
        """Löscht eine spezifische Session eines Benutzers"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM user_sessions 
                WHERE user_id = ? AND device_id = ?
            ''', (user_id, device_id))
            conn.commit()
            logger.info(f"Session gelöscht für user_id={user_id}, device_id={device_id}")

    def get_active_session(self, user_id, timeout_minutes=30):
        """Prüft ob ein Benutzer eine aktive Session hat (innerhalb der konfigurierten Zeit)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Wenn timeout_minutes 0 ist, keine Zeitbegrenzung (Session läuft nie ab)
            if timeout_minutes == 0:
                cursor.execute('''
                    SELECT device_id, last_activity FROM user_sessions
                    WHERE user_id = ?
                    ORDER BY last_activity DESC LIMIT 1
                ''', (user_id,))
            else:
                # Prüfen ob eine Session existiert, die in den letzten timeout_minutes aktiv war
                cursor.execute('''
                    SELECT device_id, last_activity FROM user_sessions
                    WHERE user_id = ?
                    AND last_activity > datetime('now', 'localtime', '-{} minutes')
                    ORDER BY last_activity DESC LIMIT 1
                '''.format(timeout_minutes), (user_id,))
            row = cursor.fetchone()
            result = dict(row) if row else None
            return result

    def delete_all_user_sessions(self, user_id):
        """Löscht alle Sessions eines Benutzers (für Login-Überschreibung)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def set_user_logged_in(self, user_id, logged_in):
        """Setzt das logged_in Flag eines Benutzers"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET logged_in = ? WHERE id = ?', (1 if logged_in else 0, user_id))
            conn.commit()

    def update_user_session_activity(self, user_id):
        """Aktualisiert die letzte Aktivität eines Benutzers in user_sessions"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE user_sessions 
                SET last_activity = datetime('now', 'localtime')
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
    
    def cleanup_inactive_sessions_and_locks(self, timeout_minutes=30):
        """Entfernt inaktive Sessions (nach timeout_minutes) und deren Locks"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Abgelaufene Locks immer löschen (unabhängig von Session-Timeout)
            cursor.execute('''
                DELETE FROM record_locks WHERE expires_at < datetime('now', 'localtime')
            ''')
            expired_locks = cursor.rowcount

            if timeout_minutes > 0:
                # Inaktive Sessions finden (keine Aktivität für timeout_minutes)
                cursor.execute('''
                    SELECT DISTINCT user_id FROM user_sessions
                    WHERE last_activity < datetime('now', 'localtime', '-{} minutes')
                '''.format(timeout_minutes))
                inactive_users = [row['user_id'] for row in cursor.fetchall()]

                # Locks dieser inaktiven Benutzer entfernen
                if inactive_users:
                    placeholders = ','.join(['?'] * len(inactive_users))
                    cursor.execute(f'''
                        DELETE FROM record_locks
                        WHERE user_id IN ({placeholders})
                    ''', inactive_users)
                    # Online-Status dieser inaktiven Benutzer zurücksetzen
                    cursor.execute(f'''
                        UPDATE users SET is_online = 0
                        WHERE id IN ({placeholders})
                    ''', inactive_users)

                # Alte Sessions löschen (älter als timeout_minutes)
                cursor.execute('''
                    DELETE FROM user_sessions
                    WHERE last_activity < datetime('now', 'localtime', '-{} minutes')
                '''.format(timeout_minutes))
                deleted_sessions = cursor.rowcount

                conn.commit()
                if deleted_sessions > 0:
                    logger.info(f"Cleanup: {deleted_sessions} inaktive Sessions gelöscht")
                if expired_locks > 0:
                    logger.info(f"Cleanup: {expired_locks} abgelaufene Locks gelöscht")
                return len(inactive_users)
            else:
                # Kein Session-Timeout - nur abgelaufene Locks bereinigen
                # Aber: Online-Status zurücksetzen für Benutzer ohne aktive Session (älter als 5 Minuten)
                cursor.execute('''
                    UPDATE users SET is_online = 0
                    WHERE id NOT IN (
                        SELECT DISTINCT user_id FROM user_sessions
                        WHERE last_activity > datetime('now', 'localtime', '-5 minutes')
                    )
                    AND is_online = 1
                ''')
                offline_users = cursor.rowcount
                
                conn.commit()
                if expired_locks > 0:
                    logger.info(f"Cleanup: {expired_locks} abgelaufene Locks gelöscht")
                if offline_users > 0:
                    logger.info(f"Cleanup: {offline_users} Benutzer auf offline gesetzt (keine aktive Session)")
                return 0

    def delete_user(self, user_id):
        """Löscht einen Benutzer (nicht admin)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row and row['role'] == 'admin':
                raise ValueError("Admin-Benutzer kann nicht gelöscht werden")

            # Zuerst abhängige Datensätze updaten/löschen (richtige Reihenfolge!)
            # 1. Sessions löschen
            try:
                cursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte user_sessions nicht bereinigen: {e}")

            # 2. Preferences löschen
            try:
                cursor.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte user_preferences nicht bereinigen: {e}")

            # 3. Record Locks löschen
            try:
                cursor.execute("DELETE FROM record_locks WHERE user_id = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte record_locks nicht bereinigen: {e}")

            # 4. Used Numbers used_by auf NULL setzen
            try:
                cursor.execute("UPDATE used_numbers SET used_by = NULL WHERE used_by = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte used_numbers nicht bereinigen: {e}")

            # Benutzernamen für Historie sichern, bevor FKs genullt werden
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user_row = cursor.fetchone()
            username = user_row['username'] if user_row else None

            # 5. Attachments uploaded_by auf NULL setzen
            try:
                cursor.execute("UPDATE attachments SET uploaded_by = NULL WHERE uploaded_by = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte attachments nicht bereinigen: {e}")

            # 6. Records: Namen bleiben in created_by_name/updated_by_name erhalten
            if username:
                try:
                    cursor.execute(
                        "UPDATE records SET created_by_name = COALESCE(created_by_name, ?) WHERE created_by = ?",
                        (username, user_id)
                    )
                    cursor.execute(
                        "UPDATE records SET updated_by_name = COALESCE(updated_by_name, ?) WHERE updated_by = ?",
                        (username, user_id)
                    )
                except Exception as e:
                    logger.warning(f"Konnte records Namen nicht bereinigen: {e}")

            try:
                cursor.execute("UPDATE records SET created_by = NULL WHERE created_by = ?", (user_id,))
                cursor.execute("UPDATE records SET updated_by = NULL WHERE updated_by = ?", (user_id,))
                cursor.execute("UPDATE records SET locked_by = NULL WHERE locked_by = ?", (user_id,))
                cursor.execute("UPDATE records SET reminder_assigned_to = NULL WHERE reminder_assigned_to = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte records nicht bereinigen: {e}")

            # 7. Erinnerungen: Name sichern, dann für alle freigeben / Ersteller nullen
            if username:
                try:
                    cursor.execute(
                        "UPDATE reminders SET created_by_name = COALESCE(created_by_name, ?) WHERE created_by = ?",
                        (username, user_id)
                    )
                except Exception as e:
                    logger.warning(f"Konnte reminders Namen nicht bereinigen: {e}")

            try:
                cursor.execute("UPDATE reminders SET assigned_to = NULL WHERE assigned_to = ?", (user_id,))
                cursor.execute("UPDATE reminders SET created_by = NULL WHERE created_by = ?", (user_id,))
            except Exception as e:
                logger.warning(f"Konnte reminders nicht bereinigen: {e}")

            # 8. Categories: created_by auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE categories SET created_by = NULL WHERE created_by = ?", (user_id,))
            except Exception:
                pass
            # 9. Number Sequences: created_by auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE number_sequences SET created_by = NULL WHERE created_by = ?", (user_id,))
            except Exception:
                pass
            # 10. Gallery Images: uploaded_by auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE gallery_images SET uploaded_by = NULL WHERE uploaded_by = ?", (user_id,))
            except Exception:
                pass
            # 11. Gallery Folders: created_by auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE gallery_folders SET created_by = NULL WHERE created_by = ?", (user_id,))
            except Exception:
                pass
            # 12. Chat Rooms: created_by auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE chat_rooms SET created_by = NULL WHERE created_by = ?", (user_id,))
            except Exception:
                pass
            # 13. Chat Messages: user_id auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE chat_messages SET user_id = NULL WHERE user_id = ?", (user_id,))
            except Exception:
                pass
            # 14. Chat Message Reads: sender_id und receiver_id auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE chat_message_reads SET sender_id = NULL WHERE sender_id = ?", (user_id,))
            except Exception:
                pass
            try:
                cursor.execute("UPDATE chat_message_reads SET receiver_id = NULL WHERE receiver_id = ?", (user_id,))
            except Exception:
                pass
            # 15. Archived Records: archived_by auf NULL setzen (wenn Tabelle existiert)
            try:
                cursor.execute("UPDATE archived_records SET archived_by = NULL WHERE archived_by = ?", (user_id,))
            except Exception:
                pass
            # 16. User Impressions: löschen (wenn Tabelle existiert)
            try:
                cursor.execute("DELETE FROM user_impressions WHERE user_id = ?", (user_id,))
            except Exception:
                pass
            # 17. User Clicks: löschen (wenn Tabelle existiert)
            try:
                cursor.execute("DELETE FROM user_clicks WHERE user_id = ?", (user_id,))
            except Exception:
                pass
            # 18. Search Logs: löschen (wenn Tabelle existiert)
            try:
                cursor.execute("DELETE FROM search_logs WHERE user_id = ?", (user_id,))
            except Exception:
                pass
            # 19. Private Messages: löschen (wenn Tabelle existiert)
            try:
                cursor.execute("DELETE FROM private_messages WHERE sender_id = ?", (user_id,))
            except Exception:
                pass
            try:
                cursor.execute("DELETE FROM private_messages WHERE receiver_id = ?", (user_id,))
            except Exception:
                pass

            # Jetzt den Benutzer löschen
            try:
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            except Exception as e:
                logger.error(f"FOREIGN KEY constraint beim Löschen von Benutzer {user_id}: {e}")
                # Versuche herauszufinden, welche Tabelle das Problem verursacht
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                for table in tables:
                    try:
                        cursor.execute(f"PRAGMA foreign_key_list({table})")
                        fks = cursor.fetchall()
                        for fk in fks:
                            if fk[2] == 'users':  # fk[2] ist die referenzierte Tabelle
                                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {fk[3]} = ?", (user_id,))
                                count = cursor.fetchone()[0]
                                if count > 0:
                                    logger.error(f"Problematische Tabelle: {table}, Spalte: {fk[3]}, Einträge: {count}")
                    except Exception:
                        pass
                raise

            conn.commit()
            return cursor.rowcount > 0
    
    def change_password(self, user_id, new_password):
        """Ändert das Passwort eines Benutzers mit bcrypt"""
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET password_hash = ? WHERE id = ?
            ''', (password_hash, user_id))
            conn.commit()
            return cursor.rowcount > 0

    # ── Reminder (Erinnerung) Methoden ─────────────────────────────
    def create_reminder(self, record_id, reminder_date, created_by, assigned_to=None, note=None):
        """Erstellt eine neue Erinnerung"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username FROM users WHERE id = ?', (created_by,))
            user_row = cursor.fetchone()
            created_by_name = user_row['username'] if user_row else None
            cursor.execute('''
                INSERT INTO reminders (record_id, reminder_date, created_by, created_by_name, assigned_to, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (record_id, reminder_date, created_by, created_by_name, assigned_to, note))
            conn.commit()
            return cursor.lastrowid

    def create_reminders_bulk(self, record_ids, reminder_date, created_by, assigned_to=None, note=None):
        """Erstellt Erinnerungn für mehrere Akten (ohne N+1-Abfragen)"""
        if not record_ids:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username FROM users WHERE id = ?', (created_by,))
            user_row = cursor.fetchone()
            created_by_name = user_row['username'] if user_row else None

            eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            cursor.execute(f'''
                SELECT DISTINCT record_id FROM reminders
                WHERE record_id IN ({platzhalter}) AND completed = 0
            ''', eindeutige_ids)
            bereits_aktiv = {row['record_id'] for row in cursor.fetchall()}

            neue_ids = [rid for rid in eindeutige_ids if rid not in bereits_aktiv]
            if neue_ids:
                cursor.executemany('''
                    INSERT INTO reminders (record_id, reminder_date, created_by, created_by_name, assigned_to, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', [
                    (rid, reminder_date, created_by, created_by_name, assigned_to, note)
                    for rid in neue_ids
                ])
            conn.commit()
            return len(neue_ids)

    def delete_termine_bulk(self, record_ids):
        """Löscht alle Kalender-Termine für mehrere Akten"""
        if not record_ids:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            
            # Clear reminder fields from records table (Kalender-Termine)
            cursor.execute(f'''
                UPDATE records 
                SET reminder_date = NULL, 
                    reminder_end_date = NULL, 
                    reminder_repeat = NULL, 
                    reminder_assigned_to = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({platzhalter})
            ''', eindeutige_ids)
            updated_records = cursor.rowcount

            conn.commit()
            # Cache invalidieren
            self.invalidate_records_cache()
            self.invalidate_cache('stats:')
            return updated_records

    def delete_erinnerungn_bulk(self, record_ids):
        """Löscht alle Erinnerungn für mehrere Akten"""
        if not record_ids:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            eindeutige_ids = list(dict.fromkeys([int(x) for x in record_ids]))
            platzhalter = ','.join(['?'] * len(eindeutige_ids))
            
            # Delete from reminders table (Erinnerungn)
            cursor.execute(f'''
                DELETE FROM reminders
                WHERE record_id IN ({platzhalter})
            ''', eindeutige_ids)
            deleted_reminders = cursor.rowcount

            conn.commit()
            # Cache invalidieren
            self.invalidate_records_cache()
            self.invalidate_cache('stats:')
            return deleted_reminders

    def get_all_reminders(self, today_only=False, include_completed=False):
        """Holt alle Erinnerungn (für alle Benutzer)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if today_only:
                if include_completed:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE DATE(r.reminder_date) = DATE('now')
                        ORDER BY r.reminder_date
                    ''')
                else:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE r.completed = 0
                        AND DATE(r.reminder_date) = DATE('now')
                        ORDER BY r.reminder_date
                    ''')
            else:
                if include_completed:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        ORDER BY r.reminder_date
                    ''')
                else:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE r.completed = 0
                        ORDER BY r.reminder_date
                    ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_reminders_for_user(self, user_id, today_only=False, include_completed=False):
        """Holt alle Erinnerungn für einen Benutzer (oder alle, wenn assigned_to NULL)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if today_only:
                if include_completed:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE (r.assigned_to = ? OR r.assigned_to IS NULL)
                        AND DATE(r.reminder_date) = DATE('now')
                        ORDER BY r.reminder_date
                    ''', (user_id,))
                else:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE r.completed = 0
                        AND (r.assigned_to = ? OR r.assigned_to IS NULL)
                        AND DATE(r.reminder_date) = DATE('now')
                        ORDER BY r.reminder_date
                    ''', (user_id,))
            else:
                if include_completed:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE (r.assigned_to = ? OR r.assigned_to IS NULL)
                        ORDER BY r.reminder_date
                    ''', (user_id,))
                else:
                    cursor.execute('''
                        SELECT r.*, rec.number, rec.title, 
                               u.username as assigned_to_username, 
                               COALESCE(r.created_by_name, c.username) as created_by_username
                        FROM reminders r
                        JOIN records rec ON r.record_id = rec.id
                        LEFT JOIN users u ON r.assigned_to = u.id
                        LEFT JOIN users c ON r.created_by = c.id
                        WHERE r.completed = 0
                        AND (r.assigned_to = ? OR r.assigned_to IS NULL)
                        ORDER BY r.reminder_date
                    ''', (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_reminders_for_record(self, record_id):
        """Holt alle Erinnerungn für eine Akte"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT r.*, u.username as assigned_to_username, c.username as created_by_username
                FROM reminders r
                LEFT JOIN users u ON r.assigned_to = u.id
                LEFT JOIN users c ON r.created_by = c.id
                WHERE r.record_id = ?
                ORDER BY r.reminder_date
            ''', (record_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def update_reminder(self, reminder_id, reminder_date=None, assigned_to=None, note=None, completed=None):
        """Aktualisiert eine Erinnerung"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            
            if reminder_date is not None:
                updates.append("reminder_date = ?")
                params.append(reminder_date)
            if assigned_to is not None:
                updates.append("assigned_to = ?")
                params.append(assigned_to)
            if note is not None:
                updates.append("note = ?")
                params.append(note)
            if completed is not None:
                updates.append("completed = ?")
                params.append(completed)
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(reminder_id)
            
            if not updates:
                return False
                
            cursor.execute(f'''
                UPDATE reminders SET {', '.join(updates)} WHERE id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_reminder(self, reminder_id):
        """Löscht eine Erinnerung"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ── Gallery Methods ─────────────────────────────
    def add_gallery_media(self, filename, original_filename, file_size, mime_type, uploaded_by, uploaded_by_name):
        """Fügt ein neues Medium zur Galerie hinzu"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO gallery_media (filename, original_filename, file_size, mime_type, uploaded_by, uploaded_by_name)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (filename, original_filename, file_size, mime_type, uploaded_by, uploaded_by_name))
            conn.commit()
            return cursor.lastrowid

    def get_gallery_media(self):
        """Holt alle Medien aus der Galerie (neueste zuerst)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM gallery_media ORDER BY created_at DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def delete_gallery_media(self, media_id):
        """Löscht ein Medium aus der Galerie"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM gallery_media WHERE id = ?', (media_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_gallery_media_by_id(self, media_id):
        """Holt ein bestimmtes Medium aus der Galerie anhand der ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM gallery_media WHERE id = ?', (media_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ── Rate-Limiting Methoden ─────────────────────────────
    def record_login_attempt(self, username, ip_address, success):
        """Zeichnet einen Login-Versuch auf"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO login_attempts (username, ip_address, success)
                VALUES (?, ?, ?)
            ''', (username, ip_address, 1 if success else 0))
            conn.commit()

    def check_login_rate_limit(self, username, ip_address, max_attempts=5, window_minutes=15):
        """Prüft ob Rate-Limit überschritten wurde"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Alte Einträge löschen (älter als window_minutes)
            cursor.execute('''
                DELETE FROM login_attempts
                WHERE attempt_time < datetime('now', '-' || ? || ' minutes')
            ''', (window_minutes,))
            
            # Fehlgeschlagene Versuche im Zeitfenster zählen
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM login_attempts
                WHERE (username = ? OR ip_address = ?)
                AND success = 0
                AND attempt_time >= datetime('now', '-' || ? || ' minutes')
            ''', (username, ip_address, window_minutes))
            
            result = cursor.fetchone()
            failed_attempts = result['count'] if result else 0
            
            # Ältesten fehlgeschlagenen Versuch finden für Wartezeit-Berechnung
            wait_seconds = 0
            if failed_attempts >= max_attempts:
                cursor.execute('''
                    SELECT attempt_time
                    FROM login_attempts
                    WHERE (username = ? OR ip_address = ?)
                    AND success = 0
                    AND attempt_time >= datetime('now', '-' || ? || ' minutes')
                    ORDER BY attempt_time ASC
                    LIMIT 1
                ''', (username, ip_address, window_minutes))
                oldest = cursor.fetchone()
                if oldest:
                    # Zeit in Sekunden bis zum Ablauf des Zeitfensters (ab dem ältesten Versuch)
                    cursor.execute('''
                        SELECT CAST((julianday(datetime(?, '+' || ? || ' minutes')) - julianday('now')) * 86400 as INTEGER) as seconds
                    ''', (oldest['attempt_time'], window_minutes))
                    wait_result = cursor.fetchone()
                    wait_seconds = wait_result['seconds'] if wait_result else 0

            conn.commit()
            return failed_attempts < max_attempts, failed_attempts, wait_seconds

    # ── Security Logs Methoden ─────────────────────────────
    def add_security_log(self, event_type, severity, message, ip_address=None, username=None):
        """Fügt einen Sicherheits-Log-Eintrag hinzu"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO security_logs (event_type, severity, message, ip_address, username)
                VALUES (?, ?, ?, ?, ?)
            ''', (event_type, severity, message, ip_address, username))
            conn.commit()

    def get_security_logs(self, limit=50, offset=0, event_type=None):
        """Ruft Sicherheits-Log-Einträge ab"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if event_type:
                cursor.execute('''
                    SELECT * FROM security_logs
                    WHERE event_type = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (event_type, limit, offset))
            else:
                cursor.execute('''
                    SELECT * FROM security_logs
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def get_security_logs_count(self):
        """Zählt alle Sicherheits-Log-Einträge"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM security_logs')
            result = cursor.fetchone()
            return result['count'] if result else 0

    def clear_old_security_logs(self, days=30):
        """Löscht alte Sicherheits-Logs (älter als X Tage)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM security_logs
                WHERE created_at < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
