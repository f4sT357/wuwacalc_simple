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

    # Emit substats (list), log_messages (list), main_stat (str or None)
    ocr_completed = pyqtSignal(list, list, object) # substats, log_messages, main_stat
    
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
                    # Try to detect main stat for this image
                    try:
                        main_stat = None
                        if hasattr(self.logic, 'detect_main_stat_from_ocr'):
                            main_stat = self.logic.detect_main_stat_from_ocr(ocr_text)
                    except Exception:
                        main_stat = None
                    
                    # Switch UI to target tab (so user sees where data will be entered)
                    switched = False
                    try:
                        if hasattr(self.app, 'select_tab_by_internal_name'):
                            switched = self.app.select_tab_by_internal_name(target_tab)
                        else:
                            from constants import TAB_CONFIGS
                            if self.app.current_config_key in TAB_CONFIGS and target_tab in TAB_CONFIGS[self.app.current_config_key]:
                                idx = TAB_CONFIGS[self.app.current_config_key].index(target_tab)
                                if hasattr(self.app, 'notebook') and self.app.notebook is not None and 0 <= idx < self.app.notebook.count():
                                    self.app.notebook.setCurrentIndex(idx)
                                    switched = True
                    except Exception:
                        switched = False

                    # Populate Tab (visible if switched)
                    self._populate_tab_data(target_tab, substats, main_stat)

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

        # Prefer truly empty tabs (no substat entries filled). If none are empty,
        # fall back to the first matching tab (allow overwrite).
        fallback_candidate = None
        for key in tab_keys:
            if key in exclude_tabs:
                continue

            content = self.app.tabs_content.get(key)
            if not content:
                continue

            # Check cost match
            tab_cost = content.get("cost")
            if tab_cost != cost:
                continue

            # Determine emptiness by inspecting sub_entries (stat/value pairs).
            try:
                sub_entries = content.get("sub_entries", [])
                is_empty = True
                for stat_widget, val_widget in sub_entries:
                    stat_text = ""
                    val_text = ""
                    if hasattr(stat_widget, "currentText"):
                        try:
                            stat_text = stat_widget.currentText() or ""
                        except Exception:
                            stat_text = ""
                    if hasattr(val_widget, "text"):
                        try:
                            val_text = val_widget.text() or ""
                        except Exception:
                            val_text = ""

                    if stat_text.strip() or val_text.strip():
                        is_empty = False
                        break

                if is_empty:
                    return key

                if fallback_candidate is None:
                    fallback_candidate = key
            except Exception:
                # If any widget inspection fails, skip this tab
                continue

        return fallback_candidate

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

    def _populate_tab_data(self, tab_name: str, substats: list, main_stat: Optional[str] = None) -> None:
        """Directly updates the widgets for the given tab.

        If `main_stat` is provided it will attempt to set the tab's main stat
        combobox to the detected value.
        """
        if tab_name not in self.app.tabs_content:
            return
        
        content = self.app.tabs_content[tab_name]
        sub_entries = content["sub_entries"]

        # Apply detected main stat if present
        if main_stat:
            try:
                main_widget = content.get("main_widget")
                if main_widget is not None:
                    disp = self.app.tr(main_stat) if isinstance(main_stat, str) else None
                    if disp and main_widget.findText(disp) != -1:
                        main_widget.setCurrentText(disp)
                        self.app.gui_log(f"Detected main stat: {disp}")
                    elif isinstance(main_stat, str) and main_widget.findText(main_stat) != -1:
                        main_widget.setCurrentText(main_stat)
                        self.app.gui_log(f"Detected main stat: {main_stat}")
                    else:
                        try:
                            from constants import STAT_ALIASES
                            applied = False
                            for key, aliases in STAT_ALIASES.items():
                                if main_stat == key or (isinstance(main_stat, str) and main_stat in aliases):
                                    display_k = self.app.tr(key)
                                    if main_widget.findText(display_k) != -1:
                                        main_widget.setCurrentText(display_k)
                                        self.app.gui_log(f"Detected main stat (alias): {display_k}")
                                        applied = True
                                        break
                            if not applied and disp:
                                main_widget.setCurrentText(disp)
                        except Exception:
                            pass
            except Exception as e:
                self.app.logger.exception(f"Failed to apply main stat: {e}")
        
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
        # Determine currently selected tab (fallback used if cost detection fails)
        try:
            selected_tab = self.app.tab_mgr.get_selected_tab_name()
        except Exception:
            selected_tab = None

        stored_original = self.app.original_image.copy() if getattr(self.app, 'original_image', None) is not None else None
        stored_cropped = cropped_img.copy()
        self.app.loaded_image = stored_cropped.copy()
        # Always update preview so user sees the cropped image immediately
        try:
            self.display_image_preview(self.app.loaded_image)
        except Exception:
            pass

        # Try OCR -> detect cost/main stat/substats
        try:
            ocr_text = self.logic._perform_ocr(cropped_img)
        except Exception:
            ocr_text = None

        main_stat = None
        substats = []
        log_messages = []

        # Decide target tab: prefer cost-detected matching empty tab
        target_tab = selected_tab
        if ocr_text:
            try:
                substats, log_messages = self.logic.parse_substats_from_ocr(ocr_text, self.app.language)
            except Exception:
                substats, log_messages = [], []

            try:
                if hasattr(self.logic, 'detect_main_stat_from_ocr'):
                    main_stat = self.logic.detect_main_stat_from_ocr(ocr_text)
            except Exception:
                main_stat = None

            try:
                cost = None
                if hasattr(self.logic, 'detect_cost_from_ocr'):
                    cost = self.logic.detect_cost_from_ocr(ocr_text)
                if cost:
                    candidate = self._find_free_tab_for_cost(cost, set())
                    if candidate:
                        target_tab = candidate
                        self.app.gui_log(f"Detected Cost: {cost} -> assigning to tab: {target_tab}")
            except Exception:
                pass

        # If no target tab yet, try any free tab
        if not target_tab:
            try:
                target_tab = self._find_any_free_tab(set())
            except Exception:
                target_tab = None

        if not target_tab:
            QMessageBox.warning(self.app, "Warning", "No available tab to assign the image. Please select a tab.")
            return

        # Save image to chosen tab
        try:
            if stored_original is not None:
                self.app.tab_mgr.save_tab_image(target_tab, stored_original, stored_cropped)
            else:
                self.app.tab_mgr.save_tab_image(target_tab, stored_cropped, stored_cropped)
        except Exception as e:
            self.app.gui_log(f"Failed to save image to tab {target_tab}: {e}")

        # If target is currently visible tab, show preview and emit signal so main handler updates widgets
        try:
            current_tab = self.app.tab_mgr.get_selected_tab_name()
        except Exception:
            current_tab = None

        if current_tab and current_tab == target_tab:
            self.display_image_preview(self.app.loaded_image)
            if substats or main_stat:
                self.ocr_completed.emit(substats, log_messages, main_stat)
            else:
                self.app.gui_log("Image saved to current tab (no OCR results).")
        else:
            # Prefer to switch the UI to the target tab so the user can observe input
            try:
                switched = False
                try:
                    if hasattr(self.app, 'select_tab_by_internal_name'):
                        switched = self.app.select_tab_by_internal_name(target_tab)
                    else:
                        # Fallback mapping using TAB_CONFIGS
                        from constants import TAB_CONFIGS
                        config_key = self.app.current_config_key
                        if config_key in TAB_CONFIGS and target_tab in TAB_CONFIGS[config_key]:
                            idx = TAB_CONFIGS[config_key].index(target_tab)
                            if hasattr(self.app, 'notebook') and self.app.notebook is not None and 0 <= idx < self.app.notebook.count():
                                self.app.notebook.setCurrentIndex(idx)
                                switched = True
                except Exception:
                    switched = False

                if switched:
                    # Show preview and emit so main handler will populate the now-active tab
                    self.display_image_preview(self.app.loaded_image)
                    if substats or main_stat:
                        self.ocr_completed.emit(substats, log_messages, main_stat)
                    else:
                        self.app.gui_log(f"Image assigned to tab: {target_tab} (no OCR results).")
                else:
                    # Fallback: populate the (possibly non-active) tab's widgets directly
                    if substats or main_stat:
                        self._populate_tab_data(target_tab, substats, main_stat)
                        for m in log_messages:
                            self.app.gui_log(m)
                        self.app.gui_log(f"Successfully applied OCR results to tab: {target_tab}.")
                    else:
                        self.app.gui_log(f"Image assigned to tab: {target_tab} (no OCR results).")
            except Exception as e:
                self.app.gui_log(f"Failed to populate or switch to tab {target_tab}: {e}")
    
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
