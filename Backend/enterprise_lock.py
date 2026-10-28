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

Enterprise-Sperrlogik-Modul für ORDAMA
Basierend auf der bewährten Odama Enterprise Sperrlogik
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

class EnterpriseLockManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        
    def get_lock_db_path(self):
        """Pfad zur Lock-Datenbank von Odama Enterprise"""
        base_dir = Path(__file__).parent.parent.parent
        return base_dir / "ORDAMA-ENTERPRICE-1.00" / "Datenbank" / "ordama.db"
    
    def is_record_locked(self, record_id, user_id):
        """Prüft ob Akte für einen Benutzer gesperrt ist (Enterprise-Logik)"""
        try:
            lock_db_path = self.get_lock_db_path()
            if not lock_db_path.exists():
                return False  # Keine Lock-DB vorhanden
            
            conn = sqlite3.connect(str(lock_db_path))
            cursor = conn.cursor()
            
            # Prüfen ob Akte gesperrt ist
            cursor.execute("SELECT locked_by FROM locks WHERE record_id = ?", (record_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0] and result[0] != user_id:
                return True  # Von anderem Benutzer gesperrt
            
            return False  # Nicht gesperrt
            
        except Exception as e:
            print(f"Fehler bei Lock-Prüfung: {e}")
            return False
    
    def lock_record(self, record_id, user_id, duration_minutes=30):
        """Sperrt eine Akte für einen Benutzer (Enterprise-Logik)"""
        try:
            lock_db_path = self.get_lock_db_path()
            lock_db_path.parent.mkdir(parents=True, exist_ok=True)
            
            conn = sqlite3.connect(str(lock_db_path))
            cursor = conn.cursor()
            
            # Lock-Tabelle erstellen falls nicht vorhanden
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS locks (
                    record_id INTEGER PRIMARY KEY,
                    locked_by INTEGER,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Akte sperren
            expires_at = datetime.now() + timedelta(minutes=duration_minutes)
            cursor.execute('''
                INSERT OR REPLACE INTO locks (record_id, locked_by, expires_at)
                VALUES (?, ?, ?)
            ''', (record_id, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            print(f"Akte {record_id} für Benutzer {user_id} gesperrt bis {expires_at}")
            return True
            
        except Exception as e:
            print(f"Fehler beim Sperren: {e}")
            return False
    
    def unlock_record(self, record_id, user_id):
        """Entsperrt eine Akte für einen Benutzer (Enterprise-Logik)"""
        try:
            lock_db_path = self.get_lock_db_path()
            conn = sqlite3.connect(str(lock_db_path))
            cursor = conn.cursor()
            
            # Prüfen ob Benutzer die Akte gesperrt hat
            cursor.execute("SELECT locked_by FROM locks WHERE record_id = ?", (record_id,))
            result = cursor.fetchone()
            
            if result and result[0] == user_id:
                # Akte entsperren
                cursor.execute("DELETE FROM locks WHERE record_id = ?", (record_id,))
                conn.commit()
                print(f"Akte {record_id} von Benutzer {user_id} entsperrt")
                success = True
            else:
                print(f"Benutzer {user_id} kann Akte {record_id} nicht entsperren")
                success = False
            
            conn.close()
            return success
            
        except Exception as e:
            print(f"Fehler beim Entsperren: {e}")
            return False
    
    def get_lock_info(self, record_id):
        """Gibt Lock-Informationen zurück"""
        try:
            lock_db_path = self.get_lock_db_path()
            conn = sqlite3.connect(str(lock_db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT locked_by, locked_at, expires_at 
                FROM locks 
                WHERE record_id = ? AND expires_at > datetime('now')
            ''', (record_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'locked': True,
                    'locked_by': result[0],
                    'locked_at': result[1],
                    'expires_at': result[2]
                }
            else:
                return {'locked': False}
                
        except Exception as e:
            print(f"Fehler bei Lock-Info: {e}")
            return {'locked': False, 'error': str(e)}
