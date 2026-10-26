import gzip
import shutil

# Datenbank aus Backup wiederherstellen
backup_file = r'c:\Users\mkohl\Desktop\ordama\Software-ORDAMA\Backups\db_backups\ordama.db.20260822_201350.gz'
target_file = r'c:\Users\mkohl\Desktop\ordama\Software-ORDAMA\Speicher\Datenbank\ordama.db'

with gzip.open(backup_file, 'rb') as f_in:
    with open(target_file, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

print('Datenbank erfolgreich wiederhergestellt')

# Prüfen ob die Datenbank jetzt funktioniert
import sqlite3
conn = sqlite3.connect(target_file)
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM user_sessions')
count = cursor.fetchone()[0]
print(f'Anzahl Sessions in wiederhergestellter DB: {count}')
conn.close()
