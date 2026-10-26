"""
Storage Manager für ORDAMA
- Speicherplatz-Berechnung mit Caching
- Dateisystem-Operationen
"""

import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageManager:
    """Verwaltet Speicherplatz-Berechnungen und Dateisystem-Operationen"""
    
    def __init__(self, base_dir, config):
        self.base_dir = Path(base_dir)
        self.config = config
        
        # Cache für Speicherberechnung
        self._storage_cache = None
        self._storage_cache_time = None
        self._storage_cache_ttl = 300  # 5 Minuten Cache
        
        # Pfad auflösen (absolut oder relativ zum base_dir)
        data_base_dir_str = config['paths'].get('data_base_dir', './Speicher')
        data_base_dir = Path(data_base_dir_str)
        if not data_base_dir.is_absolute():
            data_base_dir = self.base_dir / data_base_dir
            
        self.akten_dir = data_base_dir / "Akten"
    
    def calculate_storage_info(self):
        """Berechnet Speicherplatz-Informationen mit Caching"""
        import time
        
        # Cache prüfen
        current_time = time.time()
        if (self._storage_cache is not None and 
            self._storage_cache_time is not None and 
            (current_time - self._storage_cache_time) < self._storage_cache_ttl):
            logger.debug("Verwende gecachten Speicherplatz-Wert")
            return self._storage_cache
        
        # Speicherplatz berechnen
        try:
            # data_base_dir ermitteln
            data_base_dir = self.akten_dir.parent
            backup_dir_str = self.config['paths'].get('backup_dir', './Backups')
            backup_dir = Path(backup_dir_str)
            if not backup_dir.is_absolute():
                backup_dir = self.base_dir / backup_dir
            
            # Partition-Info für Hauptspeicher
            path_to_check = str(data_base_dir.absolute())
            usage = shutil.disk_usage(path_to_check)
            
            # Partition-Info für Backup (falls abweichend oder existiert)
            backup_usage = None
            if backup_dir.exists():
                backup_usage = shutil.disk_usage(str(backup_dir.absolute()))
            
            # Programm-Speicherverbrauch berechnen (optimiert mit os.scandir)
            total_used_bytes = 0
            if data_base_dir.exists():
                for root, dirs, files in os.walk(str(data_base_dir)):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if not os.path.islink(fp):
                                total_used_bytes += os.path.getsize(fp)
                        except (OSError, PermissionError):
                            pass

            result = {
                'total_disk_bytes': usage.total,
                'free_disk_bytes': usage.free,
                'program_used_bytes': total_used_bytes,
                'percent_disk_used': round((usage.total - usage.free) / usage.total * 100, 1),
                'backup': {
                    'total_bytes': backup_usage.total if backup_usage else 0,
                    'free_bytes': backup_usage.free if backup_usage else 0,
                    'used_bytes': (backup_usage.total - backup_usage.free) if backup_usage else 0
                }
            }
            
            # Cache aktualisieren
            self._storage_cache = result
            self._storage_cache_time = current_time
            
            return result
        except Exception as e:
            logger.error(f"Fehler beim Berechnen des Speicherplatzes: {e}")
            # Fallback: dummy daten damit Frontend nichts "verschluckt"
            return {
                'total_disk_bytes': 1,
                'free_disk_bytes': 1,
                'program_used_bytes': 0,
                'percent_disk_used': 0,
                'error': str(e)
            }
    
    def invalidate_storage_cache(self):
        """Invalidiert den Speicherplatz-Cache"""
        self._storage_cache = None
        self._storage_cache_time = None
    
    def get_akten_dir(self):
        """Gibt das Akten-Verzeichnis zurück"""
        return self.akten_dir
    
    def create_akte_directory(self, number):
        """Erstellt das Verzeichnis für eine Akte"""
        akte_dir = self.akten_dir / number
        akte_dir.mkdir(parents=True, exist_ok=True)
        return akte_dir
    
    def delete_akte_directory(self, number):
        """Löscht das Verzeichnis einer Akte"""
        akte_dir = self.akten_dir / number
        if akte_dir.exists():
            shutil.rmtree(str(akte_dir))
            return True
        return False
    
    def delete_akte_directories(self, numbers):
        """Löscht mehrere Akten-Verzeichnisse"""
        errors = []
        for number in numbers:
            try:
                self.delete_akte_directory(number)
            except Exception as e:
                logger.error(f"Fehler beim Löschen des Aktenordners ({number}): {e}")
                errors.append({'number': number, 'error': str(e)})
        return errors
