import sqlite3

conn = sqlite3.connect(r'c:\Users\User\Desktop\ORDAMA\Software\Speicher\Datenbank\ordama.db')
cursor = conn.cursor()

# Get table schema
cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()

print("Spalten in der users Tabelle:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

print(f"\nAnzahl Spalten: {len(columns)}")

conn.close()
