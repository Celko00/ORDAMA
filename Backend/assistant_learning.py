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

Assistant Learning Store für ORDAMA
- Lernbasis für Aktionswörter und Korrekturbeispiele
- Feld-Synonyms und Datumsformate
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _clean_text(value):
    if value is None:
        return None
    value = re.sub(r'\s+', ' ', str(value)).strip(" \t\r\n:;,.!?\"'")
    return value or None


def _normalize_for_search(value):
    if not value:
        return ''
    value = value.lower()
    value = value.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def _normalize_for_parse(value):
    if not value:
        return ''
    return str(value).lower()


class AssistantLearningStore:
    """Einfache lokale Lernbasis für zusätzliche Aktionswörter und Korrekturbeispiele."""

    def __init__(self, storage_path):
        self.storage_path = storage_path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as exc:
                logger.error("Fehler beim Laden der Lern-Daten: %s", exc, exc_info=True)
        return self._get_default_data()

    def _get_default_data(self):
        return {
            'feedback_examples': [],
            'positive_examples': [],
            'action_aliases': {},
            'field_aliases': {},
            'blacklist': [],
            'field_synonyms': self._get_default_field_synonyms(),
            'date_formats': self._get_default_date_formats()
        }

    def _get_default_field_synonyms(self):
        """Default field synonyms mapping - nur Felder die beim Erstellen einer Akte ausgefüllt werden können"""
        return {
            'title': ['titel', 'überschrift', 'betreff', 'namens', 'name', 'genannt', 'auf den namen', 'unter dem titel', 'bezeichnung', 'benannt', 'heißt', 'heisst', 'aktenname', 'akte heißt', 'aktenname ist'],
            'address': ['adresse', 'anschrift', 'straße', 'strasse', 'anschrift ist', 'adresse ist', 'wohnt in', 'wohnt an', 'standort'],
            'content': ['inhalt', 'beschreibung', 'notiz', 'text', 'details', 'notiere', 'schreib', 'trage ein', 'beschreibt', 'enthält', 'enthaelt', 'inhalt ist', 'text ist', 'beschreibung ist', 'mit inhalt', 'mit text', 'mit beschreibung'],
            'reminder_date': ['termin', 'termin start', 'start termin', 'am termin', 'zum termin', 'bis zum', 'termin ist', 'erinnerung', 'erinnerung an', 'erinnere mich', 'fälligkeit', 'faelligkeit'],
            'reminder_end_date': ['termin ende', 'ende termin', 'bis termin', 'bis zum termin', 'endtermin', 'endtermin ist'],
            'reminder_repeat': ['wiederholung', 'wiederhole', 'wiederholen', 'wiederkehrend', 'wiederkehrender termin', 'wiederholung ist'],
            'reminder_assigned_to': ['sichtbarkeit', 'für wen', 'für', 'sichtbar für', 'zuweisen an', 'zugewiesen an', 'erinnerung für'],
            'status': ['status', 'zustand', 'stand', 'status ist', 'zustand ist', 'stand ist', 'aktueller status', 'aktueller zustand'],
            'category': ['kategorie', 'ablage', 'ordner', 'kategorie ist', 'ablage ist', 'ordner ist', 'in ablage', 'in ordner', 'in kategorie'],
            'note': ['vermerk', 'notiz', 'hinweis', 'bemerkung', 'kommentar', 'vermerk ist', 'notiz ist', 'hinweis ist'],
            'border_color': ['rahmenfarbe', 'farbe', 'rahmen', 'farbe ist', 'rahmenfarbe ist', 'rahmen ist', 'markiert mit', 'markiere mit', 'färbe mit', 'faerbe mit'],
            'add_reminder': ['erinnerung hinzufügen', 'erinnerung hinzu', 'termin hinzufügen', 'termin hinzu', 'neue erinnerung', 'neuer termin', 'erinnerung erstellen', 'termin erstellen']
        }

    def _get_default_date_formats(self):
        """Default date format patterns - alle erdenklichen Varianten"""
        return [
            # Standardformate mit 4-stelligem Jahr
            r'\d{1,2}[./-]\d{1,2}[./-]\d{4}',  # 08.08.2026, 08/08/2026, 08-08-2026
            r'\d{4}[./-]\d{1,2}[./-]\d{1,2}',  # 2026.08.08, 2026/08/08, 2026-08-08
            
            # Standardformate mit 2-stelligem Jahr
            r'\d{1,2}[./-]\d{1,2}[./-]\d{2}',  # 08.08.26, 08/08/26, 08-08-26
            r'\d{2}[./-]\d{1,2}[./-]\d{1,2}',  # 26.08.08, 26/08/08, 26-08-08
            
            # Ausgeschriebene Monatsnamen (deutsch) mit 4-stelligem Jahr
            r'\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}',  # 8. August 2026
            r'\d{1,2}\s+(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}',  # 8 August 2026
            r'(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{1,2}\.?\s+\d{4}',  # August 8. 2026
            r'(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{1,2}\s+\d{4}',  # August 8 2026
            
            # Ausgeschriebene Monatsnamen (deutsch) mit 2-stelligem Jahr
            r'\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{2}',  # 8. August 26
            r'\d{1,2}\s+(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{2}',  # 8 August 26
            r'(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{1,2}\.?\s+\d{2}',  # August 8. 26
            r'(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{1,2}\s+\d{2}',  # August 8 26
            
            # Abgekürzte Monatsnamen (deutsch) mit 4-stelligem Jahr
            r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{4}',  # 8. Aug 2026
            r'\d{1,2}\s+(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{4}',  # 8 Aug 2026
            r'(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{1,2}\.?\s+\d{4}',  # Aug 8. 2026
            r'(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{1,2}\s+\d{4}',  # Aug 8 2026
            
            # Abgekürzte Monatsnamen (deutsch) mit 2-stelligem Jahr
            r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{2}',  # 8. Aug 26
            r'\d{1,2}\s+(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{2}',  # 8 Aug 26
            r'(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{1,2}\.?\s+\d{2}',  # Aug 8. 26
            r'(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{1,2}\s+\d{2}',  # Aug 8 26
            
            # Englische Monatsnamen mit 4-stelligem Jahr
            r'\d{1,2}\.?\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',  # 8. August 2026
            r'\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',  # 8 August 2026
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\.?\s+\d{4}',  # August 8. 2026
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\s+\d{4}',  # August 8 2026
            
            # Englische Monatsnamen mit 2-stelligem Jahr
            r'\d{1,2}\.?\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{2}',  # 8. August 26
            r'\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{2}',  # 8 August 26
            
            # Abgekürzte englische Monatsnamen mit 4-stelligem Jahr
            r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}',  # 8. Aug 2026
            r'\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}',  # 8 Aug 2026
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\.?\s+\d{4}',  # Aug 8. 2026
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+\d{4}',  # Aug 8 2026
            
            # Abgekürzte englische Monatsnamen mit 2-stelligem Jahr
            r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2}',  # 8. Aug 26
            r'\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2}',  # 8 Aug 26
            
            # Nur Jahr (4-stellig)
            r'\d{4}',  # 2026
            
            # Nur Jahr (2-stellig)
            r'\d{2}',  # 26
            
            # Monat Jahr (deutsch)
            r'(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{4}',  # August 2026
            r'(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{4}',  # Aug 2026
            r'(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{2}',  # August 26
            r'(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\s+\d{2}',  # Aug 26
            
            # Monat Jahr (englisch)
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',  # August 2026
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}',  # Aug 2026
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{2}',  # August 26
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2}',  # Aug 26
            
            # Tag Monat (ohne Jahr)
            r'\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)',  # 8. August
            r'\d{1,2}\s+(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)',  # 8 August
            r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)',  # 8. Aug
            r'\d{1,2}\s+(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)',  # 8 Aug
            r'\d{1,2}\.?\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)',  # 8. August
            r'\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)',  # 8 August
            r'\d{1,2}\.?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # 8. Aug
            r'\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # 8 Aug
            
            # ISO Format
            r'\d{4}-\d{2}-\d{2}',  # 2026-08-08
            r'\d{4}-\d{1,2}-\d{1,2}',  # 2026-8-8
            
            # Mit Präpositionen
            r'am\s+\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\.?\s+\d{4}',  # am 8. August 2026
            r'am\s+\d{1,2}\.?\s*(?:jan|feb|mar|apr|mai|jun|jul|aug|sep|okt|nov|dez)\.?\s+\d{4}',  # am 8. Aug 2026
            r'am\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}',  # am 08.08.2026
            r'am\s+\d{1,2}[./-]\d{1,2}[./-]\d{2}',  # am 08.08.26
            r'bis\s+\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\.?\s+\d{4}',  # bis 8. August 2026
            r'bis\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}',  # bis 08.08.2026
            r'zum\s+\d{1,2}\.?\s*(?:januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\.?\s+\d{4}',  # zum 8. August 2026
            r'zum\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}',  # zum 08.08.2026
        ]

    def save(self):
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Fehler beim Speichern der Lern-Daten: %s", exc, exc_info=True)

    def get_action_aliases(self, command_name):
        return list(self.data.get('action_aliases', {}).get(command_name, []))

    def find_feedback_match(self, command_text):
        normalized_command = _normalize_for_search(command_text)
        if not normalized_command:
            return None

        examples = list(self.data.get('feedback_examples', []))
        for entry in reversed(examples):
            if entry.get('normalized_command') != normalized_command:
                continue

            expected_command = entry.get('expected_command')
            corrected_data = entry.get('corrected_data') or {}
            if expected_command in {'create_record', 'update_record', 'summarize_record', 'search'}:
                return {
                    'command': expected_command,
                    'data': corrected_data
                }
        return None

    def _extract_alias_candidates(self, normalized_command):
        tokens = [
            token for token in re.findall(r'[a-zäöüß]+', normalized_command)
            if len(token) >= 4
        ]
        if not tokens:
            return []

        stop_tokens = {
            'akte', 'akten', 'vorgang', 'dossier', 'eintrag', 'fall', 'datensatz',
            'datei', 'dokument', 'bitte', 'doch', 'mal', 'heute'
        }
        filtered = [token for token in tokens if token not in stop_tokens]
        candidates = []
        if filtered:
            candidates.append(filtered[0])
        if len(filtered) >= 2:
            candidates.append(f'{filtered[0]} {filtered[1]}')
        return candidates

    def record_feedback(self, command_text, expected_command=None, corrected_data=None, is_correct=True):
        if not command_text:
            return

        normalized_command = _normalize_for_search(command_text)
        if not normalized_command:
            return

        examples = list(self.data.get('feedback_examples', []))
        
        if is_correct:
            examples.append({
                'normalized_command': normalized_command,
                'expected_command': expected_command,
                'corrected_data': corrected_data,
                'is_correct': True,
                'timestamp': datetime.now().isoformat(timespec='seconds')
            })
            # Learn from positive feedback
            self._learn_from_positive_feedback(normalized_command, expected_command)
            # Remove from blacklist if it was there
            self._remove_from_blacklist(normalized_command)
        else:
            examples.append({
                'normalized_command': normalized_command,
                'is_correct': False,
                'timestamp': datetime.now().isoformat(timespec='seconds')
            })
            # Learn synonyms from negative feedback
            self._learn_from_negative_feedback(normalized_command)
            # Add to blacklist to skip this command in future
            self._add_to_blacklist(normalized_command)

        if len(examples) > 100:
            examples = examples[-100:]

        self.data['feedback_examples'] = examples
        self.save()

    def _learn_from_negative_feedback(self, normalized_command):
        """Extract and learn synonyms from failed commands"""
        tokens = [
            token for token in re.findall(r'[a-zäöüß]+', normalized_command)
            if len(token) >= 3
        ]
        
        if not tokens:
            return
        
        action_aliases = self.data.get('action_aliases', {})
        
        for token in tokens:
            if token in {'akte', 'akten', 'vorgang', 'dossier', 'eintrag', 'fall', 'datensatz', 'datei', 'dokument', 'sache'}:
                continue
            
            for command_type in ['create_record', 'update_record', 'search']:
                if token not in action_aliases.get(command_type, []):
                    action_aliases.setdefault(command_type, []).append(token)
        
        self.data['action_aliases'] = action_aliases
        self.save()

    def _add_to_blacklist(self, normalized_command):
        """Add a command to the blacklist to skip it in future"""
        blacklist = list(self.data.get('blacklist', []))
        if normalized_command not in blacklist:
            blacklist.append(normalized_command)
            if len(blacklist) > 500:
                blacklist = blacklist[-500:]
            self.data['blacklist'] = blacklist
            self.save()

    def _remove_from_blacklist(self, normalized_command):
        """Remove a command from the blacklist"""
        blacklist = list(self.data.get('blacklist', []))
        if normalized_command in blacklist:
            blacklist.remove(normalized_command)
            self.data['blacklist'] = blacklist
            self.save()

    def is_blacklisted(self, normalized_command):
        """Check if a command is blacklisted"""
        blacklist = self.data.get('blacklist', [])
        return normalized_command in blacklist

    def get_field_synonyms(self):
        """Get all field synonyms"""
        return self.data.get('field_synonyms', self._get_default_field_synonyms())

    def add_field_synonym(self, field_name, synonym):
        """Add a synonym for a field"""
        field_synonyms = self.data.get('field_synonyms', self._get_default_field_synonyms())
        if field_name not in field_synonyms:
            field_synonyms[field_name] = []
        if synonym not in field_synonyms[field_name]:
            field_synonyms[field_name].append(synonym)
            self.data['field_synonyms'] = field_synonyms
            self.save()

    def remove_field_synonym(self, field_name, synonym):
        """Remove a synonym for a field"""
        field_synonyms = self.data.get('field_synonyms', self._get_default_field_synonyms())
        if field_name in field_synonyms and synonym in field_synonyms[field_name]:
            field_synonyms[field_name].remove(synonym)
            self.data['field_synonyms'] = field_synonyms
            self.save()

    def get_date_formats(self):
        """Get all date format patterns"""
        return self.data.get('date_formats', self._get_default_date_formats())

    def add_date_format(self, pattern):
        """Add a date format pattern"""
        date_formats = self.data.get('date_formats', self._get_default_date_formats())
        if pattern not in date_formats:
            date_formats.append(pattern)
            self.data['date_formats'] = date_formats
            self.save()

    def remove_date_format(self, pattern):
        """Remove a date format pattern"""
        date_formats = self.data.get('date_formats', self._get_default_date_formats())
        if pattern in date_formats:
            date_formats.remove(pattern)
            self.data['date_formats'] = date_formats
            self.save()

    def _learn_from_positive_feedback(self, normalized_command, expected_command):
        """Reinforce successful command patterns"""
        if not expected_command:
            return
        
        tokens = [
            token for token in re.findall(r'[a-zäöüß]+', normalized_command)
            if len(token) >= 3
        ]
        
        if not tokens:
            return
        
        action_aliases = self.data.get('action_aliases', {})
        
        for token in tokens:
            if token in {'akte', 'akten', 'vorgang', 'dossier', 'eintrag', 'fall', 'datensatz', 'datei', 'dokument', 'sache'}:
                continue
            
            if token not in action_aliases.get(expected_command, []):
                action_aliases.setdefault(expected_command, []).append(token)
        
        self.data['action_aliases'] = action_aliases
        self.save()

    def record_success(self, command_text, command_type, data=None):
        """Record successful command for learning"""
        if not command_text or not command_type:
            return

        normalized_command = _normalize_for_search(command_text)
        if not normalized_command:
            return

        positive_examples = list(self.data.get('positive_examples', []))
        
        for example in positive_examples:
            if example.get('normalized_command') == normalized_command:
                return
        
        positive_examples.append({
            'normalized_command': normalized_command,
            'command_type': command_type,
            'data': data or {},
            'timestamp': datetime.now().isoformat(timespec='seconds')
        })

        if len(positive_examples) > 200:
            positive_examples = positive_examples[-200:]

        self.data['positive_examples'] = positive_examples
        self.save()

        self._learn_aliases_from_success(normalized_command, command_type)

    def _learn_aliases_from_success(self, normalized_command, command_type):
        """Extract action aliases from successful commands"""
        tokens = [
            token for token in re.findall(r'[a-zäöüß]+', normalized_command)
            if len(token) >= 3
        ]
        
        if not tokens:
            return
        
        action_aliases = self.data.get('action_aliases', {})
        
        for token in tokens:
            if token in {'akte', 'akten', 'vorgang', 'dossier', 'eintrag', 'fall', 'datensatz', 'datei', 'dokument', 'sache'}:
                continue
            
            if token not in action_aliases.get(command_type, []):
                action_aliases.setdefault(command_type, []).append(token)
        
        self.data['action_aliases'] = action_aliases
        self.save()
