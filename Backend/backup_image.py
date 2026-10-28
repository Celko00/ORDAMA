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

Image-Based Backup System for ORDAMA
- Single-file backup format (ZIP with manifest)
- Complete system backup: database, attachments, archives, permissions, settings
- Atomic restore with rollback capability
- OCR-safe: pauses OCR during backup/restore
- Cross-platform compatible (Windows/Linux)
"""

import os
import shutil
import logging
import json
import hashlib
import zipfile
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class ImageBackupManager:
    """
    Image-based backup manager that creates complete system snapshots in single ZIP files.
    """
    
    def __init__(self, base_dir, config, db_manager=None, ocr_manager=None, security_logger=None):
        self.base_dir = Path(base_dir)
        self.config = config
        self.db_manager = db_manager
        self.ocr_manager = ocr_manager
        self.security_logger = security_logger
        
        # Resolve paths
        self.data_base_dir = self._resolve_path(self.config['paths'].get('data_base_dir', './Speicher'))
        self.data_dir = self.data_base_dir / "Datenbank"
        
        attachments_dir_str = self.config['paths'].get('attachments_dir', '')
        if attachments_dir_str:
            self.akten_dir = self._resolve_path(attachments_dir_str)
        else:
            self.akten_dir = self.data_base_dir / "Akten"
        
        self.backup_dir = self._resolve_path(self.config['paths'].get('backup_dir', './Backups'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # OCR pause lock
        self._ocr_pause_lock = threading.Lock()
        self._ocr_was_running = False
        
    def _resolve_path(self, path_str):
        """Resolve a path (relative to base_dir or absolute)"""
        p = Path(path_str)
        if p.is_absolute():
            return p
        return self.base_dir / p
    
    def _pause_ocr(self):
        """Pause OCR processing if running"""
        if self.ocr_manager:
            try:
                # Check if OCR worker is running
                if hasattr(self.ocr_manager, 'worker_thread') and self.ocr_manager.worker_thread and self.ocr_manager.worker_thread.is_alive():
                    self._ocr_was_running = True
                    # Stop OCR processing
                    if hasattr(self.ocr_manager, 'stop_event'):
                        self.ocr_manager.stop_event.set()
                    logger.info("OCR paused for backup/restore")
            except Exception as e:
                logger.warning(f"Could not pause OCR: {e}")
    
    def _resume_ocr(self):
        """Resume OCR processing if it was running"""
        if self.ocr_manager and self._ocr_was_running:
            try:
                if hasattr(self.ocr_manager, 'stop_event'):
                    self.ocr_manager.stop_event.clear()
                # Restart OCR worker if needed
                if hasattr(self.ocr_manager, 'start_worker'):
                    self.ocr_manager.start_worker()
                logger.info("OCR resumed after backup/restore")
                self._ocr_was_running = False
            except Exception as e:
                logger.warning(f"Could not resume OCR: {e}")
    
    def _close_database_safely(self):
        """Close all database connections safely"""
        if self.db_manager:
            try:
                self.db_manager.close_all_connections()
                # Additional wait to ensure file handles are released
                time.sleep(0.5)
                logger.info("Database connections closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")
    
    def _get_file_hash(self, file_path):
        """Calculate SHA-256 hash for a file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _create_manifest(self, backup_path: Path, included_items: List[Dict]) -> Dict:
        """Create backup manifest with metadata"""
        manifest = {
            "version": "2.0",
            "format": "image-backup",
            "created_at": datetime.now().isoformat(),
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "ordama_version": self._get_ordama_version(),
            "backup_file": backup_path.name,
            "backup_size_bytes": backup_path.stat().st_size if backup_path.exists() else 0,
            "backup_hash": self._get_file_hash(backup_path) if backup_path.exists() else None,
            "included_items": included_items,
            "platform": os.name,
            "config_snapshot": {
                "database": self.config.get('database', {}),
                "paths": {k: v for k, v in self.config.get('paths', {}).items() if k != 'backup_dir'}
            }
        }
        return manifest
    
    def _get_ordama_version(self):
        """Extract ORDAMA version from app.py"""
        try:
            app_py = self.base_dir / "Backend" / "app.py"
            if app_py.exists():
                with open(app_py, 'r', encoding='utf-8') as f:
                    for line in f:
                        if 'VERSION =' in line:
                            return line.split('=')[1].strip().replace('"', '').replace("'", "")
        except Exception as e:
            logger.warning(f"Could not read version: {e}")
        return "unknown"
    
    def _export_database_settings(self) -> str:
        """Export all database settings to a temporary JSON file"""
        try:
            import tempfile
            import json
            
            settings = {}
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Alle Einstellungen aus der settings Tabelle exportieren
                cursor.execute("SELECT key, value FROM settings")
                rows = cursor.fetchall()
                
                for row in rows:
                    settings[row['key']] = row['value']
            
            # In temporäre Datei schreiben
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='_settings.json', delete=False, encoding='utf-8')
            json.dump(settings, temp_file, indent=2, ensure_ascii=False)
            temp_file.close()
            
            logger.info(f"Exported {len(settings)} database settings")
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Error exporting database settings: {e}")
            return None
    
    def _import_database_settings(self, settings_file: Path):
        """Import database settings from a JSON file"""
        try:
            import json
            
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Alle Einstellungen importieren
                for key, value in settings.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO settings (key, value)
                        VALUES (?, ?)
                    """, (key, value))
                
                conn.commit()
            
            logger.info(f"Imported {len(settings)} database settings")
            
        except Exception as e:
            logger.error(f"Error importing database settings: {e}")
            raise
    
    def _check_disk_space(self, required_bytes: int) -> Dict:
        """
        Prüft, ob auf dem Ziel-Laufwerk genügend Speicherplatz vorhanden ist.
        
        Args:
            required_bytes: Benötigter Speicherplatz in Bytes
            
        Returns:
            Dict mit 'success' (True/False) und Details zum verfügbaren Platz
        """
        try:
            # Verfügbaren Speicherplatz auf dem Backup-Laufwerk prüfen
            disk_usage = shutil.disk_usage(self.backup_dir)
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
    
    def _collect_items_to_backup(self) -> List[Dict]:
        """Collect all items to include in backup"""
        items = []
        
        # 1. Database files
        if self.data_dir.exists():
            for db_file in self.data_dir.glob("*.db"):
                items.append({
                    "type": "database",
                    "source": str(db_file),
                    "dest": f"Datenbank/{db_file.name}",
                    "size": db_file.stat().st_size
                })
            # WAL and SHM files
            for extra_file in self.data_dir.glob("*-wal"):
                items.append({
                    "type": "database_extra",
                    "source": str(extra_file),
                    "dest": f"Datenbank/{extra_file.name}",
                    "size": extra_file.stat().st_size
                })
            for extra_file in self.data_dir.glob("*-shm"):
                items.append({
                    "type": "database_extra",
                    "source": str(extra_file),
                    "dest": f"Datenbank/{extra_file.name}",
                    "size": extra_file.stat().st_size
                })
        
        # 2. Akten (attachments)
        if self.akten_dir.exists():
            for root, dirs, files in os.walk(self.akten_dir):
                for file_name in files:
                    file_path = Path(root) / file_name
                    rel_path = file_path.relative_to(self.akten_dir)
                    items.append({
                        "type": "attachment",
                        "source": str(file_path),
                        "dest": f"Akten/{rel_path}".replace('\\', '/'),
                        "size": file_path.stat().st_size
                    })
        
        # 3. Form templates
        form_templates_dir = self.data_base_dir / "Formularvorlagen"
        if form_templates_dir.exists():
            for root, dirs, files in os.walk(form_templates_dir):
                for file_name in files:
                    file_path = Path(root) / file_name
                    rel_path = file_path.relative_to(form_templates_dir)
                    items.append({
                        "type": "form_template",
                        "source": str(file_path),
                        "dest": f"Formularvorlagen/{rel_path}".replace('\\', '/'),
                        "size": file_path.stat().st_size
                    })
        
        # 4. Chat data
        chat_dir = self.data_base_dir / "Chat"
        if chat_dir.exists():
            for root, dirs, files in os.walk(chat_dir):
                for file_name in files:
                    file_path = Path(root) / file_name
                    rel_path = file_path.relative_to(chat_dir)
                    items.append({
                        "type": "chat",
                        "source": str(file_path),
                        "dest": f"Chat/{rel_path}".replace('\\', '/'),
                        "size": file_path.stat().st_size
                    })
        
        # 5. Configuration files (alle Dateien in Konfiguration inklusive Unterordner)
        config_dir = self.base_dir / "Konfiguration"
        if config_dir.exists():
            for root, dirs, files in os.walk(config_dir):
                for file_name in files:
                    file_path = Path(root) / file_name
                    rel_path = file_path.relative_to(config_dir)
                    items.append({
                        "type": "config",
                        "source": str(file_path),
                        "dest": f"Konfiguration/{rel_path}".replace('\\', '/'),
                        "size": file_path.stat().st_size
                    })
        
        # 6. Archive data (archivierte Akten mit Anhängen)
        archive_dir = self.akten_dir / "Archiv"
        if archive_dir.exists():
            for root, dirs, files in os.walk(archive_dir):
                for file_name in files:
                    file_path = Path(root) / file_name
                    rel_path = file_path.relative_to(archive_dir)
                    items.append({
                        "type": "archive",
                        "source": str(file_path),
                        "dest": f"Archiv/{rel_path}".replace('\\', '/'),
                        "size": file_path.stat().st_size
                    })
        
        # 7. Database settings export (alle Einstellungen aus der Datenbank)
        if self.db_manager:
            try:
                settings_export = self._export_database_settings()
                if settings_export:
                    items.append({
                        "type": "database_settings",
                        "source": settings_export,
                        "dest": "Datenbank/settings_export.json",
                        "size": Path(settings_export).stat().st_size
                    })
            except Exception as e:
                logger.warning(f"Could not export database settings: {e}")
        
        return items
    
    def create_backup(self) -> Dict:
        """
        Create a complete image-based backup in a single ZIP file.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"ORDAMA_ImageBackup_{timestamp}.zip"
            backup_path = self.backup_dir / backup_filename
            
            logger.info(f"Starting image backup: {backup_filename}")
            
            # Pause OCR to prevent conflicts
            self._pause_ocr()
            
            # Collect items to backup
            items = self._collect_items_to_backup()
            total_size = sum(item['size'] for item in items)
            logger.info(f"Collected {len(items)} items, total size: {total_size / (1024*1024):.2f} MB")
            
            # Speicherplatz prüfen, bevor das Backup erstellt wird
            space_check = self._check_disk_space(total_size)
            if not space_check['success']:
                self._resume_ocr()
                error_msg = f"Nicht genügend Speicherplatz auf dem Ziel-Laufwerk. Verfügbar: {space_check['available_mb']} MB, Benötigt: {space_check['required_mb']} MB (Fehlend: {space_check.get('shortage_mb', 0)} MB)"
                logger.info(f"Backup abgebrochen: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'disk_space_check': space_check
                }
            
            # Create ZIP archive
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                for item in items:
                    source_path = Path(item['source'])
                    if source_path.exists():
                        try:
                            zipf.write(source_path, item['dest'])
                            logger.debug(f"Added: {item['dest']}")
                        except Exception as e:
                            logger.error(f"Failed to add {item['dest']}: {e}")
                
                # Add manifest
                manifest = self._create_manifest(backup_path, items)
                manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
                zipf.writestr("manifest.json", manifest_json)
            
            # Verify backup
            if not backup_path.exists():
                raise Exception("Backup file was not created")
            
            backup_size = backup_path.stat().st_size
            compression_ratio = (1 - backup_size / total_size) * 100 if total_size > 0 else 0
            
            logger.info(f"Image backup created successfully: {backup_filename}")
            logger.info(f"Backup size: {backup_size / (1024*1024):.2f} MB (compressed: {compression_ratio:.1f}%)")
            
            # Log security event
            if self.security_logger:
                self.security_logger.log_backup_created(backup_filename)
            
            # Resume OCR
            self._resume_ocr()
            
            return {
                'success': True,
                'timestamp': timestamp,
                'filename': backup_filename,
                'path': str(backup_path),
                'size_bytes': backup_size,
                'size_mb': round(backup_size / (1024*1024), 2),
                'items_count': len(items),
                'compression_ratio': round(compression_ratio, 1)
            }
            
        except Exception as e:
            logger.error(f"Error creating image backup: {e}")
            self._resume_ocr()
            return {'success': False, 'error': str(e)}
    
    def list_backups(self) -> List[Dict]:
        """List all available image backups"""
        backups = []
        for backup_file in sorted(self.backup_dir.glob("ORDAMA_ImageBackup_*.zip"), reverse=True):
            try:
                # Try to read manifest from ZIP
                with zipfile.ZipFile(backup_file, 'r') as zipf:
                    if 'manifest.json' in zipf.namelist():
                        manifest_json = zipf.read('manifest.json').decode('utf-8')
                        manifest = json.loads(manifest_json)
                        backups.append({
                            'filename': backup_file.name,
                            'timestamp': manifest.get('timestamp'),
                            'created_at': manifest.get('created_at'),
                            'size_bytes': backup_file.stat().st_size,
                            'size_mb': round(backup_file.stat().st_size / (1024*1024), 2),
                            'version': manifest.get('ordama_version'),
                            'items_count': len(manifest.get('included_items', [])),
                            'hash': manifest.get('backup_hash')
                        })
                    else:
                        # Legacy backup without manifest - count files in ZIP
                        file_count = len(zipf.namelist())
                        backups.append({
                            'filename': backup_file.name,
                            'timestamp': backup_file.stem.replace('ORDAMA_ImageBackup_', ''),
                            'created_at': datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat(),
                            'size_bytes': backup_file.stat().st_size,
                            'size_mb': round(backup_file.stat().st_size / (1024*1024), 2),
                            'version': 'unknown',
                            'items_count': file_count,
                            'hash': None
                        })
            except Exception as e:
                logger.warning(f"Could not read backup {backup_file.name}: {e}")
                # Try to count files even if manifest read failed
                file_count = 0
                try:
                    with zipfile.ZipFile(backup_file, 'r') as zipf:
                        file_count = len(zipf.namelist())
                except:
                    pass
                backups.append({
                    'filename': backup_file.name,
                    'timestamp': backup_file.stem.replace('ORDAMA_ImageBackup_', ''),
                    'created_at': datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat(),
                    'size_bytes': backup_file.stat().st_size,
                    'size_mb': round(backup_file.stat().st_size / (1024*1024), 2),
                    'version': 'unknown',
                    'items_count': file_count,
                    'hash': None,
                    'error': str(e)
                })
        return backups
    
    def restore_backup(self, filename: str, overwrite: bool = True) -> Dict:
        """
        Restore from an image backup using server restart method (most reliable).
        
        Args:
            filename: Name of the backup file
            overwrite: If True, overwrite existing files; if False, create backup of current state
        """
        try:
            backup_path = self.backup_dir / filename
            if not backup_path.exists():
                return {'success': False, 'error': f'Backup file not found: {filename}'}
            
            logger.info(f"Starting restore from: {filename} (server restart method)")
            
            # Pause OCR
            self._pause_ocr()
            
            # Close database connections
            self._close_database_safely()
            
            # Create temporary restore directory
            temp_restore_dir = self.backup_dir / f"temp_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            temp_restore_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Extracting backup to temporary directory: {temp_restore_dir}")
            
            # Extract backup to temporary directory
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(temp_restore_dir)
            
            logger.info(f"Backup extracted successfully to: {temp_restore_dir}")
            
            # Create restore instruction file
            restore_instruction = {
                'backup_filename': filename,
                'temp_restore_dir': str(temp_restore_dir),
                'timestamp': datetime.now().isoformat(),
                'data_dir': str(self.data_dir),
                'akten_dir': str(self.akten_dir),
                'data_base_dir': str(self.data_base_dir),
                'base_dir': str(self.base_dir)
            }
            
            instruction_file = self.backup_dir / "restore_instruction.json"
            with open(instruction_file, 'w', encoding='utf-8') as f:
                json.dump(restore_instruction, f, indent=2)
            
            logger.info(f"Restore instruction file created: {instruction_file}")
            
            # Resume OCR (will be paused again after restart)
            self._resume_ocr()
            
            return {
                'success': True,
                'filename': filename,
                'message': 'Backup extrahiert. Bitte Server manuell neu starten. Die Wiederherstellung wird automatisch durchgeführt.',
                'requires_restart': True,
                'restore_pending': True
            }
            
        except Exception as e:
            logger.error(f"Error preparing restore: {e}")
            self._resume_ocr()
            return {'success': False, 'error': str(e)}
    
    def cleanup_old_backups(self, keep_count: int = 10):
        """Delete old image backups, keeping only the most recent ones"""
        try:
            backups = self.list_backups()
            if len(backups) > keep_count:
                for backup in backups[keep_count:]:
                    backup_path = self.backup_dir / backup['filename']
                    try:
                        backup_path.unlink()
                        logger.info(f"Deleted old backup: {backup['filename']}")
                    except Exception as e:
                        logger.error(f"Could not delete {backup['filename']}: {e}")
            logger.info(f"Backup cleanup completed. Kept {min(len(backups), keep_count)} backups.")
        except Exception as e:
            logger.error(f"Error during backup cleanup: {e}")
    
    def verify_backup(self, filename: str) -> Dict:
        """Verify a backup file integrity"""
        try:
            backup_path = self.backup_dir / filename
            if not backup_path.exists():
                return {'success': False, 'error': 'Backup file not found'}
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                # Check if ZIP is valid
                bad_files = zipf.testzip()
                if bad_files:
                    return {'success': False, 'error': f'Corrupted files in backup: {bad_files}'}
                
                # Read and verify manifest
                if 'manifest.json' in zipf.namelist():
                    manifest_json = zipf.read('manifest.json').decode('utf-8')
                    manifest = json.loads(manifest_json)
                    
                    # Verify hash if available
                    if manifest.get('backup_hash'):
                        current_hash = self._get_file_hash(backup_path)
                        if current_hash != manifest['backup_hash']:
                            return {'success': False, 'error': 'Backup hash mismatch - file may be corrupted'}
                    
                    return {
                        'success': True,
                        'valid': True,
                        'version': manifest.get('version'),
                        'timestamp': manifest.get('timestamp'),
                        'items_count': len(manifest.get('included_items', []))
                    }
                else:
                    return {
                        'success': True,
                        'valid': True,
                        'version': 'legacy',
                        'timestamp': None,
                        'items_count': len(zipf.namelist())
                    }
                    
        except Exception as e:
            logger.error(f"Error verifying backup: {e}")
            return {'success': False, 'error': str(e)}
