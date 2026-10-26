"""
Dubletten-Erkennungs-Modul für ORDAMA
- Prüft auf ähnliche Akten basierend auf Titel, Inhalt und OCR
- Verwendet FTS5 für Performance-Optimierung
"""

import logging

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """Verwaltet die Dubletten-Erkennung"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def check_for_duplicates(self, title, content, address, user_id, hashtags=None, min_similarity=None):
        """Prüft auf ähnliche Akten (Dubletten) basierend auf Titel und Textinhalten (Inhalt/Adresse/Hashtags)"""
        try:
            # Schwellenwert aus Settings laden oder Standardwert 0.3 verwenden (erhöht für bessere Erkennung)
            if min_similarity is None:
                min_similarity = float(self.db_manager.get_setting('duplicate_threshold', '0.3'))
            
            hashtags = hashtags or ''
            
            # Feste Gewichtungen: Titel 70%, Inhalt 20%, OCR 10%
            # Titel ist am wichtigsten für Dubletten-Erkennung
            
            # Zweitens: Word-basierte Titel-Ähnlichkeit prüfen (Wörter in beliebiger Reihenfolge)
            # DEAKTIVIERT
            word_matches = []
            
            # Drittens: FTS5-basierte Vorfilterung für Performance bei großen Datenmengen
            content_matches = []
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Prüfen ob FTS5-Tabelle existiert
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records_fts'")
                fts_exists = cursor.fetchone() is not None
                
                if fts_exists and title:
                    # FTS5-Suche für schnelle Vorfilterung (konfigurierbares Limit)
                    # Extrahiere relevante Wörter aus Titel für FTS5-Suche mit OR-Logik
                    title_words = [w for w in title.lower().split() if len(w) >= 3]
                    candidate_limit = int(self.db_manager.get_setting('duplicate_candidate_limit', '100'))
                    if title_words:
                        # OR-Logik für FTS5: Jedes Wort einzeln suchen
                        fts_query = ' OR '.join(title_words[:5])  # Max 5 Wörter für FTS5
                        cursor.execute("""
                            SELECT r.id, r.number, r.title, r.content
                            FROM records_fts fts
                            JOIN records r ON fts.id = r.id
                            WHERE records_fts MATCH ?
                            AND r.archived = 0
                            LIMIT ?
                        """, (fts_query, candidate_limit))
                        candidate_records = [dict(row) for row in cursor.fetchall()]
                    else:
                        candidate_records = []
                else:
                    # Fallback: Nur die letzten X Akten prüfen bei großen Datenmengen
                    candidate_limit = int(self.db_manager.get_setting('duplicate_candidate_limit', '1000'))
                    cursor.execute("""
                        SELECT r.id, r.number, r.title, r.content
                        FROM records r
                        WHERE r.archived = 0
                        ORDER BY r.id DESC
                        LIMIT ?
                    """, (candidate_limit,))
                    candidate_records = [dict(row) for row in cursor.fetchall()]
            
            # OCR-Daten nur für die Kandidaten laden (Performance-Optimierung)
            if candidate_records:
                record_ids = [r['id'] for r in candidate_records]
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    placeholders = ','.join('?' * len(record_ids))
                    cursor.execute(f"""
                        SELECT record_id, GROUP_CONCAT(ocr_text, ' ') as ocr_text
                        FROM attachment_ocr
                        WHERE record_id IN ({placeholders})
                        GROUP BY record_id
                    """, record_ids)
                    ocr_data = {row['record_id']: row['ocr_text'] for row in cursor.fetchall()}
                
                # OCR-Daten zu den Kandidaten hinzufügen
                for record in candidate_records:
                    record['ocr_text'] = ocr_data.get(record['id'], '')
            
            for record in candidate_records:
                if not record.get('id'):
                    continue
                
                # Ähnlichkeit basierend auf Titel, Inhalt und OCR-Daten
                record_title = (record.get('title') or '').lower()
                record_content = (record.get('content') or '').lower()
                record_ocr = (record.get('ocr_text') or '').lower()
                new_title = (title or '').lower()
                new_content = (content or '').lower()
                
                # Phonetische Normalisierung für deutsche Umlaute
                def normalize_umlauts(text):
                    text = text.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
                    return text
                
                record_title_normalized = normalize_umlauts(record_title)
                new_title_normalized = normalize_umlauts(new_title)
                
                # Titel-Ähnlichkeit (70% Gewicht)
                title_similarity = 0
                is_exact_title_match = False
                if new_title and record_title:
                    if new_title == record_title:
                        title_similarity = 1.0
                        is_exact_title_match = True
                    else:
                        # Wörter extrahieren (mindestens 2 Zeichen) - mit normalisierten Umlauten
                        title_words = {w for w in new_title_normalized.split() if len(w) >= 2}
                        record_title_words = {w for w in record_title_normalized.split() if len(w) >= 2}
                        
                        if title_words and record_title_words:
                            # Jaccard-Ähnlichkeit für Wörter
                            intersection = len(title_words & record_title_words)
                            union = len(title_words | record_title_words)
                            jaccard = intersection / union if union > 0 else 0
                            
                            # Wenn 50%+ der Wörter übereinstimmen, hohe Ähnlichkeit
                            if jaccard >= 0.5:
                                title_similarity = 0.9
                            elif jaccard >= 0.3:
                                title_similarity = 0.7
                            elif jaccard >= 0.2:
                                title_similarity = 0.5
                            else:
                                title_similarity = jaccard
                
                # Inhalt-Ähnlichkeit (20% Gewicht)
                content_similarity = 0
                if new_content and record_content:
                    content_words = set(new_content[:300].split())
                    record_content_words = set(record_content[:300].split())
                    if content_words and record_content_words:
                        intersection = len(content_words & record_content_words)
                        union = len(content_words | record_content_words)
                        content_similarity = intersection / union if union > 0 else 0
                
                # OCR-Ähnlichkeit (10% Gewicht)
                ocr_similarity = 0
                if record_ocr:
                    ocr_words = set(record_ocr[:300].split())
                    if ocr_words:
                        # OCR mit Inhalt vergleichen
                        if new_content:
                            content_words = set(new_content[:300].split())
                            intersection = len(content_words & ocr_words)
                            union = len(content_words | ocr_words)
                            ocr_similarity = intersection / union if union > 0 else 0
                
                # Gesamt-Ähnlichkeit (70% Titel, 20% Inhalt, 10% OCR)
                similarity_score = (title_similarity * 0.7 + content_similarity * 0.2 + ocr_similarity * 0.1)
                
                # Nur Akten über dem Schwellenwert hinzufügen
                if similarity_score >= min_similarity:
                    content_matches.append({
                        'id': record['id'],
                        'number': record['number'],
                        'title': record['title'],
                        'content': (record.get('content') or '')[:200],
                        'similarity_score': round(float(similarity_score), 2),
                        'is_exact_match': is_exact_title_match,
                        'is_word_match': False
                    })
            
            # Kombiniere word_matches und content_matches, entferne Duplikate
            all_duplicates = []
            seen_ids = set()
            
            # Füge word_matches hinzu
            for match in word_matches:
                if match['id'] not in seen_ids:
                    all_duplicates.append(match)
                    seen_ids.add(match['id'])
            
            # Füge content_matches hinzu (ohne Duplikate)
            for match in content_matches:
                if match['id'] not in seen_ids:
                    all_duplicates.append(match)
                    seen_ids.add(match['id'])
            
            # Sortiere nach Ähnlichkeit (höchste zuerst)
            all_duplicates.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            if all_duplicates:
                return {
                    'has_duplicates': True,
                    'duplicates': all_duplicates,
                    'threshold': min_similarity
                }
            
            return {'has_duplicates': False, 'duplicates': []}
            
        except Exception as e:
            logger.error(f"Fehler bei Dublettenerkennung: {e}", exc_info=True)
            return {'has_duplicates': False, 'duplicates': []}
