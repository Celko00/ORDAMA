"""
Command Parser für ORDAMA Assistant
- Lokaler Parser für natürliche Sprache rund um Akten
- Extrahiert Befehle aus natürlicher Sprache
"""

import logging
import re
from datetime import datetime, timedelta

from assistant_learning import _clean_text, _normalize_for_search, _normalize_for_parse, AssistantLearningStore

logger = logging.getLogger(__name__)


class CommandParser:
    """Lokaler Parser für natürliche Sprache rund um Akten."""

    def __init__(self, learning_store=None):
        self.learning_store = learning_store
        self.month_names = {
            'januar': 1, 'februar': 2, 'maerz': 3, 'märz': 3, 'april': 4,
            'mai': 5, 'juni': 6, 'juli': 7, 'august': 8, 'september': 9,
            'oktober': 10, 'november': 11, 'dezember': 12
        }

        self.action_keywords = {
            'create_record': [
                'erstelle', 'erstell', 'erstele', 'erstel', 'werstelle', 'ertselle',
                'lege', 'anlegen', 'anlege', 'neu', 'neu anlegen', 'neue akte',
                'erzeuge', 'mach', 'mache', 'erfasse', 'eröffne', 'eroeffne',
                'erstell bitte', 'leg an', 'lege bitte an', 'lege neu an',
                'mach mir', 'mach bitte', 'fuege an', 'füge an', 'anlegen fuer',
                'anlegen für', 'als akte anlegen', 'als akte speichern', 'speichere als akte',
                'notiere', 'schreib auf', 'mach notiz', 'trage ein', 'erfasze',
                'starte', 'beginne', 'richte ein', 'mache an'
            ],
            'update_record': [
                'bearbeite', 'bearbeiten', 'aendere', 'ändere', 'aktualisiere',
                'update', 'korrigiere', 'setze', 'passe an', 'ergänze', 'ergaenze',
                'füge hinzu', 'fuege hinzu', 'ändere bei', 'ändere in', 'ändere akte',
                'bearbeite akte', 'aktualisiere akte', 'trage ein', 'trage nach',
                'setze bei', 'ändere für', 'ändere fuer', 'modifiziere', 'verändere',
                'veraendere', 'editiere', 'überarbeite', 'ueberarbeite', 'ergänze mit',
                'ergaenze mit', 'hinzufuegen', 'hinzufügen', 'schreibe um', 'aendere ab'
            ],
            'summarize_record': [
                'fasse zusammen', 'zusammenfassen', 'zusammenfassung', 'kurzfassung',
                'kurzinhalt', 'worum geht es', 'inhalt zusammenfassen', 'gib mir eine zusammenfassung',
                'kurz zusammenfassen', 'kurz erklären', 'kurz erklaeren', 'kurzüberblick',
                'kurzueberblick', 'zusammengefasst', 'was steht drin', 'was ist enthalten',
                'zeige details', 'infos anzeigen', 'informationen', 'was ist das',
                'beschreibe', 'erzähle über', 'erzaehle ueber', 'gib auskunft'
            ],
            'search': [
                'suche', 'such', 'finde', 'finden', 'zeige', 'zeige mir',
                'suche nach', 'finde akte', 'finde akten', 'öffne', 'oeffne',
                'zeige akte', 'zeige akten', 'hole', 'hole akte', 'suche akte'
            ],
            'delete_record': [
                r'lösch(?:e)?',
                r'entfern(?:e)?',
                r'entfernen'
            ],
            'archive_record': [
                r'archivier(?:e)?',
                r'archiv'
            ],
            'search': [
                r'such(?:e)?',
                r'finde',
                r'zeige\s+mir',
                r'liste\s+auf',
                r'wo\s+ist',
                r'gib\s+mir',
                r'zeig'
            ],
            'summarize_record': [
                r'zusammenfass(?:en|e)?',
                r'zusammenfassung',
                r'was\s+ist',
                r'erklär(?:e)?',
                r'info'
            ],
            'set_status': [
                r'setze\s+status',
                r'ändere\s+status',
                r'aendere\s+status',
                r'status\s+setzen'
            ],
            'set_color': [
                r'markier(?:e)?',
                r'färbe',
                r'faerbe',
                r'setze\s+farbe',
                r'ändere\s+farbe',
                r'aendere\s+farbe'
            ],
            'set_reminder': [
                r'erinner(?:e)?\s+mich',
                r'setze\s+termin',
                r'termin\s+setzen',
                r'erinnerung\s+setzen'
            ],
            'add_note': [
                r'notier(?:e)?',
                r'füge\s+notiz\s+hinzu',
                r'fuege\s+notiz\s+hinzu'
            ],
            'set_category': [
                r'kategorisier(?:e)?',
                r'verschiebe\s+in',
                r'ordne\s+ein',
                r'kategorie\s+setzen'
            ],
            'help': [
                r'hilfe',
                r'was\s+kannst\s+du',
                r'befehle',
                r'anleitung'
            ]
        }

        self.record_keywords = [
            'akte', 'akten', 'vorgang', 'dossier', 'eintrag', 'fall', 'datensatz',
            'datei', 'dokument'
        ]

        self.field_marker_patterns = self._load_field_marker_patterns()

        self.reference_markers = [
            r'akte\s*#?\s*\d+',
            r'akte',
            r'vorgang',
            r'dossier',
            r'eintrag',
            r'fall',
            r'datensatz',
            r'nummer',
            r'nr\.?'
        ]

        self.stop_word_patterns = [
            r'\bund\s+(?:dem\s+)?(?:titel|adresse|inhalt|beschreibung|notiz|text|status|kategorie|ablage|ordner|rahmenfarbe|termin|erinnerung|vermerk|hinweis|bemerkung|wiederholung|sichtbarkeit)\b',
            r'\bmit\s+(?:dem\s+)?(?:titel|adresse|inhalt|beschreibung|notiz|text|status|kategorie|ablage|ordner|rahmenfarbe|termin|erinnerung|vermerk|hinweis|bemerkung|wiederholung|sichtbarkeit)\b',
            r'\bund\s+(?:setze|ändere|aendere|aktualisiere|ergänze|ergaenze|füge|fuege|notiere|schreib(?:e)?|trage)\b',
            r'\b(?:am|zum)\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}\b',
            r'\b(?:am|zum)\s+\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}\b'
        ]

        self.noise_prefix_pattern = re.compile(
            r'^\s*(?:bitte|doch|mal|einmal|kannst\s+du|kannst\s+du\s+bitte|würdest\s+du|wuerdest\s+du|'
            r'mach(?:\s+mir)?|mach\s+bitte|leg(?:e)?\s+bitte|erstell(?:e)?\s+bitte)\s+',
            flags=re.IGNORECASE
        )

    def _load_field_marker_patterns(self):
        """Load field marker patterns from learning store or use defaults"""
        if self.learning_store:
            field_synonyms = self.learning_store.get_field_synonyms()
            patterns = {}
            for field_name, synonyms in field_synonyms.items():
                patterns[field_name] = [self._synonym_to_pattern(synonym) for synonym in synonyms]
            return patterns
        
        return {
            'title': [
                r'mit\s+(?:dem\s+)?titel',
                r'(?:und\s+)?(?:dem\s+)?titel',
                r'mit\s+dem\s+namen',
                r'überschrift',
                r'betreff',
                r'namens',
                r'name',
                r'namen',
                r'genannt',
                r'auf\s+den\s+namen',
                r'unter\s+dem\s+titel',
                r'bezeichnung',
                r'benannt',
                r'titel\s+ist',
                r'heißt',
                r'heisst'
            ],
            'address': [
                r'adresse',
                r'anschrift',
                r'straße',
                r'strasse'
            ],
            'content': [
                r'mit\s+(?:dem\s+)?inhalt',
                r'(?:und\s+)?(?:dem\s+)?inhalt',
                r'beschreibung',
                r'notiz',
                r'text',
                r'details',
                r'inhalt\s+soll\s+sein',
                r'notiere',
                r'schreib(?:e)?',
                r'trage\s+ein',
                r'mit\s+folgendem\s+inhalt',
                r'inhalt\s+ist',
                r'beschreibt',
                r'enthält',
                r'enthaelt',
                r'mit\s+dem\s+text',
                r'und\s+der\s+inhalt',
                r'und\s+inhalt',
                r'und\s+text'
            ],
            'reminder_date': [
                r'erinnerung',
                r'termin',
                r'fällig(?:keit)?',
                r'faellig(?:keit)?',
                r'erinnere mich',
                r'erinnerung an',
                r'am\s+termin',
                r'zum\s+termin',
                r'bis\s+zum'
            ],
            'reminder_end_date': [
                r'bis\s+termin',
                r'bis\s+zum\s+termin',
                r'endtermin',
                r'termin\s+ende'
            ],
            'reminder_repeat': [
                r'wiederholung',
                r'wiederhole',
                r'wiederholen',
                r'wiederkehrend',
                r'wiederkehrender\s+termin'
            ],
            'reminder_assigned_to': [
                r'sichtbarkeit',
                r'für\s+wen',
                r'für',
                r'sichtbar\s+für',
                r'zuweisen\s+an',
                r'zugewiesen\s+an',
                r'erinnerung\s+für'
            ],
            'status': [
                r'status',
                r'zustand',
                r'stand'
            ],
            'category': [
                r'kategorie',
                r'ablage',
                r'ordner'
            ],
            'note': [
                r'vermerk',
                r'notiz',
                r'hinweis',
                r'bemerkung',
                r'kommentar'
            ],
            'border_color': [
                r'rahmenfarbe',
                r'farbe',
                r'rahmen'
            ],
            'add_reminder': [
                r'erinnerung\s+hinzufügen',
                r'erinnerung\s+hinzu',
                r'termin\s+hinzufügen',
                r'termin\s+hinzu',
                r'neue\s+erinnerung',
                r'neuer\s+termin',
                r'erinnerung\s+erstellen',
                r'termin\s+erstellen'
            ]
        }

    def _synonym_to_pattern(self, synonym):
        """Convert a synonym string to a regex pattern"""
        escaped = re.escape(synonym)
        return rf'\b{escaped}\b'

    def parse(self, text):
        original = (text or '').strip()
        normalized = _normalize_for_parse(original)

        logger.info("Parse-Debug: Versuche zu parsen: '%s'", normalized)

        if not normalized:
            return {'command': 'unknown', 'original': original, '_original_command': original}

        if self.learning_store and self.learning_store.is_blacklisted(normalized):
            logger.info("Parse-Debug: Befehl ist auf der Blacklist: '%s'", normalized)
            return {'command': 'blacklisted', 'original': original, '_original_command': original, 'message': 'Dieser Befehl wurde als falsch markiert. Bitte formuliere ihn anders.'}

        if self.learning_store:
            learned_match = self.learning_store.find_feedback_match(original)
            if learned_match:
                return learned_match

        if self._contains_any(normalized, self.action_keywords['help']):
            return {'command': 'help', 'data': {}, '_original_command': original}

        if self._contains_any(normalized, self.action_keywords['summarize_record']) or self._looks_like_summarize(normalized):
            return self._extract_summarize_record(original, normalized)

        has_create_signal = self._contains_any(normalized, self.action_keywords['create_record'])
        has_record_signal = any(word in normalized for word in self.record_keywords)
        has_field_signal = any(self._extract_segment_value(original, normalized, field_name) for field_name in self.field_marker_patterns)

        if has_create_signal or (has_record_signal and has_field_signal):
            return self._extract_create_record(original, normalized)

        if self._contains_any(normalized, self.action_keywords['update_record']):
            return self._extract_update_record(original, normalized)

        if self._contains_any(normalized, self.action_keywords['delete_record']):
            return self._extract_delete_record(original, normalized)

        if self._contains_any(normalized, self.action_keywords['archive_record']):
            return self._extract_archive_record(original, normalized)

        if self._contains_any(normalized, self.action_keywords['set_status']):
            return self._extract_set_status(original, normalized)

        if self._contains_any(normalized, self.action_keywords['set_color']):
            return self._extract_set_color(original, normalized)

        if self._contains_any(normalized, self.action_keywords['set_reminder']):
            return self._extract_set_reminder(original, normalized)

        if self._contains_any(normalized, self.action_keywords['list_records']):
            return {'command': 'list_records', 'data': {}, '_original_command': original}

        if self._contains_any(normalized, self.action_keywords['add_note']):
            return self._extract_add_note(original, normalized)

        if self._contains_any(normalized, self.action_keywords['set_category']):
            return self._extract_set_category(original, normalized)

        if self._contains_any(normalized, self.action_keywords['search']):
            return self._extract_search(original, normalized)

        if has_record_signal and self._extract_date(original):
            return self._extract_create_record(original, normalized)

        logger.info("Parse-Debug: Kein Muster erkannt für '%s'", normalized)
        return {'command': 'unknown', 'original': original}

    def _contains_any(self, normalized, keywords):
        return any(keyword in normalized for keyword in keywords)

    def _looks_like_summarize(self, normalized):
        if not normalized:
            return False
        return bool(
            re.search(r'\bfasse\b.*\bzusammen\b', normalized, flags=re.IGNORECASE)
            or re.search(r'\bkurz\b.*\bzusammen\b', normalized, flags=re.IGNORECASE)
        )

    def _strip_noise_prefix(self, text):
        if not text:
            return text
        previous = None
        current = text.strip()
        while previous != current:
            previous = current
            current = self.noise_prefix_pattern.sub('', current).strip()
        return current

    def _cleanup_candidate(self, value):
        value = _clean_text(value)
        if not value:
            return None
        value = re.sub(
            r'\s+(?:und\s+)?(?:setze|ändere|aendere|aktualisiere|ergänze|ergaenze|füge|fuege|'
            r'notiere|schreib(?:e)?|trage)\b.*$',
            '',
            value,
            flags=re.IGNORECASE
        )
        value = re.sub(
            r'\s+\b(?:mit|dem|den|der|das)\s+(?:titel|inhalt|beschreibung|notiz|text|status|kategorie|'
            r'adresse|anschrift|farbe|rahmenfarbe|stadt|ort|termin|erinnerung|erinnerung)\b.*$',
            '',
            value,
            flags=re.IGNORECASE
        )
        value = re.sub(r'\s+(?:dem|den|der|das|die|ein|eine|einen|einem|zusammen|kurz|bitte)$', '', value, flags=re.IGNORECASE)
        value = re.sub(r'\s+\b(?:anlegen|anlegen\.|an|erstellen|erfasst|speichern)\b$', '', value, flags=re.IGNORECASE)
        value = re.sub(r'^\b[a-zäöüß]\b\s+', '', value, flags=re.IGNORECASE)
        value = _clean_text(value)
        if not value:
            return None

        generic_words = {
            'und', 'mit', 'ohne', 'bitte', 'neu', 'neue', 'neuen', 'eine', 'einen', 'ein',
            'akte', 'akten', 'vorgang', 'dossier', 'eintrag', 'fall', 'datensatz'
        }
        normalized_value = _normalize_for_search(value)
        if normalized_value in generic_words:
            return None
        return value

    def _extract_segment_value(self, original, normalized, field_name):
        patterns = self.field_marker_patterns.get(field_name, [])
        matches = []
        all_pattern_strings = []
        for marker_patterns in self.field_marker_patterns.values():
            all_pattern_strings.extend(marker_patterns)
        all_pattern_strings.extend(self.stop_word_patterns)

        for pattern in patterns:
            for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
                matches.append((match.start(), match.end()))

        if not matches:
            return None

        start, end = sorted(matches, key=lambda item: item[0])[0]
        next_positions = []
        for pattern in all_pattern_strings:
            for next_match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
                if next_match.start() > end:
                    next_positions.append(next_match.start())
        
        if field_name == 'title':
            date_pattern = r'\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b'
            for date_match in re.finditer(date_pattern, normalized, flags=re.IGNORECASE):
                if date_match.start() > end:
                    next_positions.append(date_match.start())
            
            month_pattern = r'\b(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\b'
            for month_match in re.finditer(month_pattern, normalized, flags=re.IGNORECASE):
                if month_match.start() > end:
                    next_positions.append(month_match.start())
            
            content_markers = r'\b(?:inhalt|beschreibung|notiz|text|details)\b'
            for content_match in re.finditer(content_markers, normalized, flags=re.IGNORECASE):
                if content_match.start() > end:
                    next_positions.append(content_match.start())
        
        next_start = min(next_positions) if next_positions else len(normalized)
        value = original[end:next_start]
        value = re.sub(r'^\s*(?:ist|auf|zu|=|:|-)\s*', '', value, flags=re.IGNORECASE)
        return _clean_text(value)

    def _extract_quoted_value(self, original):
        quoted = re.search(r'[""„](.+?)[""]', original)
        if quoted:
            return _clean_text(quoted.group(1))
        single = re.search(r"'(.+?)'", original)
        if single:
            return _clean_text(single.group(1))
        return None

    def _parse_date_text(self, text):
        """Parse a date text string and return ISO format date"""
        text_lower = text.lower()
        
        iso_match = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', text)
        if iso_match:
            year, month, day = map(int, iso_match.groups())
            try:
                return datetime(year, month, day).isoformat()
            except ValueError:
                pass
        
        numeric_match = re.search(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})', text)
        if numeric_match:
            day, month, year = map(int, numeric_match.groups())
            try:
                return datetime(year, month, day).isoformat()
            except ValueError:
                pass
        
        short_year_match = re.search(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2})', text)
        if short_year_match:
            day, month, year = map(int, short_year_match.groups())
            year = 2000 + year if year < 50 else 1900 + year
            try:
                return datetime(year, month, day).isoformat()
            except ValueError:
                pass
        
        for month_name, month_num in self.month_names.items():
            if month_name in text_lower:
                day_match = re.search(r'(\d{1,2})\.?\s*' + re.escape(month_name), text_lower)
                if day_match:
                    day = int(day_match.group(1))
                    year_match = re.search(r'\b(\d{4})\b', text)
                    if year_match:
                        year = int(year_match.group(1))
                    else:
                        year = datetime.now().year
                    try:
                        return datetime(year, month_num, day).isoformat()
                    except ValueError:
                        pass
        
        return None

    def _extract_date(self, text):
        if not text:
            return None

        date_formats = []
        if self.learning_store:
            date_formats = self.learning_store.get_date_formats()
        
        if not date_formats:
            date_formats = [
                r'\d{4}[./-]\d{1,2}[./-]\d{1,2}',
                r'\d{1,2}[./-]\d{1,2}[./-]\d{4}',
                r'\d{1,2}[./-]\d{1,2}[./-]\d{2}',
                r'\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}',
                r'\d{1,2}\s+(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}',
                r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{4}',
                r'\d{1,2}\s+(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{4}'
            ]
        
        for pattern in date_formats:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                matched_text = match.group(0)
                parsed_date = self._parse_date_text(matched_text)
                if parsed_date:
                    return parsed_date

        short_match = re.search(r'(\d{1,2})[./-](\d{1,2})(?![./-]\d)', text)
        if short_match:
            day, month = map(int, short_match.groups())
            current_year = datetime.now().year
            try:
                return datetime(current_year, month, day).isoformat()
            except ValueError:
                return None

        normalized = _normalize_for_search(text)
        month_pattern = '|'.join(map(re.escape, self.month_names.keys()))
        month_match = re.search(rf'(\d{{1,2}})\.?\s*({month_pattern})\s+(\d{{4}})', normalized, flags=re.IGNORECASE)
        if month_match:
            day = int(month_match.group(1))
            month = self.month_names[month_match.group(2).lower()]
            year = int(month_match.group(3))
            try:
                return datetime(year, month, day).isoformat()
            except ValueError:
                return None

        today = datetime.now().date()
        relative_patterns = {
            r'\bheute\b': 0,
            r'\bmorgen\b': 1,
            r'\bübermorgen\b': 2,
            r'\buebermorgen\b': 2
        }
        for pattern, days_offset in relative_patterns.items():
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return (today + timedelta(days=days_offset)).isoformat()

        return None

    def _remove_date_parts(self, text):
        if not text:
            return text
        text = re.sub(r'\b(?:am|zum|für den)\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b', '', text, flags=re.IGNORECASE)
        text = re.sub(
            r'\b(?:am|zum|für den)?\s*\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}\b',
            '',
            text,
            flags=re.IGNORECASE
        )
        return re.sub(r'\s+', ' ', text).strip()

    def _extract_title_fallback(self, original):
        quoted = self._extract_quoted_value(original)
        if quoted:
            return quoted

        original = self._strip_noise_prefix(original)
        patterns = [
            r'für\s+(.+?)(?=\s+(?:eine|einen|ein)(?:\s+\w+)?\s+(?:akte|vorgang|dossier|eintrag|fall|datensatz)\b|$)',
            r'(?:akte|vorgang|dossier|eintrag|fall|datensatz)\s+(?:für|zu|über)?\s*(.+?)(?=\s+(?:mit|und|am|zum|status|kategorie|adresse|farbe|termin)\b|$)',
            r'(?:erstelle|erstell|erstele|lege|leg|anlegen|erzeuge|mach(?:e)?|erfasse|eröffne|eroeffne)\s+(?:bitte\s+)?'
            r'(?:(?:eine|einen|ein)\s+)?(?:akte|vorgang|dossier|eintrag|fall|datensatz)?\s*'
            r'(?:für|zu|über|namens|auf\s+den\s+namen)?\s*(.+?)(?=\s+(?:mit|und|am|zum|status|kategorie|adresse|farbe|termin|anlegen|erstellen|speichern)\b|$)',
            r'(.+?)\s+als\s+(?:akte|vorgang|dossier|eintrag|fall|datensatz)(?=\s+(?:anlegen|erstellen|speichern)\b|$)',
            r'(?:neue?|neuen)\s+(?:akte|vorgang|dossier|eintrag|fall|datensatz)\s+(?:für|zu|über)?\s*(.+?)(?=\s+(?:mit|und|am|zum|status|kategorie|adresse|farbe|termin)\b|$)'
        ]

        for pattern in patterns:
            match = re.search(pattern, original, flags=re.IGNORECASE)
            if match:
                candidate = self._cleanup_candidate(match.group(1))
                if candidate:
                    return candidate
        return None

    def _extract_content_fallback(self, original, title):
        working = original
        if title:
            working = re.sub(re.escape(title), ' ', working, flags=re.IGNORECASE)
        for keyword in self.record_keywords + self.action_keywords['create_record']:
            working = re.sub(rf'\b{re.escape(keyword)}\b', ' ', working, flags=re.IGNORECASE)
        for field_name in self.field_marker_patterns:
            value = self._extract_segment_value(original, _normalize_for_parse(original), field_name)
            if value:
                working = re.sub(re.escape(value), ' ', working, flags=re.IGNORECASE)
        working = self._remove_date_parts(working)
        working = re.sub(
            r'\b(?:mit|dem|den|der|die|das|eine|einen|einem|ein|neu|bitte|anlegen|an|und|für|zum|am)\b',
            ' ',
            working,
            flags=re.IGNORECASE
        )
        working = re.sub(r'\s+', ' ', working).strip(' ,.;:-')
        return _clean_text(working)

    def _extract_create_record(self, original, normalized):
        title = self._extract_segment_value(original, normalized, 'title') or self._extract_title_fallback(original)
        content = self._extract_segment_value(original, normalized, 'content')
        address = self._extract_segment_value(original, normalized, 'address')
        status = self._extract_segment_value(original, normalized, 'status')
        category = self._extract_segment_value(original, normalized, 'category')
        border_color = self._extract_segment_value(original, normalized, 'color')
        city = self._extract_segment_value(original, normalized, 'city')
        reminder_date = self._extract_date(original)

        if not content:
            content = self._extract_content_fallback(original, title)
            if title and content and _normalize_for_search(content) == _normalize_for_search(title):
                content = None

        return {
            'command': 'create_record',
            'data': {
                'title': title,
                'content': content,
                'address': address,
                'status': status,
                'category': category,
                'border_color': border_color,
                'city': city,
                'reminder_date': reminder_date,
                '_original_command': original
            }
        }

    def _extract_record_identifier(self, original, normalized):
        number_match = re.search(r'(?:akte\s*#?|nummer\s*|nr\.?\s*)(\d{1,8})\b', original, flags=re.IGNORECASE)
        if number_match:
            return number_match.group(1)

        original = self._strip_noise_prefix(original)
        name_patterns = [
            r'(?:bei|für|von)\s+(?:der\s+)?(?:akte|vorgang|dossier|eintrag|fall|datensatz)\s+(.+?)(?=\s+(?:und\s+)?(?:setze|ändere|aendere|aktualisiere|ergänze|ergaenze|füge|fuege|notiere|schreib(?:e)?|trage|titel|inhalt|beschreibung|notiz|text|status|kategorie|adresse|farbe|termin|erinnerung|erinnerung)\b|$)',
            r'(?:akte|vorgang|dossier|eintrag|fall|datensatz)\s+(.+?)(?=\s+(?:und\s+)?(?:setze|ändere|aendere|aktualisiere|ergänze|ergaenze|füge|fuege|notiere|schreib(?:e)?|trage|titel|inhalt|beschreibung|notiz|text|status|kategorie|adresse|farbe|termin|erinnerung|erinnerung)\b|$)',
            r'(?:zusammenfassung|zusammenfassen|worum geht es in)\s+(?:von\s+)?(?:der\s+)?(?:akte\s+)?(.+)$'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, original, flags=re.IGNORECASE)
            if match:
                return self._cleanup_candidate(self._remove_date_parts(match.group(1)))

        if 'akte' in normalized:
            match = re.search(r'akte\s+(.+)$', original, flags=re.IGNORECASE)
            if match:
                tail = re.split(r'\b(?:titel|inhalt|beschreibung|notiz|text|status|kategorie|adresse|farbe|termin)\b', match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
                return self._cleanup_candidate(tail)
        return None

    def _extract_update_record(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        updates = {
            'title': self._extract_segment_value(original, normalized, 'title'),
            'content': self._extract_segment_value(original, normalized, 'content'),
            'address': self._extract_segment_value(original, normalized, 'address'),
            'status': self._extract_segment_value(original, normalized, 'status'),
            'category': self._extract_segment_value(original, normalized, 'category'),
            'border_color': self._extract_segment_value(original, normalized, 'color'),
            'city': self._extract_segment_value(original, normalized, 'city'),
            'reminder_date': self._extract_date(original)
        }

        content_mode = 'replace'
        if any(word in normalized for word in ['ergänze', 'ergaenze', 'füge hinzu', 'fuege hinzu']):
            content_mode = 'append'

        return {
            'command': 'update_record',
            'data': {
                'identifier': identifier,
                'updates': updates,
                'content_mode': content_mode,
                '_original_command': original
            }
        }

    def _extract_summarize_record(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        if not identifier:
            match = re.search(
                r'(?:fasse zusammen|zusammenfassung|zusammenfassen|kurzfassung|kurzinhalt|worum geht es in)\s+(.+)$',
                original,
                flags=re.IGNORECASE
            )
            if match:
                identifier = _clean_text(match.group(1))

        return {
            'command': 'summarize_record',
            'data': {
                'identifier': identifier,
                '_original_command': original
            }
        }

    def _extract_search(self, original, normalized):
        patterns = [
            r'(?:suche(?:\s+nach)?|such(?:\s+nach)?|finde|finden|zeige(?:\s+mir)?|öffne|oeffne|hole(?:\s+akte)?)\s+(.+)$'
        ]
        query = None
        for pattern in patterns:
            match = re.search(pattern, original, flags=re.IGNORECASE)
            if match:
                query = _clean_text(match.group(1))
                break
        if query:
            query = re.sub(r'^(?:die|den|das|eine|einen|ein)\s+', '', query, flags=re.IGNORECASE)
            query = re.sub(
                r'^(?:akte|akten|vorgang|dossier|eintrag|fall|datensatz)\s+',
                '',
                query,
                flags=re.IGNORECASE
            )
        return {
            'command': 'search',
            'data': {
                'query': query,
                '_original_command': original
            }
        }

    def _extract_delete_record(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        return {
            'command': 'delete_record',
            'data': {
                'identifier': identifier,
                '_original_command': original
            }
        }

    def _extract_archive_record(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        return {
            'command': 'archive_record',
            'data': {
                'identifier': identifier,
                '_original_command': original
            }
        }

    def _extract_set_status(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        status = None
        
        status_patterns = [
            r'(?:status|markiere\s+als|auf\s+status)\s+(?:auf\s+)?(.+?)(?:\s+(?:für|fuer|bei|in)\s+(?:akte|vorgang)|$)',
            r'(?:auf)\s+(offen|erledigt|bearbeitung|neutral)\b'
        ]
        
        for pattern in status_patterns:
            match = re.search(pattern, original, flags=re.IGNORECASE)
            if match:
                status = _clean_text(match.group(1))
                break
        
        if not status:
            if 'offen' in normalized:
                status = 'offen'
            elif 'erledigt' in normalized:
                status = 'erledigt'
            elif 'bearbeitung' in normalized:
                status = 'bearbeitung'
            elif 'neutral' in normalized:
                status = 'neutral'
        
        return {
            'command': 'set_status',
            'data': {
                'identifier': identifier,
                'status': status,
                '_original_command': original
            }
        }

    def _extract_set_color(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        color = None
        
        color_map = {
            'rot': 'border-red',
            'blau': 'border-blue',
            'gelb': 'border-yellow',
            'grün': 'border-green',
            'gruen': 'border-green',
            'magenta': 'border-magenta',
            'lila': 'border-magenta'
        }
        
        for color_name, color_class in color_map.items():
            if color_name in normalized:
                color = color_class
                break
        
        if not color:
            color_match = re.search(r'(?:farbe|rahmen|markiere\s+mit)\s+(.+?)(?:\s+(?:für|fuer|bei|in)\s+(?:akte|vorgang)|$)', original, flags=re.IGNORECASE)
            if color_match:
                color_candidate = _clean_text(color_match.group(1)).lower()
                color = color_map.get(color_candidate, color_candidate)
        
        return {
            'command': 'set_color',
            'data': {
                'identifier': identifier,
                'color': color,
                '_original_command': original
            }
        }

    def _extract_set_reminder(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        reminder_date = self._extract_date(original)
        
        return {
            'command': 'set_reminder',
            'data': {
                'identifier': identifier,
                'reminder_date': reminder_date,
                '_original_command': original
            }
        }

    def _extract_add_note(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        note = self._extract_segment_value(original, normalized, 'content')
        
        if not note:
            note_match = re.search(r'(?:notiz|notiere|schreib\s+notiz|merke|anmerkung)\s+(.+?)(?:\s+(?:für|fuer|bei|in)\s+(?:akte|vorgang)|$)', original, flags=re.IGNORECASE)
            if note_match:
                note = _clean_text(note_match.group(1))
        
        return {
            'command': 'add_note',
            'data': {
                'identifier': identifier,
                'note': note
            }
        }

    def _extract_set_category(self, original, normalized):
        identifier = self._extract_record_identifier(original, normalized)
        category = self._extract_segment_value(original, normalized, 'category')
        
        if not category:
            category_match = re.search(r'(?:kategorie|ablage|ordner|zuordnen)\s+(?:nach|zu|in)?\s*(.+?)(?:\s+(?:für|fuer|bei|in)\s+(?:akte|vorgang)|$)', original, flags=re.IGNORECASE)
            if category_match:
                category = _clean_text(category_match.group(1))
        
        return {
            'command': 'set_category',
            'data': {
                'identifier': identifier,
                'category': category
            }
        }
