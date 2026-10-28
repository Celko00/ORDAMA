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

Skript zum Erstellen von 20 Testakten für Sonnenschutz-Reparaturen im Raum Bayreuth
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

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

# Testdaten - Adressen im Raum Bayreuth (100km Umkreis)
test_adressen = [
    {
        "adresse": "Markusstraße 15, 95444 Bayreuth",
        "plz": "95444",
        "ort": "Bayreuth",
        "kunde": "Familie Müller",
        "telefon": "0921 123456"
    },
    {
        "adresse": "Kulmbacher Straße 42, 95445 Bayreuth",
        "plz": "95445",
        "ort": "Bayreuth",
        "kunde": "Herr Schmidt",
        "telefon": "0921 234567"
    },
    {
        "adresse": "Bahnhofstraße 8, 95443 Bayreuth",
        "plz": "95443",
        "ort": "Bayreuth",
        "kunde": "Frau Weber",
        "telefon": "0921 345678"
    },
    {
        "adresse": "Ludwigstraße 23, 95447 Bayreuth",
        "plz": "95447",
        "ort": "Bayreuth",
        "kunde": "Herr Fischer",
        "telefon": "0921 456789"
    },
    {
        "adresse": "Maximilianstraße 67, 95448 Bayreuth",
        "plz": "95448",
        "ort": "Bayreuth",
        "kunde": "Familie Wagner",
        "telefon": "0921 567890"
    },
    {
        "adresse": "Hauptstraße 12, 95326 Kulmbach",
        "plz": "95326",
        "ort": "Kulmbach",
        "kunde": "Herr Becker",
        "telefon": "09221 12345"
    },
    {
        "adresse": "Marktplatz 5, 91217 Hersbruck",
        "plz": "91217",
        "ort": "Hersbruck",
        "kunde": "Frau Hoffmann",
        "telefon": "09151 23456"
    },
    {
        "adresse": "Nürnberger Straße 34, 90522 Oberasbach",
        "plz": "90522",
        "ort": "Oberasbach",
        "kunde": "Herr Koch",
        "telefon": "0911 987654"
    },
    {
        "adresse": "Fürther Straße 89, 90762 Fürth",
        "plz": "90762",
        "ort": "Fürth",
        "kunde": "Familie Richter",
        "telefon": "0911 876543"
    },
    {
        "adresse": "Bamberger Straße 17, 96052 Bamberg",
        "plz": "96052",
        "ort": "Bamberg",
        "kunde": "Herr Braun",
        "telefon": "0951 765432"
    },
    {
        "adresse": "Schillerstraße 45, 96450 Coburg",
        "plz": "96450",
        "ort": "Coburg",
        "kunde": "Frau Lorenz",
        "telefon": "09561 54321"
    },
    {
        "adresse": "Goethestraße 28, 07743 Jena",
        "plz": "07743",
        "ort": "Jena",
        "kunde": "Herr Engel",
        "telefon": "03641 654321"
    },
    {
        "adresse": "Theaterstraße 9, 91522 Ansbach",
        "plz": "91522",
        "ort": "Ansbach",
        "kunde": "Familie Neumann",
        "telefon": "0981 43210"
    },
    {
        "adresse": "Königstraße 56, 90402 Nürnberg",
        "plz": "90402",
        "ort": "Nürnberg",
        "kunde": "Herr Schwarz",
        "telefon": "0911 321098"
    },
    {
        "adresse": "Weißenburger Straße 11, 91781 Weißenburg",
        "plz": "91781",
        "ort": "Weißenburg",
        "kunde": "Frau Krüger",
        "telefon": "09141 21098"
    },
    {
        "adresse": "Sonneberger Straße 33, 96515 Sonneberg",
        "plz": "96515",
        "ort": "Sonneberg",
        "kunde": "Herr Voigt",
        "telefon": "03675 10987"
    },
    {
        "adresse": "Erlanger Straße 77, 91054 Erlangen",
        "plz": "91054",
        "ort": "Erlangen",
        "kunde": "Familie Jäger",
        "telefon": "09131 76543"
    },
    {
        "adresse": "Würzburger Straße 19, 97070 Würzburg",
        "plz": "97070",
        "ort": "Würzburg",
        "kunde": "Herr Wolf",
        "telefon": "0931 65432"
    },
    {
        "adresse": "Schweinfurter Straße 52, 97421 Schweinfurt",
        "plz": "97421",
        "ort": "Schweinfurt",
        "kunde": "Frau Berger",
        "telefon": "09721 54321"
    },
    {
        "adresse": "Berliner Straße 3, 95463 Bindlach",
        "plz": "95463",
        "ort": "Bindlach",
        "kunde": "Herr Frank",
        "telefon": "09208 12345"
    },
    {
        "adresse": "Richard-Wagner-Straße 22, 95444 Bayreuth",
        "plz": "95444",
        "ort": "Bayreuth",
        "kunde": "Frau Bauer",
        "telefon": "0921 654321"
    },
    {
        "adresse": "Am Festspielhaus 5, 95444 Bayreuth",
        "plz": "95444",
        "ort": "Bayreuth",
        "kunde": "Herr Klein",
        "telefon": "0921 765432"
    },
    {
        "adresse": "Sternplatz 18, 95445 Bayreuth",
        "plz": "95445",
        "ort": "Bayreuth",
        "kunde": "Familie Lang",
        "telefon": "0921 876543"
    },
    {
        "adresse": "Rotmainstraße 33, 95447 Bayreuth",
        "plz": "95447",
        "ort": "Bayreuth",
        "kunde": "Herr Jung",
        "telefon": "0921 987654"
    },
    {
        "adresse": "Grüner Weg 7, 95448 Bayreuth",
        "plz": "95448",
        "ort": "Bayreuth",
        "kunde": "Frau Schmidt",
        "telefon": "0921 111222"
    },
    {
        "adresse": "Kirchplatz 14, 95326 Kulmbach",
        "plz": "95326",
        "ort": "Kulmbach",
        "kunde": "Herr Berger",
        "telefon": "09221 334455"
    },
    {
        "adresse": "Hofstraße 29, 91301 Forchheim",
        "plz": "91301",
        "ort": "Forchheim",
        "kunde": "Familie Martin",
        "telefon": "09191 556677"
    },
    {
        "adresse": "Erlanger Straße 45, 91052 Erlangen",
        "plz": "91052",
        "ort": "Erlangen",
        "kunde": "Herr Hermann",
        "telefon": "09131 778899"
    },
    {
        "adresse": "Bismarckstraße 12, 90409 Nürnberg",
        "plz": "90409",
        "ort": "Nürnberg",
        "kunde": "Frau König",
        "telefon": "0911 990011"
    },
    {
        "adresse": "Friedrichstraße 67, 90489 Nürnberg",
        "plz": "90489",
        "ort": "Nürnberg",
        "kunde": "Herr Peters",
        "telefon": "0911 223344"
    },
    {
        "adresse": "Mühlweg 8, 90522 Oberasbach",
        "plz": "90522",
        "ort": "Oberasbach",
        "kunde": "Familie Winkler",
        "telefon": "0911 556677"
    },
    {
        "adresse": "Gartenstraße 23, 90762 Fürth",
        "plz": "90762",
        "ort": "Fürth",
        "kunde": "Herr Roth",
        "telefon": "0911 889900"
    },
    {
        "adresse": "Hauptmarkt 16, 96052 Bamberg",
        "plz": "96052",
        "ort": "Bamberg",
        "kunde": "Frau Lange",
        "telefon": "0951 112233"
    },
    {
        "adresse": "Sandstraße 34, 96049 Bamberg",
        "plz": "96049",
        "ort": "Bamberg",
        "kunde": "Herr Pohl",
        "telefon": "0951 445566"
    },
    {
        "adresse": "Steinweg 19, 96450 Coburg",
        "plz": "96450",
        "ort": "Coburg",
        "kunde": "Familie Voigt",
        "telefon": "09561 778899"
    },
    {
        "adresse": "Markt 11, 91522 Ansbach",
        "plz": "91522",
        "ort": "Ansbach",
        "kunde": "Herr Sommer",
        "telefon": "0981 990011"
    },
    {
        "adresse": "Schloßplatz 4, 91781 Weißenburg",
        "plz": "91781",
        "ort": "Weißenburg",
        "kunde": "Frau Berg",
        "telefon": "09141 223344"
    },
    {
        "adresse": "Hindenburgstraße 27, 96515 Sonneberg",
        "plz": "96515",
        "ort": "Sonneberg",
        "kunde": "Herr Sachs",
        "telefon": "03675 556677"
    },
    {
        "adresse": "Theaterplatz 9, 97070 Würzburg",
        "plz": "97070",
        "ort": "Würzburg",
        "kunde": "Familie Richter",
        "telefon": "0931 889900"
    },
    {
        "adresse": "Kaiserstraße 52, 97070 Würzburg",
        "plz": "97070",
        "ort": "Würzburg",
        "kunde": "Herr Busch",
        "telefon": "0931 112233"
    },
    {
        "adresse": "Spitalstraße 15, 97421 Schweinfurt",
        "plz": "97421",
        "ort": "Schweinfurt",
        "kunde": "Frau Kuhn",
        "telefon": "09721 445566"
    },
    {
        "adresse": "Keßlerstraße 38, 97421 Schweinfurt",
        "plz": "97421",
        "ort": "Schweinfurt",
        "kunde": "Herr Bär",
        "telefon": "09721 778899"
    },
    {
        "adresse": "Alte Poststraße 6, 95463 Bindlach",
        "plz": "95463",
        "ort": "Bindlach",
        "kunde": "Familie Glaser",
        "telefon": "09208 990011"
    },
    {
        "adresse": "Hofheimer Straße 21, 63897 Miltenberg",
        "plz": "63897",
        "ort": "Miltenberg",
        "kunde": "Herr Funke",
        "telefon": "09371 223344"
    },
    {
        "adresse": "Untere Gasse 13, 97753 Karlstadt",
        "plz": "97753",
        "ort": "Karlstadt",
        "kunde": "Frau Horn",
        "telefon": "09353 556677"
    },
    {
        "adresse": "Münchner Straße 88, 82319 Starnberg",
        "plz": "82319",
        "ort": "Starnberg",
        "kunde": "Herr Meier",
        "telefon": "08151 667788"
    },
    {
        "adresse": "Seestraße 12, 83278 Traunstein",
        "plz": "83278",
        "ort": "Traunstein",
        "kunde": "Frau Huber",
        "telefon": "08661 889900"
    },
    {
        "adresse": "Ludwigstraße 45, 80538 München",
        "plz": "80538",
        "ort": "München",
        "kunde": "Familie Lehmann",
        "telefon": "089 112233"
    },
    {
        "adresse": "Prinzregentenstraße 23, 80538 München",
        "plz": "80538",
        "ort": "München",
        "kunde": "Herr Müller",
        "telefon": "089 445566"
    },
    {
        "adresse": "Sendlinger Straße 67, 80331 München",
        "plz": "80331",
        "ort": "München",
        "kunde": "Frau Schmidt",
        "telefon": "089 778899"
    }
]

