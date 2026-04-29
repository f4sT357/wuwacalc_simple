"""
Event Handling Module (PyQt6)

Provides event callbacks and debounce processing.
"""

import logging
from typing import Any, Optional

from PyQt6.QtWidgets import QMessageBox, QApplication
from PyQt6.QtCore import QTimer

class EventHandlers:
    """Class responsible for event handling."""
    
    def __init__(self, app):
        """
        Initialization
        
        Args:
            app: The main application instance.
        """
        self.app = app
        self.logger = logging.getLogger(__name__)
        
        # Timer references for debouncing
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.actual_save_config)
        
        self._crop_preview_timer = QTimer()
        self._crop_preview_timer.setSingleShot(True)
        self._crop_preview_timer.timeout.connect(self.app.image_proc.perform_crop_preview)
        
        self._resize_preview_timer = QTimer()
        self._resize_preview_timer.setSingleShot(True)
        self._resize_preview_timer.timeout.connect(self.app.image_proc.perform_image_preview_update_on_resize)

    def setup_connections(self) -> None:
        """
        Set up any additional connections not handled in UI creation.
        Most connections are now done in UIComponents.
        """
        pass
    
    def on_config_change(self, text: str) -> None:
        """Rebuild the tab configuration in response to a cost configuration change."""
        self.app.current_config_key = text
        if not getattr(self.app, "_updating_tabs", False):
            self.app.ui.update_tabs()
            self.app.gui_log(f"Cost configuration changed: Tabs updated by {text}")
            self.app._apply_character_main_stats()
            self.app._filter_characters_by_config()
            self.save_config()
    
    def on_character_change(self, text: str) -> None:
        """Handle character change."""
        # Retrieve the internal name directly from the UserData of the selected item
        current_index = self.app.charcombo.currentIndex()
        if current_index >= 0:
            internal_name = self.app.charcombo.itemData(current_index)
            if internal_name: # Ensure internal_name is not empty (e.g., from the initial empty item)
                self.app.character_var = internal_name
                self.app.gui_log(f"Character selected: {internal_name}")
                self.app._apply_character_main_stats()
                self.save_config()
            else:
                # If the empty item is selected, clear character_var
                self.app.character_var = ""
                self.app.gui_log("Character selection cleared.")
                self.app._apply_character_main_stats() # Apply to clear any existing stats
                self.save_config()
    
    def on_language_change(self, text: str) -> None:
        """Handle language change."""
        if text != self.app.language:
            self.app.language = text
            self.save_config()
            QMessageBox.information(
                self.app,
                self.app.tr("language_changed_title"), 
                self.app.tr("language_changed_message")
            )
            self.app.gui_log(f"Language changed to: {text} (will be fully applied after restart)")
    
    def on_mode_change(self, mode: str) -> None:
        """Handle input mode change."""
        self.app.mode_var = mode
        self.app.ui.update_ui_mode()
        self.save_config()

    def on_auto_main_change(self, checked: bool) -> None:
        self.app.auto_apply_main_stats = checked
        self.save_config()

    def on_score_mode_change(self, mode: str) -> None:
        self.app.score_mode_var = mode
        self.save_config()
    
    def on_calc_method_changed(self) -> None:
        """Handle calculation method checkbox changes."""
        # Get current checkbox states
        enabled_methods = {
            "normalized": self.app.cb_method_normalized.isChecked(),
            "ratio": self.app.cb_method_ratio.isChecked(),
            "roll": self.app.cb_method_roll.isChecked(),
            "effective": self.app.cb_method_effective.isChecked(),
            "cv": self.app.cb_method_cv.isChecked()
        }
        
        # Validate that at least one method is enabled
        if not any(enabled_methods.values()):
            # Show warning and re-enable the last unchecked method
            QMessageBox.warning(
                self.app,
                self.app.tr("warning"),
                self.app.tr("no_methods_selected")
            )
            # Re-enable the checkbox that was just unchecked
            sender = self.app.sender()
            if sender:
                sender.setChecked(True)
            return
        
        # Update config
        self.app.app_config.enabled_calc_methods = enabled_methods
        self.save_config()
        self.app.gui_log(f"Calculation methods updated: {[k for k, v in enabled_methods.items() if v]}")

    def on_crop_mode_change(self, mode: str) -> None:
        self.app.crop_mode_var = mode
        self.save_config()

    def on_crop_percent_change(self, text: str) -> None:
        try:
            # Update the var
            if self.app.ui.entry_top_p == self.app.sender():
                self.app.crop_top_percent_var = float(text)
            elif self.app.ui.entry_right_p == self.app.sender():
                self.app.crop_right_percent_var = float(text)
            
            self.save_config()
            self.schedule_crop_preview()
        except ValueError:
            pass # Ignore invalid float input

    def on_tab_changed(self, index: int) -> None:
        """Handle tab switch."""
        tab_name = self.app.tab_mgr.get_selected_tab_name()
        if tab_name:
            self.app.tab_mgr.show_tab_image(tab_name)
            self.app.tab_mgr.show_tab_result(tab_name)
    
    def cycle_theme(self) -> None:
        """Cycle between light, dark, and clear themes."""
        current = self.app._current_app_theme
        if current == "dark":
            new_theme = "light"
        elif current == "light":
            new_theme = "clear"
        else:
            new_theme = "dark"
            
        self.app.gui_log(f"Theme changed to {new_theme} mode.")
        self.app.apply_theme(new_theme)
        self.save_config()
    
    def save_config(self) -> None:
        """Schedule config save with debounce."""
        self._save_timer.start(500) # 500ms
    
    def actual_save_config(self) -> None:
        """Save current settings to config.json."""
        try:
            self.app.config_manager.update_app_setting('language', self.app.language)
            self.app.config_manager.update_app_setting('crop_mode', self.app.crop_mode_var)
            self.app.config_manager.update_app_setting('crop_top_percent', self.app.crop_top_percent_var)
            self.app.config_manager.update_app_setting('crop_right_percent', self.app.crop_right_percent_var)
            self.app.config_manager.update_app_setting('current_config_key', self.app.current_config_key)
            self.app.config_manager.update_app_setting('character_var', self.app.character_var)
            self.app.config_manager.update_app_setting('mode_var', self.app.mode_var)
            self.app.config_manager.update_app_setting('score_mode_var', self.app.score_mode_var)
            self.app.config_manager.update_app_setting('auto_apply_main_stats', self.app.auto_apply_main_stats)
            self.app.config_manager.update_app_setting('enabled_calc_methods', self.app.app_config.enabled_calc_methods)
            
            self.app.config_manager.save()
            self.logger.info("Config saved.")
        except Exception as e:
            self.app.gui_log(f"Config save error: {e}")
    
    def schedule_crop_preview(self) -> None:
        """Schedule crop preview update."""
        self._crop_preview_timer.start(100)
    
    def schedule_image_preview_update_on_resize(self, *args: Any) -> None:
        """Schedule image preview update on resize."""
        self._resize_preview_timer.start(100)
