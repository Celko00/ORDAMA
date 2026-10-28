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

Schema Manager für ORDAMA
- Tabellenerstellung und Schema-Management
- Datenbank-Migrationen
- Index-Erstellung für Performance-Optimierung
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


class SchemaManager:
    """Verwaltet Datenbank-Schema, Tabellen und Migrationen"""
    
    def __init__(self, db_connection_provider):
        """
        db_connection_provider: Funktion die eine DB-Verbindung zurückgibt
        """
        self.get_connection = db_connection_provider
    
    def initialize_database(self):
        """Initialisiert die Datenbank mit allen Tabellen"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            self._create_users_table(cursor)
            self._create_records_table(cursor)
            self._create_coordinates_table(cursor)
            self._create_categories_table(cursor)
            self._create_locks_table(cursor)
            self._create_reminders_table(cursor)
            self._create_used_numbers_table(cursor)
            self._create_user_sessions_table(cursor)
            self._create_attachments_table(cursor)
            self._create_attachment_ocr_table(cursor)
            self._create_attachment_hashes_table(cursor)
            self._create_ocr_jobs_table(cursor)
            self._create_form_templates_table(cursor)
            self._create_gallery_media_table(cursor)
            self._create_settings_table(cursor)
            self._create_login_attempts_table(cursor)
            self._create_security_logs_table(cursor)
            self._create_user_preferences_table(cursor)
            self._create_chat_rooms_table(cursor)
            self._create_chat_room_members_table(cursor)
            self._create_chat_messages_table(cursor)
            self._create_private_messages_table(cursor)
            self._create_archive_metadata_table(cursor)
            
            self._add_missing_columns(cursor)
            self._run_migrations(cursor)
            self._create_indexes(cursor)
            self._create_fts_tables(cursor)
            
            conn.commit()
    
    def _create_users_table(self, cursor):
        """Erstellt die Users Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                can_read INTEGER DEFAULT 1,
                can_write INTEGER DEFAULT 1,
                can_delete INTEGER DEFAULT 0,
                can_download INTEGER DEFAULT 1,
                can_upload INTEGER DEFAULT 1,
                can_fill_forms INTEGER DEFAULT 1,
                can_set_category INTEGER DEFAULT 1,
                can_set_status INTEGER DEFAULT 1,
                can_set_border_color INTEGER DEFAULT 1,
                can_set_reminder INTEGER DEFAULT 1,
                can_delete_termine INTEGER DEFAULT 1,
                can_set_erinnerung INTEGER DEFAULT 1,
                can_delete_erinnerung INTEGER DEFAULT 1,
                can_set_note INTEGER DEFAULT 1,
                can_archive INTEGER DEFAULT 1,
                can_view_stats INTEGER DEFAULT 1,
                can_view_records INTEGER DEFAULT 1,
                can_view_gallery INTEGER DEFAULT 1,
                can_chat INTEGER DEFAULT 1,
                can_view_map INTEGER DEFAULT 1,
                can_view_calendar INTEGER DEFAULT 1,
                can_view_assistant INTEGER DEFAULT 1,
                can_view_archive INTEGER DEFAULT 1,
                signature TEXT,
                active INTEGER DEFAULT 1,
                logged_in INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')

        # Add missing columns to existing users table
        missing_columns = [
            ('can_fill_forms', 'INTEGER DEFAULT 1'),
            ('can_set_category', 'INTEGER DEFAULT 1'),
            ('can_set_status', 'INTEGER DEFAULT 1'),
            ('can_set_border_color', 'INTEGER DEFAULT 1'),
            ('can_set_reminder', 'INTEGER DEFAULT 1'),
            ('can_delete_termine', 'INTEGER DEFAULT 1'),
            ('can_set_erinnerung', 'INTEGER DEFAULT 1'),
            ('can_delete_erinnerung', 'INTEGER DEFAULT 1'),
            ('can_set_note', 'INTEGER DEFAULT 1'),
            ('can_archive', 'INTEGER DEFAULT 1'),
            ('can_view_stats', 'INTEGER DEFAULT 1'),
            ('can_view_records', 'INTEGER DEFAULT 1'),
            ('can_view_gallery', 'INTEGER DEFAULT 1'),
            ('can_chat', 'INTEGER DEFAULT 1'),
            ('can_view_map', 'INTEGER DEFAULT 1'),
            ('can_view_calendar', 'INTEGER DEFAULT 1'),
            ('can_view_assistant', 'INTEGER DEFAULT 1'),
            ('can_view_archive', 'INTEGER DEFAULT 1'),
            ('is_online', 'INTEGER DEFAULT 0'),
            ('logged_in', 'INTEGER DEFAULT 0'),
        ]
        
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        for col_name, col_def in missing_columns:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                    logger.info(f"Added missing column {col_name} to users table")
                except Exception as e:
                    logger.error(f"Fehler beim Hinzufügen der Spalte {col_name}: {e}")
    
    def _create_records_table(self, cursor):
        """Erstellt die Records Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                hashtags TEXT,
                border_color TEXT,
                status TEXT DEFAULT 'neutral',
                address TEXT,
                archived INTEGER DEFAULT 0,
                locked_by INTEGER,
                locked_at TIMESTAMP,
                created_by INTEGER,
                created_by_name TEXT,
                updated_by INTEGER,
                updated_by_name TEXT,
                reminder_date TIMESTAMP,
                reminder_end_date TIMESTAMP,
                reminder_repeat TEXT,
                reminder_assigned_to INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id),
                FOREIGN KEY (updated_by) REFERENCES users(id),
                FOREIGN KEY (locked_by) REFERENCES users(id),
                FOREIGN KEY (reminder_assigned_to) REFERENCES users(id)
            )
        ''')
    
    def _create_coordinates_table(self, cursor):
        """Erstellt die Koordinaten Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS record_koordinaten (
                record_id INTEGER PRIMARY KEY,
                plz TEXT,
                ort TEXT,
                lat REAL,
                lon REAL,
                aktualisiert_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
            )
        ''')
    
    def _create_categories_table(self, cursor):
        """Erstellt die Categories Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
    
    def _create_locks_table(self, cursor):
        """Erstellt die Locks Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS record_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
    
    def _create_reminders_table(self, cursor):
        """Erstellt die Reminders Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                reminder_date TIMESTAMP NOT NULL,
                assigned_to INTEGER,
                created_by INTEGER,
                created_by_name TEXT,
                note TEXT,
                completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_to) REFERENCES users(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
    
    def _create_used_numbers_table(self, cursor):
        """Erstellt die Used Numbers Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS used_numbers (
                number INTEGER PRIMARY KEY,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_by INTEGER,
                FOREIGN KEY (used_by) REFERENCES users(id)
            )
        ''')
    
    def _create_user_sessions_table(self, cursor):
        """Erstellt die User Sessions Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Migration: ip_address Spalte hinzufügen falls nicht vorhanden
        cursor.execute("PRAGMA table_info(user_sessions)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'ip_address' not in columns:
            cursor.execute("ALTER TABLE user_sessions ADD COLUMN ip_address TEXT")
    
    def _create_attachments_table(self, cursor):
        """Erstellt die Attachments Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT,
                uploaded_by INTEGER,
                order_index INTEGER DEFAULT 0,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES records(id),
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        ''')
    
    def _create_attachment_ocr_table(self, cursor):
        """Erstellt die Attachment OCR Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attachment_ocr (
                attachment_id PRIMARY KEY,
                record_id INTEGER NOT NULL,
                language TEXT DEFAULT 'deu+eng',
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0,
                pages_done INTEGER DEFAULT 0,
                pages_total INTEGER DEFAULT 0,
                ocr_text TEXT,
                ocr_page_map TEXT,
                has_text INTEGER DEFAULT 0,
                error_message TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
            )
        ''')
    
    def _create_attachment_hashes_table(self, cursor):
        """Erstellt die Attachment Hashes Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attachment_hashes (
                attachment_id PRIMARY KEY,
                record_id INTEGER NOT NULL,
                phash TEXT NOT NULL,
                dhash TEXT NOT NULL,
                whash TEXT NOT NULL,
                color_histogram TEXT,
                dominant_colors TEXT,
                hsv_histogram TEXT,
                edge_density REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
            )
        ''')
    
    def _create_ocr_jobs_table(self, cursor):
        """Erstellt die OCR Jobs Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ocr_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attachment_id INTEGER NOT NULL,
                record_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
            )
        ''')
    
    def _create_form_templates_table(self, cursor):
        """Erstellt die Form Templates Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS form_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                structure TEXT NOT NULL,
                next_number INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE form_templates ADD COLUMN next_number INTEGER DEFAULT 1')
        except sqlite3.OperationalError:
            pass
    
    def _create_gallery_media_table(self, cursor):
        """Erstellt die Gallery Media Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gallery_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT,
                uploaded_by INTEGER,
                uploaded_by_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        ''')
    
    def _create_settings_table(self, cursor):
        """Erstellt die Settings Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    def _create_login_attempts_table(self, cursor):
        """Erstellt die Login Attempts Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT,
                attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER DEFAULT 0
            )
        ''')

    def _create_security_logs_table(self, cursor):
        """Erstellt die Security Logs Tabelle für die Sicherheitskonsole"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS security_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'warning',
                message TEXT NOT NULL,
                ip_address TEXT,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def _create_user_preferences_table(self, cursor):
        """Erstellt die User Preferences Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id PRIMARY KEY,
                preferences TEXT NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
    
    def _create_chat_rooms_table(self, cursor):
        """Erstellt die Chat Rooms Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')

    def _create_chat_room_members_table(self, cursor):
        """Erstellt die Chat Room Members Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_room_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(room_id, user_id)
            )
        ''')

    def _create_chat_messages_table(self, cursor):
        """Erstellt die Chat Messages Tabelle"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                file_path TEXT,
                file_name TEXT,
                file_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
    
    def _create_private_messages_table(self, cursor):
        """Erstellt die Private Messages Tabelle für 1-zu-1 Nachrichten"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                sender_username TEXT NOT NULL,
                receiver_username TEXT NOT NULL,
                message TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                file_path TEXT,
                file_name TEXT,
                file_size INTEGER,
                read_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (receiver_id) REFERENCES users(id)
            )
        ''')

    def _create_archive_metadata_table(self, cursor):
        """Erstellt die Archive Metadata Tabelle für separates Archiv-System"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archive_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                archived_by INTEGER,
                archived_by_name TEXT,
                archive_reason TEXT,
                original_folder_path TEXT,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
                FOREIGN KEY (archived_by) REFERENCES users(id),
                UNIQUE(record_id)
            )
        ''')
    
    def _add_missing_columns(self, cursor):
        """Fügt fehlende Spalten zu bestehenden Tabellen hinzu"""
        # border_color Spalte
        try:
            cursor.execute('ALTER TABLE records ADD COLUMN border_color TEXT')
        except sqlite3.OperationalError:
            pass
        
        # reminder_date Spalte
        try:
            cursor.execute('ALTER TABLE records ADD COLUMN reminder_date TIMESTAMP')
        except sqlite3.OperationalError:
            pass
        
        # reminder_end_date Spalte
        try:
            cursor.execute('ALTER TABLE records ADD COLUMN reminder_end_date TIMESTAMP')
        except sqlite3.OperationalError:
            pass
        
        # reminder_repeat Spalte
        try:
            cursor.execute('ALTER TABLE records ADD COLUMN reminder_repeat TEXT')
        except sqlite3.OperationalError:
            pass
        
        # reminder_assigned_to Spalte
        try:
            cursor.execute('ALTER TABLE records ADD COLUMN reminder_assigned_to INTEGER')
        except sqlite3.OperationalError:
            pass
        
        # status Spalte
        try:
            cursor.execute("ALTER TABLE records ADD COLUMN status TEXT DEFAULT 'neutral'")
        except sqlite3.OperationalError:
            pass
        
        # address Spalte
        try:
            cursor.execute("ALTER TABLE records ADD COLUMN address TEXT")
        except sqlite3.OperationalError:
            pass
        
        # category_id Spalte
        try:
            cursor.execute("ALTER TABLE records ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
        except sqlite3.OperationalError:
            pass
        
        # order_index Spalte für Attachments
        try:
            cursor.execute('ALTER TABLE attachments ADD COLUMN order_index INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        
        # OCR-Migrationsspalten
        for table, column, definition in [
            ('attachment_ocr', 'language', "TEXT DEFAULT 'deu+eng'"),
            ('attachment_ocr', 'status', "TEXT DEFAULT 'pending'"),
            ('attachment_ocr', 'progress', "REAL DEFAULT 0"),
            ('attachment_ocr', 'pages_done', "INTEGER DEFAULT 0"),
            ('attachment_ocr', 'pages_total', "INTEGER DEFAULT 0"),
            ('attachment_ocr', 'ocr_text', "TEXT"),
            ('attachment_ocr', 'ocr_page_map', "TEXT"),
            ('attachment_ocr', 'has_text', "INTEGER DEFAULT 0"),
            ('attachment_ocr', 'error_message', "TEXT"),
            ('attachment_ocr', 'updated_at', "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ('attachment_ocr', 'failure_count', "INTEGER DEFAULT 0"),
            ('ocr_jobs', 'priority', "INTEGER DEFAULT 0"),
            ('ocr_jobs', 'started_at', "TIMESTAMP"),
            ('ocr_jobs', 'finished_at', "TIMESTAMP"),
            ('ocr_jobs', 'error_message', "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError:
                pass
        
        # Berechtigungs-Spalten für User
        for col in ['can_read', 'can_write', 'can_delete', 'can_download', 'can_upload', 'can_fill_forms', 'can_set_category', 'can_set_status', 'can_set_border_color', 'can_set_reminder', 'can_delete_termine', 'can_set_erinnerung', 'can_delete_erinnerung', 'can_set_note', 'can_view_stats', 'can_view_records', 'can_view_gallery', 'can_view_map', 'can_view_calendar', 'can_view_assistant', 'signature']:
            try:
                if col == 'signature':
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                else:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass
        
        # Spalten für created_by_name und updated_by_name in records
        for col in ['created_by_name', 'updated_by_name']:
            try:
                cursor.execute(f"ALTER TABLE records ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        
        # Historienname für Erinnerungen
        try:
            cursor.execute('ALTER TABLE reminders ADD COLUMN created_by_name TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute('''
                UPDATE reminders
                SET created_by_name = (SELECT username FROM users WHERE id = reminders.created_by)
                WHERE created_by_name IS NULL AND created_by IS NOT NULL
            ''')
        except Exception as e:
            logger.warning(f"Migration reminders.created_by_name fehlgeschlagen: {e}")
    
    def _run_migrations(self, cursor):
        """Führt Datenbank-Migrationen durch"""
        # Migration: Für bestehende Records created_by_name und updated_by_name füllen
        try:
            cursor.execute('''
                UPDATE records 
                SET created_by_name = (SELECT username FROM users WHERE id = records.created_by)
                WHERE created_by_name IS NULL AND created_by IS NOT NULL
            ''')
            cursor.execute('''
                UPDATE records 
                SET updated_by_name = (SELECT username FROM users WHERE id = records.updated_by)
                WHERE updated_by_name IS NULL AND updated_by IS NOT NULL
            ''')
        except Exception as e:
            logger.warning(f"Migration created_by_name/updated_by_name fehlgeschlagen: {e}")
        
        # Migration: reminders.created_by zu NULLABLE ändern
        try:
            cursor.execute("PRAGMA table_info(reminders)")
            columns = cursor.fetchall()
            created_by_col = [col for col in columns if col[1] == 'created_by']
            if created_by_col and created_by_col[0][3] == 1:
                logger.info("Migriere reminders.created_by zu NULLABLE")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reminders_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_id INTEGER NOT NULL,
                        reminder_date TIMESTAMP NOT NULL,
                        assigned_to INTEGER,
                        created_by INTEGER,
                        created_by_name TEXT,
                        note TEXT,
                        completed INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
                        FOREIGN KEY (assigned_to) REFERENCES users(id),
                        FOREIGN KEY (created_by) REFERENCES users(id)
                    )
                ''')
                cursor.execute('''
                    INSERT INTO reminders_new (id, record_id, reminder_date, assigned_to, created_by, created_by_name, note, completed, created_at, updated_at)
                    SELECT id, record_id, reminder_date, assigned_to, created_by,
                           (SELECT username FROM users WHERE id = reminders.created_by),
                           note, completed, created_at, updated_at FROM reminders
                ''')
                cursor.execute('DROP TABLE reminders')
                cursor.execute('ALTER TABLE reminders_new RENAME TO reminders')
                logger.info("Migration reminders.created_by abgeschlossen")
        except Exception as e:
            logger.warning(f"Migration reminders.created_by fehlgeschlagen: {e}")
        
        # Migration: attachments.uploaded_by zu NULLABLE ändern
        try:
            cursor.execute("PRAGMA table_info(attachments)")
            columns = cursor.fetchall()
            uploaded_by_col = [col for col in columns if col[1] == 'uploaded_by']
            if uploaded_by_col and uploaded_by_col[0][3] == 1:
                logger.info("Migriere attachments.uploaded_by zu NULLABLE")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS attachments_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_id INTEGER NOT NULL,
                        filename TEXT NOT NULL,
                        original_filename TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        mime_type TEXT,
                        uploaded_by INTEGER,
                        order_index INTEGER DEFAULT 0,
                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (record_id) REFERENCES records(id),
                        FOREIGN KEY (uploaded_by) REFERENCES users(id)
                    )
                ''')
                cursor.execute('''
                    INSERT INTO attachments_new (id, record_id, filename, original_filename, file_size, mime_type, uploaded_by, order_index, uploaded_at)
                    SELECT id, record_id, filename, original_filename, file_size, mime_type, uploaded_by, order_index, uploaded_at FROM attachments
                ''')
                cursor.execute('DROP TABLE attachments')
                cursor.execute('ALTER TABLE attachments_new RENAME TO attachments')
                logger.info("Migration attachments.uploaded_by abgeschlossen")
        except Exception as e:
            logger.warning(f"Migration attachments.uploaded_by fehlgeschlagen: {e}")
        
        # Migration: number_reservations zu used_numbers
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='number_reservations'")
            old_table_exists = cursor.fetchone()
            
            if old_table_exists:
                logger.info("Migriere number_reservations zu used_numbers")
                cursor.execute('''
                    INSERT OR IGNORE INTO used_numbers (number, used_at, used_by)
                    SELECT CAST(number AS INTEGER), reserved_at, reserved_by
                    FROM number_reservations 
                    WHERE used = 1
                ''')
                cursor.execute('DROP TABLE number_reservations')
                logger.info("Migration number_reservations → used_numbers abgeschlossen")
        except Exception as e:
            logger.warning(f"Migration number_reservations → used_numbers fehlgeschlagen: {e}")
        
        # Migration: used_numbers mit bestehenden Records initialisieren
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO used_numbers (number, used_at, used_by)
                SELECT CAST(number AS INTEGER), created_at, created_by
                FROM records
                WHERE CAST(number AS INTEGER) NOT IN (SELECT number FROM used_numbers)
            ''')
            logger.info("used_numbers Tabelle mit bestehenden Records initialisiert")
        except Exception as e:
            logger.warning(f"Initialisierung used_numbers fehlgeschlagen: {e}")
    
    def _create_indexes(self, cursor):
        """Erstellt Indizes für Performance-Optimierung"""
        try:
            # Records Indizes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_archived ON records(archived)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_updated_at ON records(updated_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_pinned ON records(pinned)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_reminder_date ON records(reminder_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_status ON records(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_created_at ON records(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_category_id ON records(category_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_title ON records(title)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_border_color ON records(border_color)')
            
            # Kombinierte Indizes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_archived_updated ON records(archived, updated_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_archived_created_by ON records(archived, created_by)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_archived_status ON records(archived, status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_created_by ON records(created_by)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_updated_by ON records(updated_by)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_reminder_end_date ON records(reminder_end_date)')
            
            # Attachments Indizes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_attachments_record_id ON attachments(record_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_attachments_filename ON attachments(filename)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_attachments_original_filename ON attachments(original_filename)')
            
            # OCR Indizes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_attachment_ocr_record_id ON attachment_ocr(record_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_attachment_ocr_status ON attachment_ocr(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ocr_jobs_status_created ON ocr_jobs(status, created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ocr_jobs_attachment_id ON ocr_jobs(attachment_id)')
            
            # Weitere Indizes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_record_koordinaten_plz ON record_koordinaten(plz)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_active ON users(active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_used_numbers_number ON used_numbers(number)')
            
            # Archive Metadata Indizes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_archive_metadata_record_id ON archive_metadata(record_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_archive_metadata_archived_at ON archive_metadata(archived_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_archive_metadata_archived_by ON archive_metadata(archived_by)')
            
            logger.info("Datenbank-Indizes erfolgreich erstellt/aktualisiert")
        except Exception as e:
            logger.warning(f"Einige Indizes konnten nicht erstellt werden: {e}")
    
    def _create_fts_tables(self, cursor):
        """Erstellt FTS5-Tabellen für Volltextsuche"""
        try:
            # Suchprotokollierung
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    search_type TEXT NOT NULL,
                    search_params TEXT,
                    result_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Klick-Tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_result_clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_log_id INTEGER NOT NULL,
                    record_id INTEGER NOT NULL,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (search_log_id) REFERENCES search_logs(id),
                    FOREIGN KEY (record_id) REFERENCES records(id)
                )
            ''')
            
            # Gewichtungs-Konfiguration
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS similarity_weights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    weight_title REAL DEFAULT 1.0,
                    weight_content REAL DEFAULT 1.0,
                    weight_address REAL DEFAULT 0.5,
                    weight_hashtags REAL DEFAULT 0.8,
                    weight_category REAL DEFAULT 0.6,
                    weight_border_color REAL DEFAULT 0.3,
                    weight_status REAL DEFAULT 0.4,
                    weight_attachments REAL DEFAULT 0.5,
                    weight_ocr_text REAL DEFAULT 0.7,
                    weight_creation_date REAL DEFAULT 0.2,
                    weight_update_date REAL DEFAULT 0.3,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Lern-Statistiken
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    factor_name TEXT NOT NULL,
                    click_count INTEGER DEFAULT 0,
                    total_impressions INTEGER DEFAULT 0,
                    click_rate REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Indizes für Lern-System
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_logs_user ON search_logs(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_logs_created ON search_logs(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_result_clicks_search ON search_result_clicks(search_log_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_result_clicks_record ON search_result_clicks(record_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_similarity_weights_user ON similarity_weights(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_learning_statistics_user_factor ON learning_statistics(user_id, factor_name)')
            
            # Standard-Gewichtungen einfügen
            cursor.execute('SELECT COUNT(*) FROM similarity_weights WHERE user_id IS NULL')
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO similarity_weights 
                    (user_id, weight_title, weight_content, weight_address, weight_hashtags, 
                     weight_category, weight_border_color, weight_status, weight_attachments,
                     weight_ocr_text, weight_creation_date, weight_update_date)
                    VALUES 
                    (NULL, 1.0, 1.0, 0.5, 0.8, 0.6, 0.3, 0.4, 0.5, 0.7, 0.2, 0.3)
                ''')
            
            # FTS5 für Records
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                    title, content, number, hashtags, address,
                    content=records, content_rowid=id
                )
            ''')
            cursor.execute('DROP TRIGGER IF EXISTS trg_records_ai')
            cursor.execute('DROP TRIGGER IF EXISTS trg_records_ad')
            cursor.execute('DROP TRIGGER IF EXISTS trg_records_au')
            cursor.execute('''
                CREATE TRIGGER trg_records_ai
                AFTER INSERT ON records
                BEGIN
                    INSERT INTO records_fts(rowid, id, title, content, address, hashtags)
                    VALUES (new.id, new.id, COALESCE(new.title, ''), COALESCE(new.content, ''), COALESCE(new.address, ''), COALESCE(new.hashtags, ''));
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER trg_records_ad
                AFTER DELETE ON records
                BEGIN
                    DELETE FROM records_fts
                    WHERE rowid = old.id;
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER trg_records_au
                AFTER UPDATE ON records
                BEGIN
                    DELETE FROM records_fts
                    WHERE rowid = old.id;
                    INSERT INTO records_fts(rowid, id, title, content, address, hashtags)
                    VALUES (new.id, new.id, COALESCE(new.title, ''), COALESCE(new.content, ''), COALESCE(new.address, ''), COALESCE(new.hashtags, ''));
                END
            ''')
            
            # FTS5 für Attachments OCR
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS attachment_ocr_fts USING fts5(
                    ocr_text,
                    content=attachment_ocr, content_rowid=attachment_id
                )
            ''')
            cursor.execute('DROP TRIGGER IF EXISTS trg_attachment_ocr_ai')
            cursor.execute('DROP TRIGGER IF EXISTS trg_attachment_ocr_ad')
            cursor.execute('DROP TRIGGER IF EXISTS trg_attachment_ocr_au')
            cursor.execute('''
                CREATE TRIGGER trg_attachment_ocr_ai
                AFTER INSERT ON attachment_ocr
                BEGIN
                    INSERT INTO attachment_ocr_fts(rowid, attachment_id, record_id, ocr_text)
                    VALUES (new.attachment_id, new.attachment_id, new.record_id, COALESCE(new.ocr_text, ''));
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER trg_attachment_ocr_ad
                AFTER DELETE ON attachment_ocr
                BEGIN
                    DELETE FROM attachment_ocr_fts
                    WHERE rowid = old.attachment_id;
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER trg_attachment_ocr_au
                AFTER UPDATE ON attachment_ocr
                BEGIN
                    DELETE FROM attachment_ocr_fts
                    WHERE rowid = old.attachment_id;
                    INSERT INTO attachment_ocr_fts(rowid, attachment_id, record_id, ocr_text)
                    VALUES (new.attachment_id, new.attachment_id, new.record_id, COALESCE(new.ocr_text, ''));
                END
            ''')
            
            # FTS nur bei Bedarf neu aufbauen
            cursor.execute('SELECT COUNT(*) as cnt FROM attachment_ocr_fts')
            fts_count = cursor.fetchone()['cnt']
            cursor.execute('SELECT COUNT(*) as cnt FROM attachment_ocr')
            ocr_count = cursor.fetchone()['cnt']
            if fts_count != ocr_count:
                logger.info(f"FTS5-Index wird neu aufgebaut ({fts_count} → {ocr_count} Einträge)...")
                cursor.execute('DELETE FROM attachment_ocr_fts')
                cursor.execute('''
                    INSERT INTO attachment_ocr_fts(rowid, attachment_id, record_id, ocr_text)
                    SELECT attachment_id, attachment_id, record_id, COALESCE(ocr_text, '')
                    FROM attachment_ocr
                ''')
            
            logger.info("FTS-Tabellen erfolgreich erstellt")
        except Exception as e:
            logger.warning(f"FTS-Tabellen konnten nicht erstellt werden: {e}")
