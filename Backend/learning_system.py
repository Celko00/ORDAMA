"""
Intelligentes Lernsystem für Ähnlichkeitssuche
Lernt aus Nutzerverhalten und verbessert Suchergebnisse automatisch
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LearningSystem:
    """Verwaltet das Lernsystem für intelligente Ähnlichkeitssuche"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def log_search(self, user_id: int, search_type: str, query_params: dict, result_count: int) -> int:
        """Protokolliert eine Suchanfrage"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO search_logs (user_id, search_type, query_params, result_count)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, search_type, json.dumps(query_params), result_count))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Fehler beim Protokollieren der Suche: {e}")
            return 0
    
    def log_result_click(self, search_log_id: int, record_id: int, click_position: int):
        """Protokolliert einen Klick auf ein Suchergebnis"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO search_result_clicks (search_log_id, record_id, click_position)
                    VALUES (?, ?, ?)
                ''', (search_log_id, record_id, click_position))
                conn.commit()
        except Exception as e:
            logger.error(f"Fehler beim Protokollieren des Klicks: {e}")
    
    def get_similarity_weights(self, user_id: Optional[int] = None) -> Dict[str, float]:
        """Lädt die Gewichtungs-Konfiguration für Ähnlichkeitssuche"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Zuerst benutzerspezifische Gewichte versuchen
                if user_id:
                    cursor.execute('''
                        SELECT weight_title, weight_content, weight_address, weight_hashtags,
                               weight_category, weight_border_color, weight_status, weight_attachments,
                               weight_ocr_text, weight_creation_date, weight_update_date
                        FROM similarity_weights WHERE user_id = ?
                    ''', (user_id,))
                    weights = cursor.fetchone()
                    if weights:
                        return {
                            'title': weights['weight_title'],
                            'content': weights['weight_content'],
                            'address': weights['weight_address'],
                            'hashtags': weights['weight_hashtags'],
                            'category': weights['weight_category'],
                            'border_color': weights['weight_border_color'],
                            'status': weights['weight_status'],
                            'attachments': weights['weight_attachments'],
                            'ocr_text': weights['weight_ocr_text'],
                            'creation_date': weights['weight_creation_date'],
                            'update_date': weights['weight_update_date']
                        }
                
                # Fallback auf globale Standard-Gewichte
                cursor.execute('''
                    SELECT weight_title, weight_content, weight_address, weight_hashtags,
                           weight_category, weight_border_color, weight_status, weight_attachments,
                           weight_ocr_text, weight_creation_date, weight_update_date
                    FROM similarity_weights WHERE user_id IS NULL
                ''')
                weights = cursor.fetchone()
                if weights:
                    return {
                        'title': weights['weight_title'],
                        'content': weights['weight_content'],
                        'address': weights['weight_address'],
                        'hashtags': weights['weight_hashtags'],
                        'category': weights['weight_category'],
                        'border_color': weights['weight_border_color'],
                        'status': weights['weight_status'],
                        'attachments': weights['weight_attachments'],
                        'ocr_text': weights['weight_ocr_text'],
                        'creation_date': weights['weight_creation_date'],
                        'update_date': weights['weight_update_date']
                    }
                
                # Fallback auf Standardwerte
                return {
                    'title': 1.0,
                    'content': 1.0,
                    'address': 0.5,
                    'hashtags': 0.8,
                    'category': 0.6,
                    'border_color': 0.3,
                    'status': 0.4,
                    'attachments': 0.5,
                    'ocr_text': 0.7,
                    'creation_date': 0.2,
                    'update_date': 0.3
                }
        except Exception as e:
            logger.error(f"Fehler beim Laden der Gewichte: {e}")
            return {
                'title': 1.0,
                'content': 1.0,
                'address': 0.5,
                'hashtags': 0.8,
                'category': 0.6,
                'border_color': 0.3,
                'status': 0.4,
                'attachments': 0.5,
                'ocr_text': 0.7,
                'creation_date': 0.2,
                'update_date': 0.3
            }
    
    def update_similarity_weights(self, user_id: Optional[int], weights: Dict[str, float]):
        """Aktualisiert die Gewichtungs-Konfiguration"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if user_id:
                    # Prüfen ob benutzerspezifische Eintrag existiert
                    cursor.execute('SELECT id FROM similarity_weights WHERE user_id = ?', (user_id,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        cursor.execute('''
                            UPDATE similarity_weights
                            SET weight_title = ?, weight_content = ?, weight_address = ?, weight_hashtags = ?,
                                weight_category = ?, weight_border_color = ?, weight_status = ?, weight_attachments = ?,
                                weight_ocr_text = ?, weight_creation_date = ?, weight_update_date = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = ?
                        ''', (
                            weights.get('title', 1.0), weights.get('content', 1.0), weights.get('address', 0.5),
                            weights.get('hashtags', 0.8), weights.get('category', 0.6), weights.get('border_color', 0.3),
                            weights.get('status', 0.4), weights.get('attachments', 0.5), weights.get('ocr_text', 0.7),
                            weights.get('creation_date', 0.2), weights.get('update_date', 0.3), user_id
                        ))
                        logger.info(f"Benutzerspezifische Gewichtungen aktualisiert für user_id={user_id}")
                    else:
                        cursor.execute('''
                            INSERT INTO similarity_weights
                            (user_id, weight_title, weight_content, weight_address, weight_hashtags,
                             weight_category, weight_border_color, weight_status, weight_attachments,
                             weight_ocr_text, weight_creation_date, weight_update_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            user_id, weights.get('title', 1.0), weights.get('content', 1.0), weights.get('address', 0.5),
                            weights.get('hashtags', 0.8), weights.get('category', 0.6), weights.get('border_color', 0.3),
                            weights.get('status', 0.4), weights.get('attachments', 0.5), weights.get('ocr_text', 0.7),
                            weights.get('creation_date', 0.2), weights.get('update_date', 0.3)
                        ))
                        logger.info(f"Benutzerspezifische Gewichtungen erstellt für user_id={user_id}")
                else:
                    # Globale Gewichte aktualisieren
                    cursor.execute('SELECT id FROM similarity_weights WHERE user_id IS NULL')
                    existing = cursor.fetchone()
                    
                    if existing:
                        cursor.execute('''
                            UPDATE similarity_weights
                            SET weight_title = ?, weight_content = ?, weight_address = ?, weight_hashtags = ?,
                                weight_category = ?, weight_border_color = ?, weight_status = ?, weight_attachments = ?,
                                weight_ocr_text = ?, weight_creation_date = ?, weight_update_date = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE user_id IS NULL
                        ''', (
                            weights.get('title', 1.0), weights.get('content', 1.0), weights.get('address', 0.5),
                            weights.get('hashtags', 0.8), weights.get('category', 0.6), weights.get('border_color', 0.3),
                            weights.get('status', 0.4), weights.get('attachments', 0.5), weights.get('ocr_text', 0.7),
                            weights.get('creation_date', 0.2), weights.get('update_date', 0.3)
                        ))
                        logger.info("Globale Gewichtungen aktualisiert")
                    else:
                        cursor.execute('''
                            INSERT INTO similarity_weights
                            (user_id, weight_title, weight_content, weight_address, weight_hashtags,
                             weight_category, weight_border_color, weight_status, weight_attachments,
                             weight_ocr_text, weight_creation_date, weight_update_date)
                            VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            weights.get('title', 1.0), weights.get('content', 1.0), weights.get('address', 0.5),
                            weights.get('hashtags', 0.8), weights.get('category', 0.6), weights.get('border_color', 0.3),
                            weights.get('status', 0.4), weights.get('attachments', 0.5), weights.get('ocr_text', 0.7),
                            weights.get('creation_date', 0.2), weights.get('update_date', 0.3)
                        ))
                        logger.info("Globale Gewichtungen erstellt")
                
                conn.commit()
                logger.info(f"Gewichte erfolgreich gespeichert für user_id={user_id}")
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Gewichte: {e}")
            raise
    
    def calculate_similarity_score(self, record: dict, target_record: dict, weights: Dict[str, float]) -> float:
        """Berechnet den Ähnlichkeits-Score zwischen zwei Akten basierend auf Gewichtungen"""
        score = 0.0
        
        # Titel-Ähnlichkeit
        if record.get('title') and target_record.get('title'):
            title_similarity = self._calculate_text_similarity(record['title'], target_record['title'])
            score += title_similarity * weights.get('title', 1.0)
        
        # Inhalt-Ähnlichkeit
        if record.get('content') and target_record.get('content'):
            content_similarity = self._calculate_text_similarity(record['content'], target_record['content'])
            score += content_similarity * weights.get('content', 1.0)
        
        # Adresse-Ähnlichkeit
        if record.get('address') and target_record.get('address'):
            address_similarity = self._calculate_text_similarity(record['address'], target_record['address'])
            score += address_similarity * weights.get('address', 0.5)
        
        # Hashtags-Ähnlichkeit
        if record.get('hashtags') and target_record.get('hashtags'):
            hashtag_similarity = self._calculate_hashtag_similarity(record['hashtags'], target_record['hashtags'])
            score += hashtag_similarity * weights.get('hashtags', 0.8)
        
        # Kategorie-Übereinstimmung
        if record.get('category_id') and target_record.get('category_id'):
            category_match = 1.0 if record['category_id'] == target_record['category_id'] else 0.0
            score += category_match * weights.get('category', 0.6)
        
        # Rahmenfarbe-Übereinstimmung
        if record.get('border_color') and target_record.get('border_color'):
            color_match = 1.0 if record['border_color'] == target_record['border_color'] else 0.0
            score += color_match * weights.get('border_color', 0.3)
        
        # Status-Übereinstimmung
        if record.get('status') and target_record.get('status'):
            status_match = 1.0 if record['status'] == target_record['status'] else 0.0
            score += status_match * weights.get('status', 0.4)
        
        # Anhänge-Ähnlichkeit (Anzahl)
        attachment_count_diff = abs(record.get('attachment_count', 0) - target_record.get('attachment_count', 0))
        attachment_similarity = max(0.0, 1.0 - attachment_count_diff / 10.0)  # Normalisiert auf 0-1
        score += attachment_similarity * weights.get('attachments', 0.5)
        
        # OCR-Text-Ähnlichkeit
        if record.get('ocr_text') and target_record.get('ocr_text'):
            ocr_similarity = self._calculate_text_similarity(record['ocr_text'], target_record['ocr_text'])
            score += ocr_similarity * weights.get('ocr_text', 0.7)
        
        # Erstellungsdatum-Ähnlichkeit
        if record.get('created_at') and target_record.get('created_at'):
            try:
                from datetime import datetime
                # Konvertiere String zu datetime wenn nötig
                created_at1 = record['created_at'] if isinstance(record['created_at'], datetime) else datetime.fromisoformat(record['created_at'])
                created_at2 = target_record['created_at'] if isinstance(target_record['created_at'], datetime) else datetime.fromisoformat(target_record['created_at'])
                date_diff = abs((created_at1 - created_at2).days)
                date_similarity = max(0.0, 1.0 - date_diff / 365.0)  # Normalisiert auf 0-1 (1 Jahr)
                score += date_similarity * weights.get('creation_date', 0.2)
            except (ValueError, TypeError):
                # Bei Fehler beim Datum-Parsing überspringen
                pass
        
        # Update-Datum-Ähnlichkeit
        if record.get('updated_at') and target_record.get('updated_at'):
            try:
                from datetime import datetime
                # Konvertiere String zu datetime wenn nötig
                updated_at1 = record['updated_at'] if isinstance(record['updated_at'], datetime) else datetime.fromisoformat(record['updated_at'])
                updated_at2 = target_record['updated_at'] if isinstance(target_record['updated_at'], datetime) else datetime.fromisoformat(target_record['updated_at'])
                date_diff = abs((updated_at1 - updated_at2).days)
                date_similarity = max(0.0, 1.0 - date_diff / 365.0)  # Normalisiert auf 0-1 (1 Jahr)
                score += date_similarity * weights.get('update_date', 0.3)
            except (ValueError, TypeError):
                # Bei Fehler beim Datum-Parsing überspringen
                pass
        
        return score
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Berechnet die Ähnlichkeit zwischen zwei Texten (einfache Token-basierte Ähnlichkeit)"""
        if not text1 or not text2:
            return 0.0
        
        # Tokenisierung
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Jaccard-Ähnlichkeit
        intersection = len(tokens1.intersection(tokens2))
        union = len(tokens1.union(tokens2))
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_hashtag_similarity(self, hashtags1: str, hashtags2: str) -> float:
        """Berechnet die Ähnlichkeit zwischen Hashtags"""
        if not hashtags1 or not hashtags2:
            return 0.0
        
        # Hashtags extrahieren
        tags1 = set(tag.strip() for tag in hashtags1.split('#') if tag.strip())
        tags2 = set(tag.strip() for tag in hashtags2.split('#') if tag.strip())
        
        if not tags1 or not tags2:
            return 0.0
        
        # Jaccard-Ähnlichkeit
        intersection = len(tags1.intersection(tags2))
        union = len(tags1.union(tags2))
        
        return intersection / union if union > 0 else 0.0
    
    def learn_from_clicks(self, user_id: Optional[int] = None, days: int = 30):
        """Lernt aus Klickdaten und passt Gewichtungen automatisch an"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Klickdaten der letzten X Tage abrufen
                cutoff_date = datetime.now() - timedelta(days=days)
                cursor.execute('''
                    SELECT src.click_position, r.title, r.content, r.address, r.hashtags,
                           r.category_id, r.border_color, r.status, r.attachment_count,
                           ao.ocr_text, r.created_at, r.updated_at
                    FROM search_result_clicks src
                    JOIN search_logs sl ON src.search_log_id = sl.id
                    JOIN records r ON src.record_id = r.id
                    LEFT JOIN attachment_ocr ao ON r.id = ao.record_id
                    WHERE sl.created_at >= ? AND (sl.user_id = ? OR ? IS NULL)
                ''', (cutoff_date.isoformat(), user_id, user_id))
                
                clicks = cursor.fetchall()
                
                if not clicks:
                    logger.info("Keine Klickdaten für Lernen gefunden")
                    return
                
                # Statistiken für jeden Faktor berechnen
                factor_stats = {
                    'title': {'clicks': 0, 'impressions': 0},
                    'content': {'clicks': 0, 'impressions': 0},
                    'address': {'clicks': 0, 'impressions': 0},
                    'hashtags': {'clicks': 0, 'impressions': 0},
                    'category': {'clicks': 0, 'impressions': 0},
                    'border_color': {'clicks': 0, 'impressions': 0},
                    'status': {'clicks': 0, 'impressions': 0},
                    'attachments': {'clicks': 0, 'impressions': 0},
                    'ocr_text': {'clicks': 0, 'impressions': 0},
                    'creation_date': {'clicks': 0, 'impressions': 0},
                    'update_date': {'clicks': 0, 'impressions': 0}
                }
                
                # Klicks nach Position analysieren (frühere Positionen = wichtiger)
                for click in clicks:
                    position_weight = 1.0 / (click['click_position'] or 1)  # Position 1 = Gewicht 1.0
                    
                    if click['title']:
                        factor_stats['title']['clicks'] += position_weight
                        factor_stats['title']['impressions'] += 1
                    
                    if click['content']:
                        factor_stats['content']['clicks'] += position_weight
                        factor_stats['content']['impressions'] += 1
                    
                    if click['address']:
                        factor_stats['address']['clicks'] += position_weight
                        factor_stats['address']['impressions'] += 1
                    
                    if click['hashtags']:
                        factor_stats['hashtags']['clicks'] += position_weight
                        factor_stats['hashtags']['impressions'] += 1
                    
                    if click['category_id']:
                        factor_stats['category']['clicks'] += position_weight
                        factor_stats['category']['impressions'] += 1
                    
                    if click['border_color']:
                        factor_stats['border_color']['clicks'] += position_weight
                        factor_stats['border_color']['impressions'] += 1
                    
                    if click['status']:
                        factor_stats['status']['clicks'] += position_weight
                        factor_stats['status']['impressions'] += 1
                    
                    if click['attachment_count'] and click['attachment_count'] > 0:
                        factor_stats['attachments']['clicks'] += position_weight
                        factor_stats['attachments']['impressions'] += 1
                    
                    if click['ocr_text']:
                        factor_stats['ocr_text']['clicks'] += position_weight
                        factor_stats['ocr_text']['impressions'] += 1
                    
                    if click['created_at']:
                        factor_stats['creation_date']['clicks'] += position_weight
                        factor_stats['creation_date']['impressions'] += 1
                    
                    if click['updated_at']:
                        factor_stats['update_date']['clicks'] += position_weight
                        factor_stats['update_date']['impressions'] += 1
                
                # Neue Gewichtungen basierend auf Klick-Rate berechnen mit Vergessen-Mechanismus
                current_weights = self.get_similarity_weights(user_id)
                new_weights = {}
                
                for factor, stats in factor_stats.items():
                    if stats['impressions'] > 0:
                        click_rate = stats['clicks'] / stats['impressions']
                        
                        # Vergessen-Mechanismus: Wenn Klick-Rate niedrig ist, Gewicht reduzieren
                        # Wenn Klick-Rate hoch ist, Gewicht erhöhen
                        # Dies verhindert "Einbahnstraßen" und erlaubt Anpassung an neue Muster
                        
                        old_weight = current_weights.get(factor, 0.5)
                        
                        # Konservative Anpassung mit Vergessen-Faktor
                        learning_rate = 0.05  # Langsames Lernen
                        forget_rate = 0.03   # Langsames Vergessen
                        
                        if click_rate > 0.6:
                            # Hohe Klick-Rate: Gewicht erhöhen
                            new_weight = old_weight + learning_rate * (click_rate - 0.5)
                        elif click_rate < 0.4:
                            # Niedrige Klick-Rate: Gewicht reduzieren (Vergessen)
                            new_weight = old_weight - forget_rate * (0.5 - click_rate)
                        else:
                            # Mittlere Klick-Rate: Gewicht beibehalten
                            new_weight = old_weight
                        
                        # Gewicht auf sinnvollen Bereich begrenzen (0.1 - 2.0)
                        new_weights[factor] = max(0.1, min(2.0, new_weight))
                        
                        logger.info(f"Faktor {factor}: Klick-Rate={click_rate:.3f}, Alt={old_weight:.2f}, Neu={new_weights[factor]:.2f}")
                    else:
                        # Keine Daten: Gewicht leicht Richtung Standardwerte (0.5) bewegen
                        old_weight = current_weights.get(factor, 0.5)
                        standard_weight = 0.5
                        new_weights[factor] = old_weight + (standard_weight - old_weight) * 0.1  # 10% Richtung Standard
                
                # Gewichtungen aktualisieren
                self.update_similarity_weights(user_id, new_weights)
                
                logger.info(f"Lernen abgeschlossen: {len(clicks)} Klicks analysiert, Gewichtungen angepasst")
                
        except Exception as e:
            logger.error(f"Fehler beim Lernen aus Klicks: {e}")
    
    def get_learning_statistics(self, user_id: Optional[int] = None) -> List[Dict]:
        """Lädt Lern-Statistiken"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if user_id:
                    cursor.execute('''
                        SELECT factor_name, click_count, total_impressions, click_rate, last_updated
                        FROM learning_statistics
                        WHERE user_id = ?
                        ORDER BY factor_name
                    ''', (user_id,))
                else:
                    cursor.execute('''
                        SELECT factor_name, SUM(click_count) as click_count, 
                               SUM(total_impressions) as total_impressions,
                               AVG(click_rate) as click_rate,
                               MAX(last_updated) as last_updated
                        FROM learning_statistics
                        GROUP BY factor_name
                        ORDER BY factor_name
                    ''')
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Fehler beim Laden der Lern-Statistiken: {e}")
            return []
