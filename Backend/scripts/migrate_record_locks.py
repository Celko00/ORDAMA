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

Migration für record_locks Tabelle - ON DELETE CASCADE hinzufügen
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def migrate_database(db_path):
    """Führt die Migration durch"""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Prüfen ob die Tabelle existiert
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='record_locks'")
        if not cursor.fetchone():
            logger.info("record_locks Tabelle existiert nicht, keine Migration nötig")
            return True
        
        # Prüfen ob ON DELETE CASCADE bereits vorhanden ist
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='record_locks'")
        table_sql = cursor.fetchone()[0]
        
        if 'ON DELETE CASCADE' in table_sql:
            logger.info("record_locks Tabelle hat bereits ON DELETE CASCADE")
            return True
        
        logger.info("Starte Migration für record_locks Tabelle...")
        
        # 1. Temporäre Tabelle erstellen
        cursor.execute('''
            CREATE TABLE record_locks_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # 2. Daten kopieren
        cursor.execute('''
            INSERT INTO record_locks_new (id, record_id, user_id, locked_at, expires_at)
            SELECT id, record_id, user_id, locked_at, expires_at FROM record_locks
        ''')
        
        # 3. Alte Tabelle löschen
        cursor.execute('DROP TABLE record_locks')
        
        # 4. Neue Tabelle umbenennen
        cursor.execute('ALTER TABLE record_locks_new RENAME TO record_locks')
        
        conn.commit()
        logger.info("Migration erfolgreich abgeschlossen")
        return True
        
    except Exception as e:
        logger.error(f"Fehler bei der Migration: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    # Datenbankpfad aus Konfiguration oder Argument
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        db_path = Path('./Speicher/Datenbank/ordama.db')
    
    logging.basicConfig(level=logging.INFO)
    
    if migrate_database(db_path):
        print("Migration erfolgreich")
    else:
        print("Migration fehlgeschlagen")
        sys.exit(1)
