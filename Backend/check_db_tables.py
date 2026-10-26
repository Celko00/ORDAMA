import sqlite3

conn = sqlite3.connect(r'c:\Users\User\Desktop\ORDAMA\Software\Speicher\Datenbank\ordama.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("Tabellen in der Datenbank:")
for table in tables:
    print(f"  - {table[0]}")

# Check if user_preferences exists
if ('user_preferences',) in tables:
    print("\n✅ user_preferences Tabelle existiert")
else:
    print("\n❌ user_preferences Tabelle existiert NICHT")

conn.close()
