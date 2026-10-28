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

Gunicorn Konfiguration für ORDAMA
- Für Produktion mit 100+ Nutzern optimiert
- Verwendet WSGI statt Flask Development Server
"""

import multiprocessing
import os

# Server Socket
bind = "127.0.0.1:8080"
backlog = 2048

# Worker Processes (Anzahl der CPU-Kerne + 1, aber mindestens 4)
workers = max(4, multiprocessing.cpu_count() + 1)

# Worker Type (gevent für bessere Concurrency bei I/O-lastigen Anwendungen)
worker_class = "sync"  # Für SQLite besser sync, da Gevent Probleme mit SQLite Locking haben kann

# Worker Connections (pro Worker)
worker_connections = 1000

# Timeout
timeout = 120
keepalive = 5

# Max Requests pro Worker (um Memory Leaks vorzubeugen)
max_requests = 10000
max_requests_jitter = 1000

# Process Naming
proc_name = "ordama"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# SSL (falls benötigt)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Environment Variables für ORDAMA
raw_env = [
    'ORDAMA_SECRET_KEY=' + os.environ.get('ORDAMA_SECRET_KEY', ''),
]

# Preload App (für bessere Performance, aber nicht mit SQLite Connection Pooling kompatibel)
preload_app = False

# Graceful Shutdown Timeout
graceful_timeout = 30

# Daemon Mode (für Produktion)
daemon = False
pidfile = "/tmp/ordama.pid"
