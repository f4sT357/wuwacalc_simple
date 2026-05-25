import json
import logging
import logging.handlers
import os
import sys
import webbrowser
from typing import Any, Optional, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QComboBox,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QCheckBox, QRadioButton, QGroupBox, QSplitter, QLineEdit, QFileDialog,
    QLabel
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPen

try:
    import importlib.util
    is_pil_installed = importlib.util.find_spec('PIL') is not None
except Exception:
    is_pil_installed = False

try:
    import pytesseract
    is_pytesseract_installed = True
except ImportError:
    is_pytesseract_installed = False

from config_manager import ConfigManager
from constants import (
    CHARACTER_MAIN_STATS,
    CHARACTER_STAT_WEIGHTS,
    MAIN_STAT_OPTIONS,
    SUBSTAT_MAX_VALUES,
    TAB_CONFIGS,
    get_char_internal_name,
    THEME_COLORS,
    LOG_FILENAME,
    CONFIG_FILENAME
)
from dialogs import CharSettingDialog, DisplaySettingsDialog
from ui_components import UIComponents
from languages import TRANSLATIONS
from utils import get_app_path, setup_tesseract

# Configure root logger for DEBUG with rotating file and console handlers
try:
    app_log_path = os.path.join(get_app_path(), LOG_FILENAME)
except Exception:
    app_log_path = LOG_FILENAME

if not logging.root.handlers:
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    try:
        rh = logging.handlers.RotatingFileHandler(app_log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
        rh.setFormatter(fmt)
        rh.setLevel(logging.DEBUG)
        logging.root.addHandler(rh)
    except Exception:
        # Fallback: if file handler cannot be created, continue with console only
        pass

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.DEBUG)
    logging.root.addHandler(ch)

    logging.root.setLevel(logging.DEBUG)

