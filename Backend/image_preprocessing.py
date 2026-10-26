"""
Bildvorverarbeitungs-Modul für OCR-Optimierung
- Rauschentfernung
- Schärfung
- Binarisierung
- De-skewing
- Kontrastverbesserung
"""

import logging
from typing import Optional, Tuple

try:
    from PIL import Image, ImageFilter, ImageEnhance
    import numpy as np
    import cv2
except ImportError:
    Image = None
    ImageFilter = None
    ImageEnhance = None
    np = None
    cv2 = None

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """Klasse für Bildvorverarbeitung zur OCR-Optimierung"""
    
    def __init__(self, config: dict = None):
        """
        Initialisiert den Bildvorprozessor
        
        Args:
            config: Konfigurationsdictionary mit Einstellungen
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        
        # Vorverarbeitungs-Einstellungen
        self.denoise = self.config.get('denoise', True)
        self.sharpen = self.config.get('sharpen', True)
        self.binarize = self.config.get('binarize', False)  # Standardmäßig aus, kann bei Bedarf aktiviert werden
        self.deskew = self.config.get('deskew', True)
        self.contrast_enhance = self.config.get('contrast_enhance', True)
        
        # Parameter
        self.denoise_strength = self.config.get('denoise_strength', 3)
        self.sharpen_strength = self.config.get('sharpen_strength', 2.0)
        self.binarize_threshold = self.config.get('binarize_threshold', 127)
        self.contrast_factor = self.config.get('contrast_factor', 1.5)
        
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Wendet alle Vorverarbeitungsschritte auf ein Bild an
        
        Args:
            image: PIL Image Objekt
            
        Returns:
            Verarbeitetes PIL Image Objekt
        """
        if not self.enabled or Image is None:
            return image
            
        try:
            # 1. Kontrastverbesserung
            if self.contrast_enhance:
                image = self._enhance_contrast(image)
            
            # 2. Rauschentfernung
            if self.denoise:
                image = self._denoise(image)
            
            # 3. Schärfung
            if self.sharpen:
                image = self._sharpen(image)
            
            # 4. De-skewing (Bild gerade richten)
            if self.deskew:
                image = self._deskew(image)
            
            # 5. Binarisierung (optional)
            if self.binarize:
                image = self._binarize(image)
            
            return image
        except Exception as e:
            logger.debug(f"Bildvorverarbeitung fehlgeschlagen: {e}")
            return image
    
    def _enhance_contrast(self, image: Image.Image) -> Image.Image:
        """Verbessert den Kontrast des Bildes"""
        try:
            enhancer = ImageEnhance.Contrast(image)
            return enhancer.enhance(self.contrast_factor)
        except Exception as e:
            logger.debug(f"Kontrastverbesserung fehlgeschlagen: {e}")
            return image
    
    def _denoise(self, image: Image.Image) -> Image.Image:
        """
        Entfernt Rauschen aus dem Bild
        Verwendet Median-Filter für effektive Rauschentfernung
        """
        try:
            # Median-Filter ist gut für Rauschentfernung bei OCR
            return image.filter(ImageFilter.MedianFilter(size=self.denoise_strength))
        except Exception as e:
            logger.debug(f"Rauschentfernung fehlgeschlagen: {e}")
            return image
    
    def _sharpen(self, image: Image.Image) -> Image.Image:
        """
        Schärft das Bild für bessere Texterkennung
        Verwendet Unsharp Mask für kontrollierte Schärfung
        """
        try:
            # Unsharp Mask für bessere Ergebnisse als einfacher Sharpen-Filter
            return image.filter(ImageFilter.UnsharpMask(
                radius=2,
                percent=self.sharpen_strength * 100,
                threshold=3
            ))
        except Exception as e:
            logger.debug(f"Schärfung fehlgeschlagen: {e}")
            return image
    
    def _binarize(self, image: Image.Image) -> Image.Image:
        """
        Konvertiert das Bild in Schwarz-Weiß (Binarisierung)
        Verwendet adaptiven Threshold für bessere Ergebnisse bei verschiedenen Lichtverhältnissen
        """
        try:
            if cv2 is not None and np is not None:
                # OpenCV-basierte adaptive Binarisierung (bessere Ergebnisse)
                img_array = np.array(image.convert('L'))
                if len(img_array.shape) == 2:
                    binary = cv2.adaptiveThreshold(
                        img_array,
                        255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        11,
                        2
                    )
                    return Image.fromarray(binary)
            else:
                # Fallback: einfache Binarisierung mit PIL
                image = image.convert('L')
                threshold = self.binarize_threshold
                image = image.point(lambda x: 0 if x < threshold else 255, '1')
                return image.convert('L')
        except Exception as e:
            logger.debug(f"Binarisierung fehlgeschlagen: {e}")
            return image
    
    def _deskew(self, image: Image.Image) -> Image.Image:
        """
        Richtet schräge Bilder gerade (De-skewing)
        Verwendet Hough-Transformation zur Erkennung der Textausrichtung
        """
        try:
            if cv2 is not None and np is not None:
                return self._deskew_opencv(image)
            else:
                return self._deskew_pil(image)
        except Exception as e:
            logger.debug(f"De-skewing fehlgeschlagen: {e}")
            return image
    
    def _deskew_opencv(self, image: Image.Image) -> Image.Image:
        """De-skewing mit OpenCV (genauer)"""
        try:
            # Konvertiere zu Graustufen
            img_array = np.array(image.convert('L'))
            
            # Binarisierung
            _, binary = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Finde Konturen
            coords = np.column_stack(np.where(binary > 0))
            if len(coords) == 0:
                return image
            
            # Berechne minimal umschreibendes Rechteck
            angle = cv2.minAreaRect(coords)[-1]
            
            # Korrigiere Winkel
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            
            # Nur bei signifikantem Winkel korrigieren (> 0.5 Grad)
            if abs(angle) < 0.5:
                return image
            
            # Rotiere Bild
            (h, w) = img_array.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(img_array, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            
            return Image.fromarray(rotated)
        except Exception as e:
            logger.debug(f"OpenCV De-skewing fehlgeschlagen: {e}")
            return image
    
    def _deskew_pil(self, image: Image.Image) -> Image.Image:
        """De-skewing mit PIL (einfacher, aber weniger genau)"""
        try:
            # Einfache Heuristik: Versuche verschiedene Winkel und wähle den besten
            # Dies ist eine vereinfachte Version ohne echte Textzeilenerkennung
            return image  # Placeholder - könnte erweitert werden
        except Exception as e:
            logger.debug(f"PIL De-skewing fehlgeschlagen: {e}")
            return image
    
    def resize_for_ocr(self, image: Image.Image, min_dimension: int = 1400) -> Image.Image:
        """
        Skaliert das Bild auf eine optimale Größe für OCR
        Tesseract arbeitet am besten mit Bildern ab ~1400px in der kleineren Dimension
        
        Args:
            image: PIL Image Objekt
            min_dimension: Minimale Dimension (Breite oder Höhe)
            
        Returns:
            Skaliertes PIL Image Objekt
        """
        try:
            width, height = image.size
            if min(width, height) < min_dimension:
                scale = max(1.0, min_dimension / max(1, min(width, height)))
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                resampling = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
                return image.resize((new_width, new_height), resampling)
            return image
        except Exception as e:
            logger.debug(f"Resizing fehlgeschlagen: {e}")
            return image
    
    def convert_to_grayscale(self, image: Image.Image) -> Image.Image:
        """Konvertiert Bild zu Graustufen"""
        try:
            return image.convert('L')
        except Exception as e:
            logger.debug(f"Graustufen-Konvertierung fehlgeschlagen: {e}")
            return image
    
    def auto_contrast(self, image: Image.Image) -> Image.Image:
        """Automatische Kontrastanpassung"""
        try:
            from PIL import ImageOps
            return ImageOps.autocontrast(image)
        except Exception as e:
            logger.debug(f"Auto-Kontrast fehlgeschlagen: {e}")
            return image


def create_preprocessor(config: dict = None) -> ImagePreprocessor:
    """
    Factory-Funktion zur Erstellung eines Bildvorprozessors
    
    Args:
        config: Konfigurationsdictionary
        
    Returns:
        ImagePreprocessor Instanz
    """
    return ImagePreprocessor(config)
