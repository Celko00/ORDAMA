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

Kartenlogik für ORDAMA (Server-Version)

Ziel:
- Akteninhalt nach PLZ/Ort durchsuchen
- Koordinaten offline über lokale PLZ-Daten (Konfiguration/karte/ort.json) bestimmen
- Referenzorte (Konfiguration/karte/ref.json) für die Darstellung liefern

Wichtig:
- Keine Abhängigkeit zur Enterprise-Variante (nur Konzept übernommen, Implementierung neu)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


_RE_TAGS = re.compile(r"<[^>]+>")
_RE_PLZ = re.compile(r"\b(\d{5})\b")
# Typische deutsche Schreibweisen:
# - "95448 Bayreuth" (Standard)
# - "Bayreuth 95448" (Alternativ)
# - "D-95448 Bayreuth"
_RE_ORT_NACH_PLZ = re.compile(
    r"\b(?:D\s*-\s*)?(\d{5})\b\s+([A-Za-zÄÖÜäöüß\-\. ]{2,80})",
    re.UNICODE,
)
_RE_ORT_VOR_PLZ = re.compile(
    r"\b([A-Za-zÄÖÜäöüß\-\. ]{2,80})\b\s+(\d{5})\b",
    re.UNICODE,
)


def _html_zu_text(html: str) -> str:
    if not html:
        return ""
    # HTML grob strippen (für unsere Address-Regex reicht das; sehr schnell)
    txt = unescape(html)
    txt = txt.replace("&nbsp;", " ")
    txt = _RE_TAGS.sub(" ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _normalisiere_ortname(ort: str) -> str:
    ort = (ort or "").strip()
    ort = re.sub(r"\s+", " ", ort)
    # Häufige Zusätze entfernen, die die PLZ/Ort-Erkennung stören können
    ort = ort.replace(",", " ").replace(";", " ")
    ort = re.sub(r"\s+", " ", ort).strip()
    return ort


@dataclass(frozen=True)
class KartenPunkt:
    record_id: int
    nummer: str
    titel: str
    plz: str
    ort: str
    lat: float
    lon: float
    hashtags: str


class KartenDienst:
    """
    Lädt PLZ- und Referenzdaten einmal und bietet schnelle Lookup-Funktionen.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.konfig_dir = self.base_dir / "Konfiguration" / "karte"
        self.ort_pfad = self.konfig_dir / "ort.json"
        self.ref_pfad = self.konfig_dir / "ref.json"

        self._plz_daten: List[Dict[str, Any]] = []
        self._ref_orte: Dict[str, Dict[str, float]] = {}
        self._plz_index: Dict[str, List[Dict[str, Any]]] = {}
        
        self._ref_zeitstempel: float = 0

        self._lade_daten()

    def _lade_daten(self, nur_ref: bool = False) -> None:
        try:
            if not nur_ref:
                if self.ort_pfad.exists():
                    self._plz_daten = json.loads(self.ort_pfad.read_text(encoding="utf-8"))
                else:
                    logger.warning("PLZ-Datei fehlt: %s", self.ort_pfad)
                    self._plz_daten = []

                idx: Dict[str, List[Dict[str, Any]]] = {}
                for e in self._plz_daten:
                    p = str(e.get("plz", "")).strip()
                    if not p:
                        continue
                    idx.setdefault(p, []).append(e)
                self._plz_index = idx

            if self.ref_pfad.exists():
                self._ref_zeitstempel = self.ref_pfad.stat().st_mtime
                self._ref_orte = json.loads(self.ref_pfad.read_text(encoding="utf-8"))
            else:
                logger.warning("Referenzorte fehlen: %s", self.ref_pfad)
                self._ref_orte = {}
                self._ref_zeitstempel = 0

        except Exception as e:
            logger.error("Fehler beim Laden der Kartendaten: %s", e)
            if not nur_ref:
                self._plz_daten = []
                self._plz_index = {}
            self._ref_orte = {}
            self._ref_zeitstempel = 0

    def hole_referenzorte(self) -> Dict[str, Dict[str, float]]:
        # Prüfen ob ref.json sich geändert hat (für dynamisches Nachladen ohne Neustart)
        try:
            if self.ref_pfad.exists():
                mtime = self.ref_pfad.stat().st_mtime
                if mtime > self._ref_zeitstempel:
                    logger.info("ref.json hat sich geändert, lade neu...")
                    self._lade_daten(nur_ref=True)
        except Exception as e:
            logger.error("Fehler beim Prüfen/Nachladen von ref.json: %s", e)
            
        return self._ref_orte or {}

    def extrahiere_plz_ort(self, inhalt: str) -> Optional[Tuple[str, str]]:
        """
        Extrahiert (PLZ, Ort) aus Inhalt.
        Heuristik: erste gefundene PLZ + direkt folgender Ortsname (wenn möglich).
        """
        txt = _html_zu_text(inhalt)
        if not txt:
            return None

        # 1. Format: 12345 Ort
        m = _RE_ORT_NACH_PLZ.search(txt)
        if m:
            plz = m.group(1)
            ort_roh = m.group(2)
            ort = self._bereinige_ort(ort_roh)
            if ort:
                return plz, ort

        # 2. Format: Ort 12345
        m2 = _RE_ORT_VOR_PLZ.search(txt)
        if m2:
            ort_roh = m2.group(1)
            plz = m2.group(2)
            ort = self._bereinige_ort(ort_roh)
            if ort:
                return plz, ort

        # Fallback: nur PLZ
        m3 = _RE_PLZ.search(txt)
        if m3:
            return m3.group(1), ""

        return None

    def _bereinige_ort(self, ort_roh: str) -> str:
        # Ort bis zum nächsten Trennzeichen abschneiden (z.B. ", Deutschland")
        ort = re.split(r"[,;/]", ort_roh, 1)[0]
        # ... und zusätzlich bis zur nächsten Zahl (falls doch noch Hausnr./Zusatz kommt)
        ort = re.split(r"\b\d", ort, 1)[0]
        return _normalisiere_ortname(ort)

    def finde_koordinaten(self, plz: str, ort: str = "") -> Optional[Tuple[float, float]]:
        """
        Bestimmt Koordinaten aus PLZ (und optional Ortname als besseres Matching).
        """
        plz = (plz or "").strip()
        if not plz:
            return None

        kandidaten = self._plz_index.get(plz)
        if not kandidaten:
            return None

        ort_norm = " ".join(_normalisiere_ortname(ort).lower().split()[:2])
        if ort_norm:
            for e in kandidaten:
                name = str(e.get("name", ""))
                name_norm = " ".join(name.lower().split()[:2])
                if name_norm == ort_norm:
                    return float(e["latitude"]), float(e["longitude"])

        # Fallback: erster Treffer zur PLZ
        e0 = kandidaten[0]
        return float(e0["latitude"]), float(e0["longitude"])
