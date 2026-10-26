"""
Backup-Modul für ORDAMA (Versionsbasiert)
- Speichert Dateien nur einmal in einem Archiv
- Jeder Backup ist eine "Momentaufnahme" (Snapshot)
- Gelöschte Dateien bleiben im Archiv
- Funktioniert auf Windows UND Linux
"""

import os
import shutil
import logging
import json
import hashlib
import zipfile
import gzip
from datetime import datetime
from pathlib import Path

from system.mod.db_schutz import setze_datenbank_schutz

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, base_dir, config, security_logger=None):
        self.base_dir = Path(base_dir)
        self.config = config
        self.security_logger = security_logger
        
        # Basis-Pfade
        self.data_base_dir = self.get_resolved_path(self.config['paths'].get('data_base_dir', './Speicher'))
        self.data_dir = self.data_base_dir / "Datenbank"
        self.akten_dir = self.data_base_dir / "Akten"
        self.backup_base = self.get_resolved_path(self.config['paths'].get('backup_dir', './Backups'))
        
        # Ordnerstruktur für das alte System (deaktiviert - Image-Backup wird verwendet)
        self.archive_dir = self.backup_base / "archive"  # Hier werden alle Dateien gespeichert
        self.snapshots_dir = self.backup_base / "snapshots"  # Hier sind die Momentaufnahmen gespeichert
        self.db_backups_dir = self.backup_base / "db_backups"  # Hier sind die DB-Snapshots
        
        # Nur Haupt-Backup-Ordner erstellen, alte Unterordner nicht mehr (Image-Backup wird verwendet)
        if not self.backup_base.exists():
            self.backup_base.mkdir(parents=True, exist_ok=True)
            logger.info(f"Backup-Verzeichnis erstellt: {self.backup_base}")

    def get_resolved_path(self, path_str):
        """Löst einen Pfad auf (relativ zum base_dir oder absolut)"""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return self.base_dir / p
    
    def _get_file_hash(self, file_path):
        """Berechnet einen SHA-256 Hash für eine Datei, um sie zu identifizieren"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Datei in kleinen Chunks lesen, um Speicher zu schonen
            for chunk in iter(lambda: f.read(65536), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _archive_file(self, file_path):
        """Archiviert eine Datei (komprimiert als .gz, falls nicht schon vorhanden)"""
        if not file_path.exists():
            return None
            
        file_hash = self._get_file_hash(file_path)
        # Erstelle Unterordner, um zu viele Dateien in einem Ordner zu vermeiden
        # (Erster 2 Zeichen des Hashes als Unterordner)
        archive_subdir = self.archive_dir / file_hash[:2]
        archive_file = archive_subdir / f"{file_hash}.gz"
        
        if not archive_subdir.exists():
            archive_subdir.mkdir(parents=True, exist_ok=True)
        
        if not archive_file.exists():
            # Komprimiere Datei und speichere im Archiv
            with open(file_path, 'rb') as f_in:
                with gzip.open(archive_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.info(f"Datei archiviert (komprimiert): {file_path.name} (Hash: {file_hash[:8]})")
            
        return file_hash
    
    def _compress_db_file(self, file_path):
        """Komprimiert eine DB-Datei als .gz"""
        gz_path = Path(f"{file_path}.gz")
        if not gz_path.exists():
            with open(file_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Entferne die unkomprimierte Datei
            file_path.unlink()
        return gz_path
    
    def _decompress_db_file(self, gz_path):
        """Dekomprimiert eine .gz DB-Datei"""
        original_path = Path(str(gz_path)[:-3])  # Entferne .gz
        if not original_path.exists() and gz_path.exists():
            with gzip.open(gz_path, 'rb') as f_in:
                with open(original_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        return original_path
    
    def _check_disk_space(self, required_bytes):
        """
        Prüft, ob auf dem Ziel-Laufwerk genügend Speicherplatz vorhanden ist.
        
        Args:
            required_bytes: Benötigter Speicherplatz in Bytes
            
        Returns:
            Dict mit 'success' (True/False) und Details zum verfügbaren Platz
        """
        try:
            # Verfügbaren Speicherplatz auf dem Backup-Laufwerk prüfen
            disk_usage = shutil.disk_usage(self.backup_base)
            available_bytes = disk_usage.free
            
            # Sicherheitspuffer von 20% für Komprimierung und Metadaten
            safety_buffer = int(required_bytes * 0.2)
            required_with_buffer = required_bytes + safety_buffer
            
            available_mb = available_bytes / (1024 * 1024)
            required_mb = required_with_buffer / (1024 * 1024)
            
            logger.info(f"Speicherplatz-Prüfung: Verfügbar={available_mb:.2f} MB, Benötigt={required_mb:.2f} MB (inkl. 20% Puffer)")
            
            if available_bytes < required_with_buffer:
                return {
                    'success': False,
                    'error': 'Nicht genügend Speicherplatz',
                    'available_mb': round(available_mb, 2),
                    'required_mb': round(required_mb, 2),
                    'shortage_mb': round(required_mb - available_mb, 2)
                }
            
            return {
                'success': True,
                'available_mb': round(available_mb, 2),
                'required_mb': round(required_mb, 2)
            }
            
        except Exception as e:
            logger.error(f"Fehler bei Speicherplatz-Prüfung: {e}")
            return {
                'success': False,
                'error': f'Fehler bei Speicherplatz-Prüfung: {str(e)}'
            }
    
    def _get_snapshot_file(self, timestamp):
        """Gibt den Pfad zur Snapshot-Datei zurück"""
        return self.snapshots_dir / f"snapshot_{timestamp}.json"
    
    def create_backup(self):
        """Erstellt ein versionsbasiertes Backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Zuerst die geschätzte Größe berechnen für Speicherplatz-Prüfung
            estimated_size = 0
            if self.data_dir.exists():
                for db_file in self.data_dir.glob("*.db"):
                    estimated_size += db_file.stat().st_size
                    for extra in [f"{db_file.name}-wal", f"{db_file.name}-shm"]:
                        extra_path = self.data_dir / extra
                        if extra_path.exists():
                            estimated_size += extra_path.stat().st_size
            
            if self.akten_dir.exists():
                for root, dirs, files in os.walk(self.akten_dir):
                    for file_name in files:
                        file_path = Path(root) / file_name
                        try:
                            estimated_size += file_path.stat().st_size
                        except Exception:
                            continue
            
            # Speicherplatz prüfen, bevor das Backup erstellt wird
            space_check = self._check_disk_space(estimated_size)
            if not space_check['success']:
                error_msg = f"Nicht genügend Speicherplatz auf dem Ziel-Laufwerk. Verfügbar: {space_check['available_mb']} MB, Benötigt: {space_check['required_mb']} MB (Fehlend: {space_check.get('shortage_mb', 0)} MB)"
                logger.info(f"Backup abgebrochen: {error_msg}")
                return {'success': False, 'error': error_msg, 'disk_space_check': space_check}
            
            # 1. Zuerst sichern wir die Datenbank (komprimiert!)
            db_name = self.config['database']['name']
            db_files = []
            if self.data_dir.exists():
                for db_file in self.data_dir.glob("*.db"):
                    # DB-Datei sichern
                    db_backup_path = self.db_backups_dir / f"{db_file.name}.{timestamp}"
                    shutil.copy2(db_file, db_backup_path)
                    # Komprimiere DB-Datei
                    db_backup_gz = self._compress_db_file(db_backup_path)
                    setze_datenbank_schutz(str(db_backup_gz), aktivieren=True)
                    
                    # Auch WAL/SHM Dateien sichern (und komprimieren)
                    wal_shm_files = []
                    for extra in [f"{db_file.name}-wal", f"{db_file.name}-shm"]:
                        extra_path = self.data_dir / extra
                        if extra_path.exists():
                            extra_backup = self.db_backups_dir / f"{extra}.{timestamp}"
                            shutil.copy2(extra_path, extra_backup)
                            # Komprimiere WAL/SHM
                            extra_backup_gz = self._compress_db_file(extra_backup)
                            wal_shm_files.append(f"{extra}.gz")
                    
                    db_files.append({
                        "original_name": db_file.name,
                        "backup_name": f"{db_file.name}.{timestamp}.gz",
                        "wal_shm_files": wal_shm_files
                    })
            
            # 2. Dann sammeln und archivieren wir alle Akten-Dateien (inklusive Archiv)
            files_map = {}  # {relativer_pfad: file_hash}
            
            if self.akten_dir.exists():
                for root, dirs, files in os.walk(self.akten_dir):
                    for file_name in files:
                        file_path = Path(root) / file_name
                        try:
                            file_hash = self._archive_file(file_path)
                            if file_hash:
                                rel_path = file_path.relative_to(self.akten_dir)
                                # Pfad im JSON mit FORWARD SLASHES speichern (plattformunabhängig)
                                files_map[str(rel_path).replace('\\', '/')] = file_hash
                        except Exception as e:
                            logger.error(f"Fehler bei Archivierung von {file_path}: {e}")
            
            # 3. Erstelle die Snapshot-Datei
            snapshot = {
                "timestamp": timestamp,
                "created_at": datetime.now().isoformat(),
                "databases": db_files,
                "files": files_map
            }
            
            snapshot_file = self._get_snapshot_file(timestamp)
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            
            # 4. Info-Datei erstellen
            info_file = self.backup_base / f"ORDAMA_Backup_{timestamp}.txt"
            with open(info_file, "w", encoding="utf-8") as f:
                f.write(f"ORDAMA Versionsbackup\n")
                f.write(f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
                f.write(f"Datenbanken: {len(db_files)}\n")
                f.write(f"Dateien: {len(files_map)}\n")
            
            # KEIN ZIP MEHR! Speicherverschwendung!

            logger.info(f"Versionsbackup erfolgreich erstellt: {timestamp}")

            # Security Event loggen
            if self.security_logger:
                self.security_logger.log_backup_created(f"ORDAMA_Backup_{timestamp}")

            return {
                'success': True,
                'timestamp': timestamp,
                'path': str(self.backup_base.absolute())
            }

        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Versionsbackups: {e}")
            return {'success': False, 'error': str(e)}
    
    def list_snapshots(self):
        """Listet alle verfügbaren Snapshots auf"""
        try:
            snapshots = []
            if self.snapshots_dir.exists():
                for snap_file in sorted(self.snapshots_dir.glob("snapshot_*.json"), reverse=True):
                    try:
                        with open(snap_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            snapshots.append({
                                "timestamp": data["timestamp"],
                                "created_at": data["created_at"],
                                "num_files": len(data.get("files", {})),
                                "num_databases": len(data.get("databases", [])),
                                "file": snap_file.name
                            })
                    except Exception as e:
                        logger.warning(f"Konnte Snapshot nicht einlesen: {snap_file} - {e}")
            return snapshots
        except Exception as e:
            logger.error(f"Fehler bei Auflistung der Snapshots: {e}")
            return []
    
    def restore_snapshot(self, timestamp, overwrite=False):
        """Stellt einen Snapshot wieder her"""
        try:
            snapshot_file = self._get_snapshot_file(timestamp)
            if not snapshot_file.exists():
                return {'success': False, 'error': 'Snapshot nicht gefunden'}
            
            with open(snapshot_file, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
            
            # 1. Datenbanken wiederherstellen - Umbenennen statt Löschen/Verschieben
            # Dies vermeidet Dateisperrfehler
            if self.data_dir.exists() and not overwrite:
                # Um Overwrite zu vermeiden, benennen wir die aktuellen Dateien um
                temp_backup = self.data_base_dir / f"temp_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                temp_backup.mkdir(exist_ok=True)
                
                for db_file in self.data_dir.glob("*.db"):
                    # Unlock database before renaming
                    setze_datenbank_schutz(str(db_file), aktivieren=False)
                    # Rename instead of move
                    max_retries = 5
                    for attempt in range(max_retries):
                        try:
                            new_name = f"{db_file.stem}_backup_{datetime.now().strftime('%H%M%S')}{db_file.suffix}"
                            db_file.rename(db_file.parent / new_name)
                            # Then move to temp folder
                            shutil.move(db_file.parent / new_name, temp_backup / db_file.name)
                            logger.info(f"Database file {db_file.name} backed up successfully")
                            break
                        except PermissionError as e:
                            if attempt < max_retries - 1:
                                import time
                                time.sleep(2)
                                logger.warning(f"Retry {attempt + 1} for renaming {db_file.name}")
                            else:
                                raise
                    
                    for extra in [f"{db_file.name}-wal", f"{db_file.name}-shm"]:
                        extra_path = self.data_dir / extra
                        if extra_path.exists():
                            setze_datenbank_schutz(str(extra_path), aktivieren=False)
                            max_retries = 5
                            for attempt in range(max_retries):
                                try:
                                    new_name = f"{extra_path.stem}_backup_{datetime.now().strftime('%H%M%S')}{extra_path.suffix}"
                                    extra_path.rename(extra_path.parent / new_name)
                                    shutil.move(extra_path.parent / new_name, temp_backup / extra)
                                    logger.info(f"Extra file {extra} backed up successfully")
                                    break
                                except PermissionError as e:
                                    if attempt < max_retries - 1:
                                        import time
                                        time.sleep(2)
                                        logger.warning(f"Retry {attempt + 1} for renaming {extra}")
                                    else:
                                        logger.warning(f"Could not backup {extra}, continuing...")
            elif self.data_dir.exists():
                # Wenn Overwrite erlaubt, benennen wir Dateien um statt zu löschen
                for file in self.data_dir.iterdir():
                    if file.is_file():
                        setze_datenbank_schutz(str(file), aktivieren=False)
                        max_retries = 5
                        for attempt in range(max_retries):
                            try:
                                new_name = f"{file.stem}_backup_{datetime.now().strftime('%H%M%S')}{file.suffix}"
                                file.rename(file.parent / new_name)
                                logger.info(f"File {file.name} renamed to {new_name}")
                                break
                            except PermissionError as e:
                                if attempt < max_retries - 1:
                                    import time
                                    time.sleep(2)
                                    logger.warning(f"Retry {attempt + 1} for renaming {file.name}")
                                else:
                                    logger.warning(f"Could not rename {file.name}, continuing...")
            else:
                self.data_dir.mkdir(parents=True, exist_ok=True)
            
            for db_info in snapshot.get("databases", []):
                db_backup_gz = self.db_backups_dir / db_info["backup_name"]
                if db_backup_gz.exists():
                    # Dekomprimiere DB-Datei
                    db_backup_path = self._decompress_db_file(db_backup_gz)
                    dest_path = self.data_dir / db_info["original_name"]
                    
                    # Remove any existing WAL/SHM files before restoring
                    for extra in [f"{db_info['original_name']}-wal", f"{db_info['original_name']}-shm"]:
                        extra_path = self.data_dir / extra
                        if extra_path.exists():
                            setze_datenbank_schutz(str(extra_path), aktivieren=False)
                            max_retries = 3
                            for attempt in range(max_retries):
                                try:
                                    extra_path.unlink()
                                    break
                                except PermissionError:
                                    if attempt < max_retries - 1:
                                        import time
                                        time.sleep(1)
                                    else:
                                        logger.warning(f"Could not delete {extra}, continuing...")
                    
                    shutil.copy2(db_backup_path, dest_path)
                    setze_datenbank_schutz(str(dest_path), aktivieren=False)
                    
                    # Auch WAL/SHM Dateien wiederherstellen
                    for extra_gz in db_info.get("wal_shm_files", []):
                        extra_backup_gz = self.db_backups_dir / extra_gz
                        if extra_backup_gz.exists():
                            extra_backup = self._decompress_db_file(extra_backup_gz)
                            shutil.copy2(extra_backup, self.data_dir / extra_gz[:-3])
            
            # 2. Akten-Dateien wiederherstellen
            if self.akten_dir.exists() and not overwrite:
                # Aktuelle Akten in temp-Ordner verschieben
                temp_akten = self.data_base_dir / f"temp_akten_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(self.akten_dir), str(temp_akten))
            elif self.akten_dir.exists():
                # Ordner leeren, falls Overwrite erlaubt
                shutil.rmtree(self.akten_dir)
            
            self.akten_dir.mkdir(parents=True, exist_ok=True)
            restored_count = 0
            
            for rel_path_str, file_hash in snapshot.get("files", {}).items():
                # Relativen Pfad normalisieren (immer Forward Slash zu Path)
                rel_path = Path(rel_path_str.replace('\\', '/'))
                dest_path = self.akten_dir / rel_path
                
                # Archiv-Datei suchen (mit .gz!)
                archive_subdir = self.archive_dir / file_hash[:2]
                archive_file_gz = archive_subdir / f"{file_hash}.gz"
                
                if archive_file_gz.exists():
                    dest_parent = dest_path.parent
                    dest_parent.mkdir(parents=True, exist_ok=True)
                    # Dekomprimiere und kopiere
                    with gzip.open(archive_file_gz, 'rb') as f_in:
                        with open(dest_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    # Auf Linux: Rechte setzen (Lesen/Schreiben für alle, damit es plattformunabhängig ist!)
                    if os.name != 'nt':
                        os.chmod(dest_path, 0o666)
                        os.chmod(dest_parent, 0o777)
                    restored_count += 1
            
            logger.info(f"Snapshot {timestamp} erfolgreich wiederhergestellt: {restored_count} Dateien")
            return {
                'success': True, 
                'timestamp': timestamp,
                'restored_files': restored_count
            }
        except Exception as e:
            logger.error(f"Fehler bei Wiederherstellung des Snapshots {timestamp}: {e}")
            return {'success': False, 'error': str(e)}

    def cleanup_old_backups(self, keep_count=20):
        """Löscht alte Snapshots, behält nur die neuesten X (Dateien im Archiv bleiben erhalten!)"""
        try:
            snapshots = self.list_snapshots()
            if len(snapshots) > keep_count:
                # Alle Hashes sammeln, die in den behaltenen Snapshots verwendet werden
                keep_hashes = set()
                for snap in snapshots[:keep_count]:
                    snap_file = self.snapshots_dir / snap['file']
                    if snap_file.exists():
                        with open(snap_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            keep_hashes.update(data.get("files", {}).values())
                
                # Jetzt die alten Snapshots löschen
                for snap in snapshots[keep_count:]:
                    snap_file = self.snapshots_dir / snap['file']
                    if snap_file.exists():
                        snap_file.unlink()
                        logger.info(f"Alter Snapshot gelöscht: {snap['file']}")
                        
                        # Zugehörige DB-Backups löschen (inklusive .gz)
                        for db_file in self.db_backups_dir.glob(f"*.{snap['timestamp']}*"):
                            db_file.unlink()
                            logger.info(f"Zugehöriges DB-Backup gelöscht: {db_file.name}")
                
                # Info-Dateien löschen, wenn sie zu den gelöschten Snapshots gehören
                for info_file in self.backup_base.glob("ORDAMA_Backup_*.txt"):
                    ts = info_file.stem.replace("ORDAMA_Backup_", "")
                    if ts not in [s['timestamp'] for s in snapshots[:keep_count]]:
                        info_file.unlink()
            
            logger.info(f"Backup-Bereinigung abgeschlossen.")
        except Exception as e:
            logger.error(f"Fehler bei Bereinigung alter Backups: {e}")
