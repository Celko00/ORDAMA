"""
Suchlogik-Modul für ORDAMA
- Suchabfrage-Parsing
- SQL-Suchbedingungen
- OCR-Suche und FTS-Integration
"""

import re
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class SearchLogic:
    """Verwaltet alle Such-bezogenen Operationen"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def parse_search_query(self, search):
        """
        Parst Suchabfrage und erkennt UND/ODER-Operatoren
        Wortreihenfolge-unabhängig: Alle Wörter werden automatisch als AND behandelt
        """
        if not search:
            return []

        # Konvertiere zu Kleinbuchstaben für Case-Insensitive-Suche
        search = search.lower()

        # Ersetze Platzhalter für SQL LIKE
        # * wird zu %, ? wird zu _
        search = search.replace('*', '%').replace('?', '_')

        # Prüfe auf UND/ODER-Operatoren (deutsch)
        if ' und ' in search:
            terms = [t.strip() for t in search.split(' und ')]
            return {'type': 'AND', 'terms': terms}
        elif ' oder ' in search:
            terms = [t.strip() for t in search.split(' oder ')]
            return {'type': 'OR', 'terms': terms}
        else:
            # Automatisch alle Wörter als AND behandeln (wortreihenfolge-unabhängig)
            words = self.extract_keywords(search)
            if words:
                return {'type': 'AND', 'terms': list(words)}
            else:
                return {'type': 'SINGLE', 'terms': [search]}

    def build_search_conditions(self, parsed_search, search_type, query_prefix=''):
        """
        Baut SQL-Suchbedingungen basierend auf geparster Suchabfrage
        Wortreihenfolge-unabhängig für alle Suchtypen
        """
        conditions = []
        params = []

        if parsed_search['type'] == 'SINGLE':
            term = parsed_search['terms'][0]
            if search_type == 'title':
                conditions.append(f"{query_prefix}title LIKE ?")
                params.append(f'%{term}%')
            elif search_type == 'content':
                conditions.append(f"{query_prefix}content LIKE ?")
                params.append(f'%{term}%')
            elif search_type == 'address':
                conditions.append(f"{query_prefix}address LIKE ?")
                params.append(f'%{term}%')
            elif search_type == 'attachments':
                conditions.append(f"{query_prefix}filename LIKE ? OR {query_prefix}original_filename LIKE ?")
                params.extend([f'%{term}%', f'%{term}%'])
            elif search_type == 'ocr':
                conditions.append(f"{query_prefix}ocr_text LIKE ?")
                params.append(f'%{term}%')
            else:  # 'all'
                conditions.append(f"({query_prefix}title LIKE ? OR {query_prefix}content LIKE ? OR {query_prefix}number LIKE ? OR {query_prefix}hashtags LIKE ? OR {query_prefix}address LIKE ?)")
                params.extend([f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%'])

        elif parsed_search['type'] == 'AND':
            for term in parsed_search['terms']:
                if search_type == 'title':
                    conditions.append(f"{query_prefix}title LIKE ?")
                    params.append(f'%{term}%')
                elif search_type == 'content':
                    conditions.append(f"{query_prefix}content LIKE ?")
                    params.append(f'%{term}%')
                elif search_type == 'address':
                    conditions.append(f"{query_prefix}address LIKE ?")
                    params.append(f'%{term}%')
                elif search_type == 'attachments':
                    conditions.append(f"({query_prefix}filename LIKE ? OR {query_prefix}original_filename LIKE ?)")
                    params.extend([f'%{term}%', f'%{term}%'])
                elif search_type == 'ocr':
                    conditions.append(f"{query_prefix}ocr_text LIKE ?")
                    params.append(f'%{term}%')
                else:  # 'all'
                    conditions.append(f"({query_prefix}title LIKE ? OR {query_prefix}content LIKE ? OR {query_prefix}number LIKE ? OR {query_prefix}hashtags LIKE ? OR {query_prefix}address LIKE ?)")
                    params.extend([f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%'])

        elif parsed_search['type'] == 'OR':
            or_conditions = []
            for term in parsed_search['terms']:
                if search_type == 'title':
                    or_conditions.append(f"{query_prefix}title LIKE ?")
                    params.append(f'%{term}%')
                elif search_type == 'content':
                    or_conditions.append(f"{query_prefix}content LIKE ?")
                    params.append(f'%{term}%')
                elif search_type == 'address':
                    or_conditions.append(f"{query_prefix}address LIKE ?")
                    params.append(f'%{term}%')
                elif search_type == 'attachments':
                    or_conditions.append(f"({query_prefix}filename LIKE ? OR {query_prefix}original_filename LIKE ?)")
                    params.extend([f'%{term}%', f'%{term}%'])
                elif search_type == 'ocr':
                    or_conditions.append(f"{query_prefix}ocr_text LIKE ?")
                    params.append(f'%{term}%')
                else:  # 'all'
                    or_conditions.append(f"({query_prefix}title LIKE ? OR {query_prefix}content LIKE ? OR {query_prefix}number LIKE ? OR {query_prefix}hashtags LIKE ? OR {query_prefix}address LIKE ?)")
                    params.extend([f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%'])
            conditions.append(f"({' OR '.join(or_conditions)})")

        return ' AND '.join(conditions), params

    def matches_search_pattern(self, text, parsed_search):
        """
        Prüft, ob ein Text mit der geparsten Suchabfrage übereinstimmt
        Für Dateianhang-Suche
        """
        if not text or not parsed_search:
            return False

        text_lower = text.lower()

        if parsed_search['type'] == 'SINGLE':
            term = parsed_search['terms'][0]
            # Entferne SQL LIKE Platzhalter für einfache Suche
            clean_term = term.replace('%', '').replace('_', '')
            # Einfache substring-Suche
            return clean_term in text_lower

        elif parsed_search['type'] == 'AND':
            for term in parsed_search['terms']:
                clean_term = term.replace('%', '').replace('_', '')
                if clean_term not in text_lower:
                    return False
            return True

        elif parsed_search['type'] == 'OR':
            for term in parsed_search['terms']:
                clean_term = term.replace('%', '').replace('_', '')
                if clean_term in text_lower:
                    return True
            return False

        return False

    def build_like_conditions_for_column(self, parsed_search, column_name):
        """Baut LIKE-Bedingungen für ein beliebiges Textfeld"""
        conditions = []
        params = []

        if not parsed_search:
            return '', []

        if parsed_search['type'] == 'SINGLE':
            conditions.append(f"{column_name} LIKE ?")
            params.append(f"%{parsed_search['terms'][0]}%")
        elif parsed_search['type'] == 'AND':
            for term in parsed_search['terms']:
                conditions.append(f"{column_name} LIKE ?")
                params.append(f"%{term}%")
        elif parsed_search['type'] == 'OR':
            or_conditions = []
            for term in parsed_search['terms']:
                or_conditions.append(f"{column_name} LIKE ?")
                params.append(f"%{term}%")
            conditions.append(f"({' OR '.join(or_conditions)})")

        return ' AND '.join(conditions), params

    def _parsed_search_to_fts_query(self, parsed_search):
        """Konvertiert die bestehende Suchsyntax in eine FTS5-Suchabfrage"""
        if not parsed_search:
            return None

        def convert_term(term):
            if not term:
                return None
            normalized = term.replace('%', '*').replace('_', ' ')
            normalized = normalized.replace('"', ' ').strip()
            parts = [p for p in re.split(r'\s+', normalized) if p]
            if not parts:
                return None
            converted = []
            for part in parts:
                if '*' in part:
                    converted.append(part)
                else:
                    converted.append(f'"{part}"')
            return ' AND '.join(converted)

        converted_terms = [convert_term(term) for term in parsed_search.get('terms', [])]
        converted_terms = [term for term in converted_terms if term]
        if not converted_terms:
            return None

        if parsed_search['type'] == 'SINGLE':
            return converted_terms[0]
        if parsed_search['type'] == 'AND':
            return ' AND '.join(f"({term})" for term in converted_terms)
        if parsed_search['type'] == 'OR':
            return ' OR '.join(f"({term})" for term in converted_terms)
        return None

    def get_ocr_matching_record_ids(self, parsed_search):
        """Findet OCR-Treffer für die globale Suche"""
        if not parsed_search:
            return set()

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            try:
                fts_query = self._parsed_search_to_fts_query(parsed_search)
                if fts_query:
                    cursor.execute('''
                        SELECT DISTINCT f.record_id
                        FROM attachment_ocr_fts f
                        JOIN attachment_ocr o ON o.attachment_id = f.attachment_id
                        WHERE attachment_ocr_fts MATCH ?
                          AND o.status = 'done'
                          AND o.has_text = 1
                    ''', (fts_query,))
                    return {row['record_id'] for row in cursor.fetchall()}
            except Exception as e:
                logger.info(f"FTS-Suche nicht nutzbar, falle auf LIKE zurück: {e}")

            like_condition, params = self.build_like_conditions_for_column(parsed_search, 'ocr_text')
            if not like_condition:
                return set()

            cursor.execute(f'''
                SELECT DISTINCT record_id
                FROM attachment_ocr
                WHERE status = 'done'
                  AND has_text = 1
                  AND ocr_text IS NOT NULL
                  AND {like_condition}
            ''', params)
            return {row['record_id'] for row in cursor.fetchall()}

    def _build_search_excerpt(self, text, parsed_search, radius=90):
        """Erzeugt einen kurzen Auszug rund um den ersten Suchtreffer"""
        normalized = re.sub(r'\s+', ' ', text or '').strip()
        if not normalized:
            return ''

        terms = []
        for term in parsed_search.get('terms', []):
            clean_term = term.replace('%', '').replace('_', ' ').strip()
            if clean_term:
                terms.append(clean_term.lower())

        match_pos = -1
        match_len = 0
        text_lower = normalized.lower()
        for term in terms:
            pos = text_lower.find(term)
            if pos != -1:
                match_pos = pos
                match_len = len(term)
                break

        if match_pos == -1:
            return normalized[:radius * 2].strip()

        start = max(0, match_pos - radius)
        end = min(len(normalized), match_pos + max(match_len, 1) + radius)
        excerpt = normalized[start:end].strip()
        if start > 0:
            excerpt = f"… {excerpt}"
        if end < len(normalized):
            excerpt = f"{excerpt} …"
        return excerpt

    def _parse_ocr_page_map(self, page_map_json):
        if not page_map_json:
            return []
        try:
            parsed = json.loads(page_map_json)
            if not isinstance(parsed, list):
                return []
            result = []
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                page = int(entry.get('page', 0) or 0)
                text = entry.get('text', '')
                # Text nicht normalisieren, um die Originalposition zu erhalten
                if page > 0:
                    result.append({'page': page, 'text': text})
            return result
        except Exception:
            return []

    def _normalize_attachment_text(self, text):
        normalized = (text or '').replace('\x0c', ' ')
        normalized = re.sub(r'\r\n?', '\n', normalized)
        normalized = re.sub(r'[ \t]+', ' ', normalized)
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        return normalized.strip()

    def _find_match_in_text(self, text, parsed_search):
        normalized = re.sub(r'\s+', ' ', text or '').strip()
        if not normalized:
            return None

        text_lower = normalized.lower()
        for term in parsed_search.get('terms', []):
            clean_term = term.replace('%', '').replace('_', ' ').strip().lower()
            if not clean_term:
                continue
            pos = text_lower.find(clean_term)
            if pos != -1:
                return {
                    'term': clean_term,
                    'position': pos,
                    'text': normalized
                }
        # Wenn kein exakter Treffer gefunden wurde, nach Teilbegriffen suchen
        for term in parsed_search.get('terms', []):
            clean_term = term.replace('%', '').replace('_', ' ').strip().lower()
            if not clean_term or len(clean_term) < 3:
                continue
            # Suche nach Teilbegriffen (mindestens 3 Zeichen)
            for i in range(len(clean_term) - 2):
                partial = clean_term[i:i+3]
                pos = text_lower.find(partial)
                if pos != -1:
                    return {
                        'term': partial,
                        'position': pos,
                        'text': normalized
                    }
        return None

    def _find_ocr_match_locations(self, ocr_text, ocr_page_map, parsed_search):
        """Findet alle OCR-Treffer und gibt sie als Liste zurück"""
        page_map = self._parse_ocr_page_map(ocr_page_map)
        locations = []
        
        # Im page_map suchen - alle Treffer sammeln
        for entry in page_map:
            text = self._normalize_attachment_text(entry.get('text', ''))
            if self.matches_search_pattern(text, parsed_search):
                locations.append({
                    'page': entry['page'],
                    'snippet': self._build_search_excerpt(text, parsed_search)
                })

        # Fallback: Wenn keine Treffer im page_map, aber im gesamten Text, Seite 1 hinzufügen
        if not locations:
            fallback_text = self._normalize_attachment_text(ocr_text)
            if fallback_text and self.matches_search_pattern(fallback_text, parsed_search):
                locations.append({
                    'page': 1,
                    'snippet': self._build_search_excerpt(fallback_text, parsed_search)
                })

        # Wenn immer noch keine Treffer, aber page_map vorhanden, erste Seite hinzufügen
        if not locations and page_map:
            locations.append({
                'page': page_map[0]['page'],
                'snippet': self._build_search_excerpt(page_map[0]['text'], parsed_search)
            })

        return locations

    def get_ocr_match_details(self, parsed_search):
        """Liefert OCR-Treffer gruppiert nach Akte inklusive Dateiname und Textauszug"""
        if not parsed_search:
            return {}

        grouped_matches = defaultdict(list)

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            rows = []

            try:
                fts_query = self._parsed_search_to_fts_query(parsed_search)
                if fts_query:
                    cursor.execute('''
                        SELECT
                            o.record_id,
                            a.filename,
                            o.ocr_text,
                            o.ocr_page_map
                        FROM attachment_ocr_fts f
                        JOIN attachment_ocr o ON o.attachment_id = f.attachment_id
                        JOIN attachments a ON a.id = o.attachment_id
                        WHERE attachment_ocr_fts MATCH ?
                          AND o.status = 'done'
                          AND o.has_text = 1
                        ORDER BY o.record_id ASC, a.filename ASC
                    ''', (fts_query,))
                    rows = cursor.fetchall()
            except Exception as e:
                logger.info(f"FTS-Trefferdetails nicht nutzbar, falle auf LIKE zurück: {e}")

            if not rows:
                like_condition, params = self.build_like_conditions_for_column(parsed_search, 'o.ocr_text')
                if not like_condition:
                    return {}

                cursor.execute(f'''
                    SELECT
                        o.record_id,
                        a.filename,
                        o.ocr_text,
                        o.ocr_page_map
                    FROM attachment_ocr o
                    JOIN attachments a ON a.id = o.attachment_id
                    WHERE o.status = 'done'
                      AND o.has_text = 1
                      AND o.ocr_text IS NOT NULL
                      AND {like_condition}
                    ORDER BY o.record_id ASC, a.filename ASC
                ''', params)
                rows = cursor.fetchall()

        for row in rows:
            record_id = row['record_id']
            filename = row['filename']
            match_locations = self._find_ocr_match_locations(row['ocr_text'], row['ocr_page_map'], parsed_search)
            
            # Alle gefundenen Treffer hinzufügen
            for match_location in match_locations:
                grouped_matches[record_id].append({
                    'type': 'ocr',
                    'filename': filename,
                    'page': match_location['page'],
                    'snippet': match_location['snippet']
                })

        return dict(grouped_matches)

    def extract_keywords(self, text):
        """Extrahiert Keywords aus Text für Ähnlichkeitssuche"""
        if not text:
            return set()
        # Einfache Implementierung - kann erweitert werden
        words = text.lower().split()
        # Entferne kurze Wörter und Füllwörter
        stopwords = {'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'und', 'oder', 'für', 'mit', 'von', 'zu', 'auf', 'in', 'an'}
        return {word for word in words if len(word) > 2 and word not in stopwords}
