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

Sicherheits-Utilities für ORDAMA
- CSRF-Schutz
- Input-Sanitization gegen XSS
- File-Upload Validierung
"""

import secrets
import re
from functools import wraps
from flask import session, request, jsonify
import logging

logger = logging.getLogger(__name__)


class CSRFProtection:
    """CSRF-Schutz für Flask-Anwendungen"""
    
    @staticmethod
    def generate_token():
        """Generiert ein zufälliges CSRF-Token"""
        return secrets.token_hex(32)
    
    @staticmethod
    def get_token():
        """Holt oder erstellt ein CSRF-Token für die Session"""
        if 'csrf_token' not in session:
            session['csrf_token'] = CSRFProtection.generate_token()
        return session['csrf_token']
    
    @staticmethod
    def validate_token(token):
        """Validiert das CSRF-Token"""
        if not token:
            return False
        stored_token = session.get('csrf_token')
        if not stored_token:
            return False
        # Constant-time comparison um Timing-Attacken zu verhindern
        return secrets.compare_digest(token, stored_token)
    
    @staticmethod
    def protect(f):
        """Decorator für CSRF-Schutz bei POST/PUT/DELETE/PATCH Requests"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Nur für state-changing Methoden prüfen
            if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                # Token aus Header oder Form holen
                token = request.headers.get('X-CSRF-Token')
                if not token:
                    token = request.form.get('csrf_token')
                if not token:
                    token = request.get_json(silent=True).get('csrf_token') if request.is_json else None
                
                if not CSRFProtection.validate_token(token):
                    logger.warning(f"CSRF-Validierung fehlgeschlagen für {request.path} von {request.remote_addr}")
                    return jsonify({'error': 'CSRF-Token ungültig oder fehlt'}), 403
            
            return f(*args, **kwargs)
        return decorated_function


class InputSanitizer:
    """Input-Sanitization gegen XSS und andere Injection-Angriffe"""
    
    # Erlaubte HTML-Tags (strippen alles andere)
    ALLOWED_TAGS = {
        'b', 'i', 'u', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6'
    }
    
    # Muster für gefährliche Patterns
    DANGEROUS_PATTERNS = [
        r'<script\b[^>]*>.*?</script>',  # Script-Tags
        r'javascript:',  # JavaScript-Protokoll
        r'on\w+\s*=',  # Event-Handler (onclick, onload, etc.)
        r'<iframe\b[^>]*>',  # Iframes
        r'<object\b[^>]*>',  # Objects
        r'<embed\b[^>]*>',  # Embeds
        r'data:text/html',  # Data-URLs mit HTML
    ]
    
    @staticmethod
    def sanitize_html(text):
        """Entfernt gefährliches HTML und erlaubt nur sichere Tags"""
        if not text:
            return text
        
        # Erst alle HTML-Tags entfernen (einfachste und sicherste Methode)
        # Für ORDAMA ist das ausreichend, da wir kein rich-text editor haben
        sanitized = re.sub(r'<[^>]+>', '', text)
        
        # Zusätzlich gegen JavaScript-Protokolle prüfen
        sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @staticmethod
    def sanitize_text(text):
        """Sanitisiert einfachen Text (entfernt HTML komplett)"""
        if not text:
            return text
        return re.sub(r'<[^>]+>', '', text)
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitisiert Dateinamen gegen Path Traversal"""
        if not filename:
            return filename
        
        # Path-Traversal entfernen
        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        
        # Nur sichere Zeichen zulassen
        filename = re.sub(r'[^\w\s\-_.]', '', filename)
        
        # Doppelte Punkte und Leerzeichen entfernen
        filename = re.sub(r'\s+', '_', filename).strip()
        
        return filename
    
    @staticmethod
    def sanitize_search_query(query):
        """Sanitisiert Suchanfragen (für FTS)"""
        if not query:
            return query
        
        # Sonderzeichen escapen die für FTS gefährlich sein könnten
        # SQLite FTS5 verwendet doppelte Anführungszeichen für Phrasen
        query = query.replace('"', '\\"')
        
        return query
    
    @staticmethod
    def is_safe_text(text, max_length=10000):
        """Prüft ob Text sicher ist (Länge und Inhalt)"""
        if not text:
            return True
        
        if len(text) > max_length:
            return False
        
        # Auf gefährliche Patterns prüfen
        for pattern in InputSanitizer.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                return False
        
        return True


class FileUploadValidator:
    """Validierung für File-Uploads"""
    
    # Erlaubte Dateiendungen
    ALLOWED_EXTENSIONS = {
        # Bilder
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.ico',
        # Dokumente
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
        # Text
        '.txt', '.csv', '.rtf', '.md',
        # Archive
        '.zip', '.rar', '.7z', '.tar', '.gz',
        # Audio/Video
        '.mp3', '.mp4', '.avi', '.mov', '.wav', '.ogg', '.webm', '.flac'
    }
    
    # Gefährliche Dateiendungen (nie erlauben)
    BLOCKED_EXTENSIONS = {
        '.php', '.php3', '.php4', '.php5', '.phtml',
        '.asp', '.aspx', '.jsp', '.py', '.pl', '.cgi',
        '.sh', '.bat', '.cmd', '.exe', '.msi', '.dll',
        '.vbs', '.js', '.jar', '.app', '.deb', '.rpm'
    }
    
    # Erlaubte MIME-Types (Grundlegende Whitelist)
    ALLOWED_MIME_TYPES = {
        'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 'image/tiff',
        'application/pdf',
        'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain', 'text/csv', 'text/rtf', 'text/markdown',
        'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed',
        'application/gzip', 'application/x-tar',
        'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/flac',
        'video/mp4', 'video/avi', 'video/quicktime', 'video/webm', 'video/x-msvideo'
    }
    
    @staticmethod
    def is_allowed_extension(filename):
        """Prüft ob Dateiendung erlaubt ist"""
        if not filename:
            return False
        
        # Normalisieren
        ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        
        # Gefährliche Endungen blockieren
        if ext in FileUploadValidator.BLOCKED_EXTENSIONS:
            logger.warning(f"Blockierte Dateiendung erkannt: {ext}")
            return False
        
        # Erlaubte Endungen prüfen
        return ext in FileUploadValidator.ALLOWED_EXTENSIONS
    
    @staticmethod
    def is_allowed_mime_type(mime_type):
        """Prüft ob MIME-Type erlaubt ist"""
        if not mime_type:
            return False
        return mime_type in FileUploadValidator.ALLOWED_MIME_TYPES
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitisiert Dateinamen"""
        return InputSanitizer.sanitize_filename(filename)
    
    @staticmethod
    def validate_upload(filename, mime_type=None, file_size=None, max_size_mb=50):
        """Validiert einen kompletten File-Upload"""
        errors = []
        
        # Dateiname prüfen
        if not filename:
            errors.append('Kein Dateiname angegeben')
        else:
            sanitized = FileUploadValidator.sanitize_filename(filename)
            if sanitized != filename:
                errors.append('Dateiname enthält ungültige Zeichen')
            
            if not FileUploadValidator.is_allowed_extension(filename):
                errors.append(f'Dateiendung nicht erlaubt: {filename}')
        
        # MIME-Type prüfen
        if mime_type and not FileUploadValidator.is_allowed_mime_type(mime_type):
            errors.append(f'MIME-Type nicht erlaubt: {mime_type}')
        
        # Dateigröße prüfen
        if file_size is not None:
            max_bytes = max_size_mb * 1024 * 1024
            if file_size > max_bytes:
                errors.append(f'Datei zu groß (max {max_size_mb}MB)')
        
        return len(errors) == 0, errors
