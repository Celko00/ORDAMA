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

Bild-Hash Logik für Galerie-Ähnlichkeitssuche
Berechnet und verwaltet Bild-Hashes für die Ähnlichkeitssuche in der Galerie
"""

import sqlite3
from pathlib import Path
from PIL import Image
import imagehash
import numpy as np
import json
import cv2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GalleryHashManager:
    """Verwaltet Bild-Hashes für die Ähnlichkeitssuche"""
    
    def __init__(self, db_path, attachments_dir):
        self.db_path = Path(db_path)
        self.attachments_dir = Path(attachments_dir)
    
    def calculate_hashes(self, image_path):
        """Berechnet alle Hashes für ein Bild"""
        try:
            img = Image.open(image_path)
            img = img.convert('RGB')
            
            # Verschiedene Hash-Algorithmen
            phash = str(imagehash.phash(img))
            dhash = str(imagehash.dhash(img))
            whash = str(imagehash.whash(img))
            
            # Farb-Histogramm
            img_small = img.resize((100, 100))
            histogram = img_small.histogram()
            histogram_normalized = np.array(histogram) / np.sum(histogram)
            histogram_json = json.dumps(histogram_normalized.tolist())
            
            # OpenCV für erweiterte Analyse
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            # HSV-Farbraum für bessere Farberkennung
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
            hsv_histogram = cv2.calcHist([hsv], [0, 1, 2], None, [50, 50, 50], [0, 180, 0, 256, 0, 256])
            hsv_histogram = cv2.normalize(hsv_histogram, hsv_histogram).flatten()
            hsv_json = json.dumps(hsv_histogram.tolist())
            
            # Kanten-Erkennung (Canny)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
            
            # Dominante Farben (HSV-basiert)
            h, s, v = cv2.split(hsv)
            dominant_hue = np.argmax(np.bincount(h.flatten()))
            dominant_colors = []
            if 0 <= dominant_hue < 10 or 170 <= dominant_hue <= 180:
                dominant_colors.append('rot')
            elif 10 <= dominant_hue < 25:
                dominant_colors.append('orange')
            elif 25 <= dominant_hue < 35:
                dominant_colors.append('gelb')
            elif 35 <= dominant_hue < 85:
                dominant_colors.append('grün')
            elif 85 <= dominant_hue < 125:
                dominant_colors.append('cyan')
            elif 125 <= dominant_hue < 155:
                dominant_colors.append('blau')
            elif 155 <= dominant_hue < 170:
                dominant_colors.append('lila')
            
            if np.mean(v) > 200:
                dominant_colors.append('hell')
            elif np.mean(v) < 50:
                dominant_colors.append('dunkel')
            
            colors_json = json.dumps(dominant_colors)
            
            return {
                'phash': phash,
                'dhash': dhash,
                'whash': whash,
                'color_histogram': histogram_json,
                'dominant_colors': colors_json,
                'hsv_histogram': hsv_json,
                'edge_density': float(edge_density)
            }
        except Exception as e:
            logger.warning(f"Fehler bei Hash-Berechnung für {image_path}: {e}")
            return None
    
    def generate_missing_hashes(self):
        """Berechnet Hashes für alle Bilder ohne Hashes (Migrationstool)"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Alle Bilder finden ohne Hashes
        cursor.execute('''
            SELECT a.id, a.filename, a.record_id, r.number
            FROM attachments a
            JOIN records r ON a.record_id = r.id
            WHERE a.mime_type LIKE 'image/%'
            AND NOT EXISTS (
                SELECT 1 FROM attachment_hashes h WHERE h.attachment_id = a.id
            )
        ''')
        
        images_without_hashes = cursor.fetchall()
        total = len(images_without_hashes)
        
        if total == 0:
            logger.info("Alle Bilder haben bereits Hashes!")
            conn.close()
            return 0
        
        logger.info(f"{total} Bilder ohne Hashes gefunden. Starte Berechnung...")
        
        processed = 0
        for attachment_id, filename, record_id, record_number in images_without_hashes:
            image_path = self.attachments_dir / str(record_number) / filename
            
            if not image_path.exists():
                logger.warning(f"Bild nicht gefunden: {image_path}")
                continue
            
            hashes = self.calculate_hashes(image_path)
            if hashes:
                cursor.execute('''
                    INSERT OR REPLACE INTO attachment_hashes (
                        attachment_id, record_id, phash, dhash, whash,
                        color_histogram, dominant_colors, hsv_histogram, edge_density
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    attachment_id,
                    record_id,
                    hashes['phash'],
                    hashes['dhash'],
                    hashes['whash'],
                    hashes['color_histogram'],
                    hashes['dominant_colors'],
                    hashes['hsv_histogram'],
                    hashes['edge_density']
                ))
                conn.commit()
                processed += 1
                logger.info(f"[{processed}/{total}] Hashes berechnet für {filename}")
        
        logger.info(f"Fertig! {processed} von {total} Bildern wurden verarbeitet.")
        conn.close()
        return processed
    
    def get_hash_status(self):
        """Gibt Statistik über Hash-Status zurück"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM attachments WHERE mime_type LIKE "image/%"')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM attachment_hashes')
        hashed = cursor.fetchone()[0]
        
        conn.close()
        return {
            'total_images': total,
            'hashed_images': hashed,
            'unhashed_images': total - hashed
        }
    
    def calculate_and_store_hash(self, attachment_id, record_id, filename):
        """Berechnet und speichert Hash für ein einzelnes Bild"""
        image_path = self.attachments_dir / str(record_id) / filename
        
        if not image_path.exists():
            logger.warning(f"Bild nicht gefunden: {image_path}")
            return False
        
        hashes = self.calculate_hashes(image_path)
        if hashes:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO attachment_hashes (
                    attachment_id, record_id, phash, dhash, whash,
                    color_histogram, dominant_colors, hsv_histogram, edge_density
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                attachment_id,
                record_id,
                hashes['phash'],
                hashes['dhash'],
                hashes['whash'],
                hashes['color_histogram'],
                hashes['dominant_colors'],
                hashes['hsv_histogram'],
                hashes['edge_density']
            ))
            conn.commit()
            conn.close()
            return True
        
        return False


# Hilfsfunktion für Kompatibilität mit alten Skripten
def calculate_hashes(image_path):
    """Hilfsfunktion für direkten Aufruf (Kompatibilität)"""
    dummy_manager = GalleryHashManager("", "")
    return dummy_manager.calculate_hashes(image_path)