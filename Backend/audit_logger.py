"""
Audit-Logging Modul für ORDAMA
Speichert Benutzeraktionen (Erstellen, Bearbeiten, Löschen) in einer rotierenden Datei.
"""

import logging
import logging.handlers
from pathlib import Path
import os

class AuditLogger:
    def __init__(self, base_dir):
        self.log_dir = Path(base_dir) / "Logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.log"
        
        # Separater Logger für Audit-Events
        self.logger = logging.getLogger("ordama_audit")
        self.logger.setLevel(logging.INFO)
        
        # Verhindern, dass Audit-Logs in den Haupt-Logger fließen
        self.logger.propagate = False
        
        # Falls bereits Handler existieren (z.B. durch Re-Init), diese entfernen
        if self.logger.handlers:
            self.logger.handlers.clear()
            
        # Rotating File Handler: Max 2MB, 5 Backups (insgesamt ca. 10MB Logs)
        # Wenn voll, wird die älteste Datei überschrieben.
        handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=2 * 1024 * 1024, # 2MB
            backupCount=5,
            encoding='utf-8'
        )
        
        # Sauberes Format für das Logbuch
        formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%d.%m.%Y %H:%M:%S')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def log_action(self, user_name, action, details=""):
        """
        Loggt eine Benutzeraktion.
        Format: BENUTZER | AKTION | DETAILS
        """
        msg = f"{user_name:15} | {action:12} | {details}"
        self.logger.info(msg)
    
    def log_access(self, user_name, endpoint, method, ip_address=""):
        """
        Loggt einen HTTP-Zugriff (nur für Admins sichtbar mit farbiger Markierung).
        Format: BENUTZER | METHOD | ENDPOINT | IP
        """
        msg = f"{user_name:15} | {method:6} | {endpoint:30} | {ip_address}"
        self.logger.info(msg)

    def get_log_content(self):
        """Liest die aktuelle Log-Datei für die Anzeige im Admin-Bereich"""
        if not self.log_file.exists():
            return "Keine Log-Einträge vorhanden."
        
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Fehler beim Lesen der Log-Datei: {e}"
