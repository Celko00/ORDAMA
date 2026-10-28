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
"""

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
