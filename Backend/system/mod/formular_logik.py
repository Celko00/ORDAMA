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

Formular-Logik Modul für ORDAMA
"""

import json
import logging
import os
import base64
import re
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class FormularManager:
    def __init__(self, base_dir, db_manager, akten_manager, vorlagen_dir=None):
        self.base_dir = Path(base_dir)
        self.db_manager = db_manager
        self.akten_manager = akten_manager
        self.vorlagen_dir = Path(vorlagen_dir) if vorlagen_dir else self.base_dir / "Formularvorlagen"
        self.vorlagen_dir.mkdir(parents=True, exist_ok=True)

    def _get_template_dir(self, template_id, name):
        """Generiert einen sicheren Ordnerpfad für eine Vorlage"""
        safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip()
        return self.vorlagen_dir / f"{template_id}_{safe_name}"

    def _process_images_in_structure(self, template_dir, structure):
        """Extrahiert Base64-Bilder aus der Struktur und speichert sie als Dateien"""
        if not structure or 'elements' not in structure:
            return structure

        template_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, el in enumerate(structure['elements']):
            if el.get('type') == 'image' and el.get('content', '').startswith('data:image'):
                # Base64 Daten extrahieren
                try:
                    header, data = el['content'].split(',', 1)
                    ext = re.search(r'/(.*?);', header).group(1)
                    if ext == 'jpeg': ext = 'jpg'
                    
                    filename = f"bild_{idx}.{ext}"
                    file_path = template_dir / filename
                    
                    with open(file_path, 'wb') as f:
                        f.write(base64.b64decode(data))
                    
                    # In der Struktur nur den Dateinamen speichern
                    el['content'] = filename
                    logger.info(f"Bild gespeichert: {file_path}")
                except Exception as e:
                    logger.error(f"Fehler beim Speichern des Bildes {idx}: {e}")
        
        return structure

    def _restore_images_in_structure(self, template_dir, structure):
        """Lädt Bilddateien und konvertiert sie zurück in Base64 für das Frontend"""
        if not structure or 'elements' not in structure:
            return structure

        for el in structure.get('elements', []):
            if el.get('type') == 'image' and el.get('content') and not el['content'].startswith('data:'):
                file_path = template_dir / el['content']
                if file_path.exists():
                    try:
                        ext = file_path.suffix.lower().replace('.', '')
                        if ext == 'jpg': ext = 'jpeg'
                        with open(file_path, 'rb') as f:
                            encoded = base64.b64encode(f.read()).decode('utf-8')
                            el['content'] = f"data:image/{ext};base64,{encoded}"
                    except Exception as e:
                        logger.error(f"Fehler beim Laden des Bildes {el['content']}: {e}")
        
        return structure

    def erstelle_vorlage(self, name, structure, user_id):
        """Erstellt eine neue Formularvorlage mit eigenem Ordner für Medien"""
        next_number = structure.get('next_number', 1)
        
        # 1. In DB anlegen um ID zu erhalten
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO form_templates (name, structure, next_number, created_by) VALUES (?, ?, ?, ?)",
                (name, json.dumps(structure), next_number, user_id)
            )
            template_id = cursor.lastrowid
            conn.commit()
            
        # 2. Ordner erstellen und Bilder extrahieren
        template_dir = self._get_template_dir(template_id, name)
        template_dir.mkdir(parents=True, exist_ok=True)
        processed_structure = self._process_images_in_structure(template_dir, structure)
        
        # 3. Struktur in DB und Datei aktualisieren
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE form_templates SET structure = ? WHERE id = ?",
                (json.dumps(processed_structure), template_id)
            )
            conn.commit()

        # Als JSON-Datei im Ordner speichern
        with open(template_dir / "struktur.json", 'w', encoding='utf-8') as f:
            json.dump({'id': template_id, 'name': name, 'structure': processed_structure, 'next_number': next_number}, f, indent=4, ensure_ascii=False)
            
        # Nächste Nummer in einer separaten Datei für schnelles Update ohne DB-Lock
        with open(template_dir / "next_number.txt", 'w', encoding='utf-8') as f:
            f.write(str(next_number))
            
        # Struktur für Frontend wiederherstellen (Base64)
        restored_structure = self._restore_images_in_structure(template_dir, processed_structure)
        return {'id': template_id, 'name': name, 'structure': restored_structure, 'next_number': next_number}

    def update_vorlage(self, template_id, name, structure):
        """Aktualisiert eine bestehende Formularvorlage und ihren Medien-Ordner"""
        next_number = structure.get('next_number', 1)
        vorlage_alt = self.hole_vorlage(template_id)
        if vorlage_alt:
            alter_pfad = self._get_template_dir(template_id, vorlage_alt['name'])
            # Wenn Name sich geändert hat, Ordner umbenennen
            neuer_pfad = self._get_template_dir(template_id, name)
            if alter_pfad.exists() and alter_pfad != neuer_pfad:
                # Eventuelle Konflikte vermeiden
                if neuer_pfad.exists(): shutil.rmtree(neuer_pfad)
                alter_pfad.rename(neuer_pfad)
            template_dir = neuer_pfad
        else:
            template_dir = self._get_template_dir(template_id, name)

        template_dir.mkdir(parents=True, exist_ok=True)
        # Bilder extrahieren
        processed_structure = self._process_images_in_structure(template_dir, structure)

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE form_templates SET name = ?, structure = ?, next_number = ? WHERE id = ?",
                (name, json.dumps(processed_structure), next_number, template_id)
            )
            conn.commit()
            
        # Datei aktualisieren
        with open(template_dir / "struktur.json", 'w', encoding='utf-8') as f:
            json.dump({'id': template_id, 'name': name, 'structure': processed_structure, 'next_number': next_number}, f, indent=4, ensure_ascii=False)
            
        # Nächste Nummer Datei aktualisieren
        with open(template_dir / "next_number.txt", 'w', encoding='utf-8') as f:
            f.write(str(next_number))
            
        # Struktur für Frontend wiederherstellen (Base64)
        restored_structure = self._restore_images_in_structure(template_dir, processed_structure)
        return {'id': template_id, 'name': name, 'structure': restored_structure, 'next_number': next_number}

    def hole_vorlagen(self):
        """Listet alle Formularvorlagen auf und lädt Bilder aus Dateien"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, structure, next_number, created_at FROM form_templates ORDER BY name ASC")
            rows = cursor.fetchall()
            vorlagen = []
            for row in rows:
                vorlage = dict(row)
                structure = json.loads(row['structure'])
                template_dir = self._get_template_dir(vorlage['id'], vorlage['name'])
                
                # Nächste Nummer aus Datei laden, falls vorhanden (aktuellerer Stand)
                num_file = template_dir / "next_number.txt"
                if num_file.exists():
                    try:
                        vorlage['next_number'] = int(num_file.read_text().strip())
                    except (ValueError, IOError) as e:
                        logger.warning(f"Could not read next_number from file in list_vorlagen: {e}")
                
                # Bilder für Frontend wiederherstellen
                vorlage['structure'] = self._restore_images_in_structure(template_dir, structure)
                vorlagen.append(vorlage)
            return vorlagen

    def hole_vorlage(self, template_id):
        """Holt eine spezifische Formularvorlage inkl. Bilder"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, structure, next_number, created_at FROM form_templates WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            if row:
                vorlage = dict(row)
                structure = json.loads(row['structure'])
                template_dir = self._get_template_dir(vorlage['id'], vorlage['name'])
                
                # Nächste Nummer aus Datei laden
                num_file = template_dir / "next_number.txt"
                if num_file.exists():
                    try:
                        vorlage['next_number'] = int(num_file.read_text().strip())
                    except (ValueError, IOError) as e:
                        logger.warning(f"Could not read next_number from file in hole_vorlage: {e}")
                
                vorlage['structure'] = self._restore_images_in_structure(template_dir, structure)
                return vorlage
            return None

    def loesche_vorlage(self, template_id):
        """Löscht eine Formularvorlage und ihren gesamten Ordner"""
        vorlage = self.hole_vorlage(template_id)
        if vorlage:
            template_dir = self._get_template_dir(template_id, vorlage['name'])
            if template_dir.exists():
                shutil.rmtree(template_dir)

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM form_templates WHERE id = ?", (template_id,))
            conn.commit()
            return True

    def speichere_ausgefuelltes_formular(self, record_id, template_id, data, user_id):
        """Speichert ein ausgefülltes Formular als HTML-Anhang"""
        vorlage = self.hole_vorlage(template_id)
        if not vorlage:
            raise ValueError("Vorlage nicht gefunden")

        # Benutzer-Signatur holen
        user = self.db_manager.get_user(user_id)
        user_signature = user.get('signature') if user else None

        # Prüfen auf Auto-Nummer Felder und Zähler erhöhen
        has_autonum = any(el.get('type') == 'autonum' for el in vorlage['structure'].get('elements', []))
        if has_autonum:
            # Den Wert für die Generierung nutzen (den aktuellen Wert vor der Erhöhung)
            current_num = vorlage['next_number']
            next_num = current_num + 1

            # 1. Atomares Inkrement in der Datenbank
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE form_templates SET next_number = ? WHERE id = ?", (next_num, template_id))
                conn.commit()
                
            # 2. Datei im Vorlagen-Ordner aktualisieren
            template_dir = self._get_template_dir(template_id, vorlage['name'])
            template_dir.mkdir(parents=True, exist_ok=True)
            with open(template_dir / "next_number.txt", 'w', encoding='utf-8') as f:
                f.write(str(next_num))

            # 3. Alle autonum Felder in data befüllen
            for el in vorlage['structure'].get('elements', []):
                if el.get('type') == 'autonum':
                    data[el['id']] = str(current_num)

        # HTML-Inhalt generieren
        html_content = self._generiere_html(vorlage['name'], vorlage['structure'], data, user_signature)
        
        # Dateiname generieren
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = "".join([c for c in vorlage['name'] if c.isalnum() or c in (' ', '-', '_')]).strip()
        filename = f"Formular_{safe_name}_{timestamp}.html"
        
        # In Aktenordner speichern
        akten_info = self.akten_manager.get_akte(record_id)
        if not akten_info:
            raise ValueError("Akte nicht gefunden")
        
        akten_nummer = akten_info['number']
        akte_dir = self.akten_manager.akten_dir / akten_nummer
        akte_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = akte_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        # In Datenbank als Anhang registrieren
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT MAX(order_index) as max_idx FROM attachments WHERE record_id = ?", (record_id,))
            max_row = cursor.fetchone()
            next_idx = (max_row['max_idx'] + 1) if (max_row and max_row['max_idx'] is not None) else 0

            cursor.execute('''
                INSERT INTO attachments (
                    record_id, filename, original_filename, 
                    file_size, mime_type, uploaded_by, order_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                record_id,
                filename,
                filename,
                file_path.stat().st_size,
                "text/html",
                user_id,
                next_idx
            ))
            conn.commit()
            
        return {
            'success': True,
            'filename': filename,
            'size': file_path.stat().st_size
        }

    def speichere_pdf_anhang(self, record_id, file_storage, user_id, template_id=None):
        """Speichert eine hochgeladene PDF-Datei als Anhang einer Akte und erhöht ggf. den Zähler"""
        akten_info = self.akten_manager.get_akte(record_id)
        if not akten_info:
            raise ValueError("Akte nicht gefunden")
        
        akten_nummer = akten_info['number']
        akte_dir = self.akten_manager.akten_dir / akten_nummer
        akte_dir.mkdir(parents=True, exist_ok=True)
        
        filename = file_storage.filename
        file_path = akte_dir / filename
        
        file_storage.save(str(file_path))

        # Falls ein Template ID übergeben wurde, prüfen wir auf Auto-Nummer und erhöhen den Zähler
        if template_id:
            vorlage = self.hole_vorlage(template_id)
            if vorlage:
                has_autonum = any(el.get('type') == 'autonum' for el in vorlage['structure'].get('elements', []))
                if has_autonum:
                    next_num = vorlage['next_number'] + 1
                    # 1. Datenbank aktualisieren
                    with self.db_manager.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE form_templates SET next_number = ? WHERE id = ?", (next_num, template_id))
                        conn.commit()
                    
                    # 2. Datei im Vorlagen-Ordner aktualisieren
                    template_dir = self._get_template_dir(template_id, vorlage['name'])
                    template_dir.mkdir(parents=True, exist_ok=True)
                    with open(template_dir / "next_number.txt", 'w', encoding='utf-8') as f:
                        f.write(str(next_num))
            
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT MAX(order_index) as max_idx FROM attachments WHERE record_id = ?", (record_id,))
            max_row = cursor.fetchone()
            next_idx = (max_row['max_idx'] + 1) if (max_row and max_row['max_idx'] is not None) else 0

            cursor.execute('''
                INSERT INTO attachments (
                    record_id, filename, original_filename, 
                    file_size, mime_type, uploaded_by, order_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                record_id,
                filename,
                filename,
                file_path.stat().st_size,
                "application/pdf",
                user_id,
                next_idx
            ))
            attachment_id = cursor.lastrowid
            conn.commit()

        if getattr(self.akten_manager, 'ocr_manager', None) and attachment_id:
            try:
                self.akten_manager.ocr_manager.enqueue_attachment(attachment_id)
            except Exception:
                pass
            
        return {
            'success': True,
            'filename': filename,
            'size': file_path.stat().st_size
        }

    def _generiere_html(self, name, structure, data, user_signature=None):
        """Generiert eine HTML-Ansicht mit absolutem Positioning (WYSIWYG)"""
        width = structure.get('width', 800)
        height = structure.get('height', 1131)
        
        elements_html = ""
        for el in structure.get('elements', []):
            x = el.get('x', 0)
            y = el.get('y', 0)
            w = el.get('width', 'auto')
            style = f"position: absolute; left: {x}px; top: {y}px; "
            
            if el['type'] == 'text':
                fs = el.get('fontSize', '14px')
                fw = 'bold' if el.get('bold') else 'normal'
                content = el.get('content', '')
                # Platzhalter ersetzen
                for k, v in data.items():
                    content = content.replace(f"{{{k}}}", str(v))
                elements_html += f'<div style="{style} font-size: {fs}; font-weight: {fw}; white-space: nowrap;">{content}</div>'
            
            elif el['type'] in ['field', 'autonum', 'date']:
                field_id = el.get('id')
                val = data.get(field_id, '')
                
                # Standard-Datum falls leer
                if el['type'] == 'date' and not val:
                    val = datetime.now().strftime('%d.%m.%Y')
                
                fs = el.get('fontSize', '14px')
                fw = 'bold' if el.get('bold') else 'normal'
                
                # Unterstreichung Logik
                border_style = ""
                if el.get('hasUnderline', True):
                    u_width = el.get('underlineWidth', '100%')
                    if u_width == '100%':
                        border_style = "border-bottom: 1px solid #333;"
                    else:
                        border_style = f"background-image: linear-gradient(to right, #333 {u_width}, transparent {u_width}); background-size: 100% 1px; background-repeat: no-repeat; background-position: bottom;"
                
                elements_html += f'<div style="{style} font-size: {fs}; font-weight: {fw}; width: {w}px; {border_style} min-height: 20px;">{val}</div>'
                if el.get('label'):
                    elements_html += f'<div style="position: absolute; left: {x}px; top: {y-15}px; font-size: 10px; color: #666;">{el["label"]}</div>'
            
            elif el['type'] == 'line':
                is_vert = el.get('orientation') == 'vertical'
                length = el.get('length', 100)
                thick = el.get('thickness', '1px')
                if is_vert:
                    elements_html += f'<div style="{style} width: {thick}; height: {length}px; background: #333;"></div>'
                else:
                    elements_html += f'<div style="{style} width: {length}px; height: {thick}; background: #333;"></div>'
            
            elif el['type'] == 'box':
                elements_html += f'<div style="{style} width: {el.get("width", 100)}px; height: {el.get("height", 100)}px; border: 1px solid #333;"></div>'
            
            elif el['type'] == 'checkbox':
                checked = data.get(el.get('id'), 'false') == 'true'
                check_mark = '&#10003;' if checked else ''
                elements_html += f'<div style="{style} width: {el.get("width", 20)}px; height: {el.get("height", 20)}px; border: 1px solid #333; display: flex; align-items: center; justify-content: center; font-family: DejaVu Sans, Arial; font-size: {int(el.get("width", 20))*0.8}px;">{check_mark}</div>'
            
            elif el['type'] == 'image':
                if el.get('content'):
                    elements_html += f'<img src="{el["content"]}" style="{style} width: {el.get("width", 100)}px; height: {el.get("height", 100)}px; object-fit: contain;">'
            
            elif el['type'] == 'signature':
                sig_w = el.get('width', 200)
                sig_h = el.get('height', 60)
                if user_signature:
                    elements_html += f'<div style="{style} width: {sig_w}px; height: {sig_h}px; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: center; overflow: hidden;"><img src="{user_signature}" style="max-width: 100%; max-height: 100%; object-fit: contain;"></div>'
                else:
                    elements_html += f'<div style="{style} width: {sig_w}px; height: {sig_h}px; border-bottom: 1px solid #333; display: flex; align-items: flex-end; padding-bottom: 5px; font-size: 10px; color: #999; font-style: italic;">X ________________________</div>'

        bg_style = ""
        if structure.get('bg'):
            bg_style = f"background-image: url('{structure['bg']}'); background-size: contain; background-repeat: no-repeat;"

        html = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>{name}</title>
            <style>
                body {{ margin: 0; padding: 0; background: white; }}
                .page {{ 
                    width: {width}px; 
                    height: {height}px; 
                    background: white; 
                    position: relative; 
                    overflow: hidden;
                    {bg_style}
                }}
            </style>
        </head>
        <body>
            <div class="page">
                {elements_html}
            </div>
        </body>
        </html>
        """
        return html
