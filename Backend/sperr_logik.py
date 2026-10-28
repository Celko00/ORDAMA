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

Sperrlogik-Modul fuer ORDAMA - vereinfacht & zuverlaessig
Eine einzige Datenbank, saubere Timeout-Handhabung
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_MINUTES = 30

class SperrManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.lock_timeout_minutes = 2  # 2 Minuten für Heartbeat-basiertes System
    
    def is_record_locked(self, record_id, user_id):
        """Prueft ob Akte fuer diesen Benutzer gesperrt ist (von jemand anderem)"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id FROM record_locks 
                    WHERE record_id = ? AND expires_at > datetime('now', 'localtime')
                ''', (record_id,))
                lock = cursor.fetchone()
                return lock and lock['user_id'] != user_id
        except Exception as e:
            logger.error(f"Fehler bei Lock-Pruefung: {e}")
            return False

    def get_locked_record_ids(self, record_ids, user_id):
        """
        Prüft in einem Query, welche der angegebenen Akten durch jemand anderen gesperrt sind.
        Gibt eine Liste der gesperrten record_ids zurück.
        """
        if not record_ids:
            return []
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                platzhalter = ','.join(['?'] * len(record_ids))
                cursor.execute(f'''
                    SELECT record_id FROM record_locks
                    WHERE record_id IN ({platzhalter})
                      AND expires_at > datetime('now', 'localtime')
                      AND user_id != ?
                ''', list(record_ids) + [user_id])
                return [row['record_id'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Fehler bei Bulk-Lock-Pruefung: {e}")
            return list(record_ids)  # Fail-safe: alle als gesperrt behandeln
    
    def get_lock_info(self, record_id):
        """Gibt Lock-Info zurueck (wer hat gesperrt, wann laeuft ab)"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT l.user_id, l.expires_at, u.username
                    FROM record_locks l
                    LEFT JOIN users u ON l.user_id = u.id
                    WHERE l.record_id = ? AND l.expires_at > datetime('now', 'localtime')
                ''', (record_id,))
                lock = cursor.fetchone()
                if lock:
                    return {
                        'user_id': lock['user_id'],
                        'username': lock['username'],
                        'expires_at': lock['expires_at']
                    }
                return None
        except Exception as e:
            logger.error(f"Fehler bei Lock-Info: {e}")
            return None
    
    def lock_record(self, record_id, user_id):
        """Sperrt eine Akte fuer einen Benutzer"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # Pruefen ob bereits ein Lock dieses Benutzers existiert
                cursor.execute('''
                    SELECT user_id FROM record_locks 
                    WHERE record_id = ? AND user_id = ? AND expires_at > datetime('now', 'localtime')
                ''', (record_id, user_id))
                existing_lock = cursor.fetchone()
                
                if existing_lock:
                    # Lock bereits vorhanden - nur verlaengern
                    cursor.execute('''
                        UPDATE record_locks 
                        SET expires_at = datetime('now', 'localtime', '+{} minutes')
                        WHERE record_id = ? AND user_id = ?
                    '''.format(self.lock_timeout_minutes), (record_id, user_id))
                    conn.commit()
                    return True
                
                # Neuen Lock setzen mit konfiguriertem Timeout
                cursor.execute('''
                    INSERT INTO record_locks (record_id, user_id, expires_at)
                    VALUES (?, ?, datetime('now', 'localtime', '+{} minutes'))
                '''.format(self.lock_timeout_minutes), (record_id, user_id))
                conn.commit()
            logger.info(f"Akte {record_id} fuer Benutzer {user_id} gesperrt")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Sperren: {e}")
            return False
    
    def extend_lock(self, record_id, user_id):
        """Verlaengert eine bestehende Sperre um den konfigurierten Timeout"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # Pruefen ob Lock existiert und gehoert
                cursor.execute('''
                    SELECT user_id FROM record_locks 
                    WHERE record_id = ? AND user_id = ? AND expires_at > datetime('now', 'localtime')
                ''', (record_id, user_id))
                lock = cursor.fetchone()
                if lock:
                    # Lock verlaengern
                    cursor.execute('''
                        UPDATE record_locks 
                        SET expires_at = datetime('now', 'localtime', '+{} minutes')
                        WHERE record_id = ? AND user_id = ?
                    '''.format(self.lock_timeout_minutes), (record_id, user_id))
                    conn.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"Fehler beim Verlaengern: {e}")
            return False
    
    def unlock_record(self, record_id, user_id):
        """Entsperrt eine Akte fuer einen Benutzer"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM record_locks 
                    WHERE record_id = ? AND user_id = ?
                ''', (record_id, user_id))
                conn.commit()
                logger.info(f"Akte {record_id} fuer Benutzer {user_id} entsperrt")
                return True
        except Exception as e:
            logger.error(f"Fehler beim Entsperren: {e}")
            return False
    
    def can_unlock_record(self, record_id, user_id):
        """Prueft ob ein Benutzer eine Akte entsperren kann"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id FROM record_locks 
                WHERE record_id = ? AND expires_at > datetime('now', 'localtime')
            ''', (record_id,))
            lock = cursor.fetchone()
            return lock and lock['user_id'] == user_id
    
    def cleanup_expired_locks(self):
        """Entfernt abgelaufene Locks"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM record_locks WHERE expires_at < datetime('now', 'localtime')
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"Fehler beim Cleanup: {e}")
    
    def get_locked_records_count(self):
        """Zaehlt gesperrte Akten"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM records r
                    JOIN record_locks l ON r.id = l.record_id
                    WHERE r.archived = 0 AND l.expires_at > datetime('now', 'localtime')
                ''')
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Fehler beim Zaehlen: {e}")
            return 0
    
    def extend_user_locks(self, user_id):
        """Verlängert alle aktiven Locks eines Benutzers"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE record_locks 
                    SET expires_at = datetime('now', 'localtime', '+{} minutes')
                    WHERE user_id = ? AND expires_at > datetime('now', 'localtime')
                '''.format(self.lock_timeout_minutes), (user_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Fehler beim Verlängern der User-Locks: {e}")
            return False
    
    def release_all_user_locks(self, user_id):
        """Gibt alle Locks eines Benutzers frei (beim Logout oder Admin-Reset)"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM record_locks 
                    WHERE user_id = ?
                ''', (user_id,))
                deleted_count = cursor.rowcount
                conn.commit()
                if deleted_count > 0:
                    logger.info(f"Alle Locks für Benutzer {user_id} freigegeben ({deleted_count} Akten)")
                return deleted_count
        except Exception as e:
            logger.error(f"Fehler beim Freigeben der User-Locks: {e}")
            return 0