# Status-Optionen
status_optionen = ['offen', 'in Bearbeitung', 'erledigt', 'warten auf Material', 'abgelehnt']

# Kategorien für Sonnenschutz-Reparaturen
kategorien = [
    {"name": "Rollo", "color": "#3498db"},
    {"name": "Markisen", "color": "#e74c3c"},
    {"name": "Raffstore", "color": "#2ecc71"},
    {"name": "Jalousie", "color": "#f39c12"},
    {"name": "Rollladen", "color": "#9b59b6"},
    {"name": "Sonnenschutz", "color": "#1abc9c"},
    {"name": "Motor", "color": "#34495e"},
    {"name": "Gewebe", "color": "#16a085"},
    {"name": "Feder", "color": "#d35400"},
    {"name": "Führungsschienen", "color": "#7f8c8d"}
]

def generate_test_data():
    """Generiert Testdaten für 50 Akten"""
    import random
    test_akten = []
    
    for i, addr in enumerate(test_adressen):
        # Zufälligen Status wählen (verteilt)
        status_index = i % len(status_optionen)
        status = status_optionen[status_index]
        
        # Zufällige Kategorie wählen
        kategorie_index = i % len(kategorien)
        kategorie = kategorien[kategorie_index]
        
        # Titel erstellen - nur Kundenname
        title = addr['kunde']
        
        # Zufällig entscheiden, ob Vermerk hinzugefügt wird (ca. 70% haben Vermerk)
        hat_vermerk = random.random() < 0.7
        
        if hat_vermerk:
            # Inhalt erstellen - kürzer
            content = f"""Tel: {addr['telefon']}
{addr['adresse']}
{kategorie['name']}-Reparatur"""
        else:
            # Kein Vermerk
            content = ""
        
        # Hashtags
        hashtags = "#sonnenschutz #reparatur"
        
        # Rahmenfarbe basierend auf Status (CSS-Klassennamen statt Hex-Werte)
        border_colors = {
            'offen': 'border-yellow',
            'in Bearbeitung': 'border-blue',
            'erledigt': 'border-green',
            'warten auf Material': 'border-yellow',
            'abgelehnt': 'border-red'
        }
        border_color = border_colors.get(status, 'border-gray')
        
        # Erinnerungsdatum (nur für bestimmte Status)
        reminder_date = None
        if status in ['offen', 'in Bearbeitung', 'warten auf Material']:
            reminder_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        test_akten.append({
            'title': title,
            'content': content,
            'address': addr['adresse'],
            'hashtags': hashtags,
            'status': status,
            'border_color': border_color,
            'reminder_date': reminder_date,
            'category_name': kategorie['name'],
            'category_color': kategorie['color']
        })
    
    return test_akten