class CropOverlayLabel(QLabel):
    """QLabel that draws a crop-area overlay on top of the displayed pixmap.

    Call set_crop_overlay() with fractional coordinates (0.0-1.0 relative to
    the pixmap) to show the overlay. Call clear_overlay() to remove it.
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._crop_rect_f: Optional[tuple] = None  # (left_f, top_f, right_f, bottom_f)

    def set_crop_overlay(
        self, left_f: float, top_f: float, right_f: float, bottom_f: float
    ) -> None:
        """Show a crop-area overlay defined by fractions of the pixmap dimensions."""
        self._crop_rect_f = (left_f, top_f, right_f, bottom_f)
        self.update()

    def clear_overlay(self) -> None:
        """Remove the crop-area overlay."""
        self._crop_rect_f = None
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self._crop_rect_f is None:
            return
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return

        pw, ph = pm.width(), pm.height()
        lw, lh = self.width(), self.height()

        # Pixmap is drawn centred inside the label
        x_off = (lw - pw) // 2
        y_off = (lh - ph) // 2

        left_f, top_f, right_f, bottom_f = self._crop_rect_f
        cx = x_off + int(left_f * pw)
        cy = y_off + int(top_f * ph)
        cw = max(1, int((right_f - left_f) * pw))
        ch = max(1, int((bottom_f - top_f) * ph))
        crop_right = cx + cw
        crop_bottom = cy + ch

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # --- Semi-transparent dark mask over the non-crop areas ---
        mask_color = QColor(0, 0, 0, 130)
        painter.setBrush(mask_color)
        painter.setPen(Qt.PenStyle.NoPen)

        # Top strip
        if cy > y_off:
            painter.drawRect(x_off, y_off, pw, cy - y_off)
        # Bottom strip
        if crop_bottom < y_off + ph:
            painter.drawRect(x_off, crop_bottom, pw, (y_off + ph) - crop_bottom)
        # Left strip (clipped to crop band vertically)
        if cx > x_off:
            painter.drawRect(x_off, cy, cx - x_off, ch)
        # Right strip
        if crop_right < x_off + pw:
            painter.drawRect(crop_right, cy, (x_off + pw) - crop_right, ch)

        # --- Bright border on the crop rectangle ---
        pen = QPen(QColor(255, 70, 70), 2)
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(cx, cy, cw, ch)

        # --- Corner handles ---
        hs = 7
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 70, 70))
        for hx, hy in [
            (cx, cy),
            (crop_right - hs, cy),
            (cx, crop_bottom - hs),
            (crop_right - hs, crop_bottom - hs),
        ]:
            painter.drawRect(hx, hy, hs, hs)

        painter.end()


# New UIManager class for handling UI-related operations
class UIManager:
    def __init__(self, app_config, config_manager):
        self.app_config = app_config
        self.config_manager = config_manager
        self.main_widget = None
        self.charcombo = QComboBox()
        self.logger = logging.getLogger(__name__ + ".ui")

    def create_main_layout(self):
        """Construct the main UI layout."""
        self.main_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.charcombo)
        self.main_widget.setLayout(layout)

    def apply_theme(self, theme_name):
        """Apply the specified theme."""
        try:
            self.config_manager.update_app_setting("theme", theme_name)
            app_instance = QApplication.instance()
            app_instance.setStyle("Fusion")
        except Exception as e:
            self.logger.exception("Error applying theme '%s': %s", theme_name, e)
        except Exception as e:
            logging.exception("Unexpected error: %s", e)


# New ScoreCalculator class for handling score calculations
class ScoreCalculator:
    def __init__(self, app=None):
        self.app = app

    def calculate_all_scores(self):
        """Calculate scores for the current tabs using the simplified calculator."""
        if self.app is None:
            return {}

        tabs = {}
        for tab_name, content in self.app.tabs_content.items():
            substats = {}
            for stat_widget, value_widget in content["sub_entries"]:
                stat_name = stat_widget.currentText()
                value_text = value_widget.text().strip()
                if not stat_name or not value_text:
                    continue
                try:
                    substats[stat_name] = float(value_text)
                except ValueError:
                    continue

            tabs[tab_name] = {
                "substats": substats,
                "weights": CHARACTER_STAT_WEIGHTS.get(
                    self.app.character_var, CHARACTER_STAT_WEIGHTS["General"]
                ),
                "methods": getattr(self.app.app_config, "enabled_calc_methods", {}),
            }

        results = self.calculate_batch_scores(tabs)
        if getattr(self.app, "result_text", None) is not None:
            self.app.result_text.setPlainText("\n".join(f"{key}: {value}" for key, value in results.items()))
        return results

    def calculate_single_score(self, substats, weights, methods=None):
        """Perform single score calculation.

        `methods` is accepted for compatibility but not used by the placeholder logic.
        """
        try:
            s_vals = sum(float(v) for v in substats.values()) if isinstance(substats, dict) else float(substats)
        except Exception:
            s_vals = 0.0
        try:
            w_vals = sum(float(v) for v in weights.values()) if isinstance(weights, dict) else float(weights)
        except Exception:
            w_vals = 0.0
        return s_vals * w_vals

    def calculate_batch_scores(self, tabs):
        """Perform batch score calculations."""
        results = {}
        for tab, data in tabs.items():
            results[tab] = self.calculate_single_score(data['substats'], data['weights'], data['methods'])
        return results

# Refactor ScoreCalculatorApp to use UIManager and ScoreCalculator
class ScoreCalculatorApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        # Ensure module logger is at DEBUG level (root handlers configured above)
        self.logger.setLevel(logging.DEBUG)

        # Default fallbacks to avoid AttributeError during partial initialization
        self.language = 'ja'
        self.character_var = ''
        self.current_config_key = ''
        self.mode_var = 'manual'
        self.app_config = None

        self._init_config()
        self._init_vars()
        self._current_app_theme = self.app_config.theme

        # Initialize UI components and ScoreCalculator
        self.ui_manager = UIComponents(self)
        self.score_calculator = ScoreCalculator(self)
        self.score_calc = self.score_calculator

        # UI construction
        self.ui_manager.create_main_layout()
        self.setCentralWidget(self.ui_manager.main_widget)

        # Post-initialization setup
        QTimer.singleShot(100, self._post_init_setup)

    def _init_config(self) -> None:
        """Initialize ConfigManager and load settings."""
        config_path = os.path.join(get_app_path(), CONFIG_FILENAME)
        self.config_manager = ConfigManager(config_path)
        self.config_manager.load()
        app_config = self.config_manager.get_app_config()
        ui_config = self.config_manager.get_ui_config()

        self.WINDOW_WIDTH = ui_config.window_width
        self.WINDOW_HEIGHT = ui_config.window_height
        self.RIGHT_TOP_HEIGHT = ui_config.right_top_height
        self.LOG_MIN_HEIGHT = ui_config.log_min_height
        self.LOG_DEFAULT_HEIGHT = ui_config.log_default_height
        self.IMAGE_PREVIEW_MAX_WIDTH = ui_config.image_preview_max_width
        self.IMAGE_PREVIEW_MAX_HEIGHT = ui_config.image_preview_max_height

        self.language = app_config.language
        self.crop_top_percent = app_config.crop_top_percent
        self.crop_right_percent = app_config.crop_right_percent

        self.app_config = app_config

    def _init_vars(self) -> None:
        """Initialize UI-related variables."""
        app_config = self.app_config
        self.tabs_content = {}

        self.current_config_key = app_config.current_config_key
        self.mode_var = app_config.mode_var

        saved_char_name = app_config.character_var
        if saved_char_name:
            from constants import _CHAR_NAME_MAP_EN_TO_JP
            if saved_char_name in _CHAR_NAME_MAP_EN_TO_JP:
                self.character_var = saved_char_name
            else:
                self.character_var = get_char_internal_name(saved_char_name)
        else:
            self.character_var = ""

        self.auto_apply_main_stats = app_config.auto_apply_main_stats
        self.score_mode_var = app_config.score_mode_var
        self._updating_tabs = False
        self.crop_mode_var = app_config.crop_mode
        self.crop_top_percent_var = app_config.crop_top_percent
        self.crop_right_percent_var = app_config.crop_right_percent

        self.loaded_image = None
        self.original_image = None
        self.image_label = None
        self._image_preview = None
        self._last_displayed_image_hash = None
        self._last_image_preview = None
        self._tab_images = {}

        self._tab_results = {}
        self._character_config_map = {}

        # UI References (populated by UIManager)
        self.result_text = None
        self.log_text = None
        self.notebook = None
        self.charcombo = QComboBox()
        self.config_combo = None

    def update_text_color(self, color):
        self.config_manager.update_app_setting("text_color", color)
        self.apply_theme(self._current_app_theme)

    def update_background_image(self, image_path):
        self.config_manager.update_app_setting("background_image", image_path)
        self.apply_theme(self._current_app_theme)

    def update_background_opacity(self, opacity):
        self.config_manager.update_app_setting("background_opacity", opacity)
        self.apply_theme(self._current_app_theme)

    def update_input_bg_color(self, color):
        self.config_manager.update_app_setting("custom_input_bg_color", color)
        self.apply_theme(self._current_app_theme)

    def update_app_font(self, font_family: str):
        """Update the application font."""
        self.config_manager.update_app_setting("app_font", font_family)
        self.apply_theme(self._current_app_theme)

    def apply_theme(self, theme_name: str) -> None:
        """Apply the specified theme."""
        try:
            self._current_app_theme = theme_name
            self.config_manager.update_app_setting("theme", theme_name)
            
            app_instance = QApplication.instance()
            app_instance.setStyle("Fusion")
            self._apply_theme_stylesheet(theme_name)
        except Exception as e:
            self.logger.exception("Error applying theme '%s': %s", theme_name, e)
            QMessageBox.critical(self, "Theme Error", f"Failed to apply theme '{theme_name}':\n{e}")

    def _hex_to_rgba(self, hex_color: str, alpha: float) -> str:
        """Convert hex color to rgba string."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha})"
        return hex_color

    def _apply_theme_stylesheet(self, theme_name: str) -> None:
        """Sets the stylesheet based on the theme name."""
        colors = THEME_COLORS.get(theme_name, THEME_COLORS["light"])
        bg_image = self.app_config.background_image
        
        main_window_bg = ""
        alpha = self.app_config.background_opacity
        
        c_bg = colors['background']
        c_input = self.app_config.custom_input_bg_color if self.app_config.custom_input_bg_color else colors['input_bg']
        c_btn = colors['button_bg']
        c_btn_hover = colors['button_hover']
        c_tab = colors['tab_bg']
        c_tab_sel = colors['tab_selected']

        button_text_color = self.app_config.text_color
        tab_text_color = self.app_config.text_color

        if bg_image:
            if not os.path.isabs(bg_image):
                bg_image = os.path.join(get_app_path(), bg_image)

        if bg_image and os.path.exists(bg_image):
            img_path = bg_image.replace("\\", "/")
            main_window_bg = f"border-image: url('{img_path}') 0 0 0 0 stretch stretch;"
            
            c_bg = self._hex_to_rgba(c_bg, alpha)
            c_input = self._hex_to_rgba(c_input, alpha)
            c_btn = self._hex_to_rgba(c_btn, alpha)
            c_btn_hover = self._hex_to_rgba(c_btn_hover, alpha)
            c_tab = self._hex_to_rgba(c_tab, alpha)
            c_tab_sel = self._hex_to_rgba(c_tab_sel, alpha)
        
        font_style = ""
        if self.app_config.app_font:
            font_style = f"font-family: '{self.app_config.app_font}';"

        QApplication.instance().setStyleSheet(f"""
            QMainWindow {{ background-color: {colors['background']}; {main_window_bg} color: {self.app_config.text_color}; {font_style} }}
            QWidget {{ background-color: {c_bg}; color: {self.app_config.text_color}; {font_style} }}
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background-color: {c_input}; color: {self.app_config.text_color}; border: 1px solid {colors['border']}; {font_style} }}
            QPushButton {{ background-color: {c_btn}; color: {button_text_color}; border: 1px solid {colors['border']}; padding: 5px; {font_style} }}
            QPushButton:hover {{ background-color: {colors['button_hover']}; }}
            QTabWidget::pane {{ border: 1px solid {colors['border']}; background-color: {c_bg}; }}
            QTabBar::tab {{ background: {c_tab}; color: {tab_text_color}; padding: 5px; {font_style} }}
            QTabBar::tab:selected {{ background: {c_tab_sel}; }}
            QGroupBox {{ border: 1px solid {colors['group_border']}; margin-top: 10px; background-color: {c_bg}; {font_style} }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; background-color: transparent; }}
            QComboBox QAbstractItemView {{ background-color: {c_input}; color: {self.app_config.text_color}; selection-background-color: {colors['button_hover']}; {font_style} }}
            QRubberBand {{ background-color: transparent; border: 1px solid #FFD700; selection-background-color: transparent; }}
        """)

    def tr(self, key: str, *args: Any) -> str:
        """Translate a key with fallback to Japanese and then the key itself."""
        lang_dict = TRANSLATIONS.get(self.language, {})
        text = lang_dict.get(key)
        
        if text is None:
            text = TRANSLATIONS.get("ja", {}).get(key, key)
            
        if args:
            try:
                return text.format(*args)
            except Exception:
                self.logger.warning("Failed to format translation string '%s' with args %s", text, args, exc_info=True)
                return text
        return text
        
    def gui_log(self, msg: str) -> None:
        """Simple logging to GUI."""
        self.logger.info(msg)
        if self.log_text is not None:
            try:
                self.log_text.append(str(msg))
            except Exception as e:
                self.logger.debug(f"GUI log update failed: {e}")

    def show_ocr_error_message(self, title: str, message: str) -> None:
        """Slot to show a critical message box for OCR errors."""
        QMessageBox.critical(self, title, message)

    def show_info_message(self, title: str, message: str) -> None:
        """Slot to show an informational message box."""
        QMessageBox.information(self, title, message)
        
    def on_character_profile_saved(self, name: str, config_key: str) -> None:
        """Slot to handle post-save actions for a character profile."""
        self._character_config_map[name] = config_key
        self._filter_characters_by_config()

    def on_ocr_completed(self, substats: list[dict], log_messages: list[str]) -> None:
        """Slot to handle the results of OCR processing."""
        for msg in log_messages:
            self.gui_log(msg)
        
        if not substats:
            self.gui_log("OCR completed but no substats were parsed.")
            return
            
        tab_name = self.get_selected_tab_name()
        if not tab_name:
            self.gui_log("OCR auto-fill failed: No tab selected")
            return
        if tab_name not in self.tabs_content:
            self.gui_log(f"OCR auto-fill failed: Tab '{tab_name}' not found")
            return
            
        content = self.tabs_content[tab_name]
        sub_entries = content["sub_entries"]
        
        for i, substat_data in enumerate(substats):
            if i < len(sub_entries):
                stat_found = substat_data.get("stat", "")
                num_found = substat_data.get("value", "")
                
                translated_stat = self.tr(stat_found)
                sub_entries[i][0].setCurrentText(translated_stat)
                sub_entries[i][1].setText(num_found)
        
        self.gui_log("Successfully applied OCR results to the current tab.")

    def _open_readme(self) -> None:
        """Opens the README file."""
        try:
            base_dir = get_app_path()
            readme_path = os.path.join(base_dir, "README.html")
            if os.path.exists(readme_path):
                webbrowser.open(readme_path)
            else:
                QMessageBox.critical(self, "Error", f"README file not found:\n{readme_path}")
        except Exception as e:
            self.logger.exception(f"README open error: {e}")
            QMessageBox.critical(self, "Error", f"Could not open README:\n{e}")

    def _update_main_stat_combobox(self, combo: QComboBox, content: dict, mainstats: dict) -> None:
        """Helper to update a single main stat combobox."""
        if not combo:
            return

        combo.blockSignals(True)
        try:
            cost_key = content.get("cost_key", content["cost"])
            fallback_key = content["cost"]
            target_key = None
            if cost_key in mainstats:
                target_key = cost_key
            elif fallback_key in mainstats:
                target_key = fallback_key
            elif f"{fallback_key}_1" in mainstats:
                target_key = f"{fallback_key}_1"
            
            if target_key and mainstats.get(target_key):
                stat_name = mainstats[target_key]
                translated_stat = self.tr(stat_name)
                index = combo.findText(translated_stat)
                if index >= 0:
                    combo.setCurrentIndex(index)
                else:
                    combo.setCurrentText(translated_stat)
        except Exception as e:
            self.logger.exception(f"Error updating main stat combobox: {e}")
        finally:
            combo.blockSignals(False)

    def _apply_character_main_stats(self, force: bool = False) -> None:
        """Automatically enters main stats."""
        if not force and not self.auto_apply_main_stats:
            return
        mainstats = CHARACTER_MAIN_STATS.get(self.character_var)
        if not mainstats:
            return
        
        if self.charcombo:
            self.charcombo.blockSignals(True)

        for tab_name, content in self.tabs_content.items():
            combo = content["main_widget"]
            self._update_main_stat_combobox(combo, content, mainstats)
        
        if self.charcombo:
            self.charcombo.blockSignals(False)

    def _is_pillow_installed(self) -> bool:
        return is_pil_installed

    def _is_pytesseract_installed(self) -> bool:
        return is_pytesseract_installed

    def _is_tesseract_configured(self) -> bool:
        try:
            if is_pytesseract_installed:
                pytesseract.get_tesseract_version()
                return True
        except Exception:
            pass
        return False

    def _check_and_alert_environment(self) -> None:
        try:
            is_pil = self._is_pillow_installed()
            is_pytess = self._is_pytesseract_installed()
            is_tess_cfg = self._is_tesseract_configured()

            missing_libs = []
            if not is_pil:
                missing_libs.append("Pillow")
            if not is_pytess:
                missing_libs.append("pytesseract")
            
            if missing_libs:
                self.gui_log(f"Warning: The following libraries are missing: {', '.join(missing_libs)}")
                self.gui_log("To use the OCR feature, please install these libraries.")
            elif not is_tess_cfg:
                self.gui_log("Warning: Tesseract is not configured correctly.")
                self.gui_log("To use OCR, please install Tesseract and set the path.")
            else:
                self.gui_log("Environment check: OCR feature is available.")
        except Exception as e:
            self.logger.warning(f"Environment check error: {e}", exc_info=True)

    def _post_init_setup(self) -> None:
        """Post-initialization setup."""
        # Ensure tabs exist; use a safe update_tabs implementation below
        try:
            self.update_tabs()
        except Exception:
            self.logger.debug("Safe update_tabs fallback will run", exc_info=True)
            self._safe_update_tabs()
        self.update_ui_mode()
        self._load_character_profiles()
        self._filter_characters_by_config()
        self._check_and_alert_environment()
    
    def opencharsetting(self) -> None:
        """Display the character settings dialog."""
        try:
            dlg = CharSettingDialog(self, self.register_char)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open character settings window:\n{e}")
            self.gui_log(f"Character settings display error: {e}")

    def open_display_settings(self) -> None:
        """Display the display settings dialog."""
        try:
            dlg = DisplaySettingsDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open display settings window:\n{e}")
            self.gui_log(f"Display settings display error: {e}")

    def _update_char_combobox(self, items_to_add: list[tuple[str, str]], current_internal_name: str = "") -> None:
        self.gui_log(f"DEBUG: _update_char_combobox - Started. current_internal_name='{current_internal_name}'")

        if self.charcombo is None:
            return
        
        self.charcombo.blockSignals(True)
        self.charcombo.clear()
        self.charcombo.addItem("", userData="")

        for translated_name, char_name in items_to_add:
            self.charcombo.addItem(translated_name, userData=char_name)
        
        target_index = 0
        if current_internal_name:
            index = self.charcombo.findData(current_internal_name)
            if index != -1:
                target_index = index
        
        self.charcombo.setCurrentIndex(target_index)
        self.charcombo.blockSignals(False)

    def register_char(self, name_jp: str, name_en: str, costkey: str, mainstats: dict, weights: dict) -> None:
        """Register a character's settings."""
        internal_char_name = name_en
        
        from constants import _CHAR_NAME_MAP_JP_TO_EN, _CHAR_NAME_MAP_EN_TO_JP
        _CHAR_NAME_MAP_JP_TO_EN[name_jp] = internal_char_name
        _CHAR_NAME_MAP_EN_TO_JP[internal_char_name] = name_jp
        
        CHARACTER_STAT_WEIGHTS[internal_char_name] = weights or CHARACTER_STAT_WEIGHTS.get(internal_char_name, CHARACTER_STAT_WEIGHTS["General"])
        CHARACTER_MAIN_STATS[internal_char_name] = mainstats or CHARACTER_MAIN_STATS.get(internal_char_name, {})

        try:
            items_to_add = sorted([(self.tr(char), char) for char in CHARACTER_STAT_WEIGHTS.keys()], key=lambda x: x[0])
            self._update_char_combobox(items_to_add, internal_char_name)
            self.character_var = internal_char_name
        except Exception as e:
            self.logger.exception(f"Failed to update charcombo: {e}")

        normalized_key = self._normalize_cost_key(costkey, self.current_config_key)
        self.current_config_key = normalized_key
        if self.config_combo:
            idx = self.config_combo.findText(normalized_key)
            if idx >= 0:
                self.config_combo.setCurrentIndex(idx)

        self._apply_character_main_stats()
        self._save_character_profile(internal_char_name, costkey, mainstats, weights)

    # ----------------------------------------------------
    # Consolidated methods from TabManager
    # ----------------------------------------------------
    def get_selected_tab_name(self) -> Optional[str]:
        """Get the internal key of the currently selected tab."""
        if self.notebook is None:
            return None
        index = self.notebook.currentIndex()
        if index == -1:
            return None
            
        config_key = self.current_config_key
        if config_key in TAB_CONFIGS:
            keys = TAB_CONFIGS[config_key]
            if index < len(keys):
                return keys[index]
        return self.notebook.tabText(index)
    
    def show_tab_image(self, tab_name: str) -> None:
        """Display the image saved in the tab."""
        if self.image_label is None:
            return
        data = self._tab_images.get(tab_name)
        if data and data.get("cropped") is not None:
            self.loaded_image = data["cropped"].copy()
            self.original_image = data["original"].copy()
            self.display_image_preview(self.loaded_image)
        else:
            self.loaded_image = None
            self.original_image = None
            self.image_label.setText(self.tr("no_image"))
            self.image_label.setPixmap(QPixmap())
    
    def save_tab_result(self, tab_name: str) -> None:
        """Save the current calculation result for each tab."""
        if self.result_text is None:
            return
        try:
            result_content = self.result_text.toHtml()
            self._tab_results[tab_name] = {
                "content": result_content
            }
        except Exception as e:
            self.logger.warning(f"Failed to save tab result: {e}", exc_info=True)
    
    def show_tab_result(self, tab_name: str) -> None:
        """Restore the saved calculation result."""
        if self.result_text is None:
            return
        
        result_data = self._tab_results.get(tab_name)
        if result_data:
            try:
                self.result_text.setHtml(result_data["content"])
            except Exception as e:
                self.logger.warning(f"Failed to restore tab result: {e}", exc_info=True)
        else:
            self.result_text.clear()
    
    def clear_current_tab(self) -> None:
        """Clear the contents of the current tab only."""
        try:
            tab_name = self.get_selected_tab_name()
            if not tab_name or tab_name not in self.tabs_content:
                return
            
            content = self.tabs_content[tab_name]
            content["main_widget"].setCurrentIndex(-1)
            for stat_widget, val_widget in content["sub_entries"]:
                stat_widget.setCurrentIndex(-1)
                val_widget.clear()
            
            if tab_name in self._tab_images:
                del self._tab_images[tab_name]
            if tab_name in self._tab_results:
                del self._tab_results[tab_name]
            
            self.show_tab_image(tab_name)
            self.show_tab_result(tab_name)
            self.gui_log(f"Cleared the contents of tab '{tab_name}'.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear tab: {e}")

    def clear_all(self) -> None:
        """Reset all tabs, text, logs, input values, etc."""
        try:
            for content in self.tabs_content.values():
                content["main_widget"].setCurrentIndex(-1)
                for stat_widget, val_widget in content["sub_entries"]:
                    stat_widget.setCurrentIndex(-1)
                    val_widget.clear()
            
            if self.result_text:
                self.result_text.clear()
            if self.log_text:
                self.log_text.clear()
                
            self.loaded_image = None
            self.original_image = None
            self._image_preview = None
            self._tab_images.clear()
            self._tab_results.clear()
            
            if self.image_label:
                self.image_label.setText(self.tr("no_image"))
                self.image_label.setPixmap(QPixmap())
                
            self.gui_log("All items have been cleared.")
        except Exception as e:
            QMessageBox.critical(self, "Clear Error", f"Failed to reset items: {e}")

    def export_result_to_txt(self) -> None:
        """Export the score calculation result to a text file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Result", "", "Text Files (*.txt);;All Files (*.*)"
            )
            if not file_path:
                return
            text = self.result_text.toPlainText()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            QMessageBox.information(self, "Success", "Calculation result exported to text file.")
            self.gui_log(f"Exported calculation result to TXT file: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")

    def save_tab_image(self, tab_name: str, original_image, cropped_image):
        self._tab_images[tab_name] = {
            "original": original_image,
            "cropped": cropped_image
        }
    
    def get_tab_image(self, tab_name: str) -> Optional[Dict[str, Any]]:
        return self._tab_images.get(tab_name)

    # ----------------------------------------------------
    # Consolidated methods from EventHandlers
    # ----------------------------------------------------
    def on_config_change(self, text: str) -> None:
        self.current_config_key = text
        if not getattr(self, "_updating_tabs", False):
            self.update_tabs()
            self.gui_log(f"Cost configuration changed: Tabs updated by {text}")
            self._apply_character_main_stats()
            self._filter_characters_by_config()
            self.save_config()
    
    def on_character_change(self, text: str) -> None:
        current_index = self.charcombo.currentIndex()
        if current_index >= 0:
            internal_name = self.charcombo.itemData(current_index)
            if internal_name:
                self.character_var = internal_name
                self.gui_log(f"Character selected: {internal_name}")
                self._apply_character_main_stats()
                self.save_config()
            else:
                self.character_var = ""
                self.gui_log("Character selection cleared.")
                self._apply_character_main_stats()
                self.save_config()
    
    def on_language_change(self, text: str) -> None:
        if text != self.language:
            self.language = text
            self.save_config()
            self.retranslate_ui()
            self.gui_log(f"Language changed to: {text}")
    
    def on_mode_change(self, mode: str) -> None:
        self.mode_var = mode
        self.update_ui_mode()
        self.save_config()

    def on_auto_main_change(self, checked: bool) -> None:
        self.auto_apply_main_stats = checked
        self.save_config()

    def on_score_mode_change(self, mode: str) -> None:
        self.score_mode_var = mode
        self.save_config()
    
    def on_calc_method_changed(self) -> None:
        enabled_methods = {
            "normalized": self.cb_method_normalized.isChecked(),
            "ratio": self.cb_method_ratio.isChecked(),
            "roll": self.cb_method_roll.isChecked(),
            "effective": self.cb_method_effective.isChecked(),
            "cv": self.cb_method_cv.isChecked()
        }
        
        if not any(enabled_methods.values()):
            QMessageBox.warning(
                self,
                self.tr("warning"),
                self.tr("no_methods_selected")
            )
            sender = self.sender()
            if sender:
                sender.setChecked(True)
            return
        
        self.app_config.enabled_calc_methods = enabled_methods
        self.save_config()
        self.gui_log(f"Calculation methods updated: {[k for k, v in enabled_methods.items() if v]}")

    def on_crop_mode_change(self, mode: str) -> None:
        self.crop_mode_var = mode
        self.save_config()

    def on_crop_percent_change(self, text: str) -> None:
        try:
            if self.entry_top_p == self.sender():
                self.crop_top_percent_var = float(text)
            elif self.entry_right_p == self.sender():
                self.crop_right_percent_var = float(text)
            
            self.save_config()
            self.schedule_crop_preview()
        except ValueError:
            pass

    def on_tab_changed(self, index: int) -> None:
        tab_name = self.get_selected_tab_name()
        if tab_name:
            self.show_tab_image(tab_name)
            self.show_tab_result(tab_name)
    
    def cycle_theme(self) -> None:
        current = self._current_app_theme
        if current == "dark":
            new_theme = "light"
        elif current == "light":
            new_theme = "clear"
        else:
            new_theme = "dark"
            
        self.gui_log(f"Theme changed to {new_theme} mode.")
        self.apply_theme(new_theme)
        self.save_config()
    
    def save_config(self) -> None:
        self._save_timer.start(500)
    
    def actual_save_config(self) -> None:
        """Save current settings to config.json."""
        try:
            self.config_manager.update_app_setting('language', self.language)
            self.config_manager.update_app_setting('crop_mode', self.crop_mode_var)
            self.config_manager.update_app_setting('crop_top_percent', self.crop_top_percent_var)
            self.config_manager.update_app_setting('crop_right_percent', self.crop_right_percent_var)
            self.config_manager.update_app_setting('current_config_key', self.current_config_key)
            self.config_manager.update_app_setting('character_var', self.character_var)
            self.config_manager.update_app_setting('mode_var', self.mode_var)
            self.config_manager.update_app_setting('score_mode_var', self.score_mode_var)
            self.config_manager.update_app_setting('auto_apply_main_stats', self.auto_apply_main_stats)
            self.config_manager.update_app_setting('enabled_calc_methods', self.app_config.enabled_calc_methods)
            
            self.config_manager.save()
            self.logger.info("Config saved.")
        except Exception as e:
            self.gui_log(f"Config save error: {e}")
    
    def schedule_crop_preview(self) -> None:
        self._crop_preview_timer.start(100)
    
    def schedule_image_preview_update_on_resize(self, *args: Any) -> None:
        self._resize_preview_timer.start(100)

    # ----------------------------------------------------
    # Consolidated methods from UIComponents
    # ----------------------------------------------------
    def create_main_layout(self) -> None:
        """Create the main window's entire UI."""
        self.main_widget = QWidget()
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.create_left_pane(left_layout, self.charcombo)
        self.main_splitter.addWidget(left_container)
        
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.create_right_pane(right_layout)
        self.main_splitter.addWidget(right_container)

        self.main_splitter.setSizes([500, 400])
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)

    def create_left_pane(self, parent_layout: QVBoxLayout, charcombo: QComboBox) -> None:
        self.create_settings_frame(parent_layout, charcombo)
        self.create_buttons_frame(parent_layout)

        self.notebook = QTabWidget()
        self.notebook.blockSignals(True)
        self.notebook.currentChanged.connect(self.on_tab_changed)
        self.notebook.blockSignals(False)
        parent_layout.addWidget(self.notebook)

        self.create_result_frame(parent_layout)

    def create_settings_frame(self, parent_layout: QVBoxLayout, charcombo: QComboBox) -> None:
        self.settings_group = QGroupBox(self.tr("basic_settings"))
        settings_layout = QGridLayout(self.settings_group)
        parent_layout.addWidget(self.settings_group)

        # Row 0
        self.lbl_cost_config = QLabel(self.tr("cost_config"))
        settings_layout.addWidget(self.lbl_cost_config, 0, 0)
        self.config_combo = QComboBox()
        self.config_combo.addItems(list(TAB_CONFIGS.keys()))
        self.config_combo.blockSignals(True)
        self.config_combo.setCurrentText(self.current_config_key)
        self.config_combo.blockSignals(False)
        self.config_combo.currentTextChanged.connect(self.on_config_change)
        settings_layout.addWidget(self.config_combo, 0, 1)

        self.lbl_character = QLabel(self.tr("character"))
        settings_layout.addWidget(self.lbl_character, 0, 2)
        charcombo.setObjectName("CharComboBox")
        charcombo.currentTextChanged.connect(self.on_character_change)
        settings_layout.addWidget(charcombo, 0, 3)

        self.lbl_language = QLabel(self.tr("language"))
        settings_layout.addWidget(self.lbl_language, 0, 4)
        lang_combo = QComboBox()
        lang_combo.addItems(["ja", "en", "zh-TW"])
        lang_combo.setCurrentText(self.language)
        lang_combo.currentTextChanged.connect(self.on_language_change)
        settings_layout.addWidget(lang_combo, 0, 5)

        # Row 1: Input Mode
        self.lbl_input_mode = QLabel(self.tr("input_mode"))
        settings_layout.addWidget(self.lbl_input_mode, 1, 0)
        mode_layout = QHBoxLayout()

        self.rb_manual = QRadioButton(self.tr("manual"))
        self.rb_ocr = QRadioButton(self.tr("ocr"))

        self.mode_group = QGroupBox()
        self.mode_group.setLayout(QHBoxLayout())

        mode_layout.addWidget(self.rb_manual)
        mode_layout.addWidget(self.rb_ocr)

        if self.mode_var == "manual":
            self.rb_manual.setChecked(True)
        else:
            self.rb_ocr.setChecked(True)

        self.rb_manual.toggled.connect(
            lambda c: self.on_mode_change("manual") if c else None
        )
        self.rb_ocr.toggled.connect(
            lambda c: self.on_mode_change("ocr") if c else None
        )

        settings_layout.addLayout(mode_layout, 1, 1, 1, 3)

        # Auto Main & Theme
        right_sub_layout = QVBoxLayout()
        self.cb_auto_main = QCheckBox(self.tr("auto_main"))
        self.cb_auto_main.setChecked(self.auto_apply_main_stats)
        self.cb_auto_main.toggled.connect(self.on_auto_main_change)
        right_sub_layout.addWidget(self.cb_auto_main)

        settings_layout.addLayout(right_sub_layout, 1, 4, 1, 2)

        # Row 2: Calculation Mode
        self.lbl_calc_mode = QLabel(self.tr("calc_mode"))
        settings_layout.addWidget(self.lbl_calc_mode, 2, 0)
        calc_mode_layout = QHBoxLayout()
        self.rb_batch = QRadioButton(self.tr("batch"))
        self.rb_single = QRadioButton(self.tr("single_only"))

        if self.score_mode_var == "batch":
            self.rb_batch.setChecked(True)
        else:
            self.rb_single.setChecked(True)

        self.rb_batch.toggled.connect(
            lambda c: self.on_score_mode_change("batch") if c else None
        )
        self.rb_single.toggled.connect(
            lambda c: self.on_score_mode_change("single") if c else None
        )

        calc_mode_layout.addWidget(self.rb_batch)
        calc_mode_layout.addWidget(self.rb_single)
        settings_layout.addLayout(calc_mode_layout, 2, 1, 1, 3)

        # Row 3: Calculation Methods Selection
        self.lbl_calc_methods = QLabel(self.tr("calc_methods"))
        settings_layout.addWidget(self.lbl_calc_methods, 3, 0)

        methods_layout = QHBoxLayout()
        self.cb_method_normalized = QCheckBox(self.tr("method_normalized"))
        self.cb_method_ratio = QCheckBox(self.tr("method_ratio"))
        self.cb_method_roll = QCheckBox(self.tr("method_roll"))
        self.cb_method_effective = QCheckBox(self.tr("method_effective"))
        self.cb_method_cv = QCheckBox(self.tr("method_cv"))

        enabled_methods = self.app_config.enabled_calc_methods
        self.cb_method_normalized.setChecked(enabled_methods.get("normalized", True))
        self.cb_method_ratio.setChecked(enabled_methods.get("ratio", True))
        self.cb_method_roll.setChecked(enabled_methods.get("roll", True))
        self.cb_method_effective.setChecked(enabled_methods.get("effective", True))
        self.cb_method_cv.setChecked(enabled_methods.get("cv", True))

        self.cb_method_normalized.toggled.connect(self.on_calc_method_changed)
        self.cb_method_ratio.toggled.connect(self.on_calc_method_changed)
        self.cb_method_roll.toggled.connect(self.on_calc_method_changed)
        self.cb_method_effective.toggled.connect(self.on_calc_method_changed)
        self.cb_method_cv.toggled.connect(self.on_calc_method_changed)

        methods_layout.addWidget(self.cb_method_normalized)
        methods_layout.addWidget(self.cb_method_ratio)
        methods_layout.addWidget(self.cb_method_roll)
        methods_layout.addWidget(self.cb_method_effective)
        methods_layout.addWidget(self.cb_method_cv)
        methods_layout.addStretch()

        settings_layout.addLayout(methods_layout, 3, 1, 1, 5)

    def update_tabs(self) -> None:
        """Delegate tab updating to UIManager if available, otherwise use safe fallback."""
        if hasattr(self, 'ui_manager') and hasattr(self.ui_manager, 'update_tabs'):
            return self.ui_manager.update_tabs()
        return self._safe_update_tabs()

    def _safe_update_tabs(self) -> None:
        """Create minimal tabs so the UI can start without full tab logic implemented."""
        try:
            if not hasattr(self, 'notebook') or self.notebook is None:
                self.notebook = QTabWidget()
            self.notebook.clear()
            self.tabs_content = {}
            config_key = getattr(self, 'current_config_key', list(TAB_CONFIGS.keys())[0])
            tab_names = TAB_CONFIGS.get(config_key, list(TAB_CONFIGS.values())[0])
            for tab_name in tab_names:
                page = QWidget()
                layout = QVBoxLayout(page)
                main_combo = QComboBox()
                main_combo.addItems([self.tr(s) for s in MAIN_STAT_OPTIONS.get('4', [])])
                layout.addWidget(main_combo)
                sub_entries = []
                for i in range(5):
                    stat_combo = QComboBox()
                    stat_combo.addItems([''] + [self.tr(s) for s in list(SUBSTAT_MAX_VALUES.keys())])
                    val_entry = QLineEdit()
                    row_widget = QWidget()
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.addWidget(stat_combo)
                    row_layout.addWidget(val_entry)
                    layout.addWidget(row_widget)
                    sub_entries.append((stat_combo, val_entry))
                self.notebook.addTab(page, tab_name)
                self.tabs_content[tab_name] = {
                    'main_widget': main_combo,
                    'sub_entries': sub_entries
                }
        except Exception:
            self.logger.exception("Failed to create safe tabs")

    def _load_character_profiles(self) -> None:
        """Load character profile JSONs from the `character_settings_jsons` folder.

        This is a lightweight loader used to initialize the character combobox.
        """
        try:
            base = os.path.join(get_app_path(), 'character_settings_jsons')
            items_to_add = []
            config_map = {}
            if os.path.isdir(base):
                for fname in os.listdir(base):
                    if not fname.lower().endswith('.json'):
                        continue
                    path = os.path.join(base, fname)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            j = json.load(f)
                        en = j.get('EN') or j.get('internal') or os.path.splitext(fname)[0]
                        jp = j.get('JP') or j.get('name') or en
                        items_to_add.append((self.tr(jp), en))
                        config_map[en] = self.current_config_key
                        self.logger.info("DEBUG: _load_character_profiles - Processing file: %s", fname)
                        self.logger.info("DEBUG: _load_character_profiles - Initial from JSON: EN='%s', JP='%s'", en, jp)
                    except Exception:
                        self.logger.exception("Failed to read character file: %s", fname)
            # Always include General
            if 'General' not in [i[1] for i in items_to_add]:
                items_to_add.append((self.tr('汎用'), 'General'))
                config_map['General'] = self.current_config_key

            self._character_config_map = config_map
            self.gui_log("Character profiles loaded and map created.")
            self._update_char_combobox(items_to_add, self.character_var)
        except Exception:
            self.logger.exception("_load_character_profiles failed")

    def _filter_characters_by_config(self) -> None:
        try:
            current_key = getattr(self, 'current_config_key', None)
            allowed = [name for name, cfg in self._character_config_map.items() if cfg == current_key]

            items_to_add = []
            if allowed:
                items_to_add = sorted([(self.tr(char_name), char_name) for char_name in allowed], key=lambda x: x[0])
            else:
                items_to_add = sorted([(self.tr(char_name), char_name) for char_name in CHARACTER_STAT_WEIGHTS.keys()], key=lambda x: x[0])

            current_internal_name = getattr(self, 'character_var', '')
            self._update_char_combobox(items_to_add, current_internal_name)
        except Exception as e:
            self.logger.exception(f"Failed to filter characters by config: {e}")

    def update_ui_mode(self) -> None:
        """Update UI visibility based on current mode (ocr/manual)."""
        try:
            if getattr(self, 'mode_var', 'manual') == 'ocr':
                if hasattr(self, 'image_frame') and self.image_frame is not None:
                    self.image_frame.setVisible(True)
            else:
                if hasattr(self, 'image_frame') and self.image_frame is not None:
                    self.image_frame.setVisible(False)
        except Exception:
            self.logger.exception("update_ui_mode failed")


if __name__ == "__main__":
    try:
        # Ensure Tesseract is set up only when running the application, not on import
        try:
            setup_tesseract()
        except Exception:
            logging.getLogger(__name__).warning("setup_tesseract() failed at startup, continuing without OCR setup")

        app = QApplication(sys.argv)
        window = ScoreCalculatorApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.getLogger(__name__).critical("Critical unhandled exception during application startup: %s", e, exc_info=True)
        try:
            QMessageBox.critical(None, "Fatal Error", f"An unhandled error occurred during application startup:\n{e}\n\nCheck the log file for more details.")
        except Exception:
            pass
        sys.exit(1)
