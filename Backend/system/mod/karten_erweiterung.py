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

import json
import math
import re
from pathlib import Path

def berechne_distanz(lat1, lon1, lat2, lon2):
    """
    Berechnet die Entfernung zwischen zwei Punkten auf der Erde in Kilometern.
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def lade_json(pfad):
    if not Path(pfad).exists():
        return None
    with open(pfad, 'r', encoding='utf-8') as f:
        return json.load(f)

def speichere_json(pfad, daten):
    with open(pfad, 'w', encoding='utf-8') as f:
        json.dump(daten, f, indent=4, ensure_ascii=False)

def ist_echte_stadt(name):
    """
    Prüft, ob ein Name wahrscheinlich eine echte Stadt/Gemeinde ist.
    """
    if not name or len(name) < 3:
        return False
        
    # 1. Namen mit Zahlen konsequent ausschließen (z.B. "huck 24", "Route 66")
    if re.search(r"\d", name):
        return False

    # 2. Bundesländer ausschließen
    bundeslaender = [
        "Bayern", "Baden-Württemberg", "Berlin", "Brandenburg", "Bremen", 
        "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen", 
        "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen", 
        "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen"
    ]
    if name in bundeslaender:
        return False
        
    # 3. Firmen, Marken, Berufe und Behörden
    sperr_begriffe = [
        " AG", " GmbH", " KG", " SE", " OHG", " e.V.", " Co. ", "Corp", " mbH", " eG",
        "Conrad", "Siemens", "Telekom", "Elektronik", "Logistik", "Zentrum", "HUK", "huck",
        "Finanzamt", "Amtsgericht", "Schule", "Universität", "Hochschule", "Klinik", "Krankenhaus",
        "Kirche", "Post", "Bank", "Sparkasse", "Bahnhof", "Flughafen", "Hafen",
        "Industrie", "Gewerbe", "Park", "Messe", "Arena", "Stadion", "Museum",
        "Theater", "Oper", "Schloss", "Burg", "Kaserne", "Amt ", "Behörde",
        "Service", "Zentrale", "Verwaltung", "Bund ", "Land ", "Kreis ",
        "Amazon", "Google", "Microsoft", "Apple", "Lidl", "Aldi", "Rewe", "Edeka",
        "Rechtsanwalt", "Notar", "Steuerberater", "Pharma", "Zeitung", "Verlag",
        "Versicherung", "Krankenkasse", "Ersatzkasse", "Consulting", "Engineering",
        "hilfe", "Werk ", " Werk", " Ltd", "Inc.", "Shop", "Markt", "Filiale", 
        "Agentur", "Büro", "Kanzlei", "Studio", "Atelier", "Praxis"
    ]
    for sb in sperr_begriffe:
        if sb.lower() in name.lower():
            return False
            
    # 4. Ortsteile / Spezifische Standorte
    if name.lower().startswith("stadt ") or name.lower().startswith("gemeinde "):
        return False
        
    ortsteil_muster = [
        r"-Nord$", r"-Süd$", r"-Ost$", r"-West$", r" Mitte$", r" Altstadt$",
        r" Hauptbahnhof$", r" Gewerbegebiet$", r" Industriepark$", r" Hbf$",
        r" Bahnhof$", r" Siedlung$", r" Ortsteil$", r" Dorf$", r" Werk$",
        r" Justiz", r" Polizei"
    ]
    
    # Doppelnamen nur zulassen, wenn sie geografisch üblich sind
    if "-" in name and not any(x in name for x in ["Oder", "Main", "Donau", "Inn", "Saale", "Lahn", "Weser", "Elbe"]):
        # Ausnahmen für echte Stadt-Doppelnamen
        if not name in ["Aue-Bad Schlema", "Annaberg-Buchholz", "Idar-Oberstein", "Villingen-Schwenningen"]: 
             return False

    for muster in ortsteil_muster:
        if re.search(muster, name, re.IGNORECASE):
            return False
            
    # 5. Abkürzungen
    if re.search(r"\b[A-Z]{2,}\b", name): 
        return False
        
    if " Dr. " in name or name.startswith("Dr. "):
        return False
        
    return True

def staedte_erweitern():
    base_dir = Path(__file__).parent.parent.parent.parent
    konfig_dir = base_dir / "Konfiguration" / "karte"
    ort_pfad = konfig_dir / "ort.json"
    ref_pfad = konfig_dir / "ref.json"
    
    ort_daten = lade_json(ort_pfad)
    ref_daten = lade_json(ref_pfad) or {}
    
    if not ort_daten:
        print("Fehler: ort.json fehlt.")
        return

    # Liste komplett neu aufbauen, um Fehler wie "huck 24" zu entfernen
    bereinigte_ref = {}
    koordinaten_liste = []
    
    # 1. Große Städte (Level 0) validieren
    for name, daten in ref_daten.items():
        if daten.get("level") == 0 and ist_echte_stadt(name):
            bereinigte_ref[name] = daten
            koordinaten_liste.append((daten["lat"], daten["lon"]))

    print(f"Bestehende valide Hauptorte: {len(bereinigte_ref)}")
    
    # 2. Neue Orte aus ort.json sammeln
    ort_eindeutig = {}
    for eintrag in ort_daten:
        name = eintrag.get("name", "").strip()
        if not name or name in bereinigte_ref:
            continue
            
        if ist_echte_stadt(name):
            if name not in ort_eindeutig:
                ort_eindeutig[name] = {
                    "lat": eintrag["latitude"],
                    "lon": eintrag["longitude"]
                }

    print(f"Validierte neue Kandidaten: {len(ort_eindeutig)}")

    mindestabstand_l1 = 10.0
    mindestabstand_l2 = 5.0
    sortierte_orte = sorted(ort_eindeutig.items())

    neue_l1 = 0
    neue_l2 = 0
    kandidaten_l2 = []

    # Level 1 (10km)
    for name, coords in sortierte_orte:
        lat1, lon1 = coords["lat"], coords["lon"]
        zu_nah = False
        for lat2, lon2 in koordinaten_liste:
            if berechne_distanz(lat1, lon1, lat2, lon2) < mindestabstand_l1:
                zu_nah = True
                break
        
        if not zu_nah:
            bereinigte_ref[name] = {"lat": lat1, "lon": lon1, "level": 1}
            koordinaten_liste.append((lat1, lon1))
            neue_l1 += 1
        else:
            kandidaten_l2.append((name, coords))

    # Level 2 (5km)
    for name, coords in kandidaten_l2:
        lat1, lon1 = coords["lat"], coords["lon"]
        zu_nah = False
        for lat2, lon2 in koordinaten_liste:
            if berechne_distanz(lat1, lon1, lat2, lon2) < mindestabstand_l2:
                zu_nah = True
                break
        
        if not zu_nah:
            bereinigte_ref[name] = {"lat": lat1, "lon": lon1, "level": 2}
            koordinaten_liste.append((lat1, lon1))
            neue_l2 += 1

    print(f"Level 1 Orte hinzugefügt (10km): {neue_l1}")
    print(f"Level 2 Orte hinzugefügt (5km): {neue_l2}")
    print(f"Gesamtzahl Referenzorte: {len(bereinigte_ref)}")

    speichere_json(ref_pfad, bereinigte_ref)
    print(f"Daten erfolgreich in {ref_pfad} aktualisiert.")

if __name__ == "__main__":
    staedte_erweitern()
