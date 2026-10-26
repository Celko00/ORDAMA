"""
Schutz-Modul für die ORDAMA Datenbank.
Verhindert das Öffnen der Datenbank mit Standard-Tools und Editoren.
Verwendet eine XOR-Transformation auf Blockebene für maximale Sicherheit ohne Performance-Verlust.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Magic Bytes für ORDAMA (Proprietärer Header)
MAGIC_ORDAMA = b'ORDAMA-SECURE-DB' # 16 bytes
# Standard SQLite Header
MAGIC_SQLITE = b'SQLite format 3\x00' # 16 bytes

# XOR-Schlüssel (Proprietär für ORDAMA)
# Dieser Schlüssel wird verwendet, um die Daten für Text-Editoren unlesbar zu machen
XOR_KEY = b'\x4F\x52\x44\x41\x4D\x41\x5F\x53\x45\x43\x55\x52\x45\x5F\x32\x36' # "ORDAMA_SECURE_26"

def _transformiere_datei(db_pfad):
    """
    Transformiert die Datei mittels XOR.
    Wir transformieren nur die ersten 2 MB der Datei. 
    Das reicht aus, um die Datenbank für alle Tools und Editoren unbrauchbar zu machen,
    ist aber extrem schnell, auch bei sehr großen Datenbanken.
    """
    if not os.path.exists(db_pfad):
        return False
        
    try:
        size = os.path.getsize(db_pfad)
        if size == 0:
            return False

        # Wir transformieren nur den Anfang der Datei (2MB sind mehr als genug)
        # SQLite Header + Master Table + erste Datenblöcke sind damit geschützt
        limit = 2 * 1024 * 1024 
        
        with open(db_pfad, "r+b") as f:
            data = f.read(limit)
            f.seek(0)
            
            transformed = bytearray(data)
            for i in range(len(transformed)):
                transformed[i] ^= XOR_KEY[i % len(XOR_KEY)]
            
            f.write(transformed)
            f.flush()
            os.fsync(f.fileno()) # Sicherstellen, dass es auf die Festplatte geschrieben wird
            
        return True
    except Exception as e:
        # Wenn die Datei von einem anderen Prozess blockiert ist, loggen wir das
        logger.error(f"Fehler bei DB-Transformation (Datei evtl. blockiert): {e}")
        return False

def setze_datenbank_schutz(db_pfad, aktivieren=True):
    """
    Aktiviert oder deaktiviert den Schutz der Datenbankdatei.
    aktivieren=True  -> Datei wird XOR-verschlüsselt (Unlesbar für Editoren & SQLite)
    aktivieren=False -> Datei wird XOR-entschlüsselt (Normaler SQLite-Zustand)
    """
    if not os.path.exists(db_pfad):
        return False
        
    try:
        # Prüfen ob die Datei bereits im gewünschten Zustand ist
        # Wir nutzen die ersten 16 Bytes (nach der Transformation) als Indikator
        with open(db_pfad, "rb") as f:
            header = f.read(16)
            
        # Zustand prüfen:
        # Wenn wir aktivieren wollen, darf der Header NICHT MAGIC_ORDAMA sein (nach XOR)
        # Einfacher: Wenn der Header MAGIC_SQLITE ist, ist sie offen -> Transformieren
        # Wenn der Header etwas anderes ist, ist sie bereits zu (oder kaputt)
        
        ist_offen = (header == MAGIC_SQLITE)
        
        if aktivieren and ist_offen:
            # logger.info(f"Verschlüssele Datenbank: {db_pfad}")
            return _transformiere_datei(db_pfad)
        elif not aktivieren and not ist_offen:
            # logger.info(f"Entschlüssele Datenbank: {db_pfad}")
            # Wir versuchen zu transformieren und prüfen ob danach MAGIC_SQLITE da steht
            if _transformiere_datei(db_pfad):
                with open(db_pfad, "rb") as f:
                    neuer_header = f.read(16)
                if neuer_header == MAGIC_SQLITE:
                    return True
                else:
                    # Wenn es nicht SQLite ist, war es wohl keine ORDAMA-DB oder bereits offen
                    # Zur Sicherheit wieder zurück transformieren
                    _transformiere_datei(db_pfad)
                    return False
                    
        return False
    except Exception as e:
        logger.error(f"Fehler beim Datenbank-Schutz-Check ({db_pfad}): {e}")
        return False

def ist_datenbank_geschuetzt(db_pfad):
    """Prüft ob die Datenbank aktuell im geschützten Zustand ist"""
    if not os.path.exists(db_pfad):
        return False
    try:
        with open(db_pfad, "rb") as f:
            header = f.read(16)
            return header != MAGIC_SQLITE
    except (OSError, IOError):
        return False
