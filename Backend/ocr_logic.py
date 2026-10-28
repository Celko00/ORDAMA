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

OCR-Logik für ORDAMA
- asynchrone Verarbeitung per Hintergrund-Thread
- Queue in SQLite
- Tesseract via subprocess
- PDF-Rendering via pypdfium2 (optional)
"""

import logging
import os
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, time as dt_time
from pathlib import Path

# Konstanten für OCR-Konfiguration
OCR_ERROR_MESSAGE_MAX_LENGTH = 1000
OCR_TIMEOUT_SECONDS = 300

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - optional
    Image = None
    ImageOps = None

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - optional
    pdfium = None

try:
    from image_preprocessing import ImagePreprocessor
except ImportError:  # pragma: no cover - optional
    ImagePreprocessor = None

logger = logging.getLogger(__name__)


class OCRManager:
    BILD_ENDUNGEN = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
    PDF_ENDUNGEN = {'.pdf'}
    TEXT_ENDUNGEN = {
        '.txt', '.md', '.markdown', '.rtf', '.csv', '.json', '.xml', '.html', '.htm', '.log'
    }

    def __init__(self, base_dir, config, db_manager):
        self.base_dir = Path(base_dir)
        self.config = config
        self.db_manager = db_manager
        self.stop_event = threading.Event()
        self.worker_thread = None

        ocr_config = config.get('ocr', {})
        self.enabled = ocr_config.get('enabled', True)
        self.default_lang = ocr_config.get('lang', 'deu+eng')
        self.poll_interval = float(ocr_config.get('poll_interval_seconds', 2.5))
        self.render_scale = float(ocr_config.get('render_scale', 2.0))
        # Throttling-Einstellungen
        self.page_delay = float(ocr_config.get('page_delay_seconds', 0.5))  # Wartezeit zwischen PDF-Seiten
        self.job_delay = float(ocr_config.get('job_delay_seconds', 1.0))    # Wartezeit zwischen Jobs
        # Zeitplan-Einstellungen
        self.schedule_mode = ocr_config.get('schedule_mode', 'always')  # 'always' oder 'scheduled'
        self.schedule_start = ocr_config.get('schedule_start', '20:00')  # Format: 'HH:MM'
        self.schedule_end = ocr_config.get('schedule_end', '06:00')      # Format: 'HH:MM'
        
        # Bildvorverarbeitung initialisieren
        preprocessing_config = ocr_config.get('preprocessing', {})
        if ImagePreprocessor:
            self.image_preprocessor = ImagePreprocessor(preprocessing_config)
        else:
            self.image_preprocessor = None
            logger.warning("Bildvorverarbeitung nicht verfügbar (image_preprocessing Modul nicht gefunden)")
        
        # Zuerst versuchen, lokale Tesseract-Installation im Projekt zu finden
        # (Windows oft "Tesseract", Offline-Skript/Linux: "tesseract")
        local_tesseract_dir = None
        for candidate in (self.base_dir / "Tesseract", self.base_dir / "tesseract"):
            if candidate.exists():
                local_tesseract_dir = candidate
                break
        found_tesseract = False
        
        if local_tesseract_dir:
            # Plattform-spezifischen Unterordner auswählen
            if os.name == 'nt':  # Windows
                platform_dir = local_tesseract_dir / "windows"
                exe_name = "tesseract.exe"
            else:  # Linux/macOS
                platform_dir = local_tesseract_dir / "linux"
                exe_name = "tesseract"
                
            logger.info(f"Suche nach lokaler Tesseract-Installation in: {platform_dir}")
            
            if platform_dir.exists():
                local_tesseract_exe = platform_dir / exe_name
                
                if local_tesseract_exe.exists():
                    # Make sure Linux tesseract is executable
                    if os.name != 'nt':
                        try:
                            local_tesseract_exe.chmod(local_tesseract_exe.stat().st_mode | 0o755)
                        except Exception as e:
                            logger.warning(f"Could not set executable permission on {local_tesseract_exe}: {e}")
                    self.tesseract_cmd = str(local_tesseract_exe)
                    found_tesseract = True
                    logger.info(f"Lokale Tesseract-Installation gefunden: {self.tesseract_cmd}")
                    
                    # Tessdata-Verzeichnis setzen: Entweder im Plattform-Ordner oder im Hauptordner
                    local_tessdata = platform_dir / "tessdata"
                    if not local_tessdata.exists():
                        local_tessdata = local_tesseract_dir / "tessdata"
                    
                    if local_tessdata.exists():
                        self.tessdata_dir = str(local_tessdata)
                        logger.info(f"Lokales tessdata-Verzeichnis gefunden: {self.tessdata_dir}")
        
        if not found_tesseract:
            # Versuchen, System-Tesseract zu finden
            self.tesseract_cmd = ocr_config.get('tesseract_cmd', 'tesseract')
            self.tessdata_dir = ocr_config.get('tessdata_dir')
            
            # Auf Windows nach gängigen Installationspfaden suchen
            if os.name == 'nt':
                common_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
                ]
                for path in common_paths:
                    if Path(path).exists():
                        self.tesseract_cmd = path
                        found_tesseract = True
                        logger.info(f"System-Tesseract-Installation gefunden: {self.tesseract_cmd}")
                        # Versuche, tessdata im gleichen Ordner zu finden
                        possible_tessdata = Path(path).parent / "tessdata"
                        if possible_tessdata.exists():
                            self.tessdata_dir = str(possible_tessdata)
                            logger.info(f"System-tessdata-Verzeichnis gefunden: {self.tessdata_dir}")
                        break
        
        logger.info(f"Verwende Tesseract: {self.tesseract_cmd}")
        if self.tessdata_dir:
            logger.info(f"Verwende tessdata: {self.tessdata_dir}")

    def reload_config(self, new_config: dict):
        """
        Lädt die OCR-Konfiguration neu während des Betriebs
        
        Args:
            new_config: Neue Konfiguration aus settings.json
        """
        ocr_config = new_config.get('ocr', {})
        
        # OCR-Parameter aktualisieren
        self.enabled = ocr_config.get('enabled', True)
        self.default_lang = ocr_config.get('lang', 'deu+eng')
        self.poll_interval = float(ocr_config.get('poll_interval_seconds', 2.5))
        self.render_scale = float(ocr_config.get('render_scale', 2.0))
        self.page_delay = float(ocr_config.get('page_delay_seconds', 0.5))
        self.job_delay = float(ocr_config.get('job_delay_seconds', 1.0))
        self.schedule_mode = ocr_config.get('schedule_mode', 'always')
        self.schedule_start = ocr_config.get('schedule_start', '20:00')
        self.schedule_end = ocr_config.get('schedule_end', '06:00')
        
        # Bildvorverarbeitung neu initialisieren
        preprocessing_config = ocr_config.get('preprocessing', {})
        if ImagePreprocessor:
            self.image_preprocessor = ImagePreprocessor(preprocessing_config)
        
        logger.info(f"OCR-Konfiguration neu geladen: enabled={self.enabled}, lang={self.default_lang}, oem={ocr_config.get('oem', '3')}, psm={ocr_config.get('psm', '6')}")

    def _is_scheduled_time(self):
        """Prüft, ob die aktuelle Uhrzeit im erlaubten Zeitfenster liegt"""
        if self.schedule_mode == 'always':
            return True
        
        try:
            now = datetime.now().time()
            start_time = dt_time.fromisoformat(self.schedule_start)
            end_time = dt_time.fromisoformat(self.schedule_end)
            
            # Wenn Endzeit vor Startzeit (z.B. 20:00 bis 06:00), liegt das Zeitfenster über Mitternacht
            if end_time < start_time:
                # Aktuelle Zeit ist im Fenster, wenn sie >= Startzeit ODER <= Endzeit
                return now >= start_time or now <= end_time
            else:
                # Normales Zeitfenster (z.B. 08:00 bis 18:00)
                return start_time <= now <= end_time
        except Exception as e:
            logger.warning(f"Fehler beim Prüfen des OCR-Zeitplans: {e}")
            return True  # Bei Fehlern immer erlauben

    def start(self):
        """Startet den OCR-Worker"""
        if not self.enabled:
            logger.info("OCR ist deaktiviert.")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self._recover_interrupted_jobs()

        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name='ordama-ocr-worker',
            daemon=True
        )
        self.worker_thread.start()

        # Check if local tesseract exists and is executable, otherwise check shutil.which
        local_path = Path(self.tesseract_cmd)
        if (local_path.is_file() and os.access(local_path, os.X_OK)) or shutil.which(self.tesseract_cmd):
            logger.info("OCR-Worker gestartet.")
        else:
            logger.warning(
                "OCR-Worker gestartet, aber Tesseract wurde nicht gefunden. "
                "OCR-Jobs landen bis zur Installation im Fehlerstatus."
            )

        try:
            queued_count = self.enqueue_missing_attachments()
            if queued_count:
                logger.info("OCR-Backfill gestartet: %s bestehende Anhänge vorgemerkt.", queued_count)
        except Exception as e:
            logger.warning(f"OCR-Backfill konnte nicht gestartet werden: {e}")

    def stop(self, timeout=5):
        """Beendet den OCR-Worker sauber"""
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=timeout)

    def ist_datei_ocr_faehig(self, filename, mime_type=None):
        suffix = Path(filename).suffix.lower()
        if suffix in self.PDF_ENDUNGEN or suffix in self.BILD_ENDUNGEN or suffix in self.TEXT_ENDUNGEN:
            return True
        if mime_type:
            return (
                mime_type.startswith('image/') 
                or mime_type == 'application/pdf' 
                or mime_type.startswith('text/')
            )
        return False

    def enqueue_attachment(self, attachment_id, force=False):
        """Legt einen OCR-Job für einen vorhandenen Anhang an"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.id, a.record_id, a.filename, a.mime_type, r.number
                FROM attachments a
                JOIN records r ON r.id = a.record_id
                WHERE a.id = ?
            ''', (attachment_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Anhang für OCR nicht gefunden")

            if not self.ist_datei_ocr_faehig(row['filename'], row['mime_type']):
                cursor.execute('''
                    INSERT INTO attachment_ocr (
                        attachment_id, record_id, language, status, progress,
                        pages_done, pages_total, error_message, updated_at
                    ) VALUES (?, ?, ?, 'disabled', 0, 0, 0, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(attachment_id) DO UPDATE SET
                        record_id=excluded.record_id,
                        language=excluded.language,
                        status='disabled',
                        progress=0,
                        pages_done=0,
                        pages_total=0,
                        error_message=excluded.error_message,
                        updated_at=CURRENT_TIMESTAMP
                ''', (
                    row['id'],
                    row['record_id'],
                    self.default_lang,
                    'OCR für diesen Dateityp deaktiviert'
                ))
                conn.commit()
                return {'queued': False, 'status': 'disabled'}

            if not force:
                cursor.execute('''
                    SELECT 1
                    FROM ocr_jobs
                    WHERE attachment_id = ? AND status IN ('pending', 'running')
                    LIMIT 1
                ''', (attachment_id,))
                if cursor.fetchone():
                    return {'queued': False, 'status': 'already_pending'}

            cursor.execute('''
                INSERT INTO attachment_ocr (
                    attachment_id, record_id, language, status, progress,
                    pages_done, pages_total, error_message, updated_at
                ) VALUES (?, ?, ?, 'pending', 0, 0, 0, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(attachment_id) DO UPDATE SET
                    record_id=excluded.record_id,
                    language=excluded.language,
                    status='pending',
                    progress=0,
                    pages_done=0,
                    pages_total=0,
                    error_message=NULL,
                    updated_at=CURRENT_TIMESTAMP
            ''', (row['id'], row['record_id'], self.default_lang))

            if force:
                cursor.execute('''
                    UPDATE ocr_jobs
                    SET status = 'error',
                        finished_at = CURRENT_TIMESTAMP,
                        error_message = COALESCE(error_message, 'Durch Neuverarbeitung ersetzt')
                    WHERE attachment_id = ? AND status IN ('pending', 'running')
                ''', (attachment_id,))

            cursor.execute('''
                INSERT INTO ocr_jobs (
                    attachment_id, record_id, filename, status, created_at
                ) VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP)
            ''', (row['id'], row['record_id'], row['filename']))
            conn.commit()

            return {'queued': True, 'status': 'pending'}

    def enqueue_attachment_by_record_and_filename(self, record_id, filename, force=False):
        """Queue-Helfer auf Basis von Akten-ID und Dateiname"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id
                FROM attachments
                WHERE record_id = ? AND filename = ?
                LIMIT 1
            ''', (record_id, filename))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Anhang nicht gefunden")
        return self.enqueue_attachment(row['id'], force=force)

    def enqueue_missing_attachments(self):
        """
        Legt OCR-Jobs für bestehende, OCR-fähige Anhänge an,
        die noch keinen validen OCR-Status haben.
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.id, a.filename, a.mime_type
                FROM attachments a
                LEFT JOIN attachment_ocr o ON o.attachment_id = a.id
                WHERE o.attachment_id IS NULL
                   OR (
                        COALESCE(o.status, '') = ''
                        AND COALESCE(TRIM(o.ocr_text), '') = ''
                      )
                ORDER BY a.id ASC
            ''')
            rows = cursor.fetchall()

        queued_count = 0
        for row in rows:
            if not self.ist_datei_ocr_faehig(row['filename'], row['mime_type']):
                continue
            try:
                result = self.enqueue_attachment(row['id'])
                if result.get('queued'):
                    queued_count += 1
            except Exception as e:
                logger.warning(f"OCR-Backfill für Anhang {row['id']} fehlgeschlagen: {e}")

        return queued_count

    def _worker_loop(self):
        while not self.stop_event.is_set():
            try:
                # Prüfe, ob OCR aktuell gemäß Zeitplan laufen darf
                if not self._is_scheduled_time():
                    self.stop_event.wait(self.poll_interval)
                    continue
                
                job = self._claim_next_job()
                if not job:
                    self.stop_event.wait(self.poll_interval)
                    continue
                self._process_job(job)
                
                # Warte zwischen Jobs, um System zu schonen
                if self.job_delay > 0:
                    self.stop_event.wait(self.job_delay)
            except Exception as e:  # pragma: no cover - Worker soll nie komplett sterben
                logger.exception(f"OCR-Worker Fehler: {e}")
                self.stop_event.wait(self.poll_interval)

    def _claim_next_job(self):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, attachment_id, record_id, filename
                FROM ocr_jobs
                WHERE status = 'pending'
                ORDER BY priority DESC, id ASC
                LIMIT 1
            ''')
            job = cursor.fetchone()
            if not job:
                return None

            cursor.execute('''
                UPDATE ocr_jobs
                SET status = 'running',
                    started_at = CURRENT_TIMESTAMP,
                    error_message = NULL
                WHERE id = ? AND status = 'pending'
            ''', (job['id'],))
            if cursor.rowcount != 1:
                conn.commit()
                return None

            cursor.execute('''
                INSERT INTO attachment_ocr (
                    attachment_id, record_id, language, status, progress,
                    pages_done, pages_total, error_message, updated_at
                ) VALUES (?, ?, ?, 'running', 0, 0, 0, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(attachment_id) DO UPDATE SET
                    record_id=excluded.record_id,
                    language=excluded.language,
                    status='running',
                    progress=0,
                    pages_done=0,
                    pages_total=0,
                    error_message=NULL,
                    updated_at=CURRENT_TIMESTAMP
            ''', (job['attachment_id'], job['record_id'], self.default_lang))
            conn.commit()
            return dict(job)

    def _process_job(self, job):
        attachment = self._get_attachment_info(job['attachment_id'])
        if not attachment:
            self._finish_job_error(job['id'], job['attachment_id'], 'Anhang existiert nicht mehr')
            return

        file_path = Path(attachment['path'])
        if not file_path.exists():
            self._finish_job_error(job['id'], job['attachment_id'], 'Datei existiert nicht mehr')
            return

        try:
            extracted = self._extract_text(file_path, job['attachment_id'])
            if isinstance(extracted, dict):
                text = extracted.get('text', '')
                page_map_json = self._normalize_page_map(extracted.get('page_map'))
            else:
                text = extracted
                page_map_json = None

            normalized_text = self._normalize_text(text)
            has_text = 1 if normalized_text else 0

            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE attachment_ocr
                    SET status = 'done',
                        progress = 1,
                        ocr_text = ?,
                        ocr_page_map = ?,
                        has_text = ?,
                        error_message = NULL,
                        failure_count = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE attachment_id = ?
                ''', (normalized_text, page_map_json, has_text, job['attachment_id']))
                cursor.execute('''
                    UPDATE ocr_jobs
                    SET status = 'done',
                        finished_at = CURRENT_TIMESTAMP,
                        error_message = NULL
                    WHERE id = ?
                ''', (job['id'],))
                conn.commit()
        except Exception as e:
            self._finish_job_error(job['id'], job['attachment_id'], str(e))

    def _recover_interrupted_jobs(self):
        """
        Setzt beim Start hängengebliebene Jobs zurück.
        Das verhindert den Zustand:
        - ocr_jobs.status = running
        - attachment_ocr.status = pending
        z. B. nach Prozessabbruch zwischen Claim und Verarbeitung.
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT attachment_id
                FROM ocr_jobs
                WHERE status = 'running'
            ''')
            attachment_ids = [row['attachment_id'] for row in cursor.fetchall()]
            if not attachment_ids:
                conn.commit()
                return

            placeholders = ','.join(['?'] * len(attachment_ids))

            cursor.execute('''
                UPDATE ocr_jobs
                SET status = 'pending',
                    started_at = NULL,
                    finished_at = NULL,
                    error_message = NULL
                WHERE status = 'running'
            ''')
            recovered_jobs = cursor.rowcount

            cursor.execute(f'''
                UPDATE attachment_ocr
                SET status = 'pending',
                    progress = 0,
                    pages_done = 0,
                    pages_total = 0,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE attachment_id IN ({placeholders})
                  AND status != 'done'
            ''', attachment_ids)
            recovered_status_rows = cursor.rowcount
            conn.commit()

        logger.info(
            "OCR-Wiederherstellung abgeschlossen: %s Jobs, %s Statuszeilen zurückgesetzt.",
            recovered_jobs,
            recovered_status_rows
        )

    def _set_ocr_running(self, attachment_id, record_id):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO attachment_ocr (
                    attachment_id, record_id, language, status, progress,
                    pages_done, pages_total, error_message, updated_at
                ) VALUES (?, ?, ?, 'running', 0, 0, 0, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(attachment_id) DO UPDATE SET
                    record_id=excluded.record_id,
                    language=excluded.language,
                    status='running',
                    progress=0,
                    pages_done=0,
                    pages_total=0,
                    error_message=NULL,
                    updated_at=CURRENT_TIMESTAMP
            ''', (attachment_id, record_id, self.default_lang))
            conn.commit()

    def _update_progress(self, attachment_id, pages_done, pages_total):
        progress = (pages_done / pages_total) if pages_total else 0
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE attachment_ocr
                SET status = 'running',
                    pages_done = ?,
                    pages_total = ?,
                    progress = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ?
            ''', (pages_done, pages_total, progress, attachment_id))
            conn.commit()

    def _finish_job_error(self, job_id, attachment_id, error_message):
        message = (error_message or 'Unbekannter OCR-Fehler').strip()
        logger.warning(f"OCR-Job fehlgeschlagen (Job {job_id}, Anhang {attachment_id}): {message}")
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE attachment_ocr
                SET status = 'error',
                    progress = 0,
                    error_message = ?,
                    failure_count = COALESCE(failure_count, 0) + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ?
            ''', (message[:OCR_ERROR_MESSAGE_MAX_LENGTH], attachment_id))
            cursor.execute('''
                UPDATE ocr_jobs
                SET status = 'error',
                    finished_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
            ''', (message[:OCR_ERROR_MESSAGE_MAX_LENGTH], job_id))
            conn.commit()

    def _extract_text(self, file_path, attachment_id):
        suffix = file_path.suffix.lower()
        if suffix in self.TEXT_ENDUNGEN:
            return self._extract_text_file(file_path, attachment_id)
        if suffix in self.PDF_ENDUNGEN:
            return self._extract_pdf_text(file_path, attachment_id)
        if suffix in self.BILD_ENDUNGEN:
            return self._extract_image_text(file_path, attachment_id)
        raise RuntimeError("Dateityp wird für OCR nicht unterstützt")
        
    def _extract_text_file(self, file_path, attachment_id):
        """Extrahiert Text direkt aus einer Textdatei"""
        self._update_progress(attachment_id, 0, 1)
        
        # Versuche verschiedene Kodierungen zu lesen
        text = ""
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    text = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        self._update_progress(attachment_id, 1, 1)
        
        return {
            'text': text,
            'page_map': [{'page': 1, 'text': text}]
        }

    def _extract_image_text(self, file_path, attachment_id):
        if Image is None:
            raise RuntimeError("Pillow ist nicht installiert")

        self._update_progress(attachment_id, 0, 1)
        with Image.open(file_path) as img:
            text = self._ocr_pil_image(img)
        self._update_progress(attachment_id, 1, 1)
        return {
            'text': text,
            'page_map': [{'page': 1, 'text': text}]
        }

    def _extract_pdf_text(self, file_path, attachment_id):
        if pdfium is None:
            raise RuntimeError("pypdfium2 ist nicht installiert")
        if Image is None:
            raise RuntimeError("Pillow ist nicht installiert")

        doc = pdfium.PdfDocument(str(file_path))
        pages_total = len(doc)
        texts = []
        page_map = []
        self._update_progress(attachment_id, 0, max(pages_total, 1))

        for index in range(pages_total):
            # Prüfe, ob der Worker gestoppt wurde
            if self.stop_event.is_set():
                break
                
            page = doc[index]
            bitmap = None
            try:
                bitmap = page.render(scale=self.render_scale)
                pil_image = bitmap.to_pil()
                page_text = self._ocr_pil_image(pil_image)
                if page_text.strip():
                    texts.append(page_text.strip())
                    page_map.append({
                        'page': index + 1,
                        'text': page_text
                    })
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    bitmap.close()
                except Exception:
                    pass

            self._update_progress(attachment_id, index + 1, pages_total)
            
            # Warte zwischen Seiten, um System zu schonen (außer bei letztem Seiten)
            if index < pages_total - 1 and self.page_delay > 0:
                self.stop_event.wait(self.page_delay)

        try:
            doc.close()
        except Exception:
            pass
        return {
            'text': '\n\n'.join(texts),
            'page_map': page_map
        }

    def _ocr_pil_image(self, image):
        self._ensure_tesseract_available()
        if ImageOps is None:
            raise RuntimeError("Pillow ist nicht vollständig verfügbar")

        prepared = image.convert('L')
        
        # Bildvorverarbeitung anwenden, wenn verfügbar
        if self.image_preprocessor:
            prepared = self.image_preprocessor.preprocess_image(prepared)
        else:
            # Fallback: ursprüngliche einfache Vorverarbeitung
            prepared = ImageOps.autocontrast(prepared)

        width, height = prepared.size
        if min(width, height) < 1400:
            scale = max(1.0, 1400 / max(1, min(width, height)))
            prepared = prepared.resize(
                (int(width * scale), int(height * scale)),
                Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp_path = Path(tmp.name)
        try:
            prepared.save(tmp_path, format='PNG')
            
            # OCR-Parameter aus Konfiguration oder Standardwerte
            oem = self.config.get('ocr', {}).get('oem', '3')  # 3 = Legacy + LSTM (bessere Kompatibilität)
            psm = self.config.get('ocr', {}).get('psm', '6')  # 6 = Single uniform block (besser für gescannte Dokumente)
            dpi = self.config.get('ocr', {}).get('dpi', 300)
            
            command = [
                self.tesseract_cmd,
                str(tmp_path),
                'stdout',
                '-l', self.default_lang,
                '--oem', str(oem),
                '--psm', str(psm),
                '--dpi', str(dpi)
            ]
            env = self._build_tesseract_env()
            # Prüfe, ob wir eine portable Linux-Tesseract-Installation haben mit lib-Ordner
            if os.name != 'nt':  # Nicht Windows
                tesseract_path = Path(self.tesseract_cmd)
                if tesseract_path.parent.name == 'linux':
                    lib_dir = tesseract_path.parent / 'lib'
                    if lib_dir.exists():
                        if "LD_LIBRARY_PATH" in env:
                            env["LD_LIBRARY_PATH"] = f"{str(lib_dir)}:{env['LD_LIBRARY_PATH']}"
                        else:
                            env["LD_LIBRARY_PATH"] = str(lib_dir)
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                timeout=OCR_TIMEOUT_SECONDS,
                check=False
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or '').strip()
                raise RuntimeError(stderr or 'Tesseract konnte den Text nicht erkennen')
            return completed.stdout or ''
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _ensure_tesseract_available(self):
        # First check if it's a local executable file (not just in PATH)
        local_path = Path(self.tesseract_cmd)
        if local_path.is_file() and os.access(local_path, os.X_OK):
            return True
        if not shutil.which(self.tesseract_cmd):
            raise RuntimeError(
                "Tesseract ist nicht installiert oder nicht im PATH. "
                "Bitte Tesseract auf dem Server installieren."
            )

    def _build_tesseract_env(self):
        env = os.environ.copy()
        tessdata_dir = self._resolve_tessdata_dir()
        if tessdata_dir:
            env['TESSDATA_PREFIX'] = str(tessdata_dir)
        return env

    def _resolve_tessdata_dir(self):
        candidates = []

        if self.tessdata_dir:
            candidates.append(Path(self.tessdata_dir))

        # First check if self.tesseract_cmd is a local file path
        local_tesseract = Path(self.tesseract_cmd)
        if local_tesseract.exists():
            resolved = local_tesseract
        else:
            # Otherwise try to find via shutil.which
            tesseract_path = shutil.which(self.tesseract_cmd) or self.tesseract_cmd
            resolved = Path(tesseract_path)
        
        if resolved:
            if resolved.suffix.lower() == '.cmd':
                candidates.append((resolved.parent / '..' / 'app' / 'tesseract' / 'tessdata').resolve())
                candidates.append((resolved.parent / '..' / 'app' / 'tesseract').resolve())
            candidates.append((resolved.parent / 'tessdata').resolve())
            candidates.append(resolved.parent.resolve())

        for candidate in candidates:
            try:
                if candidate.exists():
                    if (candidate / 'configs').exists() or list(candidate.glob('*.traineddata')):
                        return candidate
            except Exception:
                continue
        return None

    def _get_attachment_info(self, attachment_id):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    a.id,
                    a.record_id,
                    a.filename,
                    a.mime_type,
                    r.number
                FROM attachments a
                JOIN records r ON r.id = a.record_id
                WHERE a.id = ?
            ''', (attachment_id,))
            row = cursor.fetchone()
            if not row:
                return None

            akten_dir = Path(self.config['paths'].get('data_base_dir', './Speicher'))
            if not akten_dir.is_absolute():
                akten_dir = self.base_dir / akten_dir
            file_path = akten_dir / 'Akten' / row['number'] / row['filename']
            result = dict(row)
            result['path'] = str(file_path)
            return result

    def _normalize_text(self, text):
        text = (text or '').replace('\x0c', ' ')
        text = re.sub(r'\r\n?', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _normalize_page_map(self, page_map):
        normalized_map = []
        for entry in page_map or []:
            try:
                page_number = int(entry.get('page', 0))
            except Exception:
                continue
            normalized_text = self._normalize_text(entry.get('text', ''))
            if page_number <= 0 or not normalized_text:
                continue
            normalized_map.append({
                'page': page_number,
                'text': normalized_text
            })
        # Immer ein leeres Array zurückgeben, wenn keine Einträge vorhanden sind
        # statt None, damit das Frontend weiß, dass ein page_map existiert
        return json.dumps(normalized_map, ensure_ascii=False)