def insert_test_records():
    """Fügt Testdaten in die Datenbank ein"""
    test_akten = generate_test_data()
    
    # User-ID holen (erster User in der Datenbank)
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users LIMIT 1")
        user_row = cursor.fetchone()
        
        if not user_row:
            print("Kein Benutzer in der Datenbank gefunden. Bitte zuerst einen Benutzer erstellen.")
            return
        
        user_id = user_row['id']
        
        # Username holen
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        username = cursor.fetchone()['username']
    
    # Kategorien erstellen oder abrufen
    category_map = {}
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        for kategorie in kategorien:
            # Prüfen ob Kategorie bereits existiert
            cursor.execute("SELECT id FROM categories WHERE name = ?", (kategorie['name'],))
            existing = cursor.fetchone()
            
            if existing:
                category_map[kategorie['name']] = existing['id']
            else:
                # Neue Kategorie erstellen
                cursor.execute('''
                    INSERT INTO categories (name, color, created_by)
                    VALUES (?, ?, ?)
                ''', (kategorie['name'], kategorie['color'], user_id))
                category_map[kategorie['name']] = cursor.lastrowid
        
        conn.commit()
    
    # Nächste Aktennummer holen
    next_number = db_manager.get_next_record_number(user_id)
    
    # Akten einfügen
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        
        for i, akte in enumerate(test_akten):
            # Aktennummer generieren
            number = str(int(next_number) + i)
            
            # Category ID holen
            category_id = category_map.get(akte['category_name'])
            
            try:
                cursor.execute('''
                    INSERT INTO records (number, title, content, address, hashtags, border_color, status, created_by, created_by_name, updated_by, updated_by_name, reminder_date, category_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    number,
                    akte['title'],
                    akte['content'],
                    akte['address'],
                    akte['hashtags'],
                    akte['border_color'],
                    akte['status'],
                    user_id,
                    username,
                    user_id,
                    username,
                    akte['reminder_date'],
                    category_id
                ))
                
                record_id = cursor.lastrowid
                print(f"Akte {i+1} erstellt: {akte['title']} (Nummer: {number}, Status: {akte['status']}, Kategorie: {akte['category_name']})")
                
            except Exception as e:
                print(f"Fehler beim Erstellen von Akte {i+1}: {e}")
                continue
        
        conn.commit()
    
    print(f"\nErfolgreich {len(test_akten)} Testakten erstellt!")

if __name__ == "__main__":
    print("Erstelle Testakten für Sonnenschutz-Reparaturen im Raum Bayreuth...")
    insert_test_records()
