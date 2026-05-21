import json
import logging
import os
import sys
import webbrowser
import re
import shutil
import time
import hashlib
from typing import Any, Callable, Optional, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QStyleFactory, QComboBox,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QScrollArea,
    QTextEdit, QLabel, QPushButton, QCheckBox, QRadioButton, QGroupBox,
    QSplitter, QFrame, QLineEdit, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QPixmap, QImage, QPainter, QColor, QPen

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageQt, ImageGrab
    is_pil_installed = True
except ImportError:
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
    STAT_ALIASES,
    SUBSTAT_MAX_VALUES,
    SUBSTAT_TYPES,
    TAB_CONFIGS,
    get_char_internal_name,
    get_char_japanese_name,
    THEME_COLORS,
    LOG_FILENAME,
    CONFIG_FILENAME
)
from dialogs import CharSettingDialog, CropDialog, DisplaySettingsDialog
from echo_data import EchoData
from languages import TRANSLATIONS
from utils import crop_image_by_percent, get_app_path, get_substat_display, setup_tesseract

# Tesseract setup
setup_tesseract()

class CropOverlayLabel(QLabel):
    """QLabel that draws a crop-area overlay on top of the displayed pixmap.

    Call set_crop_overlay() with fractional coordinates (0.0-1.0 relative to
    the pixmap) to show the overlay.  Call clear_overlay() to remove it.
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._crop_rect_f: Optional[tuple] = None  # (left_f, top_f, right_f, bottom_f)

    def set_crop_overlay(self, left_f: float, top_f: float, right_f: float, bottom_f: float) -> None:
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
        for hx, hy in [(cx, cy), (crop_right - hs, cy),
                       (cx, crop_bottom - hs), (crop_right - hs, crop_bottom - hs)]:
            painter.drawRect(hx, hy, hs, hs)

        painter.end()


# New UIManager class for handling UI-related operations
class UIManager:
    def __init__(self, app_config, config_manager):
        self.app_config = app_config
        self.config_manager = config_manager
        self.main_widget = None
        self.charcombo = QComboBox()

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
            app = QApplication.instance()
            app.setStyle("Fusion")
        except Exception as e:
            logging.exception(f"Error applying theme '{theme_name}': {e}")

# New ScoreCalculator class for handling score calculations
class ScoreCalculator:
    def __init__(self):
        pass

    def calculate_single_score(self, substats, weights, methods):
        """Perform single score calculation."""
        # Placeholder for actual calculation logic
        return sum(substats.values()) * sum(weights.values())

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
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(get_app_path(), LOG_FILENAME), encoding='utf-8'),
                logging.StreamHandler()
            ])

        self._init_config()
        self._init_vars()

        # Initialize UIManager and ScoreCalculator
        self.ui_manager = UIManager(self.app_config, self.config_manager)
        self.score_calculator = ScoreCalculator()

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
        self.app_config = self.config_manager.get_app_config()

    def _init_vars(self) -> None:
        """Initialize variables."""
        self.tabs_content = {}
        self.loaded_image = None
        self.original_image = None

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
            
            app = QApplication.instance()
            app.setStyle("Fusion")
            self._apply_theme_stylesheet(theme_name)
        except Exception as e:
            self.logger.exception(f"Error applying theme '{theme_name}': {e}")
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
                self.logger.warning(f"Failed to format translation string '{text}' with args {args}", exc_info=True)
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
        self.update_tabs()
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
            
        self.rb_manual.toggled.connect(lambda c: self.on_mode_change("manual") if c else None)
        self.rb_ocr.toggled.connect(lambda c: self.on_mode_change("ocr") if c else None)
        
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
            
        self.rb_batch.toggled.connect(lambda c: self.on_score_mode_change("batch") if c else None)
        self.rb_single.toggled.connect(lambda c: self.on_score_mode_change("single") if c else None)
        
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

    def create_buttons_frame(self, parent_layout: QVBoxLayout) -> None:
        self.button_frame = QFrame()
        btn_layout = QHBoxLayout(self.button_frame)
        btn_layout.setContentsMargins(0, 5, 0, 5)
        parent_layout.addWidget(self.button_frame)
        
        buttons = [
            ("calculate", self.calculate_all_scores),
            ("export_txt", self.export_result_to_txt),
            ("clear_all", self.clear_all),
            ("clear_tab", self.clear_current_tab),
            ("char_setting", self.opencharsetting),
            ("help", self._open_readme),
            ("display_settings", self.open_display_settings)
        ]
        self.action_buttons = {}
        for key, command in buttons:
            btn = QPushButton(self.tr(key))
            btn.clicked.connect(command)
            btn_layout.addWidget(btn)
            self.action_buttons[key] = btn
        
        btn_layout.addStretch()

    def create_right_pane(self, parent_layout: QVBoxLayout) -> None:
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        parent_layout.addWidget(right_splitter)
        
        self.image_container = QWidget()
        image_layout = QVBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.create_image_frame(image_layout)
        right_splitter.addWidget(self.image_container)
        
        self.log_group = QGroupBox(self.tr("log"))
        log_layout = QVBoxLayout(self.log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        right_splitter.addWidget(self.log_group)
        
        right_splitter.setSizes([350, 150])

    def create_image_frame(self, parent_layout: QVBoxLayout) -> None:
        self.image_frame = QGroupBox(self.tr("ocr_image"))
        layout = QVBoxLayout(self.image_frame)
        parent_layout.addWidget(self.image_frame)
        
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton(self.tr("load_image"))
        self.btn_load.clicked.connect(self.import_image)
        self.btn_paste = QPushButton(self.tr("paste_clipboard"))
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        self.btn_crop = QPushButton(self.tr("perform_crop"))
        self.btn_crop.clicked.connect(self.perform_crop)
        
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_paste)
        btn_layout.addWidget(self.btn_crop)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        crop_layout = QHBoxLayout()
        self.lbl_crop_mode = QLabel(self.tr("crop_mode"))
        crop_layout.addWidget(self.lbl_crop_mode)
        
        self.rb_crop_drag = QRadioButton(self.tr("drag"))
        self.rb_crop_percent = QRadioButton(self.tr("percent"))
        
        if self.crop_mode_var == "drag":
            self.rb_crop_drag.setChecked(True)
        else:
            self.rb_crop_percent.setChecked(True)
            
        self.rb_crop_drag.toggled.connect(lambda c: self.on_crop_mode_change("drag") if c else None)
        self.rb_crop_percent.toggled.connect(lambda c: self.on_crop_mode_change("percent") if c else None)
        
        crop_layout.addWidget(self.rb_crop_drag)
        crop_layout.addWidget(self.rb_crop_percent)
        
        self.lbl_top_percent = QLabel(self.tr("top_percent"))
        crop_layout.addWidget(self.lbl_top_percent)
        self.entry_top_p = QLineEdit(str(self.crop_top_percent_var))
        self.entry_top_p.setFixedWidth(50)
        self.entry_top_p.textChanged.connect(self.on_crop_percent_change)
        crop_layout.addWidget(self.entry_top_p)
        
        self.lbl_right_percent = QLabel(self.tr("right_percent"))
        crop_layout.addWidget(self.lbl_right_percent)
        self.entry_right_p = QLineEdit(str(self.crop_right_percent_var))
        self.entry_right_p.setFixedWidth(50)
        self.entry_right_p.textChanged.connect(self.on_crop_percent_change)
        crop_layout.addWidget(self.entry_right_p)
        
        crop_layout.addStretch()
        layout.addLayout(crop_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.image_label = CropOverlayLabel(self.tr("no_image"))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self.image_label)
        layout.addWidget(scroll)

    def create_result_frame(self, parent_layout: QVBoxLayout) -> None:
        self.result_group = QGroupBox(self.tr("calc_result"))
        layout = QVBoxLayout(self.result_group)
        parent_layout.addWidget(self.result_group)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)

    def update_tabs(self) -> None:
        """Update tabs based on configuration."""
        if self.notebook is None:
            return
            
        self._updating_tabs = True
        try:
            config_key = self.current_config_key
            if config_key not in TAB_CONFIGS:
                self.gui_log(f"Invalid cost key '{config_key}' detected, falling back to 43311")
                config_key = "43311"
                self.current_config_key = config_key
                if self.config_combo:
                    self.config_combo.setCurrentText(config_key)
            
            new_config_tab_names = TAB_CONFIGS[config_key]
            
            # Save existing data
            old_data = {}
            for tab_name, content in self.tabs_content.items():
                main_val = content["main_widget"].currentText()
                sub_vals = []
                for stat_widget, val_widget in content["sub_entries"]:
                    sub_vals.append((stat_widget.currentText(), val_widget.text()))
                old_data[tab_name] = {
                    "main_stat": main_val,
                    "substats": sub_vals
                }
            
            # Clear all tabs
            self.notebook.clear()
            self.tabs_content = {}
            
            cost_totals = {}
            for tab_name in new_config_tab_names:
                first_digit = next((ch for ch in tab_name if ch.isdigit()), None)
                if first_digit:
                    cost_totals[first_digit] = cost_totals.get(first_digit, 0) + 1
            cost_counts = {k: 0 for k in cost_totals.keys()}

            for tab_name in new_config_tab_names:
                cost_num = next((ch for ch in tab_name if ch.isdigit()), "1")
                cost_counts[cost_num] = cost_counts.get(cost_num, 0) + 1
                occurrence = cost_counts[cost_num]
                total = cost_totals.get(cost_num, 1)
                cost_key = cost_num if total == 1 else f"{cost_num}_{occurrence}"
                
                # Create Tab Page
                page = QWidget()
                page_layout = QVBoxLayout(page)
                
                # Main Stat
                main_group = QGroupBox(self.tr("main_stat"))
                main_layout = QVBoxLayout(main_group)
                page_layout.addWidget(main_group)
                
                fallback_main_stats = [self.tr("HP"), self.tr("ATK"), self.tr("DEF")]
                translated_main_options = [self.tr(s) for s in MAIN_STAT_OPTIONS.get(cost_num, fallback_main_stats)]
                
                main_combo = QComboBox()
                main_combo.addItems(translated_main_options)
                main_layout.addWidget(main_combo)
                
                # Substats
                sub_group = QGroupBox(self.tr("substats"))
                sub_layout = QGridLayout(sub_group)
                page_layout.addWidget(sub_group)
                
                sub_entries = []
                translated_sub_options = [""] + [self.tr(s) for s in list(SUBSTAT_MAX_VALUES.keys())]
                
                for i in range(5):
                    row = i // 2
                    col = i % 2
                    
                    cell_widget = QWidget()
                    cell_layout = QHBoxLayout(cell_widget)
                    cell_layout.setContentsMargins(0, 0, 0, 0)
                    
                    stat_combo = QComboBox()
                    stat_combo.addItems(translated_sub_options)
                    
                    val_entry = QLineEdit()
                    val_entry.setFixedWidth(60)
                    
                    cell_layout.addWidget(stat_combo)
                    cell_layout.addWidget(val_entry)
                    
                    sub_layout.addWidget(cell_widget, row, col)
                    sub_entries.append((stat_combo, val_entry))
                
                page_layout.addStretch()
                
                # Add to Notebook
                tab_label = tab_name
                if "cost" in tab_name:
                    try:
                        parts = tab_name.split('_')
                        c_num = parts[0].replace("cost", "")
                        base_label = self.tr("cost_echo", c_num)
                        
                        suffix = ""
                        if len(parts) >= 3 and parts[2].isdigit():
                            suffix = f" {parts[2]}"
                        
                        tab_label = f"{base_label}{suffix}"
                    except Exception:
                        pass

                self.notebook.addTab(page, tab_label)
                
                self.tabs_content[tab_name] = {
                    "cost": cost_num,
                    "cost_key": cost_key,
                    "main_widget": main_combo,
                    "sub_entries": sub_entries
                }
                
                # Restore data
                if tab_name in old_data:
                    data = old_data[tab_name]
                    main_combo.setCurrentText(data["main_stat"])
                    for i, (s_val, v_val) in enumerate(data["substats"]):
                        if i < len(sub_entries):
                            sub_entries[i][0].setCurrentText(s_val)
                            sub_entries[i][1].setText(v_val)

        except Exception as e:
            self.gui_log(f"Tab update error: {e}")
        finally:
            self._updating_tabs = False

    def update_ui_mode(self) -> None:
        """Update the UI mode (OCR vs Manual)."""
        mode = self.mode_var
        if mode == "ocr":
            self.image_frame.setVisible(True)
        else:
            self.image_frame.setVisible(False)

    def retranslate_ui(self) -> None:
        """Update all UI text based on the current language."""
        if hasattr(self, "settings_group") and self.settings_group: self.settings_group.setTitle(self.tr("basic_settings"))
        if hasattr(self, "lbl_cost_config") and self.lbl_cost_config: self.lbl_cost_config.setText(self.tr("cost_config"))
        if hasattr(self, "lbl_character") and self.lbl_character: self.lbl_character.setText(self.tr("character"))
        if hasattr(self, "lbl_language") and self.lbl_language: self.lbl_language.setText(self.tr("language"))
        if hasattr(self, "lbl_input_mode") and self.lbl_input_mode: self.lbl_input_mode.setText(self.tr("input_mode"))
        if hasattr(self, "rb_manual") and self.rb_manual: self.rb_manual.setText(self.tr("manual"))
        if hasattr(self, "rb_ocr") and self.rb_ocr: self.rb_ocr.setText(self.tr("ocr"))
        if hasattr(self, "cb_auto_main") and self.cb_auto_main: self.cb_auto_main.setText(self.tr("auto_main"))
        if hasattr(self, "lbl_calc_mode") and self.lbl_calc_mode: self.lbl_calc_mode.setText(self.tr("calc_mode"))
        if hasattr(self, "rb_batch") and self.rb_batch: self.rb_batch.setText(self.tr("batch"))
        if hasattr(self, "rb_single") and self.rb_single: self.rb_single.setText(self.tr("single_only"))
        if hasattr(self, "lbl_calc_methods") and self.lbl_calc_methods: self.lbl_calc_methods.setText(self.tr("calc_methods"))
        
        # Calc Methods Checkboxes
        if hasattr(self, "cb_method_normalized") and self.cb_method_normalized: self.cb_method_normalized.setText(self.tr("method_normalized"))
        if hasattr(self, "cb_method_ratio") and self.cb_method_ratio: self.cb_method_ratio.setText(self.tr("method_ratio"))
        if hasattr(self, "cb_method_roll") and self.cb_method_roll: self.cb_method_roll.setText(self.tr("method_roll"))
        if hasattr(self, "cb_method_effective") and self.cb_method_effective: self.cb_method_effective.setText(self.tr("method_effective"))
        if hasattr(self, "cb_method_cv") and self.cb_method_cv: self.cb_method_cv.setText(self.tr("method_cv"))
        
        # Image Area
        if hasattr(self, "image_frame") and self.image_frame: self.image_frame.setTitle(self.tr("ocr_image"))
        if hasattr(self, "btn_load") and self.btn_load: self.btn_load.setText(self.tr("load_image"))
        if hasattr(self, "btn_paste") and self.btn_paste: self.btn_paste.setText(self.tr("paste_clipboard"))
        if hasattr(self, "btn_crop") and self.btn_crop: self.btn_crop.setText(self.tr("perform_crop"))
        if hasattr(self, "lbl_crop_mode") and self.lbl_crop_mode: self.lbl_crop_mode.setText(self.tr("crop_mode"))
        if hasattr(self, "rb_crop_drag") and self.rb_crop_drag: self.rb_crop_drag.setText(self.tr("drag"))
        if hasattr(self, "rb_crop_percent") and self.rb_crop_percent: self.rb_crop_percent.setText(self.tr("percent"))
        if hasattr(self, "lbl_top_percent") and self.lbl_top_percent: self.lbl_top_percent.setText(self.tr("top_percent"))
        if hasattr(self, "lbl_right_percent") and self.lbl_right_percent: self.lbl_right_percent.setText(self.tr("right_percent"))
        
        # Results & Logs
        if hasattr(self, "result_group") and self.result_group: self.result_group.setTitle(self.tr("calc_result"))
        if hasattr(self, "log_group") and self.log_group: self.log_group.setTitle(self.tr("log"))
        
        # Buttons Frame
        if hasattr(self, "action_buttons") and self.action_buttons:
            for key, btn in self.action_buttons.items():
                btn.setText(self.tr(key))
        
        self._filter_characters_by_config()
        self.update_tabs()

    # ----------------------------------------------------
    # Consolidated methods from ImageProcessor
    # ----------------------------------------------------
    def import_image(self) -> None:
        """Load one or multiple images for OCR."""
        if not is_pil_installed:
            QMessageBox.critical(self, "Error", "Pillow is not installed. Image operations require Pillow.")
            return
        
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Image File(s)",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*.*)"
        )
        if not file_paths:
            self.gui_log("Image selection was cancelled.")
            return
            
        try:
            if len(file_paths) == 1:
                file_path = file_paths[0]
                if not os.path.isfile(file_path):
                    QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
                    return
                
                image = Image.open(file_path)
                self.process_loaded_image(image, file_path)
            else:
                self.process_batch_images(file_paths)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image(s):\n{e}")
            self.logger.exception(f"Image load error: {e}")
            self.gui_log(f"Image load error: {e}")

    def process_batch_images(self, file_paths: list[str]) -> None:
        self.gui_log(f"Starting batch processing of {len(file_paths)} images...")
        assigned_tabs = set()
        successful_count = 0
        
        for file_path in file_paths:
            try:
                if not os.path.isfile(file_path):
                    continue
                    
                image = Image.open(file_path)
                image.load()
                filename = os.path.basename(file_path)
                
                if self.crop_mode_var == "percent":
                    top_p = self.crop_top_percent_var
                    right_p = self.crop_right_percent_var
                    cropped_img = crop_image_by_percent(image, top_p, right_p)
                else:
                    cropped_img = image.copy()
                
                ocr_text = self._perform_ocr(cropped_img)
                if not ocr_text:
                    self.gui_log(f"[{filename}] OCR failed: No text detected.")
                    continue
                    
                cost = self.detect_cost_from_ocr(ocr_text)
                
                target_tab = None
                if cost:
                    self.gui_log(f"[{filename}] Detected Cost: {cost}")
                    target_tab = self._find_free_tab_for_cost(cost, assigned_tabs)
                else:
                    self.gui_log(f"[{filename}] Cost not detected. Attempting to assign to first available empty slot.")
                    target_tab = self._find_any_free_tab(assigned_tabs)
                
                if target_tab:
                    self.gui_log(f"[{filename}] Assigning to tab: {target_tab}")
                    assigned_tabs.add(target_tab)
                    
                    substats, logs = self.parse_substats_from_ocr(ocr_text, self.language)
                    self._populate_tab_data(target_tab, substats)
                    self.save_tab_image(target_tab, image.copy(), cropped_img.copy())
                    
                    current_tab = self.get_selected_tab_name()
                    if current_tab and current_tab == target_tab:
                        self.original_image = image.copy()
                        self.loaded_image = cropped_img.copy()
                        self.display_image_preview(self.loaded_image)
                    
                    successful_count += 1
                else:
                     self.gui_log(f"[{filename}] No suitable free tab found (Cost: {cost if cost else 'Unknown'}). Skipping.")
                
            except Exception as e:
                self.gui_log(f"Error processing {file_path}: {e}")
                
        self.gui_log(f"Batch processing completed. {successful_count}/{len(file_paths)} images processed.")

    def _find_free_tab_for_cost(self, cost: str, exclude_tabs: set) -> Optional[str]:
        config_key = self.current_config_key
        if config_key not in TAB_CONFIGS:
             return None
             
        tab_keys = TAB_CONFIGS[config_key]
        for key in tab_keys:
            if key in exclude_tabs:
                continue
            
            content = self.tabs_content.get(key)
            if not content:
                continue
                
            tab_cost = content.get("cost")
            if tab_cost != cost:
                continue
            
            return key
        return None

    def _find_any_free_tab(self, exclude_tabs: set) -> Optional[str]:
        config_key = self.current_config_key
        if config_key not in TAB_CONFIGS:
             return None
        
        for key in TAB_CONFIGS[config_key]:
            if key not in exclude_tabs:
                return key
        return None

    def _populate_tab_data(self, tab_name: str, substats: list) -> None:
        if tab_name not in self.tabs_content:
            return
            
        content = self.tabs_content[tab_name]
        sub_entries = content["sub_entries"]
        
        for stat_widget, val_widget in sub_entries:
            stat_widget.setCurrentIndex(0)
            val_widget.clear()
            
        for i, substat_data in enumerate(substats):
            if i < len(sub_entries):
                stat_found = substat_data.get("stat", "")
                num_found = substat_data.get("value", "")
                
                translated_stat = self.tr(stat_found)
                sub_entries[i][0].setCurrentText(translated_stat)
                sub_entries[i][1].setText(num_found)

    def paste_from_clipboard(self) -> None:
        """Load image from the clipboard."""
        if not is_pil_installed:
            QMessageBox.critical(self, "Error", "Pillow is not installed. Image operations require Pillow.")
            return
        
        try:
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            
            if mime_data.hasImage():
                image = ImageGrab.grabclipboard()
                if isinstance(image, Image.Image):
                    self.process_loaded_image(image, "clipboard image")
                else:
                    self.gui_log("No compatible image found on clipboard via PIL.")
            else:
                self.gui_log("No image found on the clipboard.")
        except Exception as e:
            self.logger.exception(f"Error loading image from clipboard: {e}")
            self.gui_log(f"Error loading image from clipboard: {e}")
    
    def process_loaded_image(self, image: Any, source_name: str) -> None:
        """Common image loading process."""
        tab_name = self.get_selected_tab_name()
        if not tab_name:
            QMessageBox.warning(self, "Warning", "Please select a tab to associate the image with.")
            return

        self.original_image = image.copy()
        self.apply_cropped_image(image)
        self.gui_log(f"Image loaded: {source_name}")
    
    def perform_crop(self) -> None:
        """Perform cropping based on the current mode."""
        if self.original_image is None:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return

        mode = self.crop_mode_var
        if mode == "percent":
            self.apply_percent_crop()
        else:
            self.open_crop_dialog()
    
    def apply_percent_crop(self) -> None:
        """Perform cropping by percentage."""
        try:
            top_p = self.crop_top_percent_var
            right_p = self.crop_right_percent_var
            
            cropped = crop_image_by_percent(self.original_image, top_p, right_p)
            self.gui_log(f"Applied percent crop: Top {top_p}%, Right {right_p}%")
            self.apply_cropped_image(cropped)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error applying percent crop: {e}")
            self.logger.exception(f"Percent crop error: {e}")
            self.gui_log(f"Percent crop error: {e}")
    
    def open_crop_dialog(self) -> None:
        """Open a crop dialog for the current original image."""
        if self.original_image is None:
            QMessageBox.warning(self, "Warning", "No image loaded.")
            return
            
        try:
            crop_dialog = CropDialog(self, self.original_image)
            if crop_dialog.exec():
                if crop_dialog.result:
                    if crop_dialog.result[0] == 'coords':
                        _, left, top, right, bottom = crop_dialog.result
                        try:
                            cropped_img = self.original_image.crop((left, top, right, bottom))
                            self.gui_log(f"Cropped with coordinates: ({left},{top}) - ({right},{bottom})")
                            self.apply_cropped_image(cropped_img)
                        except Exception as ve:
                            QMessageBox.critical(self, "Error", f"Failed to crop with coordinates:\n{ve}")
                            self.logger.exception(f"Coordinate crop error: {ve}")
                            self.gui_log(f"Coordinate crop error: {ve}")
            else:
                self.gui_log("Crop cancelled.")
        except Exception as e:
            self.logger.exception(f"Crop dialog error: {e}")
            self.gui_log(f"Crop dialog error: {e}")
    
    def apply_cropped_image(self, cropped_img: Any) -> None:
        """Save, display, and run OCR on the cropped image."""
        tab_name = self.get_selected_tab_name()
        if not tab_name:
            return

        stored_original = self.original_image.copy()
        stored_cropped = cropped_img.copy()
        self.loaded_image = stored_cropped.copy()
        
        self.save_tab_image(tab_name, stored_original, stored_cropped)
        self.display_image_preview(self.loaded_image)
        
        ocr_text = self._perform_ocr(cropped_img)
        if ocr_text is not None:
            substats, log_messages = self.parse_substats_from_ocr(ocr_text, self.language)
            self.on_ocr_completed(substats, log_messages)
    
    def display_image_preview(self, image: Any) -> None:
        """Update the image preview label."""
        if not is_pil_installed or self.image_label is None or image is None:
            return
        
        try:
            image_hash_data = (image.mode, image.size, hashlib.md5(image.tobytes()).hexdigest())
            
            if image_hash_data == self._last_displayed_image_hash and self._last_image_preview is not None:
                self.image_label.setPixmap(self._last_image_preview)
                self.image_label.setText("")
                if isinstance(self.image_label, CropOverlayLabel):
                    self.image_label.clear_overlay()
                return
            
            qim = ImageQt.ImageQt(image)
            pixmap = QPixmap.fromImage(qim)
            
            scaled_pixmap = pixmap.scaled(
                self.IMAGE_PREVIEW_MAX_WIDTH, 
                self.IMAGE_PREVIEW_MAX_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self._image_preview = scaled_pixmap
            self._last_displayed_image_hash = image_hash_data
            self._last_image_preview = scaled_pixmap
            
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setText("")
            # Clear any crop overlay when showing a finalised (cropped) image
            if isinstance(self.image_label, CropOverlayLabel):
                self.image_label.clear_overlay()
        except Exception as e:
            self.logger.exception(f"Image preview update error: {e}")
            self.gui_log(f"Image preview update error: {e}")
    
    def perform_crop_preview(self) -> None:
        """Show the original image with a crop-boundary overlay.

        Unlike apply_percent_crop(), this does NOT commit the crop — it just
        gives the user a visual hint of where the crop will land.
        """
        if self.original_image is None or self.image_label is None:
            return
        if not isinstance(self.image_label, CropOverlayLabel):
            return
        try:
            top_p = self.crop_top_percent_var
            right_p = self.crop_right_percent_var

            # --- Display the full original image ---
            if is_pil_installed:
                qim = ImageQt.ImageQt(self.original_image)
                pixmap = QPixmap.fromImage(qim)
                scaled = pixmap.scaled(
                    self.IMAGE_PREVIEW_MAX_WIDTH,
                    self.IMAGE_PREVIEW_MAX_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled)
                self.image_label.setText("")

            # --- Compute crop rectangle as fractions of the original image ---
            # crop_image_by_percent takes the top-right corner:
            #   left  = w * (1 - right_p/100)  → left_f  = 1 - right_p/100
            #   top   = 0                        → top_f   = 0.0
            #   right = w                        → right_f = 1.0
            #   bottom= h * top_p/100            → bottom_f= top_p/100
            left_f   = 1.0 - (right_p / 100.0)
            top_f    = 0.0
            right_f  = 1.0
            bottom_f = top_p / 100.0

            # Clamp to valid range
            left_f   = max(0.0, min(1.0, left_f))
            bottom_f = max(0.0, min(1.0, bottom_f))

            self.image_label.set_crop_overlay(left_f, top_f, right_f, bottom_f)
        except Exception as e:
            self.logger.debug(f"Crop preview error: {e}")
    
    def perform_image_preview_update_on_resize(self) -> None:
        """Update the image preview on resize."""
        if self.loaded_image is not None:
            self.display_image_preview(self.loaded_image)

    # ----------------------------------------------------
    # Consolidated methods from AppLogic
    # ----------------------------------------------------
    def _perform_ocr(self, image: Any) -> Optional[str]:
        start_time = time.time()
        if not is_pytesseract_installed:
            self.gui_log(self.tr("pytesseract_not_installed"))
            return None

        if ScoreCalculatorApp._tesseract_cmd_cached:
            pytesseract.pytesseract.tesseract_cmd = ScoreCalculatorApp._tesseract_cmd_cached
        else:
            current_tcmd = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
            if current_tcmd and (os.path.sep in str(current_tcmd) or os.path.isabs(str(current_tcmd))):
                if not os.path.isfile(current_tcmd):
                    found = shutil.which("tesseract")
                    if found:
                        pytesseract.pytesseract.tesseract_cmd = found
                        self.gui_log(self.tr("tesseract_found_path", found))
                    else:
                        self.gui_log(self.tr("ocr_tesseract_not_found", current_tcmd))
                        return None
                ScoreCalculatorApp._tesseract_cmd_cached = pytesseract.pytesseract.tesseract_cmd
            else:
                found = shutil.which("tesseract")
                if found:
                    pytesseract.pytesseract.tesseract_cmd = found
                    self.gui_log(self.tr("tesseract_found_path", found))
                    ScoreCalculatorApp._tesseract_cmd_cached = found
                else:
                    self.gui_log(self.tr("tesseract_not_found_sys"))
                    return None

        try:
            processed = self._preprocess_for_ocr(image)
            custom_config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
            ocr_text = pytesseract.image_to_string(processed, lang="jpn+eng", config=custom_config)
            end_time = time.time()
            self.gui_log(f"OCR process took {end_time - start_time:.2f} seconds.")
            return ocr_text
        except pytesseract.TesseractError as te:
            self.show_ocr_error_message(self.tr("ocr_error_title"), self.tr("ocr_lang_data_error", te))
            self.gui_log(self.tr("ocr_lang_data_error_log", te))
        except FileNotFoundError as fnf:
            self.show_ocr_error_message(self.tr("ocr_error_title"), self.tr("tesseract_exec_not_found", fnf))
            self.gui_log(self.tr("tesseract_exec_error_log", fnf))
        except Exception as ocr_error:
            self.show_ocr_error_message(self.tr("ocr_error_title"), self.tr("ocr_process_error", ocr_error))
            self.gui_log(self.tr("ocr_process_error_log", ocr_error))
        return None

    def _preprocess_for_ocr(self, image: Any) -> Any:
        if not is_pil_installed or image is None:
            return image
        processed = image.convert("L")
        max_side = max(processed.size)
        if max_side < 1600:
            scale = 2
            processed = processed.resize(
                (processed.width * scale, processed.height * scale),
                Image.Resampling.LANCZOS
            )
        processed = ImageOps.autocontrast(processed)
        processed = ImageEnhance.Contrast(processed).enhance(1.8)
        processed = ImageEnhance.Sharpness(processed).enhance(1.2)
        threshold = 170
        processed = processed.point(lambda p: 255 if p > threshold else 0)
        return processed

    def parse_substats_from_ocr(self, ocr_text: str, language: str) -> tuple[list[dict], list[str]]:
        if not ocr_text or not ocr_text.strip():
            return [], []

        lines = [
            re.sub(r'^[\.\-・\s]+', '', line.strip())
            for line in ocr_text.strip().splitlines()
            if line.strip()
        ]
        last_five = lines[-5:] if len(lines) >= 5 else lines
        
        alias_pairs = ScoreCalculatorApp._ALIAS_PAIRS_CACHED
        found_substats = []
        log_messages = []

        for i, line in enumerate(last_five):
            stat_found = ""
            num_found = ""
            is_percent = False
            for stat, alias in alias_pairs:
                if alias in line:
                    stat_found = stat
                    nums = re.findall(r"[\d\.]+", line.replace('％', '%'))
                    if nums:
                        num_found = nums[0]
                        if "%" in line or "％" in line or "パーセント" in line:
                            is_percent = True
                    break
            
            if stat_found:
                found_substats.append({"stat": stat_found, "value": num_found})
                stat_name_for_log = self.tr(stat_found)
                log_messages.append(self.tr("ocr_auto_fill_success", i+1, stat_name_for_log, num_found, "%" if is_percent else ""))
        
        return found_substats, log_messages

    def detect_cost_from_ocr(self, ocr_text: str) -> Optional[str]:
        if not ocr_text:
            return None
        
        cost_pattern = re.compile(r'(?:COST|Cost|cost|コスト)[\s:.]*([134])')
        match = cost_pattern.search(ocr_text)
        if match:
            return match.group(1)
            
        if "Overlord" in ocr_text or "怒涛" in ocr_text or "海嘯" in ocr_text: 
             return "4"
        if "Elite" in ocr_text or "巨浪" in ocr_text:
             return "3"
        if "Common" in ocr_text or "軽波" in ocr_text:
             return "1"
             
        return None

    def _save_character_profile(self, name: str, costkey: str, mainstats: dict, weights: dict) -> None:
        try:
            base_dir = get_app_path()
            folder_name = "character_settings_jsons"
            target_dir = os.path.join(base_dir, folder_name)
            os.makedirs(target_dir, exist_ok=True)
            
            japanese_name_for_file = get_char_japanese_name(name)
            safe_name = self._sanitize_filename(japanese_name_for_file) or "character"
            file_path = os.path.join(target_dir, f"{safe_name}_character.json")
            
            normalized_key = self._normalize_cost_key(costkey, "43311")
            
            payload = {
                "character": name,
                "character_jp": japanese_name_for_file,
                "costkey": costkey,
                "config": normalized_key,
                "character_mainstats": mainstats,
                "character_weights": weights
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            
            self.gui_log(f"Character profile saved: {name} -> {file_path}")
            self.on_character_profile_saved(name, normalized_key)
            
        except Exception as e:
            self.gui_log(f"Error saving character profile: {e}")

    def _load_character_profiles(self) -> tuple[dict[str, str], list[tuple[str, str]]]:
        character_config_map = {}
        items_to_add = []

        try:
            base_dir = get_app_path()
            folder_name = "character_settings_jsons"
            target_dir = os.path.join(base_dir, folder_name)
            
            from constants import _CHAR_NAME_MAP_EN_TO_JP
            predefined_chars = [name for name in _CHAR_NAME_MAP_EN_TO_JP.keys() if name in CHARACTER_STAT_WEIGHTS]
            for char_name in predefined_chars:
                items_to_add.append((self.tr(char_name), char_name))

            if not os.path.exists(target_dir):
                self.gui_log(f"Character settings folder not found: {target_dir}")
                self._character_config_map = character_config_map
                self._update_char_combobox(items_to_add, self.character_var)
                return character_config_map, items_to_add

            for filename in os.listdir(target_dir):
                if not filename.endswith("_character.json"):
                    continue
                
                file_path = os.path.join(target_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    char_name_en = data.get("character")
                    char_name_jp = data.get("character_jp")

                    if not char_name_en and char_name_jp:
                        char_name_en = get_char_internal_name(char_name_jp)
                    elif not char_name_jp and char_name_en:
                        derived_jp_name = get_char_japanese_name(char_name_en)
                        if derived_jp_name == char_name_en:
                            char_name_jp = self.tr(char_name_en)
                        else:
                            char_name_jp = derived_jp_name
                    
                    if not (char_name_en and char_name_jp):
                        continue
                    
                    CHARACTER_STAT_WEIGHTS[char_name_en] = data.get("character_weights", {})
                    CHARACTER_MAIN_STATS[char_name_en] = data.get("character_mainstats", {})
                    config = data.get("config") or data.get("costkey") or "43311"
                    normalized_config = self._normalize_cost_key(config, "43311")
                    character_config_map[char_name_en] = normalized_config

                    if not any(item for item in items_to_add if item[1] == char_name_en):
                        items_to_add.append((char_name_jp, char_name_en))
                    
                    self.gui_log(f"Loaded character file: {char_name_en} ({filename})")

                except Exception as e:
                    self.gui_log(f"Warning: Error loading character file ({filename}): {e}")
            
            items_to_add.sort(key=lambda x: x[0])
            self.gui_log(f"Character list prepared: {len(items_to_add)} characters")
            self._character_config_map = character_config_map
            self._update_char_combobox(items_to_add, self.character_var)
            return character_config_map, items_to_add
            
        except Exception as e:
            self.gui_log(f"Error loading character profiles: {e}")
            return {}, []

    def _filter_characters_by_config(self) -> None:
        try:
            current_key = self.current_config_key
            allowed = [name for name, cfg in self._character_config_map.items() if cfg == current_key]
            
            items_to_add = []
            if allowed:
                items_to_add = sorted([(self.tr(char_name), char_name) for char_name in allowed], key=lambda x: x[0])
            else:
                items_to_add = sorted([(self.tr(char_name), char_name) for char_name in CHARACTER_STAT_WEIGHTS.keys()], key=lambda x: x[0])
            
            current_internal_name = self.character_var
            self._update_char_combobox(items_to_add, current_internal_name)

        except Exception as e:
            self.logger.exception(f"Failed to filter characters by config: {e}")

    def save_data(self, file_path: str, config_key: str, character_var: str, auto_apply: bool, score_mode: str, tabs_content: dict) -> None:
        if not file_path:
            return
        try:
            data = {
                "config": config_key,
                "character": character_var,
                "character_jp": get_char_japanese_name(character_var) if character_var else None,
                "auto_apply": auto_apply,
                "score_mode": score_mode,
                "echoes": {}
            }
            for tab_name, content in tabs_content.items():
                echo_data = {
                    "main_stat": content.get("main_stat", ""),
                    "substats": content.get("substats", [])
                }
                data["echoes"][tab_name] = echo_data
                
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.show_info_message("Success", "Data saved successfully.")
            self.gui_log(f"Saved to: {file_path}")
        except Exception as e:
            self.show_info_message("Error", f"Save failed: {e}")
            self.gui_log(f"Save error: {e}")

    def _load_data(self, file_path: str) -> Optional[dict]:
        if not file_path:
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            character_name_jp = data.get('character_jp')
            character_name = data.get('character')
            
            if character_name and character_name_jp:
                from constants import _CHAR_NAME_MAP_JP_TO_EN, _CHAR_NAME_MAP_EN_TO_JP
                if character_name_jp not in _CHAR_NAME_MAP_JP_TO_EN:
                    _CHAR_NAME_MAP_JP_TO_EN[character_name_jp] = character_name
                if character_name not in _CHAR_NAME_MAP_EN_TO_JP:
                    _CHAR_NAME_MAP_EN_TO_JP[character_name] = character_name_jp
            elif character_name and not character_name_jp:
                character_name_jp = get_char_japanese_name(character_name)
            elif character_name_jp and not character_name:
                character_name = get_char_internal_name(character_name_jp)
            
            if not character_name and character_name_jp:
                character_name = get_char_internal_name(character_name_jp)
            elif not character_name_jp and character_name:
                character_name_jp = get_char_japanese_name(character_name)
            
            if not (character_name and character_name_jp):
                if not character_name_jp and character_name:
                    character_name_jp = character_name
                if not character_name and character_name_jp:
                    character_name = character_name_jp

            custom_weights = data.get("character_weights")
            if custom_weights and character_name:
                CHARACTER_STAT_WEIGHTS[character_name] = custom_weights

            custom_mainstats = data.get("character_mainstats")
            if custom_mainstats and character_name:
                CHARACTER_MAIN_STATS[character_name] = custom_mainstats

            config_value = data.get("config") or data.get("costkey") or "43311"
            normalized_config = self._normalize_cost_key(config_value, "43311")

            echoes_data = data.get("echoes", {})
            for tab_name, echo_data in echoes_data.items():
                main_stat_raw = echo_data.get("main_stat", "")
                resolved_main_stat = self._resolve_stat_name(main_stat_raw)
                echo_data["main_stat"] = resolved_main_stat or main_stat_raw
                
                for substat in echo_data.get("substats", []):
                    stat_name_raw = substat.get("stat", "")
                    resolved_substat = self._resolve_stat_name(stat_name_raw)
                    substat["stat"] = resolved_substat or stat_name_raw

            loaded_ui_data = {
                "character_name": character_name,
                "character_added": "custom" if custom_weights or custom_mainstats else None,
                "auto_apply": data.get("auto_apply", True),
                "score_mode": data.get("score_mode", "batch"),
                "config_key": normalized_config,
                "echoes": echoes_data,
                "force_apply_main_stats": bool(custom_mainstats) or not echoes_data
            }
            
            self.show_info_message("Success", "Data loaded.")
            self.gui_log("Data loading complete.")
            return loaded_ui_data
        except Exception as e:
            self.show_info_message("Error", f"Load failed: {e}")
            self.gui_log(f"Load error: {e}")
            return None

    def _resolve_stat_name(self, raw_name: str) -> Optional[str]:
        if not raw_name:
            return None
        for key, aliases in STAT_ALIASES.items():
            if raw_name == key or self.tr(key) == raw_name:
                return key
            if raw_name in aliases:
                return key
        return None

    def _normalize_cost_key(self, costkey: Any, current_config: str) -> str:
        if isinstance(costkey, str):
            digits = ''.join(ch for ch in costkey if ch.isdigit())
            if digits in TAB_CONFIGS:
                return digits
        elif isinstance(costkey, (list, tuple)):
            digits = ''.join(str(int(c)) for c in costkey)
            if digits in TAB_CONFIGS:
                return digits
        
        if current_config in TAB_CONFIGS:
            return current_config
        return "43311"

    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[^0-9A-Za-z一-龠ぁ-んァ-ヴー_-]', '_', name)

    # ----------------------------------------------------
    # Consolidated methods from ScoreCalculator
    # ----------------------------------------------------
    def calculate_all_scores(self) -> None:
        try:
            character = self.character_var
            weights = CHARACTER_STAT_WEIGHTS.get(character, CHARACTER_STAT_WEIGHTS["General"])
            score_mode = self.score_mode_var
            
            if score_mode == "single":
                self.calculate_single_score(weights, character)
            else:
                self.calculate_batch_scores(weights, character)
        except Exception as e:
            self.logger.exception(f"Score calculation error: {e}")
            self.gui_log(f"Score calculation error:\n{e}")
            QMessageBox.critical(self, "Error", f"An error occurred during score calculation:\n{e}")

    def extract_substats(self, content: dict) -> dict:
        substats = {}
        for stat_widget, value_widget in content["sub_entries"]:
            stat_name = stat_widget.currentText()
            value_str = value_widget.text()
            if stat_name and value_str:
                try:
                    # Look up structural key from translated text
                    internal_stat_name = self._resolve_stat_name(stat_name)
                    if internal_stat_name:
                        value = float(value_str)
                        substats[internal_stat_name] = value
                except ValueError:
                    continue
        return substats
    
    def calculate_single_score(self, weights: dict, character: str) -> None:
        try:
            if self.notebook is None:
                QMessageBox.warning(self, "Warning", "No tab selected.")
                return

            index = self.notebook.currentIndex()
            if index == -1:
                QMessageBox.warning(self, "Warning", "No tab selected.")
                return
                
            tab_name = self.get_selected_tab_name()
            if not tab_name or tab_name not in self.tabs_content:
                QMessageBox.critical(self, "Error", "Tab information not found.")
                return
            
            enabled_methods = self.app_config.enabled_calc_methods
            if not any(enabled_methods.values()):
                QMessageBox.warning(self, self.tr("warning"), self.tr("no_methods_selected"))
                return
            
            content = self.tabs_content[tab_name]
            main_stat = content["main_widget"].currentText()
            
            self.result_text.clear()
            if not main_stat:
                self.result_text.append(f"The main stat for {tab_name} is not entered.")
                return
            
            substats = self.extract_substats(content)
            internal_main_stat = self._resolve_stat_name(main_stat) or main_stat
            echo = EchoData(content["cost"], internal_main_stat, substats)
            
            evaluation = echo.evaluate_comprehensive(weights, enabled_methods)
            html = self._generate_single_score_html(
                character, tab_name, content, main_stat, echo, evaluation
            )
            
            self.result_text.setHtml(html)
            self.save_tab_result(tab_name)
            self.gui_log(f"Individual evaluation for {tab_name} complete.")
            
        except Exception as e:
            self.logger.exception(f"Individual score calculation error: {e}")
            self.gui_log(f"Individual score calculation error: {e}")
            QMessageBox.critical(self, "Error", f"Individual score calculation error:\n{e}")

    def calculate_batch_scores(self, weights: dict, character: str) -> None:
        try:
            enabled_methods = self.app_config.enabled_calc_methods
            if not any(enabled_methods.values()):
                QMessageBox.warning(self, self.tr("warning"), self.tr("no_methods_selected"))
                return
            
            all_evaluations = []
            total_scores = {"total": 0.0}
            for method in ["normalized", "ratio", "roll", "effective", "cv"]:
                if enabled_methods.get(method, False):
                    total_scores[method] = 0.0
            
            calculated_count = 0
            
            for tab_name, content in self.tabs_content.items():
                try:
                    main_stat = content["main_widget"].currentText()
                    if not main_stat:
                        continue
                    
                    substats = self.extract_substats(content)
                    internal_main_stat = self._resolve_stat_name(main_stat) or main_stat
                    echo = EchoData(content["cost"], internal_main_stat, substats)
                    
                    evaluation = echo.evaluate_comprehensive(weights, enabled_methods)
                    
                    eval_data = {
                        "tab_name": tab_name,
                        "effective_count": evaluation['effective_count'],
                        "total": evaluation['total_score'],
                        "recommendation": TRANSLATIONS.get(self.language, TRANSLATIONS["en"])[evaluation['recommendation']]
                    }
                    
                    for method, score in evaluation['individual_scores'].items():
                        eval_data[method] = score
                        total_scores[method] += score
                    
                    all_evaluations.append(eval_data)
                    total_scores["total"] += evaluation['total_score']
                    calculated_count += 1
                    
                except Exception as e:
                    self.logger.exception(f"Calculation error for {tab_name}: {e}")
                    self.gui_log(f"Calculation error for {tab_name}: {e}")
            
            self.result_text.clear()
            if calculated_count == 0:
                self.result_text.setText("No data available.\n")
            else:
                html = self._generate_batch_score_html(
                    character, calculated_count, all_evaluations, total_scores, enabled_methods
                )
                self.result_text.setHtml(html)
                self.gui_log(f"Batch calculation for {character} complete ({calculated_count} echoes).")
                
        except Exception as e:
            self.logger.exception(f"Batch calculation error: {e}")
            self.gui_log(f"Batch calculation error: {e}")
            QMessageBox.critical(self, "Error", f"Batch calculation error:\n{e}")

    def get_score_rating(self, total_score: float) -> str:
        if total_score >= 500: return "rating_sss_global"
        elif total_score >= 450: return "rating_ss_global"
        elif total_score >= 400: return "rating_s_global"
        elif total_score >= 350: return "rating_a_global"
        elif total_score >= 300: return "rating_b_global"
        return "rating_c_global"

    def _get_rating_color(self, rating_text: str) -> str:
        if any(keyword in rating_text for keyword in ["SSS", "Perfect", "God"]): return "#FF4500"
        elif any(keyword in rating_text for keyword in ["SS", "Top", "Excellent"]): return "#FF7F50"
        elif any(keyword in rating_text for keyword in ["S", "Win"]): return "#1E90FF"
        elif any(keyword in rating_text for keyword in ["A", "Good", "Practical"]): return "#32CD32"
        return "#666666"

    def _generate_single_score_html(self, character, tab_name, content, main_stat, echo, evaluation):
        html = f"<h3><u>{character} - {tab_name} Individual Score</u></h3>"
        html += f"<hr>"
        
        html += f"<b>Echo Information</b><br>"
        html += f"Cost: {content['cost']}<br>"
        html += f"Main Stat: {main_stat}<br>"
        html += f"Level: {echo.level}<br>"
        html += f"Number of Effective Substats: {evaluation['effective_count']}<br>"
        
        html += f"<br><b>Substats</b><br>"
        substats = echo.substats
        if substats:
            for name, value in substats.items():
                translated_name = self.tr(name)
                html += f"&nbsp;&nbsp;• {translated_name}: {value}<br>"
        else:
            html += "None<br>"
        html += f"<br><hr>"
        
        html += f"<b>Score by Evaluation Method</b><br>"
        
        def format_score_block(label, score, rating_info, desc):
            block = f"[{label}]<br>"
            block += f"<b>Score: {score:.2f}</b><br>"
            
            if isinstance(rating_info, tuple):
                rating_key = rating_info[0]
                rating_args = rating_info[1:]
                rating_text = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])[rating_key].format(*rating_args)
            else:
                rating_text = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])[rating_info]

            color = self._get_rating_color(rating_text)
            block += f"<span style='color:{color}'>Rating: {rating_text}</span><br>"
            block += f"Description: {desc}<br><br>"
            return block

        method_info = {
            "normalized": {
                "label": self.tr("normalized_score_label"),
                "desc": self.tr("normalized_score_desc"),
                "rating_func": lambda s: echo.get_rating_normalized(s)
            },
            "ratio": {
                "label": self.tr("ratio_score_label"),
                "desc": self.tr("ratio_score_desc"),
                "rating_func": lambda s: echo.get_rating_ratio(s)
            },
            "roll": {
                "label": self.tr("roll_quality_label"),
                "desc": self.tr("roll_quality_desc"),
                "rating_func": lambda s: echo.get_rating_roll(s)
            },
            "effective": {
                "label": self.tr("effective_stat_label"),
                "desc": self.tr("effective_stat_desc"),
                "rating_func": lambda s: echo.get_rating_effective(s, evaluation['effective_count'])
            },
            "cv": {
                "label": self.tr("cv_score_label"),
                "desc": self.tr("cv_score_desc"),
                "rating_func": lambda s: echo.get_rating_cv(s)
            }
        }
        
        for method, score in evaluation['individual_scores'].items():
            if method in method_info:
                info = method_info[method]
                rating = info["rating_func"](score)
                html += format_score_block(info["label"], score, rating, info["desc"])

        html += f"<hr>"
        html += f"<b>Overall Evaluation</b><br>"
        html += f"<b>Total Score: {evaluation['total_score']:.2f}</b><br>"
        
        final_rating = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])[evaluation['rating']]
        final_color = self._get_rating_color(final_rating)
        
        html += f"<span style='color:{final_color}'>Overall Rating: {final_rating}</span><br>"
        html += f"Recommendation: {TRANSLATIONS.get(self.language, TRANSLATIONS['en'])[evaluation['recommendation']]}<br>"
        
        return html

    def _generate_batch_score_html(self, character, calculated_count, all_evaluations, total_scores, enabled_methods):
        html = f"<h3><u>{character} Echo Scores (Batch Calculation)</u></h3>"
        html += f"<hr>"
        html += f"Calculated: {calculated_count} / {len(self.tabs_content)} echoes<br>"
        html += f"<hr>"
        
        method_labels = {
            "normalized": self.tr("method_normalized"),
            "ratio": self.tr("method_ratio"),
            "roll": self.tr("method_roll"),
            "effective": self.tr("method_effective"),
            "cv": self.tr("method_cv")
        }
        
        for i, eval_data in enumerate(all_evaluations, 1):
            html += f"<b>--- Echo {i}: {eval_data['tab_name']} ---</b><br>"
            
            method_num = 1
            for method in ["normalized", "ratio", "roll", "effective", "cv"]:
                if enabled_methods.get(method, False) and method in eval_data:
                    score = eval_data[method]
                    label = method_labels.get(method, method)
                    
                    if method == "effective":
                        html += f"├ [{method_num}] {label}: {score:.2f} ({eval_data['effective_count']} stats)<br>"
                    else:
                        html += f"├ [{method_num}] {label}: {score:.2f}<br>"
                    method_num += 1
            
            score_color = "#666666"
            if eval_data['total'] >= 80: score_color = "#FF4500"
            elif eval_data['total'] >= 70: score_color = "#FF7F50"
            elif eval_data['total'] >= 60: score_color = "#1E90FF"
            elif eval_data['total'] >= 50: score_color = "#32CD32"
            
            html += f"└ <b><span style='color:{score_color}'>Total Score: {eval_data['total']:.2f}</span></b><br>"
            html += f"&nbsp;&nbsp;Recommendation: {eval_data['recommendation']}<br><br>"
        
        html += f"<hr>"
        html += f"<b>Average Scores ({calculated_count} echoes)</b><br>"
        
        for method in ["normalized", "ratio", "roll", "effective", "cv"]:
            if enabled_methods.get(method, False) and method in total_scores:
                avg = total_scores[method] / calculated_count
                label = method_labels.get(method, method)
                html += f"├ {label} Average: {avg:.2f}<br>"
        
        avg_total = total_scores["total"] / calculated_count
        avg_rating = self.get_score_rating(avg_total)
        avg_rating_text = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])[avg_rating]
        avg_color = self._get_rating_color(avg_rating_text)
        
        html += f"└ <b><span style='color:{avg_color}'>Total Average: {avg_total:.2f}</span></b><br>"
        html += f"<span style='color:{avg_color}'>Overall Rating: {avg_rating_text}</span><br>"
        
        return html

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = ScoreCalculatorApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.getLogger(__name__).critical(f"Critical unhandled exception during application startup: {e}", exc_info=True)
        QMessageBox.critical(None, "Fatal Error", f"An unhandled error occurred during application startup:\n{e}\n\nCheck the log file for more details.")
        sys.exit(1)
