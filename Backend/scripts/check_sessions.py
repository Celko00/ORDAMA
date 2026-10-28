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
