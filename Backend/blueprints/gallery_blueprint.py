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

Gallery Blueprint - Medien-Galerie
"""

import logging
import uuid
import re
import json
import sys
from collections import Counter
from flask import Blueprint, request, jsonify, session, send_from_directory
from pathlib import Path
from PIL import Image
import imagehash
import numpy as np

# security_utils importieren
sys.path.insert(0, str(Path(__file__).parent.parent))
from security_utils import InputSanitizer, FileUploadValidator

logger = logging.getLogger(__name__)

gallery_bp = Blueprint('gallery', __name__, url_prefix='/api/gallery')


def init_gallery_blueprint(app, auth_manager, db_manager, base_dir, config):
    """Initialisiert das Gallery Blueprint mit den Managern"""

    # Deutsche Füllwörter und Stopwords
    GERMAN_STOPWORDS = {
        'der', 'die', 'das', 'den', 'dem', 'des', 'der', 'die', 'das',
        'ein', 'eine', 'einer', 'eines', 'einem', 'einen', 'eine',
        'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'sie', 'Sie',
        'mein', 'dein', 'sein', 'ihr', 'unser', 'euer', 'ihr',
        'meine', 'deine', 'seine', 'ihre', 'unsere', 'eure',
        'meinen', 'deinen', 'seinen', 'ihren', 'unseren', 'euren',
        'meinem', 'deinem', 'seinem', 'ihrem', 'unserem', 'eurem',
        'meiner', 'deiner', 'seiner', 'ihrer', 'unserer', 'eurer',
        'meines', 'deines', 'seines', 'ihres', 'unseres', 'eures',
        'und', 'oder', 'aber', 'denn', 'sondern', 'wenn', 'wann', 'wie',
        'wo', 'warum', 'weshalb', 'weswegen', 'dass', 'daß', 'ob',
        'weil', 'obwohl', 'während', 'nachdem', 'bevor', 'sobald',
        'in', 'an', 'auf', 'bei', 'mit', 'nach', 'von', 'zu', 'für',
        'über', 'durch', 'aus', 'gegen', 'ohne', 'um', 'entlang',
        'hier', 'dort', 'da', 'dann', 'jetzt', 'später', 'früher',
        'nicht', 'kein', 'keine', 'keiner', 'keines', 'nichts',
        'alle', 'alle', 'allem', 'allen', 'aller', 'alles',
        'viel', 'viele', 'vielem', 'vielen', 'vieler', 'vieles',
        'wenig', 'wenige', 'wenigem', 'wenigen', 'weniger', 'weniges',
        'ganz', 'ganze', 'ganzem', 'ganzen', 'ganzer', 'ganzes',
        'ja', 'nein', 'doch', 'mal', 'schon', 'noch', 'auch',
        'sein', 'haben', 'werden', 'tun', 'machen', 'gehen', 'kommen',
        'sagen', 'sehen', 'wissen', 'können', 'müssen', 'sollen',
        'wollen', 'dürfen', 'mögen', 'dürfen',
        'ist', 'sind', 'war', 'waren', 'wird', 'werden', 'wurde', 'wurden',
        'hat', 'habe', 'haben', 'hatte', 'hatten', 'hast', 'habt',
        'kann', 'kannst', 'können', 'könnte', 'könnten', 'konnte', 'konnten',
        'muss', 'musst', 'müssen', 'müsste', 'müssten', 'musste', 'mussten',
        'soll', 'sollst', 'sollen', 'sollte', 'sollten', 'sollte', 'sollten',
        'will', 'willst', 'wollen', 'wollte', 'wollten', 'wollte', 'wollten',
        'mag', 'magst', 'mögen', 'möchte', 'möchten', 'mochte', 'mochten',
        'durf', 'darfst', 'dürfen', 'dürfte', 'dürften', 'durfte', 'durften',
        'es', 'etwas', 'jemand', 'niemand', 'man', 'einer', 'keiner',
        'sich', 'dir', 'mir', 'uns', 'euch', 'ihnen', 'mich',
        'dieser', 'diese', 'dieses', 'jener', 'jene', 'jenes',
        'welcher', 'welche', 'welches', 'welcher', 'welche', 'welches',
        'jeder', 'jede', 'jedes', 'mancher', 'manche', 'manches',
        'beide', 'beiden', 'beider', 'beides', 'sämtliche', 'sämtlicher',
        'irgend', 'irgendwelche', 'irgendwelcher', 'irgendwelches',
        'ein paar', 'ein bisschen', 'ein wenig', 'viele', 'wenige',
        'etwa', 'circa', 'ungefähr', 'genau', 'kaum', 'fast', 'beinahe',
        'sehr', 'ganz', 'besonders', 'eher', 'vielmehr', 'weniger',
        'mehr', 'am meisten', 'am wenigsten', 'besser', 'schlechter',
        'gut', 'schlecht', 'einfach', 'leicht', 'schwer', 'möglich',
        'unmöglich', 'notwendig', 'wichtig', 'wesentlich', 'bedeutend',
        'neu', 'alt', 'jung', 'groß', 'klein', 'lang', 'kurz', 'hoch', 'tief',
        'breit', 'schmal', 'dick', 'dünn', 'stark', 'schwach', 'hell', 'dunkel',
        'schön', 'hässlich', 'freundlich', 'feindlich', 'gut', 'böse',
        'richtig', 'falsch', 'wahr', 'unwahr', 'echt', 'unecht'
    }

    def normalize_text(text):
        """Normalisiert Text für Vergleichszwecke"""
        if not text:
            return ''
        text = str(text).lower()
        text = re.sub(r'[äöüß]', lambda m: {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}[m.group()], text)
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def extract_keywords(text):
        """Extrahiert relevante Keywords aus Text, entfernt Füllwörter"""
        if not text:
            return set()
        
        words = normalize_text(text).split()
        # Filter out stopwords and short words
        keywords = {word for word in words if word not in GERMAN_STOPWORDS and len(word) > 2}
        return keywords

    def extract_record_metadata(record_data):
        """Extrahiert und kombiniert alle Metadaten aus einer Akte"""
        metadata_parts = []
        
        # Wichtige Felder extrahieren
        if record_data.get('title'):
            metadata_parts.append(record_data['title'])
        if record_data.get('content'):
            metadata_parts.append(record_data['content'])
        if record_data.get('hashtags'):
            metadata_parts.append(record_data['hashtags'])
        if record_data.get('category_name'):
            metadata_parts.append(record_data['category_name'])
        if record_data.get('address'):
            metadata_parts.append(record_data['address'])
        if record_data.get('ocr_text'):
            metadata_parts.append(record_data['ocr_text'])
        
        # Alle Metadaten kombinieren
        combined_text = ' '.join(filter(None, metadata_parts))
        
        # Keywords extrahieren
        return extract_keywords(combined_text)

    def calculate_text_similarity(record1_data, record2_data):
        """Berechnet Text-Ähnlichkeit basierend auf gemeinsamen Keywords aus Akten-Metadaten"""
        if not record1_data or not record2_data:
            return 0
        
        keywords1 = extract_record_metadata(record1_data)
        keywords2 = extract_record_metadata(record2_data)
        
        if not keywords1 or not keywords2:
            return 0
        
        # Jaccard-Ähnlichkeit
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        
        if union == 0:
            return 0
        
        return intersection / union

    def calculate_hash_distance(hash1, hash2):
        """Berechnet Hamming-Distanz zwischen zwei ImageHashes"""
        try:
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            return h1 - h2
        except Exception as e:
            logger.warning(f"Fehler bei Hash-Distanz: {e}")
            return 999

    # Pfad für Akten (Galerie zeigt nur Anhänge aus Akten) – gleicher Pfad wie AktenManager
    data_base_dir_str = config['paths'].get('data_base_dir', './Speicher')
    data_base_dir = Path(data_base_dir_str)
    if not data_base_dir.is_absolute():
        data_base_dir = Path(base_dir) / data_base_dir

    attachments_dir_str = config['paths'].get('attachments_dir', '')
    if attachments_dir_str:
        akten_dir = Path(attachments_dir_str)
        if not akten_dir.is_absolute():
            akten_dir = Path(base_dir) / akten_dir
    else:
        akten_dir = data_base_dir / "Akten"

    ALLOWED_STATUSES = {'neutral', 'offen', 'erledigt', 'bearbeitung'}
    ALLOWED_COLORS = {'', 'border-red', 'border-blue', 'border-yellow', 'border-green', 'border-magenta'}

    @gallery_bp.route('', methods=['GET'])
    @auth_manager.login_required
    def list_media():
        try:
            # Pagination mit konsistenten Limits
            try:
                limit = int(request.args.get('limit', 50))
                offset = int(request.args.get('offset', 0))
            except (ValueError, TypeError):
                limit = 50
                offset = 0
            
            # Validierung: sinnvolle Limits
            limit = max(1, min(limit, 200))
            offset = max(0, offset)
            
            filter_val = request.args.get('filter', 'all')
            sort_val = request.args.get('sort', 'newest')
            category_val = request.args.get('category', '')
            search_val = request.args.get('search', '').strip()
            search_type = request.args.get('search_type', 'all')

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                where_clauses_attachments = []
                params = []

                # Suchtyp-Reiter nur bei Suche anwenden
                if search_val:
                    # Suchbegriff in einzelne Wörter zerlegen für wortreihenfolge-unabhängige Suche
                    import re
                    search_words = re.findall(r'\b\w+\b', search_val.lower())
                    # Stopwörter entfernen
                    stop_words = {'der', 'die', 'das', 'und', 'oder', 'mit', 'für', 'von', 'zu', 'in', 'auf', 'bei', 'als', 'wie', 'im', 'am', 'um', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'eines'}
                    search_words = [w for w in search_words if len(w) > 1 and w not in stop_words]
                    
                    if search_words:
                        if search_type == 'all':
                            word_conditions = []
                            for word in search_words:
                                pattern = f'%{word}%'
                                word_conditions.append('(a.original_filename LIKE ? OR a.filename LIKE ? OR r.number LIKE ? OR r.title LIKE ?)')
                                params.extend([pattern, pattern, pattern, pattern])
                            where_clauses_attachments.append(f"({' AND '.join(word_conditions)})")
                        elif search_type == 'image':
                            word_conditions = []
                            for word in search_words:
                                pattern = f'%{word}%'
                                word_conditions.append('(a.original_filename LIKE ? OR a.filename LIKE ? OR r.number LIKE ? OR r.title LIKE ?)')
                                params.extend([pattern, pattern, pattern, pattern])
                            where_clauses_attachments.append(f"({' AND '.join(word_conditions)}) AND a.mime_type LIKE 'image/%'")
                        elif search_type == 'video':
                            word_conditions = []
                            for word in search_words:
                                pattern = f'%{word}%'
                                word_conditions.append('(a.original_filename LIKE ? OR a.filename LIKE ? OR r.number LIKE ? OR r.title LIKE ?)')
                                params.extend([pattern, pattern, pattern, pattern])
                            where_clauses_attachments.append(f"({' AND '.join(word_conditions)}) AND a.mime_type LIKE 'video/%'")
                        elif search_type == 'audio':
                            word_conditions = []
                            for word in search_words:
                                pattern = f'%{word}%'
                                word_conditions.append('(a.original_filename LIKE ? OR a.filename LIKE ? OR r.number LIKE ? OR r.title LIKE ?)')
                                params.extend([pattern, pattern, pattern, pattern])
                            where_clauses_attachments.append(f"({' AND '.join(word_conditions)}) AND a.mime_type LIKE 'audio/%'")

                if filter_val in ('type_all', 'source_all', 'all'):
                    pass
                elif filter_val.startswith('status_'):
                    status = filter_val.replace('status_', '')
                    if status in ALLOWED_STATUSES:
                        where_clauses_attachments.append('r.status = ?')
                        params.append(status)
                elif filter_val == 'recent':
                    where_clauses_attachments.append('a.uploaded_at >= datetime("now", "-7 days")')
                elif filter_val == 'recent30':
                    where_clauses_attachments.append('a.uploaded_at >= datetime("now", "-30 days")')
                elif filter_val == 'recent365':
                    where_clauses_attachments.append('a.uploaded_at >= datetime("now", "-365 days")')
                elif filter_val.startswith('color_'):
                    color = filter_val.replace('color_', '')
                    if color == 'standard':
                        where_clauses_attachments.append('(r.border_color IS NULL OR r.border_color = "")')
                    elif color in ALLOWED_COLORS or color.startswith('border-'):
                        where_clauses_attachments.append('r.border_color = ?')
                        params.append(color)
                elif filter_val.startswith('type_'):
                    media_type = filter_val.replace('type_', '')
                    if media_type == 'image':
                        where_clauses_attachments.append('a.mime_type LIKE ?')
                        params.append('image/%')
                    elif media_type == 'video':
                        where_clauses_attachments.append('a.mime_type LIKE ?')
                        params.append('video/%')
                    elif media_type == 'audio':
                        where_clauses_attachments.append('a.mime_type LIKE ?')
                        params.append('audio/%')
                elif filter_val == 'has_reminders':
                    where_clauses_attachments.append('r.id IN (SELECT DISTINCT record_id FROM reminders)')
                elif filter_val == 'has_my_reminders':
                    user_id = session.get('user_id')
                    where_clauses_attachments.append('r.id IN (SELECT DISTINCT record_id FROM reminders WHERE assigned_to = ?)')
                    params.append(user_id)
                elif filter_val == 'expired_erinnerungn':
                    where_clauses_attachments.append('r.id IN (SELECT DISTINCT record_id FROM reminders WHERE completed = 0 AND reminder_date < date("now"))')
                elif filter_val == 'expired_termine':
                    where_clauses_attachments.append('r.reminder_date IS NOT NULL AND r.reminder_date < date("now")')

                if category_val:
                    try:
                        category_id = int(category_val)
                        where_clauses_attachments.append('r.category_id = ?')
                        params.append(category_id)
                    except ValueError:
                        pass

                # Archivierte Akten ausschließen
                where_clauses_attachments.append('r.archived = 0')

                # Keine MIME-Type-Einschränkung mehr - alle Anhänge anzeigen
                # Die MIME-Type-Filterung passiert nur über die Suchtyp-Reiter bei Suche
                if where_clauses_attachments:
                    where_attachments = "WHERE " + " AND ".join(where_clauses_attachments)
                else:
                    where_attachments = ""

                sort_map = {
                    'newest': 'ORDER BY created_at DESC',
                    'oldest': 'ORDER BY created_at ASC',
                    'name_asc': 'ORDER BY original_filename ASC',
                    'name_desc': 'ORDER BY original_filename DESC',
                    'size_desc': 'ORDER BY file_size DESC',
                    'size_asc': 'ORDER BY file_size ASC',
                }
                order_by = sort_map.get(sort_val, 'ORDER BY created_at DESC')

                count_query = f'''
                    SELECT COUNT(*) as total FROM attachments a
                    JOIN records r ON a.record_id = r.id
                    LEFT JOIN categories c ON r.category_id = c.id
                    {where_attachments}
                '''
                cursor.execute(count_query, params)
                total_count = cursor.fetchone()['total']

                query = f'''
                    SELECT
                        'attachment' as type,
                        a.id,
                        a.filename,
                        a.original_filename,
                        a.file_size,
                        a.mime_type,
                        NULL as uploaded_by_name,
                        a.uploaded_at as created_at,
                        a.record_id,
                        r.number as record_number,
                        r.title as record_title,
                        r.status as record_status,
                        r.border_color as record_color,
                        r.category_id as record_category_id,
                        c.name as record_category_name
                    FROM attachments a
                    JOIN records r ON a.record_id = r.id
                    LEFT JOIN categories c ON r.category_id = c.id
                    {where_attachments}
                    {order_by}
                    LIMIT ? OFFSET ?
                '''
                query_params = list(params) + [limit, offset]
                cursor.execute(query, query_params)
                rows = cursor.fetchall()

            media_list = []
            for row in rows:
                item = dict(row)
                item['id'] = f"att_{item['id']}"
                media_list.append(item)

            return jsonify({
                'success': True, 
                'media': media_list, 
                'pagination': {
                    'total': total_count, 
                    'limit': limit, 
                    'offset': offset
                }
            })
        except Exception as e:
            logger.error(f"Medienliste fehlgeschlagen: {e}")
            return jsonify({'error': f'Medienliste fehlgeschlagen: {str(e)}'}), 500

    @gallery_bp.route('/<path:media_identifier>', methods=['GET'])
    @auth_manager.login_required
    def get_media(media_identifier):
        try:
            if not media_identifier.startswith('att_'):
                return jsonify({'error': 'Nur Anhänge aus Akten werden unterstützt'}), 400

            attachment_id = int(media_identifier.split('_')[1])
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                # Dateien liegen unter Akten/{Aktenzeichen}/, nicht unter der numerischen ID
                cursor.execute('''
                    SELECT a.filename, r.number as record_number, a.mime_type
                    FROM attachments a
                    JOIN records r ON a.record_id = r.id
                    WHERE a.id = ?
                ''', (attachment_id,))
                attachment = cursor.fetchone()

            if not attachment:
                return jsonify({'error': 'Medium nicht gefunden'}), 404

            record_dir = akten_dir / str(attachment['record_number'])
            file_path = record_dir / attachment['filename']
            
            if not file_path.exists():
                return jsonify({'error': 'Datei nicht gefunden'}), 404

            # Optimiertes Streaming für Videos mit Range Request Unterstützung
            response = send_from_directory(
                str(record_dir), 
                attachment['filename'], 
                conditional=True,
                max_age=31536000  # 1 Jahr Caching für statische Medien
            )
            
            # Zusätzliche Caching-Header für bessere Performance
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            response.headers['Accept-Ranges'] = 'bytes'
            
            # Für Videos: optimierte Streaming-Header
            mime_type = attachment['mime_type'] if attachment['mime_type'] else ''
            if mime_type.startswith('video/'):
                response.headers['X-Content-Type-Options'] = 'nosniff'
                response.headers['Content-Disposition'] = 'inline'
            
            return response
        except Exception as e:
            logger.error(f"Medienabruf fehlgeschlagen: {e}")
            return jsonify({'error': f'Medienabruf fehlgeschlagen: {str(e)}'}), 500

    @gallery_bp.route('/thumbnail/<path:media_identifier>', methods=['GET'])
    @auth_manager.login_required
    def get_thumbnail(media_identifier):
        """Liefert ein Thumbnail für ein Medium mit reduzierter Auflösung"""
        try:
            # Verschiedene Formate unterstützen: att_123 oder nur 123
            if media_identifier.startswith('att_'):
                attachment_id = int(media_identifier.split('_')[1])
            else:
                # Versuch, direkt als Zahl zu parsen
                try:
                    attachment_id = int(media_identifier)
                except ValueError:
                    return jsonify({'error': 'Ungültiges Medienformat'}), 400
            size = int(request.args.get('size', 200))  # Standard: 200px
            size = min(max(size, 50), 400)  # Begrenzung: 50-400px

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT a.filename, r.number as record_number, a.mime_type
                    FROM attachments a
                    JOIN records r ON a.record_id = r.id
                    WHERE a.id = ?
                ''', (attachment_id,))
                attachment = cursor.fetchone()

            if not attachment:
                logger.warning(f"Thumbnail: Attachment {attachment_id} nicht in Datenbank gefunden")
                return jsonify({'error': 'Medium nicht gefunden'}), 404

            # Nur Bilder als Thumbnails
            if not attachment['mime_type'] or not attachment['mime_type'].startswith('image/'):
                logger.info(f"Thumbnail: Attachment {attachment_id} ist kein Bild (mime_type: {attachment['mime_type']})")
                return get_media(media_identifier)  # Für Nicht-Bilder Original zurückgeben

            record_dir = akten_dir / str(attachment['record_number'])
            image_path = record_dir / attachment['filename']

            if not image_path.exists():
                logger.warning(f"Thumbnail: Datei nicht gefunden: {image_path}")
                return jsonify({'error': 'Datei nicht gefunden'}), 404

            # Thumbnail-Cache-Verzeichnis
            cache_dir = base_dir / '.uploads' / 'thumbnails'
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Cache-Dateiname basierend auf Pfad, Größe und Änderungsdatum
            cache_key = f"{attachment_id}_{size}_{image_path.stat().st_mtime}"
            cache_file = cache_dir / f"{cache_key}.jpg"

            # Thumbnail aus Cache oder generieren
            if cache_file.exists():
                return send_from_directory(str(cache_dir), cache_file.name, mimetype='image/jpeg')

            # Thumbnail generieren
            try:
                with Image.open(image_path) as img:
                    # RGBA zu RGB konvertieren, falls Alpha-Kanal vorhanden
                    if img.mode == 'RGBA':
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3])  # Alpha-Kanal als Maske
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    # Aspect Ratio beibehalten
                    img.thumbnail((size, size), Image.Resampling.LANCZOS)

                    # Als JPEG speichern für kleinere Dateigröße
                    img.save(cache_file, 'JPEG', quality=85, optimize=True)

                return send_from_directory(str(cache_dir), cache_file.name, mimetype='image/jpeg')
            except Exception as e:
                logger.error(f"Thumbnail-Generierung fehlgeschlagen für {image_path}: {e}")
                # Fallback: Original zurückgeben
                return get_media(media_identifier)

        except Exception as e:
            logger.error(f"Thumbnail-Abruf fehlgeschlagen für {media_identifier}: {e}", exc_info=True)
            return jsonify({'error': f'Thumbnail-Abruf fehlgeschlagen: {str(e)}'}), 500

    @gallery_bp.route('/similar-images/<int:reference_attachment_id>', methods=['GET'])
    @auth_manager.login_required
    def find_similar_images(reference_attachment_id):
        """Sucht ähnliche Bilder basierend auf Hash-Ähnlichkeit und Text-Ähnlichkeit (Reverse Image Search)"""
        try:
            limit = int(request.args.get('limit', 50))
            offset = int(request.args.get('offset', 0))
            max_distance = int(request.args.get('max_distance', 26))  # Max Hamming-Distanz
            text_deviation = float(request.args.get('text_weight', 0.3))  # API-Parameter heißt text_weight, aber wir behandeln es als Text-Abweichung
            
            limit = min(max(limit, 1), 200)
            offset = max(offset, 0)
            text_deviation = max(0, min(1, text_deviation))
            
            # Hash und Record-Daten des Referenzbildes holen
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ah.phash, ah.dhash, ah.whash, ah.dominant_colors,
                           r.title, r.content, r.hashtags, c.name as category_name,
                           r.address, ao.ocr_text
                    FROM attachment_hashes ah
                    JOIN attachments a ON ah.attachment_id = a.id
                    JOIN records r ON a.record_id = r.id
                    LEFT JOIN categories c ON r.category_id = c.id
                    LEFT JOIN attachment_ocr ao ON ah.attachment_id = ao.attachment_id
                    WHERE ah.attachment_id = ?
                ''', (reference_attachment_id,))
                ref_data = cursor.fetchone()
                
                if not ref_data:
                    return jsonify({'error': 'Referenzbild nicht gefunden oder keine Hashes verfügbar'}), 404
            
            # Alle anderen Bild-Hashes und Record-Daten abrufen
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        ah.attachment_id,
                        ah.record_id,
                        ah.phash,
                        ah.dhash,
                        ah.whash,
                        ah.dominant_colors,
                        a.filename,
                        a.original_filename,
                        a.file_size,
                        a.mime_type,
                        a.uploaded_at as created_at,
                        r.number as record_number,
                        r.title as record_title,
                        r.content as record_content,
                        r.hashtags as record_hashtags,
                        r.status as record_status,
                        r.border_color as record_color,
                        r.category_id as record_category_id,
                        c.name as record_category_name,
                        r.address as record_address,
                        ao.ocr_text
                    FROM attachment_hashes ah
                    JOIN attachments a ON ah.attachment_id = a.id
                    JOIN records r ON ah.record_id = r.id
                    LEFT JOIN categories c ON r.category_id = c.id
                    LEFT JOIN attachment_ocr ao ON ah.attachment_id = ao.attachment_id
                    WHERE ah.attachment_id != ?
                ''', (reference_attachment_id,))
                rows = cursor.fetchall()
            
            # Ähnlichkeit berechnen
            similar_images = []
            for row in rows:
                try:
                    # Hamming-Distanzen für verschiedene Hash-Algorithmen
                    phash_dist = calculate_hash_distance(ref_data['phash'], row['phash'])
                    dhash_dist = calculate_hash_distance(ref_data['dhash'], row['dhash'])
                    whash_dist = calculate_hash_distance(ref_data['whash'], row['whash'])
                    
                    # Durchschnittliche visuelle Distanz (niedriger = ähnlicher)
                    visual_distance = (phash_dist + dhash_dist + whash_dist) / 3
                    
                    # Text-Ähnlichkeit basierend auf Akten-Metadaten berechnen
                    ref_record_data = {
                        'title': ref_data['title'],
                        'content': ref_data['content'],
                        'hashtags': ref_data['hashtags'],
                        'category_name': ref_data['category_name'],
                        'address': ref_data['address'],
                        'ocr_text': ref_data['ocr_text']
                    }
                    
                    row_record_data = {
                        'title': row['record_title'],
                        'content': row['record_content'],
                        'hashtags': row['record_hashtags'],
                        'category_name': row['record_category_name'],
                        'address': row['record_address'],
                        'ocr_text': row['ocr_text']
                    }
                    
                    text_similarity = calculate_text_similarity(ref_record_data, row_record_data)
                    
                    # Kombinierter Score: niedriger ist besser
                    # Text-Ähnlichkeit wird in Distanz umgewandelt (1 - similarity)
                    text_distance = 1 - text_similarity
                    
                    # Gewichteter Durchschnitt - text_deviation bestimmt wie stark Text-Abweichung einfließt
                    # Höhere text_deviation = Text muss genauer passen (geringere Toleranz)
                    combined_distance = (visual_distance * (1 - text_deviation)) + (text_distance * text_deviation * 30)  # *30 um Skalierung anzugleichen
                    
                    # Nur Bilder innerhalb der max_distance aufnehmen
                    if combined_distance <= max_distance:
                        row_data = dict(row)
                        row_data['similarity_score'] = combined_distance
                        row_data['visual_distance'] = visual_distance
                        row_data['text_similarity'] = text_similarity
                        row_data['id'] = f"att_{row['attachment_id']}"
                        similar_images.append((combined_distance, row_data))
                except Exception as e:
                    logger.warning(f"Fehler bei Ähnlichkeitsberechnung für Bild {row['attachment_id']}: {e}")
                    continue
            
            # Nach Ähnlichkeit sortieren (niedrigste Distanz zuerst)
            similar_images.sort(key=lambda x: x[0])
            
            # Paginierung anwenden - sicherstellen dass offset nicht größer als Ergebnisse ist
            offset = min(offset, len(similar_images))
            paginated_results = [item[1] for item in similar_images[offset:offset + limit]]
            
            logger.info(f"Ähnlichkeitssuche: {len(similar_images)} Bilder gefunden (Schwellenwert: {max_distance}, Text-Abweichung: {text_deviation}), zeige {len(paginated_results)} ab Offset {offset}")
            
            return jsonify({
                'success': True,
                'media': paginated_results,
                'pagination': {
                    'total': len(similar_images),
                    'limit': limit,
                    'offset': offset
                },
                'reference_image_id': f"att_{reference_attachment_id}",
                'search_parameters': {
                    'max_distance': max_distance,
                    'text_deviation': text_deviation
                }
            })
        except Exception as e:
            logger.error(f"Ähnlichkeitssuche fehlgeschlagen: {e}")
            return jsonify({'error': f'Ähnlichkeitssuche fehlgeschlagen: {str(e)}'}), 500

    @gallery_bp.route('/similar-images', methods=['GET'])
    @auth_manager.login_required
    def find_similar_images_multiple():
        """Sucht ähnliche Bilder basierend auf mehreren Referenzbildern (OR-Logik)"""
        try:
            limit = int(request.args.get('limit', 50))
            offset = int(request.args.get('offset', 0))
            max_distance = int(request.args.get('max_distance', 26))
            text_deviation = float(request.args.get('text_weight', 0.3))
            
            # Mehrere Referenz-IDs aus Parameter extrahieren
            reference_ids = request.args.getlist('reference_ids[]')
            if not reference_ids:
                return jsonify({'error': 'Keine Referenzbilder angegeben'}), 400
            
            reference_ids = [int(rid) for rid in reference_ids]
            
            limit = min(max(limit, 1), 200)
            offset = max(offset, 0)
            text_deviation = max(0, min(1, text_deviation))
            
            # Hash- und Record-Daten aller Referenzbilder holen
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(reference_ids))
                cursor.execute(f'''
                    SELECT ah.attachment_id, ah.phash, ah.dhash, ah.whash, ah.dominant_colors,
                           r.title, r.content, r.hashtags, c.name as category_name,
                           r.address, ao.ocr_text
                    FROM attachment_hashes ah
                    JOIN attachments a ON ah.attachment_id = a.id
                    JOIN records r ON a.record_id = r.id
                    LEFT JOIN categories c ON r.category_id = c.id
                    LEFT JOIN attachment_ocr ao ON ah.attachment_id = ao.attachment_id
                    WHERE ah.attachment_id IN ({placeholders})
                ''', reference_ids)
                ref_images = cursor.fetchall()
                
                if not ref_images:
                    return jsonify({'error': 'Keine Referenzbilder gefunden oder keine Hashes verfügbar'}), 404
            
            # Kombinierte Keywords aus allen Referenzbildern erstellen
            all_ref_keywords = set()
            for ref_data in ref_images:
                ref_record_data = {
                    'title': ref_data['title'],
                    'content': ref_data['content'],
                    'hashtags': ref_data['hashtags'],
                    'category_name': ref_data['category_name'],
                    'address': ref_data['address'],
                    'ocr_text': ref_data['ocr_text']
                }
                all_ref_keywords.update(extract_record_metadata(ref_record_data))
            
            # Alle anderen Bild-Hashes und Record-Daten abrufen
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(reference_ids))
                cursor.execute(f'''
                    SELECT 
                        ah.attachment_id,
                        ah.record_id,
                        ah.phash,
                        ah.dhash,
                        ah.whash,
                        ah.dominant_colors,
                        a.filename,
                        a.original_filename,
                        a.file_size,
                        a.mime_type,
                        a.uploaded_at as created_at,
                        r.number as record_number,
                        r.title as record_title,
                        r.content as record_content,
                        r.hashtags as record_hashtags,
                        r.status as record_status,
                        r.border_color as record_color,
                        r.category_id as record_category_id,
                        c.name as record_category_name,
                        r.address as record_address,
                        ao.ocr_text
                    FROM attachment_hashes ah
                    JOIN attachments a ON ah.attachment_id = a.id
                    JOIN records r ON ah.record_id = r.id
                    LEFT JOIN categories c ON r.category_id = c.id
                    LEFT JOIN attachment_ocr ao ON ah.attachment_id = ao.attachment_id
                    WHERE ah.attachment_id NOT IN ({placeholders})
                ''', reference_ids)
                rows = cursor.fetchall()
            
            # Ähnlichkeit für jedes Bild gegen alle Referenzbilder berechnen (OR-Logik)
            similar_images = {}
            for row in rows:
                try:
                    row_record_data = {
                        'title': row['record_title'],
                        'content': row['record_content'],
                        'hashtags': row['record_hashtags'],
                        'category_name': row['record_category_name'],
                        'address': row['record_address'],
                        'ocr_text': row['ocr_text']
                    }
                    
                    row_keywords = extract_record_metadata(row_record_data)
                    
                    # Beste Ähnlichkeit zu einem der Referenzbilder finden
                    best_distance = float('inf')
                    best_visual_distance = float('inf')
                    best_text_similarity = 0
                    
                    for ref_data in ref_images:
                        # Hamming-Distanzen für verschiedene Hash-Algorithmen
                        phash_dist = calculate_hash_distance(ref_data['phash'], row['phash'])
                        dhash_dist = calculate_hash_distance(ref_data['dhash'], row['dhash'])
                        whash_dist = calculate_hash_distance(ref_data['whash'], row['whash'])
                        
                        # Durchschnittliche visuelle Distanz
                        visual_distance = (phash_dist + dhash_dist + whash_dist) / 3
                        
                        # Text-Ähnlichkeit basierend auf Keywords berechnen
                        ref_record_data = {
                            'title': ref_data['title'],
                            'content': ref_data['content'],
                            'hashtags': ref_data['hashtags'],
                            'category_name': ref_data['category_name'],
                            'address': ref_data['address'],
                            'ocr_text': ref_data['ocr_text']
                        }
                        ref_keywords = extract_record_metadata(ref_record_data)
                        
                        # Jaccard-Ähnlichkeit der Keywords
                        if ref_keywords and row_keywords:
                            intersection = len(ref_keywords & row_keywords)
                            union = len(ref_keywords | row_keywords)
                            text_similarity = intersection / union if union > 0 else 0
                        else:
                            text_similarity = 0
                        
                        # Kombinierter Score
                        text_distance = 1 - text_similarity
                        combined_distance = (visual_distance * (1 - text_deviation)) + (text_distance * text_deviation * 30)
                        
                        # Beste Distanz merken
                        if combined_distance < best_distance:
                            best_distance = combined_distance
                            best_visual_distance = visual_distance
                            best_text_similarity = text_similarity
                    
                    # Nur Bilder innerhalb der max_distance aufnehmen
                    if best_distance <= max_distance:
                        row_data = dict(row)
                        row_data['similarity_score'] = best_distance
                        row_data['visual_distance'] = best_visual_distance
                        row_data['text_similarity'] = best_text_similarity
                        row_data['id'] = f"att_{row['attachment_id']}"
                        # Vermeide Duplikate durch Dict
                        similar_images[row_data['id']] = (best_distance, row_data)
                except Exception as e:
                    logger.warning(f"Fehler bei Ähnlichkeitsberechnung für Bild {row['attachment_id']}: {e}")
                    continue
            
            # Nach Ähnlichkeit sortieren
            sorted_images = sorted(similar_images.values(), key=lambda x: x[0])
            
            # Paginierung anwenden
            offset = min(offset, len(sorted_images))
            paginated_results = [item[1] for item in sorted_images[offset:offset + limit]]
            
            logger.info(f"Multi-Referenz-Ähnlichkeitssuche: {len(sorted_images)} Bilder gefunden ({len(reference_ids)} Referenzen, Schwellenwert: {max_distance}, Text-Abweichung: {text_deviation}), zeige {len(paginated_results)} ab Offset {offset}")
            
            return jsonify({
                'success': True,
                'media': paginated_results,
                'pagination': {
                    'total': len(sorted_images),
                    'limit': limit,
                    'offset': offset
                },
                'reference_image_ids': [f"att_{rid}" for rid in reference_ids],
                'search_parameters': {
                    'max_distance': max_distance,
                    'text_deviation': text_deviation,
                    'reference_count': len(reference_ids)
                }
            })
        except Exception as e:
            logger.error(f"Multi-Referenz-Ähnlichkeitssuche fehlgeschlagen: {e}")
            return jsonify({'error': f'Multi-Referenz-Ähnlichkeitssuche fehlgeschlagen: {str(e)}'}), 500

    @gallery_bp.route('/preferences', methods=['GET', 'POST'])
    @auth_manager.login_required
    def gallery_preferences():
        """Nutzerspezifische Galerie-Einstellungen speichern oder laden"""
        try:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'Benutzer nicht angemeldet'}), 401

            if request.method == 'GET':
                # Einstellungen laden
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT preferences FROM user_preferences WHERE user_id = ?
                    ''', (user_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        preferences = json.loads(row['preferences'])
                        gallery_prefs = preferences.get('gallery', {})
                    else:
                        # Standardwerte
                        gallery_prefs = {
                            'similarity_threshold': 26,
                            'text_deviation': 0.3
                        }
                    
                    return jsonify({
                        'success': True,
                        'preferences': gallery_prefs
                    })
            
            elif request.method == 'POST':
                # Einstellungen speichern
                data = request.get_json()
                similarity_threshold = data.get('similarity_threshold', 26)
                text_deviation = data.get('text_deviation', 0.3)
                
                # Werte validieren
                similarity_threshold = max(0, min(30, int(similarity_threshold)))
                text_deviation = max(0, min(1, float(text_deviation)))
                
                with db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Prüfen ob Eintrag existiert
                    cursor.execute('SELECT preferences FROM user_preferences WHERE user_id = ?', (user_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        # Aktualisieren
                        preferences = json.loads(row['preferences'])
                        preferences['gallery'] = {
                            'similarity_threshold': similarity_threshold,
                            'text_deviation': text_deviation
                        }
                        cursor.execute('''
                            UPDATE user_preferences 
                            SET preferences = ?, updated_at = CURRENT_TIMESTAMP 
                            WHERE user_id = ?
                        ''', (json.dumps(preferences), user_id))
                    else:
                        # Neu erstellen
                        preferences = {
                            'gallery': {
                                'similarity_threshold': similarity_threshold,
                                'text_deviation': text_deviation
                            }
                        }
                        cursor.execute('''
                            INSERT INTO user_preferences (user_id, preferences)
                            VALUES (?, ?)
                        ''', (user_id, json.dumps(preferences)))
                    
                    conn.commit()
                
                return jsonify({
                    'success': True,
                    'preferences': {
                        'similarity_threshold': similarity_threshold,
                        'text_deviation': text_deviation
                    }
                })
                
        except Exception as e:
            logger.error(f"Galerie-Einstellungen fehlgeschlagen: {e}")
            return jsonify({'error': f'Galerie-Einstellungen fehlgeschlagen: {str(e)}'}), 500

    return gallery_bp