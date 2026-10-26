"""
Skript zum Löschen der Testakten (Nummern 1033-1052)
"""

import sys
import json
from pathlib import Path

# Pfad zur Datenbank-Konfiguration
base_dir = Path(__file__).parent.parent.parent
config_file = base_dir / "Konfiguration" / "settings.json"

# Konfiguration laden
config = {
    "paths": {
        "data_base_dir": "./Speicher",
        "attachments_dir": ""
    },
    "database": {
        "name": "ordama.db"
    }
}

if config_file.exists():
    with open(config_file, 'r', encoding='utf-8') as f:
        config.update(json.load(f))

# Datenbank-Manager importieren und initialisieren
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import DatabaseManager

db_manager = DatabaseManager(base_dir, config)

def delete_test_records():
    """Löscht Testakten mit Nummern 1000-1049"""
    test_numbers = list(range(1000, 1050))  # 1000 bis 1049
    
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        # Zuerst die IDs der zu löschenden Akten holen
        placeholders = ','.join(['?'] * len(test_numbers))
        cursor.execute(f"SELECT id, number FROM records WHERE number IN ({placeholders})", test_numbers)
        records_to_delete = cursor.fetchall()
        
        if not records_to_delete:
            print("Keine Testakten zum Löschen gefunden.")
            return
        
        record_ids = [r['id'] for r in records_to_delete]
        record_numbers = [r['number'] for r in records_to_delete]
        
        print(f"Finde {len(records_to_delete)} Testakten zum Löschen: {record_numbers}")
        
        # Abhängige Datensätze löschen
        placeholders_ids = ','.join(['?'] * len(record_ids))
        cursor.execute(f"DELETE FROM reminders WHERE record_id IN ({placeholders_ids})", record_ids)
        cursor.execute(f"DELETE FROM attachments WHERE record_id IN ({placeholders_ids})", record_ids)
        cursor.execute(f"DELETE FROM record_locks WHERE record_id IN ({placeholders_ids})", record_ids)
        cursor.execute(f"DELETE FROM record_koordinaten WHERE record_id IN ({placeholders_ids})", record_ids)
        
        # Akten selbst löschen
        cursor.execute(f"DELETE FROM records WHERE id IN ({placeholders_ids})", record_ids)
        
        # Nummern aus used_numbers entfernen
        cursor.execute(f"DELETE FROM used_numbers WHERE number IN ({placeholders})", test_numbers)
        
        conn.commit()
        
        print(f"Erfolgreich {len(records_to_delete)} Testakten gelöscht!")

if __name__ == "__main__":
    print("Lösche Testakten...")
    delete_test_records()
