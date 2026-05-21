import sys
import os
from PIL import Image
import logging
import sys
import os
import logging
try:
    import pytesseract
except ImportError:
    pytesseract = None

def get_app_path() -> str:
    """Get the directory path of the executable (PyInstaller compatible)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def crop_image_by_percent(img: "Image.Image", top_percent: float, right_percent: float) -> "Image.Image":
    """Crops an area from the top-right corner of the image, based on percentages.

    Args:
        img: Pillow Image object.
        top_percent: The percentage to crop from the top (0-100).
        right_percent: The percentage to crop from the right (0-100).

    Returns:
        The cropped Image object.

    Raises:
        ValueError: If the percentage settings are invalid.
    """
    w, h = img.size
    width = int(w * (right_percent / 100))
    height = int(h * (top_percent / 100))
    left = w - width
    top = 0
    right = w
    bottom = height
    if width <= 0 or height <= 0 or left < 0 or bottom > h:
        raise ValueError("Invalid percentage settings")
    return img.crop((left, top, right, bottom))

def get_substat_display(stat_name, value):
    """
    Display string for substats.
    If '%' is in stat_name, display with '%', otherwise as is.
    """
    if "%" in stat_name:
        return f"{stat_name} : {value} %"
    else:
        return f"{stat_name} : {value}"

def setup_tesseract():
    """Set up and confirm the path for Tesseract OCR."""
    logger = logging.getLogger(__name__)
    if pytesseract is None:
        logger.warning("pytesseract is not installed. OCR functions will be unavailable.")
        return

    if sys.platform != 'win32':
        logger.info("Tesseract setup is configured for Windows. On other OS, it's assumed to be in PATH.")
        return

    # Prioritize checking the path for Tesseract bundled with PyInstaller
    bundled_tesseract = None
    bundled_tessdata = None
    
    if getattr(sys, 'frozen', False):
        # If running with PyInstaller
        base_path = sys._MEIPASS
        bundled_tesseract = os.path.join(base_path, 'tesseract', 'tesseract.exe')
        bundled_tessdata = os.path.join(base_path, 'tesseract', 'tessdata')
        logger.info(f"PyInstaller environment detected: base_path={base_path}")
        logger.info(f"Bundled Tesseract path: {bundled_tesseract}")
        logger.info(f"Bundled tessdata path: {bundled_tessdata}")
    
    # Search for Tesseract with priority
    possible_paths = [
        bundled_tesseract,  # Bundled Tesseract (highest priority)
        r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe',
        r'C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe',
    ]
    
    # Exclude None
    possible_paths = [p for p in possible_paths if p]
    
    tesseract_found = False
    for path in possible_paths:
        logger.info(f"Checking for Tesseract at: {path}")
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"[OK] Tesseract path set to: {path}")
            
            # Set TESSDATA_PREFIX environment variable
            if bundled_tesseract and path == bundled_tesseract:
                if bundled_tessdata and os.path.exists(bundled_tessdata):
                    os.environ['TESSDATA_PREFIX'] = bundled_tessdata + os.sep
                    logger.info(f"[OK] TESSDATA_PREFIX set to: {os.environ['TESSDATA_PREFIX']}")
                    # Log contents of tessdata for debugging
                    try:
                        tessdata_files = os.listdir(bundled_tessdata)
                        logger.info(f"[OK] Found {len(tessdata_files)} files in tessdata.")
                        important_files = ['eng.traineddata', 'jpn.traineddata', 'jpn_vert.traineddata']
                        for f in important_files:
                            if f in tessdata_files:
                                logger.info(f"  [OK] Found {f}")
                    except Exception as e:
                        logger.warning(f"Could not list tessdata contents: {e}")
                else:
                    logger.warning(f"Bundled tessdata not found at: {bundled_tessdata}")
            else:
                # For system-installed Tesseract
                tessdata_dir = os.path.join(os.path.dirname(path), 'tessdata')
                if os.path.exists(tessdata_dir):
                    os.environ['TESSDATA_PREFIX'] = tessdata_dir + os.sep
                    logger.info(f"[OK] TESSDATA_PREFIX set for system Tesseract: {os.environ['TESSDATA_PREFIX']}")
            
            tesseract_found = True
            break
    
    if not tesseract_found:
        logger.warning("[ERROR] Tesseract executable not found.")
        logger.warning("  Searched paths:")
        for p in possible_paths:
            logger.warning(f"    - {p}")

    # Check Tesseract version
    try:
        version = pytesseract.get_tesseract_version()
        logger.info(f"[OK] Tesseract version: {version}")
    except Exception as e:
        logger.warning(f"[ERROR] Could not get Tesseract version: {e}")
        logger.warning(f"   pytesseract.tesseract_cmd = {pytesseract.pytesseract.tesseract_cmd}")
        if 'TESSDATA_PREFIX' in os.environ:
            logger.warning(f"   TESSDATA_PREFIX = {os.environ['TESSDATA_PREFIX']}")
