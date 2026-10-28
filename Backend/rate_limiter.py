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

Rate Limiter für ORDAMA
- Schützt vor Überlastung durch einzelne Nutzer
- Token Bucket Algorithmus
"""

import time
import logging
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Konstanten für Rate Limiting
DEFAULT_RATE_LIMIT = 100  # 100 Requests pro Minute
DEFAULT_BURST = 20  # 20 Requests sofort erlaubt


class RateLimiter:
    """Rate Limiter mit Fixed Window und harter Sperrdauer"""
    
    def __init__(self, rate=DEFAULT_RATE_LIMIT, burst=DEFAULT_BURST):
        self.rate = rate  # Tokens pro Sekunde
        self.burst = burst  # Max Tokens im Bucket
        self.buckets = defaultdict(dict)
        self.lock = Lock()
        
        # Cleanup Task für alte Einträge
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # Alle 5 Minuten cleanup
    
    def _cleanup_old_entries(self):
        """Entfernt alte Einträge um Speicher zu sparen"""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        with self.lock:
            keys_to_remove = []
            for key, bucket in self.buckets.items():
                # Entferne Einträge die älter als 10 Minuten sind
                if now - bucket.get('last_update', 0) > 600:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.buckets[key]
            
            if keys_to_remove:
                logger.info(f"Rate Limiter Cleanup: {len(keys_to_remove)} alte Einträge entfernt")
            
            self.last_cleanup = now
    
    def is_allowed(self, identifier, block_duration_seconds=60):
        """
        Prüft ob eine Anfrage erlaubt ist
        
        Args:
            identifier: Eindeutige ID (z.B. IP-Adresse oder User-ID)
            block_duration_seconds: Sperrdauer in Sekunden nach Überschreitung
        
        Returns:
            Tuple (allowed: bool, remaining: int)
        """
        self._cleanup_old_entries()
        
        now = time.time()
        
        with self.lock:
            bucket = self.buckets[identifier]
            
            # Prüfen ob IP gesperrt ist
            blocked_until = bucket.get('blocked_until', 0)
            if now < blocked_until:
                # IP ist noch gesperrt
                remaining_blocked = int(blocked_until - now)
                return False, 0
            
            # Request-Counter für aktuelles Fenster
            window_start = bucket.get('window_start', now)
            request_count = bucket.get('request_count', 0)
            
            # Fenster zurücksetzen wenn älter als 1 Minute
            if now - window_start >= 60:
                window_start = now
                request_count = 0
            
            # Prüfen ob Limit überschritten
            if request_count >= self.rate:
                # Limit überschritten - IP sperren
                bucket['blocked_until'] = now + block_duration_seconds
                bucket['window_start'] = window_start
                bucket['request_count'] = request_count
                return False, 0
            
            # Request zählen
            request_count += 1
            bucket['window_start'] = window_start
            bucket['request_count'] = request_count
            bucket['last_update'] = now
            
            remaining = self.rate - request_count
            return True, remaining
    
    def get_remaining_tokens(self, identifier):
        """Gibt verbleibende Requests zurück"""
        with self.lock:
            bucket = self.buckets.get(identifier, {})
            request_count = bucket.get('request_count', 0)
            return max(0, self.rate - request_count)
    
    def reset(self, identifier):
        """Setzt den Bucket für einen Identifier zurück"""
        with self.lock:
            if identifier in self.buckets:
                del self.buckets[identifier]


class RateLimitMiddleware:
    """Flask Middleware für Rate Limiting"""
    
    def __init__(self, app, rate_limiter=None, security_logger=None):
        # Vermeide doppeltes Wrapping
        if hasattr(app, '_rate_limit_wrapped'):
            self.app = app.wsgi_app
            self.rate_limiter = rate_limiter or getattr(app, '_rate_limiter', RateLimiter())
            self.security_logger = security_logger or getattr(app, '_security_logger', None)
        else:
            self.app = app.wsgi_app
            self.rate_limiter = rate_limiter or RateLimiter()
            self.security_logger = security_logger
            app._rate_limit_wrapped = True
            app._rate_limiter = self.rate_limiter
            app._security_logger = self.security_logger
        
        # Konfiguration aus settings.json laden
        self.enabled = True
        self.rate_limit_per_minute = DEFAULT_RATE_LIMIT
        self.block_duration_seconds = 60  # Standard: 60 Sekunden Sperrdauer
        self.exclude_paths = [
            '/api/health',
            '/api/auth/heartbeat',
            '/api/auth/me',
            '/api/server-name',
            '/api/csrf-token'
        ]
        self.exclude_static = True  # Statische Dateien ausschließen
    
    def __call__(self, environ, start_response):
        """WSGI Middleware"""
        path = environ.get('PATH_INFO', '')
        
        # Statische Dateien und ausgeschlossene Pfade nicht limitieren
        if self.exclude_static and (
            path.endswith(('.html', '.css', '.js', '.png', '.ico', '.jpg', '.jpeg', '.svg', '.woff', '.woff2')) or
            path.startswith('/static') or
            path in self.exclude_paths
        ):
            return self.app(environ, start_response)
        
        # Identifier aus IP-Adresse holen
        identifier = self._get_identifier(environ)
        
        # Rate Limit prüfen
        if self.enabled:
            allowed, remaining = self.rate_limiter.is_allowed(identifier, self.block_duration_seconds)
            
            if not allowed:
                # Rate Limit überschritten
                
                # Security Event loggen
                if self.security_logger:
                    self.security_logger.log_rate_limit_exceeded(identifier)
                
                response_body = b'{"error": "Zu viele Anfragen. Bitte warten Sie einen Moment."}'
                start_response('429 Too Many Requests', [
                    ('Content-Type', 'application/json'),
                    ('Content-Length', str(len(response_body))),
                    ('Retry-After', str(self.block_duration_seconds)),
                    ('X-RateLimit-Limit', str(self.rate_limit_per_minute)),
                    ('X-RateLimit-Remaining', '0'),
                    ('X-RateLimit-Reset', str(int(time.time()) + self.block_duration_seconds))
                ])
                return [response_body]
            
            # Rate Limit Header hinzufügen
            def custom_start_response(status, headers, exc_info=None):
                headers.append(('X-RateLimit-Limit', str(self.rate_limit_per_minute)))
                headers.append(('X-RateLimit-Remaining', str(remaining)))
                headers.append(('X-RateLimit-Reset', str(int(time.time()) + self.block_duration_seconds)))
                return start_response(status, headers, exc_info)
            
            return self.app(environ, custom_start_response)
        
        return self.app(environ, start_response)
    
    def _get_identifier(self, environ):
        """Extrahiert Identifier aus Request (IP-Adresse)"""
        # Versuche verschiedene Header für IP-Adresse
        headers = environ.get('HTTP_X_FORWARDED_FOR', '')
        if headers:
            # X-Forwarded-For kann mehrere IPs enthalten (client, proxy1, proxy2)
            client_ip = headers.split(',')[0].strip()
            return client_ip
        
        # Cloudflare Connecting IP
        cf_ip = environ.get('HTTP_CF_CONNECTING_IP', '')
        if cf_ip:
            return cf_ip
        
        # Remote Addr
        return environ.get('REMOTE_ADDR', 'unknown')
    
    def configure(self, settings):
        """Konfiguriert den Rate Limiter aus settings.json"""
        self.enabled = settings.get('enabled', True)
        self.rate_limit_per_minute = settings.get('rate_limit_per_minute', DEFAULT_RATE_LIMIT)
        self.block_duration_seconds = settings.get('block_duration_seconds', 60)
        
        # Rate Limiter neu konfigurieren
        self.rate_limiter = RateLimiter(rate=self.rate_limit_per_minute, burst=self.rate_limit_per_minute)
        
        logger.info(f"Rate Limiter konfiguriert: enabled={self.enabled}, rate={self.rate_limit_per_minute}/min, block_duration={self.block_duration_seconds}s")
    
    def set_security_logger(self, security_logger):
        """Setzt den Security Logger nachträglich"""
        self.security_logger = security_logger
