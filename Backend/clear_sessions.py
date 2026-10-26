import sqlite3
from pathlib import Path

# Pfad zur Datenbank
db_path = Path(__file__).parent.parent / "Speicher" / "Datenbank" / "ordama.db"

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Alle Sessions löschen
    cursor.execute("DELETE FROM user_sessions")
    conn.commit()
    
    # Überprüfen, ob gelöscht wurde
    cursor.execute("SELECT COUNT(*) FROM user_sessions")
    count = cursor.fetchone()[0]
    
    print(f"Alle Sessions gelöscht. Verbleibende Sessions: {count}")
    
    conn.close()
except Exception as e:
    print(f"Fehler: {e}")
