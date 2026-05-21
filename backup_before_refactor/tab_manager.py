"""
Tab Management Module (PyQt6)

Provides functions for managing, saving, restoring, clearing, and exporting tab data.
"""

import logging
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import QMessageBox, QFileDialog
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt

class TabManager:
    """Class responsible for managing tab data."""
    
    def __init__(self, app):
        """
        Initialization
        
        Args:
            app: The main application instance.
        """
        self.app = app
        self.logger = logging.getLogger(__name__)
        
        # Data storage for each tab
        self._tab_images: Dict[str, Dict[str, Any]] = {}
        self._tab_results: Dict[str, Dict[str, Any]] = {}
    
    def get_selected_tab_name(self) -> Optional[str]:
        """Get the internal key of the currently selected tab."""
        if self.app.notebook is None:
            return None
        index = self.app.notebook.currentIndex()
        if index == -1:
            return None
            
        # Return internal key from config instead of localized label
        config_key = self.app.current_config_key
        # We need direct access to TAB_CONFIGS constants
        # It's better to import it inside method or use app attribute if stored
        from constants import TAB_CONFIGS
        if config_key in TAB_CONFIGS:
             keys = TAB_CONFIGS[config_key]
             if index < len(keys):
                 return keys[index]
        
        # Fallback to tabText if something fails (though this shouldn't happen)
        return self.app.notebook.tabText(index)
    
    def show_tab_image(self, tab_name: str) -> None:
        """Display the image saved in the tab."""
        if self.app.image_label is None:
            return
        data = self._tab_images.get(tab_name)
        if data and data.get("cropped") is not None:
            self.app.loaded_image = data["cropped"].copy()
            self.app.original_image = data["original"].copy()
            self.app.image_proc.display_image_preview(self.app.loaded_image)
        else:
            self.app.loaded_image = None
            self.app.original_image = None
            self.app.image_label.setText("No image loaded")
            self.app.image_label.setPixmap(QPixmap()) # Clear image
    
    def save_tab_result(self, tab_name: str) -> None:
        """Save the current calculation result for each tab."""
        if self.app.result_text is None:
            return
        try:
            result_content = self.app.result_text.toHtml()
            self._tab_results[tab_name] = {
                "content": result_content
            }
        except Exception as e:
            self.logger.warning(f"Failed to save tab result: {e}", exc_info=True)
    
    def show_tab_result(self, tab_name: str) -> None:
        """Restore the saved calculation result."""
        if self.app.result_text is None:
            return
        
        result_data = self._tab_results.get(tab_name)
        if result_data:
            try:
                self.app.result_text.setHtml(result_data["content"])
            except Exception as e:
                self.logger.warning(f"Failed to restore tab result: {e}", exc_info=True)
        else:
            self.app.result_text.clear()
    
    def clear_current_tab(self) -> None:
        """Clear the contents of the current tab only."""
        try:
            tab_name = self.get_selected_tab_name()
            if not tab_name or tab_name not in self.app.tabs_content:
                return
            
            content = self.app.tabs_content[tab_name]
            # Reset widgets
            content["main_widget"].setCurrentIndex(-1)
            for stat_widget, val_widget in content["sub_entries"]:
                stat_widget.setCurrentIndex(-1)
                val_widget.clear()
            
            # Also clear the image
            if tab_name in self._tab_images:
                del self._tab_images[tab_name]
            # Also clear the calculation result
            if tab_name in self._tab_results:
                del self._tab_results[tab_name]
            
            self.show_tab_image(tab_name)
            self.show_tab_result(tab_name)
            
            self.app.gui_log(f"Cleared the contents of tab '{tab_name}'.")
        except Exception as e:
            error_msg = f"Failed to clear tab: {e}"
            QMessageBox.critical(self.app, "Error", error_msg)
            self.logger.exception(f"Tab clear error: {e}")
    
    def clear_all(self) -> None:
        """Reset all tabs, text, logs, input values, etc."""
        try:
            # Reset all tab contents
            for content in self.app.tabs_content.values():
                content["main_widget"].setCurrentIndex(-1)
                for stat_widget, val_widget in content["sub_entries"]:
                    stat_widget.setCurrentIndex(-1)
                    val_widget.clear()
            
            if self.app.result_text:
                self.app.result_text.clear()
            if self.app.log_text:
                self.app.log_text.clear()
                
            self.app.loaded_image = None
            self.app.original_image = None
            self.app._image_preview = None
            self._tab_images.clear()
            self._tab_results.clear()
            
            if self.app.image_label:
                self.app.image_label.setText("No image loaded")
                self.app.image_label.setPixmap(QPixmap())
                
            self.app.gui_log("All items have been cleared.")
        except Exception as e:
            error_msg = f"Failed to reset items: {e}"
            QMessageBox.critical(self.app, "Clear Error", error_msg)
            self.logger.exception(f"Clear all error: {e}")
    
    def export_result_to_txt(self) -> None:
        """Export the score calculation result to a text file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self.app, "Save Result", "", "Text Files (*.txt);;All Files (*.*)"
            )
            if not file_path:
                return
            text = self.app.result_text.toPlainText()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            QMessageBox.information(self.app, "Success", "Calculation result exported to text file.")
            self.app.gui_log(f"Exported calculation result to TXT file: {file_path}")
        except Exception as e:
            QMessageBox.critical(self.app, "Error", f"Export failed:\n{e}")
            self.logger.exception(f"Error during export: {e}")
            self.app.gui_log(f"Error during export: {e}")
    
    def save_tab_image(self, tab_name: str, original_image, cropped_image):
        """Save image data to the tab."""
        self._tab_images[tab_name] = {
            "original": original_image,
            "cropped": cropped_image
        }
    
    def get_tab_image(self, tab_name: str) -> Optional[Dict[str, Any]]:
        """Get the image data for the tab."""
        return self._tab_images.get(tab_name)
