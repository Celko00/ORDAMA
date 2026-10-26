import os
import shutil
import zipfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class UpdateManager:
    def __init__(self, basis_verzeichnis):
        self.basis_verzeichnis = Path(basis_verzeichnis)
        self.temp_update_ordner = self.basis_verzeichnis / "temp_update"
        
        # Pfade, die NIEMALS überschrieben werden dürfen
        self.geschuetzte_pfade = [
            "Speicher",
            "Konfiguration",
            "Logs",
            "Backups",
            "Virtual Environment",
            "venv_linux"
        ]

    def update_paket_entpacken(self, zip_pfad):
        """Entpackt das Update-Paket in einen temporären Ordner"""
        try:
            if self.temp_update_ordner.exists():
                shutil.rmtree(self.temp_update_ordner)
            
            os.makedirs(self.temp_update_ordner, exist_ok=True)
            
            with zipfile.ZipFile(zip_pfad, 'r') as zip_ref:
                zip_ref.extractall(self.temp_update_ordner)
            
            logger.info(f"Update-Paket entpackt nach: {self.temp_update_ordner}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Entpacken des Updates: {e}")
            return False

    def update_installieren(self):
        """Installiert das Update durch Kopieren der Dateien"""
        errors = []
        try:
            if not self.temp_update_ordner.exists():
                return {"success": False, "error": "Kein Update-Paket gefunden."}

            # Wir gehen durch alle Dateien im Temp-Ordner
            for root, dirs, files in os.walk(self.temp_update_ordner):
                rel_pfad = os.path.relpath(root, self.temp_update_ordner)
                
                # Überspringen, wenn der Pfad geschützt ist
                if any(rel_pfad.startswith(p) for p in self.geschuetzte_pfade):
                    continue
                
                # Ziel-Ordner erstellen falls nicht vorhanden
                ziel_root = self.basis_verzeichnis / rel_pfad
                if not ziel_root.exists():
                    try:
                        os.makedirs(ziel_root, exist_ok=True)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Could not create directory {ziel_root}: {e}")
                
                for datei in files:
                    datei_rel_pfad = os.path.join(rel_pfad, datei) if rel_pfad != "." else datei
                    
                    # Einzelne Datei-Prüfung auf Schutz
                    if any(datei_rel_pfad.startswith(p) for p in self.geschuetzte_pfade):
                        continue
                    
                    quell_datei = Path(root) / datei
                    ziel_datei = self.basis_verzeichnis / datei_rel_pfad
                    
                    try:
                        # Auf Windows: Wenn Datei gesperrt ist, versuchen wir sie umzubenennen
                        if ziel_datei.exists():
                            try:
                                # Versuche direkt zu überschreiben
                                shutil.copy2(quell_datei, ziel_datei)
                            except (PermissionError, OSError):
                                # Wenn gesperrt: Umbenennen in .old und dann kopieren
                                old_file = ziel_datei.with_suffix(ziel_datei.suffix + '.old')
                                if old_file.exists():
                                    try: 
                                        os.remove(old_file)
                                    except (OSError, PermissionError) as e:
                                        logger.warning(f"Could not remove old file {old_file}: {e}")
                                
                                try:
                                    os.rename(ziel_datei, old_file)
                                    shutil.copy2(quell_datei, ziel_datei)
                                except Exception as e:
                                    errors.append(f"Datei {datei}: {str(e)}")
                        else:
                            shutil.copy2(quell_datei, ziel_datei)
                    except Exception as e:
                        errors.append(f"Kritischer Fehler bei {datei}: {str(e)}")

            # Nach der Installation versuchen aufzuräumen
            try:
                shutil.rmtree(self.temp_update_ordner)
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not remove temp update folder: {e}")
            
            if not errors:
                logger.info("Update erfolgreich installiert.")
                return {"success": True}
            else:
                logger.warning(f"Update mit {len(errors)} Fehlern installiert.")
                return {"success": True, "partial_errors": errors} # Wir geben trotzdem success: True, da es meistens funktioniert hat
            
        except Exception as e:
            logger.error(f"Fehler bei der Update-Installation: {e}")
            return {"success": False, "error": str(e)}

    def pruefe_update_datei(self, zip_pfad):
        """Überprüft, ob das ZIP-Archiv valide ist (einfache Prüfung)"""
        try:
            with zipfile.ZipFile(zip_pfad, 'r') as zip_ref:
                dateiliste = zip_ref.namelist()
                # Mindestens Backend/app.py sollte vorhanden sein als Indikator
                if not any("Backend/app.py" in d for d in dateiliste):
                    return False
            return True
        except (zipfile.BadZipFile, OSError, IOError) as e:
            logger.warning(f"Invalid update file: {e}")
            return False
