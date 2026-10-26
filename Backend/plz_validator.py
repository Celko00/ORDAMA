"""
Postleitzahl-Validator für ORDAMA

Prüft ob eine Postleitzahl im System vorhanden ist (basierend auf Konfiguration/karte/ort.json)
und gibt eine Warnung zurück wenn die PLZ nicht gefunden wurde.
"""

import re
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class PLZValidator:
    """Validiert Postleitzahlen gegen das System-PLZ-Verzeichnis"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.konfig_dir = self.base_dir / "Konfiguration" / "karte"
        self.ort_pfad = self.konfig_dir / "ort.json"
        
        self._plz_set = set()
        self._geladen = False
        
        self._lade_plz_daten()
    
    def _lade_plz_daten(self):
        """Lädt alle gültigen PLZ aus der ort.json Datei"""
        try:
            logger.info(f"PLZ-Validator: Suche nach ort.json unter: {self.ort_pfad}")
            logger.info(f"PLZ-Validator: base_dir = {self.base_dir}")
            logger.info(f"PLZ-Validator: Datei existiert: {self.ort_pfad.exists()}")
            
            if self.ort_pfad.exists():
                import json
                with open(self.ort_pfad, 'r', encoding='utf-8') as f:
                    daten = json.load(f)
                
                # Alle PLZ in ein Set für schnellen Lookup
                self._plz_set = {str(entry.get("plz", "")).strip() for entry in daten if entry.get("plz")}
                self._geladen = True
                logger.info(f"PLZ-Validator geladen: {len(self._plz_set)} gültige Postleitzahlen")
                logger.info(f"PLZ-Validator: Beispiel-PLZ: {list(self._plz_set)[:5]}")
            else:
                logger.warning(f"PLZ-Datei nicht gefunden: {self.ort_pfad}")
                self._geladen = False
        except Exception as e:
            logger.error(f"Fehler beim Laden der PLZ-Daten: {e}")
            self._geladen = False
    
    def extrahiere_plz(self, text: Optional[str]) -> Optional[str]:
        """
        Extrahiert die erste 5-stellige Postleitzahl aus einem Text
        """
        if not text:
            return None
        
        # Regex für 5-stellige deutsche PLZ
        match = re.search(r'\b(\d{5})\b', text)
        if match:
            return match.group(1)
        return None
    
    def pruefe_plz_format(self, text: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Prüft ob eine PLZ das korrekte Format hat (5-stellig)
        
        Args:
            text: Der zu prüfende Text (kann PLZ enthalten)
            
        Returns:
            Tuple (ist_gueltig, fehlermeldung)
            - ist_gueltig: True wenn Format korrekt oder keine PLZ
            - fehlermeldung: None wenn gültig, sonst Warnmeldung
        """
        if not text:
            return True, None
        
        # Prüfen ob eine 5-stellige PLZ vorhanden ist
        plz = self.extrahiere_plz(text)
        
        if plz:
            # PLZ gefunden - Format ist korrekt
            return True, None
        
        # Prüfen ob eine PLZ mit falschem Format vorhanden ist (z.B. 6-stellig)
        # Regex für Zahlenfolgen die wie PLZ aussehen aber nicht 5-stellig sind
        invalid_plz_match = re.search(r'\b(\d{1,4}|\d{6,})\b', text)
        if invalid_plz_match:
            invalid_plz = invalid_plz_match.group(1)
            warnung = f"Die Postleitzahl '{invalid_plz}' scheint ungültig zu sein. Eine deutsche Postleitzahl besteht aus genau 5 Ziffern. Möchten Sie trotzdem fortfahren?"
            return False, warnung
        
        # Keine PLZ gefunden - ist erlaubt
        return True, None
    
    def pruefe_plz(self, plz: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Prüft ob eine Postleitzahl im System vorhanden ist
        
        Args:
            plz: Die zu prüfende Postleitzahl (5-stellig)
            
        Returns:
            Tuple (ist_gueltig, fehlermeldung)
            - ist_gueltig: True wenn PLZ vorhanden oder Validator nicht geladen
            - fehlermeldung: None wenn gültig, sonst Warnmeldung
        """
        if not plz:
            # Keine PLZ angegeben - ist erlaubt, keine Warnung
            return True, None
        
        plz = str(plz).strip()
        
        # Wenn PLZ-Daten nicht geladen werden konnten, Warnung ausgeben aber nicht blockieren
        if not self._geladen:
            logger.warning(f"PLZ-Validator nicht geladen - kann PLZ {plz} nicht validieren")
            return True, None
        
        # Prüfen ob PLZ im System vorhanden ist
        if plz in self._plz_set:
            return True, None
        
        # PLZ nicht gefunden - Warnmeldung zurückgeben
        warnung = f"Die Postleitzahl '{plz}' ist nicht im System hinterlegt. Möchten Sie trotzdem fortfahren?"
        return False, warnung
    
    def pruefe_adresse(self, adresse: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Prüft eine komplette Adresse auf eine gültige Postleitzahl
        
        Args:
            adresse: Die zu prüfende Adresse (kann PLZ enthalten)
            
        Returns:
            Tuple (ist_gueltig, fehlermeldung)
        """
        if not adresse:
            # Keine Adresse angegeben - Warnung
            warnung = "Es wurde keine Adresse eingegeben. Möchten Sie trotzdem fortfahren?"
            return False, warnung
        
        # Zuerst das Format prüfen
        format_valid, format_warning = self.pruefe_plz_format(adresse)
        if not format_valid:
            return False, format_warning
        
        # PLZ aus Adresse extrahieren
        plz = self.extrahiere_plz(adresse)
        
        if not plz:
            # Keine PLZ in Adresse gefunden - Warnung
            warnung = "Es konnte keine Postleitzahl in der Adresse erkannt werden. Eine deutsche Postleitzahl besteht aus 5 Ziffern. Möchten Sie trotzdem fortfahren?"
            return False, warnung
        
        # Gefundene PLZ prüfen
        return self.pruefe_plz(plz)
    
    def neu_laden(self):
        """Lädt die PLZ-Daten neu (z.B. nach Aktualisierung der ort.json)"""
        self._lade_plz_daten()
