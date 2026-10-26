import sqlite3

conn = sqlite3.connect(r'c:\Users\mkohl\Desktop\ordama\Software-ORDAMA\Speicher\Datenbank\ordama.db')
cursor = conn.cursor()

# Alle Sessions anzeigen
cursor.execute('SELECT * FROM user_sessions')
rows = cursor.fetchall()
print(f'Anzahl Sessions: {len(rows)}')
for row in rows:
    print(row)

# Alle Sessions löschen
cursor.execute('DELETE FROM user_sessions')
conn.commit()
print(f'{cursor.rowcount} Sessions gelöscht')

conn.close()
