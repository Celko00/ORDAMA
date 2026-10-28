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

Security Events Modul für ORDAMA
- Zentralisierte Logging-Funktion für Sicherheitsereignisse
- Speichert Events in der security_logs Tabelle
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SecurityEventLogger:
    """Verwaltet das Logging von Sicherheitsereignissen"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def log_event(self, event_type: str, severity: str, message: str,
                  ip_address: Optional[str] = None, username: Optional[str] = None,
                  additional_data: Optional[dict] = None):
        """
        Loggt ein Sicherheitsereignis

        Args:
            event_type: Art des Events (z.B. 'rate_limit_exceeded', 'login_failed', 'ip_blocked')
            severity: Schweregrad ('danger', 'warning', 'info')
            message: Beschreibung des Events
            ip_address: IP-Adresse des Users (optional)
            username: Username des Users (optional)
            additional_data: Zusätzliche Daten als JSON (optional)
        """
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Prüfen ob Tabelle existiert
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='security_logs'
                """)
                if not cursor.fetchone():
                    logger.info("Security Logs Tabelle existiert nicht - wird erstellt")
                    self._create_security_logs_table(cursor)
                    conn.commit()
                else:
                    # Prüfen ob additional_data Spalte existiert
                    cursor.execute("PRAGMA table_info(security_logs)")
                    columns = [row[1] for row in cursor.fetchall()]
                    if 'additional_data' not in columns:
                        logger.info("additional_data Spalte fehlt - wird hinzugefügt")
                        cursor.execute("ALTER TABLE security_logs ADD COLUMN additional_data TEXT")
                        conn.commit()

                # Event loggen (ohne additional_data wenn Spalte fehlt)
                cursor.execute("PRAGMA table_info(security_logs)")
                columns = [row[1] for row in cursor.fetchall()]
                has_additional_data = 'additional_data' in columns

                if has_additional_data:
                    cursor.execute("""
                        INSERT INTO security_logs
                        (event_type, severity, message, ip_address, username, additional_data, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        event_type,
                        severity,
                        message,
                        ip_address,
                        username,
                        str(additional_data) if additional_data else None,
                        datetime.now().isoformat()
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO security_logs
                        (event_type, severity, message, ip_address, username, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        event_type,
                        severity,
                        message,
                        ip_address,
                        username,
                        datetime.now().isoformat()
                    ))

                conn.commit()
                logger.info(f"Security Event logged: {event_type} - {message}")

        except Exception as e:
            logger.error(f"Fehler beim Loggen von Security Event: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _create_security_logs_table(self, cursor):
        """Erstellt die security_logs Tabelle wenn sie nicht existiert"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                ip_address TEXT,
                username TEXT,
                additional_data TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Prüfen ob additional_data Spalte existiert (für Kompatibilität mit schema_manager)
        cursor.execute("PRAGMA table_info(security_logs)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'additional_data' not in columns:
            cursor.execute("ALTER TABLE security_logs ADD COLUMN additional_data TEXT")
        
        # Index für Performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_security_logs_created_at 
            ON security_logs(created_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_security_logs_severity 
            ON security_logs(severity)
        """)
    
    # Convenience Methods für häufige Events

    # === SECURITY EVENTS (Sicherheit-Tab) ===
    def log_rate_limit_exceeded(self, ip_address: str, username: Optional[str] = None):
        """Loggt Rate Limit Überschreitung"""
        logger.info(f"Rate Limit Event wird geloggt: IP={ip_address}")
        self.log_event(
            event_type='security',
            severity='warning',
            message='Rate Limit überschritten - Zu viele Anfragen',
            ip_address=ip_address,
            username=username
        )

    def log_login_failed(self, ip_address: str, username: Optional[str] = None, reason: str = ""):
        """Loggt fehlgeschlagenen Login-Versuch"""
        message = f'Login fehlgeschlagen'
        if reason:
            message += f' - {reason}'
        self.log_event(
            event_type='security',
            severity='warning',
            message=message,
            ip_address=ip_address,
            username=username
        )

    def log_ip_blocked(self, ip_address: str, reason: str = ""):
        """Loggt IP-Blocking"""
        message = f'IP blockiert'
        if reason:
            message += f' - {reason}'
        self.log_event(
            event_type='security',
            severity='danger',
            message=message,
            ip_address=ip_address
        )

    def log_unauthorized_access(self, ip_address: str, resource: str, username: Optional[str] = None):
        """Loggt unautorisierten Zugriffsversuch"""
        self.log_event(
            event_type='security',
            severity='danger',
            message=f'Unautorisierter Zugriffsversuch auf {resource}',
            ip_address=ip_address,
            username=username
        )

    # === SYSTEM EVENTS (System-Tab) ===
    def log_system_start(self):
        """Loggt System-Start"""
        self.log_event(
            event_type='system',
            severity='info',
            message='System gestartet'
        )

    def log_admin_action(self, action: str, username: str, ip_address: Optional[str] = None):
        """Loggt Admin-Aktion"""
        self.log_event(
            event_type='system',
            severity='info',
            message=f'Admin-Aktion: {action}',
            ip_address=ip_address,
            username=username
        )

    def log_user_created(self, username: str, created_by: str, ip_address: Optional[str] = None):
        """Loggt User-Erstellung"""
        self.log_event(
            event_type='system',
            severity='info',
            message=f'Benutzer erstellt: {username} von {created_by}',
            ip_address=ip_address,
            username=created_by
        )

    def log_user_deleted(self, username: str, deleted_by: str, ip_address: Optional[str] = None):
        """Loggt User-Löschung"""
        self.log_event(
            event_type='system',
            severity='warning',
            message=f'Benutzer gelöscht: {username} von {deleted_by}',
            ip_address=ip_address,
            username=deleted_by
        )

    def log_password_changed(self, username: str, changed_by: str, ip_address: Optional[str] = None):
        """Loggt Passwort-Änderung"""
        self.log_event(
            event_type='system',
            severity='info',
            message=f'Passwort geändert für: {username} von {changed_by}',
            ip_address=ip_address,
            username=changed_by
        )

    def log_backup_created(self, backup_name: str, username: Optional[str] = None):
        """Loggt Backup-Erstellung"""
        self.log_event(
            event_type='system',
            severity='info',
            message=f'Backup erstellt: {backup_name}',
            username=username
        )

    def log_license_check(self, status: str, valid: bool):
        """Loggt Lizenz-Check"""
        severity = 'info' if valid else 'danger'
        self.log_event(
            event_type='system',
            severity=severity,
            message=f'Lizenz-Check: {status} (Valid: {valid})'
        )

    def log_database_error(self, error: str, operation: str):
        """Loggt Datenbank-Fehler"""
        self.log_event(
            event_type='system',
            severity='danger',
            message=f'Datenbank-Fehler bei {operation}: {error}'
        )

    # === NETWORK EVENTS (Netz-Tab) ===
    def log_server_started(self, host: str, port: int):
        """Loggt Server-Start mit Netzwerk-Info"""
        self.log_event(
            event_type='network',
            severity='info',
            message=f'Server gestartet auf {host}:{port}'
        )

    def log_client_connected(self, ip_address: str, user_agent: Optional[str] = None):
        """Loggt Client-Verbindung"""
        message = f'Client verbunden: {ip_address}'
        if user_agent:
            message += f' ({user_agent[:50]}...)'
        self.log_event(
            event_type='network',
            severity='info',
            message=message,
            ip_address=ip_address
        )
    
    def clear_old_logs(self, days: int = 30):
        """Löscht alte Logs (älter als X Tage)"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM security_logs 
                    WHERE datetime(created_at) < datetime('now', ? || ' days')
                """, (f'-{days}',))
                deleted = cursor.rowcount
                conn.commit()
                logger.info(f'{deleted} alte Security Logs gelöscht (älter als {days} Tage)')
                return deleted
        except Exception as e:
            logger.error(f"Fehler beim Löschen alter Logs: {e}")
            return 0
