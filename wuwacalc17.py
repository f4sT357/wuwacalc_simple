import json
import logging
import os


import sys
import webbrowser

from typing import Any, Callable, Optional

from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QStyleFactory, QComboBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QFont

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



# Import new modules
from score_calculator import ScoreCalculator
from tab_manager import TabManager
from event_handlers import EventHandlers
from ui_components import UIComponents
from image_processor import ImageProcessor
from app_logic import AppLogic

# Tesseract setup
setup_tesseract()

class ScoreCalculatorApp(QMainWindow):

    _ALIAS_PAIRS_CACHED: list[tuple[str, str]] = []

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
        
        # Theme handling
        self._current_app_theme = self.app_config.theme
        self.apply_theme(self._current_app_theme)

        # Cache alias_pairs
        if not ScoreCalculatorApp._ALIAS_PAIRS_CACHED:
            alias_pairs = []
            for stat, aliases in STAT_ALIASES.items():
                for alias in aliases:
                    alias_pairs.append((stat, alias))
            alias_pairs.sort(key=lambda x: -len(x[1]))
            ScoreCalculatorApp._ALIAS_PAIRS_CACHED = alias_pairs

        self.setWindowTitle("Wuthering Waves Echo Score Calculator")
        self.resize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        # Instantiate component modules
        self.score_calc = ScoreCalculator(self)
        self.tab_mgr = TabManager(self)
        self.logic = AppLogic(self.tr)
        self.image_proc = ImageProcessor(self, self.logic)
        self.events = EventHandlers(self)
        self.ui = UIComponents(self)
        self.charcombo = QComboBox() # ScoreCalculatorAppのインスタンス変数としてcharcomboを初期化
        
        # Connect signals from logic to slots in the main app
        self.logic.log_message.connect(self.gui_log)
        self.logic.ocr_error.connect(self.show_ocr_error_message)
        self.logic.info_message.connect(self.show_info_message)
        self.logic.character_profile_saved.connect(self.on_character_profile_saved)
        
        # Connect signals from image processor
        self.image_proc.ocr_completed.connect(self.on_ocr_completed)
        
        # Timer references (using QTimer in PyQt6, handled in events or here)
        self._debounce_timers = {}

        # UI construction
        # UI construction
        self.ui.create_main_layout()
        self.setCentralWidget(self.ui.main_widget)
        
        # Post-initialization setup
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
        
        # Replaced tk.StringVar with simple attributes. 
        # Updates will be handled via signals/slots in EventHandlers.
        self.current_config_key = app_config.current_config_key
        self.mode_var = app_config.mode_var
        
        # Handle both old and new character name formats
        saved_char_name = app_config.character_var
        if saved_char_name:
            # Check if this is already an internal name (exists in mappings)
            from constants import _CHAR_NAME_MAP_EN_TO_JP
            if saved_char_name in _CHAR_NAME_MAP_EN_TO_JP:
                # Already in internal format
                self.character_var = saved_char_name
            else:
                # Might be Japanese name, convert to internal
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
        self.image_label = None # Will be QLabel
        self._image_preview = None
        self._last_displayed_image_hash = None
        self._last_image_preview = None
        self._tab_images = {}
        
        self._tab_results = {}
        self._character_config_map = {}
        
        # UI References (will be populated by UIComponents)
        self.result_text = None
        self.log_text = None
        self.notebook = None
        self.charcombo = None
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
        # Re-apply theme to incorporate font change into stylesheet
        self.apply_theme(self._current_app_theme)

    def apply_theme(self, theme_name: str) -> None:
        """Apply the specified theme."""
        try:
            self._current_app_theme = theme_name
            self.config_manager.update_app_setting("theme", theme_name)
            
            app = QApplication.instance()
            app.setStyle("Fusion")
            self._apply_theme_stylesheet(theme_name) # Unified method call
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
        
        # Base colors (solid or transparent based on settings)
        c_bg = colors['background']
        # Use custom input bg if set, otherwise theme default
        c_input = self.app_config.custom_input_bg_color if self.app_config.custom_input_bg_color else colors['input_bg']
        c_btn = colors['button_bg']
        c_btn_hover = colors['button_hover']
        c_tab = colors['tab_bg']
        c_tab_sel = colors['tab_selected']

        # Use the global text color for buttons and tabs to ensure consistency
        # This allows users to customize all text colors, not just widget text
        button_text_color = self.app_config.text_color
        tab_text_color = self.app_config.text_color

        if bg_image:
            # Resolve relative path
            if not os.path.isabs(bg_image):
                bg_image = os.path.join(get_app_path(), bg_image)

        if bg_image and os.path.exists(bg_image):
            # Use forward slashes for CSS url
            img_path = bg_image.replace("\\", "/")
            main_window_bg = f"border-image: url('{img_path}') 0 0 0 0 stretch stretch;"
            
            # Apply opacity to all elements including input if custom
            c_bg = self._hex_to_rgba(c_bg, alpha)
            c_input = self._hex_to_rgba(c_input, alpha)
            c_btn = self._hex_to_rgba(c_btn, alpha)
            c_btn_hover = self._hex_to_rgba(c_btn_hover, alpha)
            c_tab = self._hex_to_rgba(c_tab, alpha)
            c_tab_sel = self._hex_to_rgba(c_tab_sel, alpha)
        
        
        # Font settings
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

    def _set_light_theme_stylesheet(self) -> None:
        """Sets the light theme stylesheet."""
        colors = THEME_COLORS["light"]
        bg_image = self.app_config.background_image
        
        main_window_bg = ""
        alpha = self.app_config.background_opacity
        
        # Base colors (solid or transparent based on settings)
        c_bg = colors['background']
        c_input = colors['input_bg']
        c_btn = colors['button_bg']
        c_btn_hover = colors['button_hover']
        c_tab = colors['tab_bg']
        c_tab_sel = colors['tab_selected']
        
        if bg_image:
            # Resolve relative path
            if not os.path.isabs(bg_image):
                bg_image = os.path.join(get_app_path(), bg_image)

        if bg_image and os.path.exists(bg_image):
            # Use forward slashes for CSS url
            img_path = bg_image.replace("\\", "/")
            main_window_bg = f"border-image: url('{img_path}') 0 0 0 0 stretch stretch;"
            
            # Apply opacity
            c_bg = self._hex_to_rgba(c_bg, alpha)
            c_input = self._hex_to_rgba(c_input, alpha)
            c_btn = self._hex_to_rgba(c_btn, alpha)
            c_btn_hover = self._hex_to_rgba(c_btn_hover, alpha)
            c_tab = self._hex_to_rgba(c_tab, alpha)
            c_tab_sel = self._hex_to_rgba(c_tab_sel, alpha)

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {colors['background']}; {main_window_bg} color: {self.app_config.text_color}; }}
            QWidget {{ background-color: {c_bg}; color: {self.app_config.text_color}; }}
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background-color: {c_input}; color: {self.app_config.text_color}; border: 1px solid {colors['border']}; }}
            QPushButton {{ background-color: {c_btn}; color: {colors['button_text']}; border: 1px solid {colors['border']}; padding: 5px; }}
            QPushButton:hover {{ background-color: {c_btn_hover}; }}
            QTabWidget::pane {{ border: 1px solid {colors['border']}; background-color: {c_bg}; }}
            QTabBar::tab {{ background: {c_tab}; color: {colors['tab_text']}; padding: 5px; }}
            QTabBar::tab:selected {{ background: {c_tab_sel}; }}
            QGroupBox {{ border: 1px solid {colors['group_border']}; margin-top: 10px; background-color: {c_bg}; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; background-color: transparent; }}
        """)

    def tr(self, key: str, *args: Any) -> str:
        """
        Translate a key with fallback to Japanese and then the key itself.
        """
        # 1. Try target language
        lang_dict = TRANSLATIONS.get(self.language, {})
        text = lang_dict.get(key)
        
        # 2. Fallback to Japanese
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
                # Limit line count if needed, QTextEdit handles it reasonably well but good to prune
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
            
        tab_name = self.tab_mgr.get_selected_tab_name()
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

        combo.blockSignals(True)  # Block signals for individual main stat combo boxes
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
            self.logger.exception(f"Error updating main stat combobox for content {content}: {e}")
        finally:
            combo.blockSignals(False)  # Unblock signals for individual main stat combo boxes

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
        """Checks if Pillow (PIL) is installed."""
        try:
            from PIL import Image
            return True
        except ImportError:
            return False

    def _is_pytesseract_installed(self) -> bool:
        """Checks if pytesseract is installed."""
        try:
            import pytesseract
            return True
        except ImportError:
            return False

    def _is_tesseract_configured(self) -> bool:
        """Checks if Tesseract is correctly configured by trying to get its version."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def _check_and_alert_environment(self) -> None:
        """Environment check."""
        try:
            is_pil_installed = self._is_pillow_installed()
            is_pytesseract_installed = self._is_pytesseract_installed()
            is_tesseract_configured = self._is_tesseract_configured()

            missing_libs = []
            if not is_pil_installed:
                missing_libs.append("Pillow")
            if not is_pytesseract_installed:
                missing_libs.append("pytesseract")
            
            if missing_libs:
                self.gui_log(f"Warning: The following libraries are missing: {', '.join(missing_libs)}")
                self.gui_log("To use the OCR feature, please install these libraries.")
            elif not is_tesseract_configured:
                self.gui_log(f"Warning: Tesseract is not configured correctly.")
                self.gui_log("To use OCR, please install Tesseract and set the path.")
            else:
                self.gui_log("Environment check: OCR feature is available.")
        except Exception as e:
            self.logger.warning(f"Environment check error: {e}", exc_info=True)

    def _post_init_setup(self) -> None:
        """Post-initialization setup."""
        self.events.setup_connections() 
        self.ui.update_tabs()
        self.ui.update_ui_mode()
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

    def update_background_image(self, new_path: str) -> None:
        """Update the background image and re-apply theme."""
        try:
            self.app_config.background_image = new_path
            self.config_manager.update_app_setting("background_image", new_path)
            self.apply_theme(self._current_app_theme)
            self.gui_log(f"Background image updated: {new_path}")
        except Exception as e:
            self.logger.exception(f"Error updating background image: {e}")
            QMessageBox.critical(self, "Settings Error", f"Failed to update background image:\n{e}")

    def update_background_opacity(self, opacity: float) -> None:
        """Update the background opacity and re-apply theme."""
        try:
            self.app_config.background_opacity = opacity
            self.config_manager.update_app_setting("background_opacity", opacity)
            self.apply_theme(self._current_app_theme)
        except Exception as e:
            self.logger.exception(f"Error updating background opacity: {e}")
            QMessageBox.critical(self, "Settings Error", f"Failed to update background opacity:\n{e}")

    def update_text_color(self, new_color: str) -> None:
        """Update the text color and re-apply theme."""
        try:
            self.app_config.text_color = new_color
            self.config_manager.update_app_setting("text_color", new_color)
            self.apply_theme(self._current_app_theme) # Re-apply theme to update colors
            self.gui_log(f"Text color updated to {new_color}")
        except Exception as e:
            self.logger.exception(f"Error updating text color to {new_color}: {e}")
            QMessageBox.critical(self, "Settings Error", f"Failed to update text color:\n{e}")

    def _update_char_combobox(self, items_to_add: list[tuple[str, str]], current_internal_name: str = "") -> None:
        """
        Updates the character combobox with new items and attempts to restore selection.
        :param items_to_add: A list of (translated_name, internal_name) tuples to add to the combobox.
        :param current_internal_name: The internal name of the character to try and select after updating.
        """
        self.gui_log(f"DEBUG: _update_char_combobox - Started. current_internal_name='{current_internal_name}'")

        if self.charcombo is None:
            self.gui_log("DEBUG: _update_char_combobox - self.charcombo is None, returning.")
            return
        
        # Check if the underlying C++ object is still alive
        if not self.charcombo.parent():
            self.gui_log("DEBUG: _update_char_combobox - self.charcombo C++ object is not alive, returning.")
            return

        self.charcombo.blockSignals(True)
        self.charcombo.clear()

        self.gui_log("DEBUG: _update_char_combobox - Adding empty item.")
        self.charcombo.addItem("", userData="")

        for translated_name, char_name in items_to_add:
            self.gui_log(f"DEBUG: _update_char_combobox - Adding item: Display='{translated_name}', Internal='{char_name}'")
            self.charcombo.addItem(translated_name, userData=char_name)
        
        target_index = 0
        if current_internal_name:
            index = self.charcombo.findData(current_internal_name)
            if index != -1:
                target_index = index
                self.gui_log(f"DEBUG: _update_char_combobox - Found '{current_internal_name}' at index {target_index}.")
            else:
                self.gui_log(f"DEBUG: _update_char_combobox - '{current_internal_name}' not found in combobox items.")
        
        self.charcombo.setCurrentIndex(target_index)
        self.charcombo.blockSignals(False)
        self.gui_log(f"DEBUG: _update_char_combobox - Finished. Current selected index: {self.charcombo.currentIndex()}, text: '{self.charcombo.currentText()}' (Internal: '{self.charcombo.currentData()}')")

    def register_char(self, name_jp: str, name_en: str, costkey: str, mainstats: dict, weights: dict) -> None:
        """Register a character's settings."""
        # Use the provided English name as the internal identifier
        internal_char_name = name_en
        
        # Update the character name mappings
        from constants import _CHAR_NAME_MAP_JP_TO_EN, _CHAR_NAME_MAP_EN_TO_JP
        _CHAR_NAME_MAP_JP_TO_EN[name_jp] = internal_char_name
        _CHAR_NAME_MAP_EN_TO_JP[internal_char_name] = name_jp
        
        # Update CHARACTER_STAT_WEIGHTS and CHARACTER_MAIN_STATS
        CHARACTER_STAT_WEIGHTS[internal_char_name] = weights or CHARACTER_STAT_WEIGHTS.get(internal_char_name, CHARACTER_STAT_WEIGHTS["General"])
        CHARACTER_MAIN_STATS[internal_char_name] = mainstats or CHARACTER_MAIN_STATS.get(internal_char_name, {})

        try:
            # Repopulate all characters to ensure the new one appears, maintaining sorting
            items_to_add = sorted([(self.tr(char), char) for char in CHARACTER_STAT_WEIGHTS.keys()], key=lambda x: x[0])
            self._update_char_combobox(items_to_add, internal_char_name)
            self.character_var = internal_char_name # Ensure this is updated after combo box update
        except Exception as e:
            self.logger.exception(f"Failed to update charcombo after registering character: {e}")

        normalized_key = self.logic._normalize_cost_key(costkey, self.current_config_key)
        self.current_config_key = normalized_key
        # Update config combo if exists
        if self.config_combo:
            idx = self.config_combo.findText(normalized_key)
            if idx >= 0:
                self.config_combo.setCurrentIndex(idx)

        self._apply_character_main_stats()
        # Pass the internal_char_name to _save_character_profile
        self._save_character_profile(internal_char_name, costkey, mainstats, weights)

    def _save_character_profile(self, name: str, costkey: str, mainstats: dict, weights: dict) -> None:
        self.logic._save_character_profile(name, costkey, mainstats, weights)

    def _load_character_profiles(self) -> None:
        """Load character profiles from AppLogic and store the config map."""
        config_map, items_to_add = self.logic._load_character_profiles() # items_to_add も取得
        self._character_config_map = config_map
        self.gui_log("Character profiles loaded and map created.")
        
        # 読み込んだキャラクターでコンボボックスを初期化
        self._update_char_combobox(items_to_add, self.character_var)

    def _filter_characters_by_config(self) -> None:
        try:
            current_key = self.current_config_key
            allowed = [name for name, cfg in self._character_config_map.items() if cfg == current_key]
            
            items_to_add = []
            if allowed:
                # Use self.tr for translated display name
                items_to_add = sorted([(self.tr(char_name), char_name) for char_name in allowed], key=lambda x: x[0])
            else:
                # Use self.tr for translated display name for all available characters
                items_to_add = sorted([(self.tr(char_name), char_name) for char_name in CHARACTER_STAT_WEIGHTS.keys()], key=lambda x: x[0])
            
            current_internal_name = self.character_var
            self._update_char_combobox(items_to_add, current_internal_name)

        except Exception as e:
            self.logger.exception(f"Failed to filter characters by config: {e}")

    def _update_tabs(self, *args: Any) -> None:
        """Delegate to UIComponents or TabManager, but currently logic is here."""
        # For PyQt6, we'll delegate this fully to UIComponents or TabManager to avoid clutter here.
        # But since the original code had it here, I'll implement a bridge.
        self.ui.update_tabs()

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = ScoreCalculatorApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        # Log the error before exiting
        logging.getLogger(__name__).critical(f"Critical unhandled exception during application startup: {e}", exc_info=True)
        QMessageBox.critical(None, "Fatal Error", f"An unhandled error occurred during application startup:\n{e}\n\nCheck the log file for more details.")
        sys.exit(1)
