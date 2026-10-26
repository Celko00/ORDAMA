import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Speicher', 'Datenbank', 'ordama.db')
db_path = os.path.normpath(db_path)

print("Verbinde zu DB:", db_path)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n=== Prüfe und migriere reminders ====")

def migrate_table(table_name, old_columns, new_create_sql):
    try:
        print(f"\nMigrationsschritt für Tabelle {table_name}")
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        print(f"Aktuelle Spalten: {cols}")
        
        # 1. Neue Tabelle erstellen
        cursor.execute(new_create_sql)
        
        # 2. Daten kopieren
        cursor.execute(f"INSERT INTO {table_name}_new SELECT * FROM {table_name}")
        
        # 3. Alte Tabelle löschen
        cursor.execute(f"DROP TABLE {table_name}")
        
        # 4. Neue Tabelle umbenennen
        cursor.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")
        
        print(f"Erfolgreich migriert: {table_name}")
        conn.commit()
    except Exception as e:
        print(f"FEHLER bei {table_name}: {e}")
        conn.rollback()

# 1. reminders
migrate_table(
    "reminders",
    ["id", "record_id", "reminder_date", "assigned_to", "created_by", "note", "completed", "created_at", "updated_at"],
    """CREATE TABLE reminders_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER NOT NULL,
        reminder_date TIMESTAMP NOT NULL,
        assigned_to INTEGER,
        created_by INTEGER,
        note TEXT,
        completed INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_to) REFERENCES users(id),
        FOREIGN KEY (created_by) REFERENCES users(id)
    )"""
)

# 2. attachments
migrate_table(
    "attachments",
    ["id", "record_id", "filename", "original_filename", "file_size", "mime_type", "uploaded_by", "order_index", "uploaded_at"],
    """CREATE TABLE attachments_new (
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
    )"""
)

# 3. used_numbers (neue Tabelle ersetzt number_reservations)
# Diese Migration ist nicht mehr nötig, da die neue Tabelle in database.py erstellt wird

conn.commit()
conn.close()
print("\n=== Fertig!")
