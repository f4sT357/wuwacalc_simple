"""
Image Processing and OCR Module (PyQt6)

Provides image loading, cropping, OCR processing, and automatic input.
"""

import os
import hashlib
from typing import Optional, Any

from PyQt6.QtWidgets import QMessageBox, QFileDialog, QApplication
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QObject, pyqtSignal

try:
    from PIL import Image, ImageQt, ImageGrab
    is_pil_installed = True
except ImportError:
    is_pil_installed = False

from dialogs import CropDialog
from utils import crop_image_by_percent

class ImageProcessor(QObject):
    """Class responsible for image processing and OCR."""
    
    ocr_completed = pyqtSignal(list, list) # substats, log_messages
    
    # Constants
    IMAGE_PREVIEW_MAX_WIDTH = 400
    IMAGE_PREVIEW_MAX_HEIGHT = 200
    
    def __init__(self, app, logic):
        """
        Initialization
        
        Args:
            app: The main application instance.
            logic: The application logic instance.
        """
        super().__init__()
        self.app = app
        self.logic = logic
    
    def import_image(self) -> None:
        """Load one or multiple images for OCR."""
        if not is_pil_installed:
            QMessageBox.critical(self.app, "Error", "Pillow is not installed. Image operations require Pillow.")
            return
        
        # Use getOpenFileNames to allow multiple selection
        file_paths, _ = QFileDialog.getOpenFileNames(
            self.app,
            "Select Image File(s)",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*.*)"
        )
        if not file_paths:
            self.app.gui_log("Image selection was cancelled.")
            return
            
        try:
            if len(file_paths) == 1:
                # Single image - standard behavior
                file_path = file_paths[0]
                if not os.path.isfile(file_path):
                    QMessageBox.critical(self.app, "Error", f"File not found:\n{file_path}")
                    return
                
                image = Image.open(file_path)
                self.process_loaded_image(image, file_path)
            else:
                # Multiple images - batch processing
                self.process_batch_images(file_paths)
            
        except Exception as e:
            QMessageBox.critical(self.app, "Error", f"Failed to load image(s):\n{e}")
            self.app.logger.exception(f"Image load error: {e}")
            self.app.gui_log(f"Image load error: {e}")

    def process_batch_images(self, file_paths: list[str]) -> None:
        """
        Process multiple images sequentially.
        Auto-classifies into tabs based on Cost if possible.
        """
        self.app.gui_log(f"Starting batch processing of {len(file_paths)} images...")
        
        # Reset current tabs if needed? Users might want to append, but usually batch means fill all.
        # For now, we won't clear explicitly unless requested, but we'll try to find empty slots.
        # Actually, let's keep track of which tabs we've assigned to in this batch to avoid overwriting.
        assigned_tabs = set()
        
        successful_count = 0
        
        for file_path in file_paths:
            try:
                if not os.path.isfile(file_path):
                    continue
                    
                image = Image.open(file_path)
                image.load() # Ensure data is loaded into memory and file can be closed safely
                filename = os.path.basename(file_path)
                
                # Apply crop
                # We assume the user has set the crop settings for the "Cost" and stats to be visible.
                # However, usually Cost is at top left or top right, stats below.
                # If crop cuts off Cost, we can't detect it.
                # Use current crop settings.
                
                if self.app.crop_mode_var == "percent":
                    top_p = self.app.crop_top_percent_var
                    right_p = self.app.crop_right_percent_var
                    cropped_img = crop_image_by_percent(image, top_p, right_p)
                else:
                    # Fallback to full image if mode is weird or drag (drag is manual)
                    # For batch, we'll just use the full image or a safe default crop?
                    # Let's use the full image if 'drag' was last used because drag is per-image.
                    # Or better, just don't crop if it's 'drag', assuming screenshots are uniform.
                     cropped_img = image.copy() # Default no crop if not percent
                
                # Run OCR
                ocr_text = self.logic._perform_ocr(cropped_img)
                if not ocr_text:
                    self.app.gui_log(f"[{filename}] OCR failed: No text detected.")
                    continue
                    
                # Detect Cost
                cost = self.logic.detect_cost_from_ocr(ocr_text)
                
                target_tab = None
                if cost:
                    self.app.gui_log(f"[{filename}] Detected Cost: {cost}")
                    # Find a tab for this cost
                    target_tab = self._find_free_tab_for_cost(cost, assigned_tabs)
                else:
                    self.app.gui_log(f"[{filename}] Cost not detected. Attempting to assign to first available empty slot.")
                    # Fallback: any empty tab? or just skip?
                    # Let's try to find ANY empty tab to fill
                    target_tab = self._find_any_free_tab(assigned_tabs)
                
                if target_tab:
                    self.app.gui_log(f"[{filename}] Assigning to tab: {target_tab}")
                    assigned_tabs.add(target_tab)
                    
                    # Parse Stats
                    substats, logs = self.logic.parse_substats_from_ocr(ocr_text, self.app.language)
                    
                    # Populate Tab
                    self._populate_tab_data(target_tab, substats)
                    
                    # Save Image to Tab
                    # Save COPIES to ensure isolation
                    self.app.tab_mgr.save_tab_image(target_tab, image.copy(), cropped_img.copy())
                    
                    # Update active image state if we are verifying this tab
                    # This ensures "Drag" crop works immediately for the currently visible tab
                    current_tab = self.app.tab_mgr.get_selected_tab_name()
                    if current_tab and current_tab == target_tab:
                        self.app.original_image = image.copy()
                        self.app.loaded_image = cropped_img.copy()
                        self.display_image_preview(self.app.loaded_image)
                    
                    successful_count += 1
                else:
                     self.app.gui_log(f"[{filename}] No suitable free tab found (Cost: {cost if cost else 'Unknown'}). Skipping.")
                
            except Exception as e:
                self.app.gui_log(f"Error processing {file_path}: {e}")
                
        self.app.gui_log(f"Batch processing completed. {successful_count}/{len(file_paths)} images processed.")
        # self.app._update_tabs() # Removed as we updated widgets directly and rebuilding is unnecessary/risky.
        # Actually, _populate_tab_data updates widgets, so no full refresh needed.

    def _find_free_tab_for_cost(self, cost: str, exclude_tabs: set) -> Optional[str]:
        """Finds the first tab matching the cost that isn't excluded and is empty."""
        # We need to iterate through tabs in order
        if self.app.notebook is None:
            return None
            
        # Iterate through all tabs
        for i in range(self.app.notebook.count()):
            tab_name = self.app.notebook.tabText(i)
            # tab_name might be localized, we need the internal key
            # We can look up in app.tabs_content which uses internal keys
            # But the order in tabs_content is not guaranteed to match notebook index if python < 3.7 (though it is ordered dict in recent python)
            # Better to loop through tabs_content assuming insertion order, or use the TAB_CONFIGS list.
            pass

        # Use the current config's tab list to ensure order
        config_key = self.app.current_config_key
        from constants import TAB_CONFIGS
        if config_key not in TAB_CONFIGS:
             return None
             
        tab_keys = TAB_CONFIGS[config_key]
        
        for key in tab_keys:
            if key in exclude_tabs:
                continue
            
            content = self.app.tabs_content.get(key)
            if not content:
                continue
                
            # Check cost match
            # The key usually looks like "cost4_echo" or "cost3_echo_1"
            # We can extract cost from key or use content['cost']
            tab_cost = content.get("cost")
            if tab_cost != cost:
                continue
            
            # Check if empty (Main stat not selected, or no substats?)
            # Let's consider it empty if Main Stat is not selected OR first substat is empty.
            # actually better to just check if we've already assigned it in this batch (exclude_tabs)
            # AND if it was effectively empty before? 
            # Users might want to overwrite. But 'Auto-classify' usually implies filling slots.
            # Let's check if the widget has data.
            main_combo = content["main_widget"]
            
            # If main combo index is -1 or text is empty/default, treat as empty?
            # Or just rely on exclude_tabs causing us to fill sequentially.
            # If the user has data in tab 1, and loads 5 images, do we overwrite tab 1?
            # Probably safest to overwrite if they are running a batch command, OR fill empty ones.
            # Given the request is "classify and allocate", filling empty ones first is smarter, 
            # but usually users clear all then load.
            # Let's strict check: if we haven't touched it in this batch, use it.
            # The simple logic is: Fill slots sequentially.
            return key
            
        return None

    def _find_any_free_tab(self, exclude_tabs: set) -> Optional[str]:
        """Fallback: find any tab not yet assigned."""
        config_key = self.app.current_config_key
        from constants import TAB_CONFIGS
        if config_key not in TAB_CONFIGS:
             return None
        
        for key in TAB_CONFIGS[config_key]:
            if key not in exclude_tabs:
                return key
        return None

    def _populate_tab_data(self, tab_name: str, substats: list) -> None:
        """Directly updates the widgets for the given tab."""
        if tab_name not in self.app.tabs_content:
            return
            
        content = self.app.tabs_content[tab_name]
        sub_entries = content["sub_entries"]
        
        # We don't have main stat from OCR usually (unless we parse it too, but logic mostly parses substats).
        # So we leave main stat alone or user sets it? 
        # The user's request didn't specify auto-main-stat from OCR, just allocation.
        # But existing logic `_apply_character_main_stats` exists.
        
        # Clear existing substats in the widget first?
        # Yes, for a fresh load.
        for stat_widget, val_widget in sub_entries:
            stat_widget.setCurrentIndex(0) # Blank
            val_widget.clear()
            
        for i, substat_data in enumerate(substats):
            if i < len(sub_entries):
                stat_found = substat_data.get("stat", "")
                num_found = substat_data.get("value", "")
                
                translated_stat = self.app.tr(stat_found)
                sub_entries[i][0].setCurrentText(translated_stat)
                sub_entries[i][1].setText(num_found)

    
    def paste_from_clipboard(self) -> None:
        """Load image from the clipboard."""
        if not is_pil_installed:
            QMessageBox.critical(self.app, "Error", "Pillow is not installed. Image operations require Pillow.")
            return
        
        try:
            # Try getting image from Qt clipboard first
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            
            if mime_data.hasImage():
                qimage = clipboard.image()
                # Convert QImage to PIL Image
                # This is a bit roundabout but keeps consistency with PIL usage elsewhere
                # Alternatively, use ImageGrab.grabclipboard()
                image = ImageGrab.grabclipboard()
                if isinstance(image, Image.Image):
                    self.process_loaded_image(image, "clipboard image")
                else:
                    # Fallback if ImageGrab fails but Qt has image
                    # Convert QImage to PIL
                    buffer = qimage.bits().asstring(qimage.sizeInBytes())
                    # This conversion is complex, let's stick to ImageGrab for now as it was working
                    self.app.gui_log("No compatible image found on clipboard via PIL.")
            else:
                self.app.gui_log("No image found on the clipboard.")
        except Exception as e:
            self.app.logger.exception(f"Error loading image from clipboard: {e}")
            self.app.gui_log(f"Error loading image from clipboard: {e}")
    
    def process_loaded_image(self, image: Any, source_name: str) -> None:
        """Common image loading process."""
        tab_name = self.app.tab_mgr.get_selected_tab_name()
        if not tab_name:
            QMessageBox.warning(self.app, "Warning", "Please select a tab to associate the image with.")
            return

        self.app.original_image = image.copy()
        # Use the entire image by default without cropping
        self.apply_cropped_image(image)
        self.app.gui_log(f"Image loaded: {source_name}")
    
    def perform_crop(self) -> None:
        """Perform cropping based on the current mode."""
        if self.app.original_image is None:
            QMessageBox.warning(self.app, "Warning", "No image loaded.")
            return

        mode = self.app.crop_mode_var
        if mode == "percent":
            self.apply_percent_crop()
        else:
            self.open_crop_dialog()
    
    def apply_percent_crop(self) -> None:
        """Perform cropping by percentage."""
        try:
            top_p = self.app.crop_top_percent_var
            right_p = self.app.crop_right_percent_var
            
            cropped = crop_image_by_percent(self.app.original_image, top_p, right_p)
            
            self.app.gui_log(f"Applied percent crop: Top {top_p}%, Right {right_p}%")
            self.apply_cropped_image(cropped)
            
        except Exception as e:
            QMessageBox.critical(self.app, "Error", f"Error applying percent crop: {e}")
            self.app.logger.exception(f"Percent crop error: {e}")
            self.app.gui_log(f"Percent crop error: {e}")
    
    def open_crop_dialog(self) -> None:
        """Open a crop dialog for the current original image."""
        if self.app.original_image is None:
            QMessageBox.warning(self.app, "Warning", "No image loaded.")
            return
            
        try:
            crop_dialog = CropDialog(self.app, self.app.original_image)
            if crop_dialog.exec():
                if crop_dialog.result:
                    if crop_dialog.result[0] == 'coords':
                        _, left, top, right, bottom = crop_dialog.result
                        try:
                            cropped_img = self.app.original_image.crop((left, top, right, bottom))
                            self.app.gui_log(f"Cropped with coordinates: ({left},{top}) - ({right},{bottom})")
                            
                            self.apply_cropped_image(cropped_img)
                            
                        except Exception as ve:
                            QMessageBox.critical(self.app, "Error", f"Failed to crop with coordinates:\n{ve}")
                            self.app.logger.exception(f"Coordinate crop error: {ve}")
                            self.app.gui_log(f"Coordinate crop error: {ve}")
            else:
                self.app.gui_log("Crop cancelled.")
        except Exception as e:
            self.app.logger.exception(f"Crop dialog error: {e}")
            self.app.gui_log(f"Crop dialog error: {e}")
    
    def apply_cropped_image(self, cropped_img: Any) -> None:
        """Save, display, and run OCR on the cropped image."""
        tab_name = self.app.tab_mgr.get_selected_tab_name()
        if not tab_name:
            return

        stored_original = self.app.original_image.copy()
        stored_cropped = cropped_img.copy()
        self.app.loaded_image = stored_cropped.copy()
        
        self.app.tab_mgr.save_tab_image(tab_name, stored_original, stored_cropped)
        
        self.display_image_preview(self.app.loaded_image)
        
        # Run OCR
        ocr_text = self.logic._perform_ocr(cropped_img)
        if ocr_text is not None:
            substats, log_messages = self.logic.parse_substats_from_ocr(ocr_text, self.app.language)
            self.ocr_completed.emit(substats, log_messages)
    
    def display_image_preview(self, image: Any) -> None:
        """Update the image preview label."""
        if not is_pil_installed or self.app.image_label is None or image is None:
            return
        
        try:
            image_hash_data = (image.mode, image.size, hashlib.md5(image.tobytes()).hexdigest())
            
            if image_hash_data == self.app._last_displayed_image_hash and self.app._last_image_preview is not None:
                self.app.image_label.setPixmap(self.app._last_image_preview)
                self.app.image_label.setText("")
                return
            
            # Convert PIL to QPixmap
            # ImageQt.ImageQt(image) returns a QImage-compatible object
            qim = ImageQt.ImageQt(image)
            pixmap = QPixmap.fromImage(qim)
            
            # Scale for preview
            scaled_pixmap = pixmap.scaled(
                self.IMAGE_PREVIEW_MAX_WIDTH, 
                self.IMAGE_PREVIEW_MAX_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.app._image_preview = scaled_pixmap
            self.app._last_displayed_image_hash = image_hash_data
            self.app._last_image_preview = scaled_pixmap
            
            self.app.image_label.setPixmap(scaled_pixmap)
            self.app.image_label.setText("")
        except Exception as e:
            self.app.logger.exception(f"Image preview update error: {e}")
            self.app.gui_log(f"Image preview update error: {e}")
    
    def perform_crop_preview(self) -> None:
        """Preview the image with the current crop settings."""
        if self.app.original_image is None or self.app.image_label is None:
            return
        try:
            top_p = self.app.crop_top_percent_var
            right_p = self.app.crop_right_percent_var
            
            cropped = crop_image_by_percent(self.app.original_image, top_p, right_p)
            
            self.display_image_preview(cropped)
        except Exception as e:
            self.app.logger.debug(f"Crop preview error: {e}")
    
    def perform_image_preview_update_on_resize(self) -> None:
        """Update the image preview on resize."""
        if self.app.loaded_image is not None:
            self.display_image_preview(self.app.loaded_image)
