"""
Cache Manager für ORDAMA
- Thread-sicherer Cache mit TTL
- Cache-Invalidierung und Pattern-Matching
"""

import time
import logging
from threading import Lock

logger = logging.getLogger(__name__)

# Konstanten für Cache-Konfiguration
CACHE_TTL_SECONDS = 300  # 5 Minuten
CACHE_MAX_ITEMS = 10000  # Max 10.000 Einträge im Cache (für 250.000 Akten)


class SimpleCache:
    """Einfacher Thread-sicherer Cache mit TTL und Größenlimit"""
    def __init__(self, default_ttl=CACHE_TTL_SECONDS, max_items=CACHE_MAX_ITEMS):
        self.cache = {}
        self.lock = Lock()
        self.default_ttl = default_ttl
        self.max_items = max_items
    
    def get(self, key):
        with self.lock:
            entry = self.cache.get(key)
            if entry is None:
                return None
            # Prüfen ob abgelaufen
            if time.time() > entry['expires']:
                del self.cache[key]
                return None
            return entry['value']
    
    def set(self, key, value, ttl=None):
        with self.lock:
            ttl = ttl if ttl is not None else self.default_ttl
            
            # Prüfen ob Cache voll ist und wenn ja, alte Einträge entfernen
            if len(self.cache) >= self.max_items and key not in self.cache:
                self._cleanup_expired_and_oldest()
            
            self.cache[key] = {
                'value': value,
                'expires': time.time() + ttl,
                'created': time.time()
            }
    
    def _cleanup_expired_and_oldest(self):
        """Entfernt abgelaufene Einträge und bei Bedarf die ältesten"""
        # Zuerst abgelaufene entfernen
        expired_keys = [k for k, v in self.cache.items() if time.time() > v['expires']]
        for key in expired_keys:
            del self.cache[key]
        
        # Wenn noch zu viele Einträge, älteste entfernen (nach created Zeit)
        if len(self.cache) >= self.max_items:
            # Sortiere nach created Zeit und entferne die ältesten 10%
            sorted_items = sorted(self.cache.items(), key=lambda x: x[1]['created'])
            to_remove = int(self.max_items * 0.1)  # 10% entfernen
            for key, _ in sorted_items[:to_remove]:
                del self.cache[key]
            logger.info(f"Cache-Cleanup: {to_remove} älteste Einträge entfernt")
    
    def invalidate(self, key):
        with self.lock:
            if key in self.cache:
                del self.cache[key]
    
    def invalidate_pattern(self, pattern):
        """Invalidiert alle Keys die mit pattern beginnen"""
        with self.lock:
            keys_to_delete = [k for k in self.cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self.cache[key]
    
    def clear(self):
        with self.lock:
            self.cache.clear()


class CacheManager:
    """Verwaltet Cache-Operationen für die Anwendung"""
    
    def __init__(self, default_ttl=CACHE_TTL_SECONDS):
        self.cache = SimpleCache(default_ttl=default_ttl)
    
    def get(self, key):
        """Holt einen Wert aus dem Cache"""
        return self.cache.get(key)
    
    def set(self, key, value, ttl=None):
        """Speichert einen Wert im Cache"""
        self.cache.set(key, value, ttl)
    
    def invalidate(self, key):
        """Invalidiert einen spezifischen Key"""
        self.cache.invalidate(key)
    
    def invalidate_pattern(self, pattern):
        """Invalidiert alle Keys die mit pattern beginnen"""
        self.cache.invalidate_pattern(pattern)
    
    def invalidate_records_cache(self):
        """Invalidiert alle Cache-Einträge die mit Akten zu tun haben"""
        self.cache.invalidate_pattern('records:')
        self.cache.invalidate_pattern('stats:')
        self.cache.invalidate_pattern('categories:')
    
    def invalidate_user_cache(self, user_id=None):
        """Invalidiert User-spezifische Cache-Einträge"""
        if user_id:
            self.cache.invalidate_pattern(f'user:{user_id}:')
        else:
            self.cache.invalidate_pattern('user:')
    
    def clear_all(self):
        """Leert den gesamten Cache"""
        self.cache.clear()
