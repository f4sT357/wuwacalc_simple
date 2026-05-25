"""
Dialog Classes Module (PyQt6)

Provides character setting and image cropping dialogs.
"""

import os
from typing import Callable

from utils import get_app_path

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QComboBox, QPushButton, QGroupBox, 
                             QMessageBox, QWidget, QRubberBand, QColorDialog,
                             QFileDialog, QSlider)
from PyQt6.QtCore import Qt, QRect, QSize, QPoint, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QFontDatabase

# ImageQt should be imported from PIL.ImageQt
try:
    from PIL import Image, ImageQt
    is_pil_installed = True
except ImportError:
    is_pil_installed = False

class CharSettingDialog(QDialog):
    """Character settings dialog."""
    
    def __init__(self, parent, on_register_char: Callable):
        super().__init__(parent)
        self.app = parent
        self.on_register_char = on_register_char
        
        self.setWindowTitle(self.app.tr("char_setting_title"))
        self.resize(550, 500)
        
        # Definitions
        self.cost_presets = {
            "[4,3,3,1,1]": [4, 3, 3, 1, 1],
            "[4,4,1,1,1]": [4, 4, 1, 1, 1]
        }
        from constants import MAIN_STAT_OPTIONS, SUBSTAT_MAX_VALUES
        self.main_stats = MAIN_STAT_OPTIONS
        self.substat_candidates = list(SUBSTAT_MAX_VALUES.keys())
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Row 1: Name and English Name
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(self.app.tr("char_name")))
        self.entry_name = QLineEdit()
        row1.addWidget(self.entry_name)
        
        row1.addWidget(QLabel(self.app.tr("char_name_en")))
        self.entry_name_en = QLineEdit()
        self.entry_name_en.setPlaceholderText(self.app.tr("char_name_en_placeholder"))
        row1.addWidget(self.entry_name_en)
        layout.addLayout(row1)
        
        # Row 2: Preset
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(self.app.tr("cost_config")))
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(list(self.cost_presets.keys()))
        self.combo_preset.currentTextChanged.connect(self.update_main_stat_options)
        row2.addWidget(self.combo_preset)
        layout.addLayout(row2)
        
        # Slot Config
        slot_group = QGroupBox(self.app.tr("echo_5_slot_config"))
        slot_layout = QVBoxLayout(slot_group)
        layout.addWidget(slot_group)
        
        self.slot_labels = []
        self.slot_combos = []
        
        for i in range(5):
            r_layout = QHBoxLayout()
            lbl = QLabel()
            lbl.setFixedWidth(120)
            self.slot_labels.append(lbl)
            r_layout.addWidget(lbl)
            
            cb = QComboBox()
            self.slot_combos.append(cb)
            r_layout.addWidget(cb)
            
            slot_layout.addLayout(r_layout)
            
        self.update_main_stat_options()
        
        # Effective Substats
        eff_group = QGroupBox(self.app.tr("effective_substats_weights"))
        eff_layout = QVBoxLayout(eff_group)
        layout.addWidget(eff_group)
        
        self.eff_combos = []
        self.eff_weights = []
        
        for i in range(5):
            r_layout = QHBoxLayout()
            r_layout.addWidget(QLabel(self.app.tr("effective_substat_n", i+1)))
            
            cb = QComboBox()
            cb.addItems([""] + self.substat_candidates) # Add empty option
            self.eff_combos.append(cb)
            r_layout.addWidget(cb)
            
            r_layout.addWidget(QLabel(self.app.tr("weight")))
            entry = QLineEdit("1")
            entry.setFixedWidth(60)
            self.eff_weights.append(entry)
            r_layout.addWidget(entry)
            
            eff_layout.addLayout(r_layout)
            
        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton(self.app.tr("save"))
        btn_save.clicked.connect(self.on_save_char)
        btn_close = QPushButton(self.app.tr("close"))
        btn_close.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def update_main_stat_options(self, *args):
        preset_key = self.combo_preset.currentText()
        if not preset_key: return
        
        costs = self.cost_presets[preset_key]
        for i, cost in enumerate(costs):
            cb = self.slot_combos[i]
            cb.clear()
            vals = self.main_stats.get(str(cost), [""])
            # Add empty option at the beginning
            cb.addItems([""] + vals)
            
            self.slot_labels[i].setText(self.app.tr("cost_echo", cost))
            
        # Clear remaining
        for j in range(len(costs), 5):
            self.slot_combos[j].clear()
            self.slot_labels[j].setText("")

    def on_save_char(self):
        name = self.entry_name.text().strip()
        if not name:
            QMessageBox.critical(self, self.app.tr("error"), self.app.tr("enter_char_name"))
            return
            
        name_en = self.entry_name_en.text().strip()
        if not name_en:
            QMessageBox.critical(self, self.app.tr("error"), self.app.tr("enter_char_name_en"))
            return
            
        preset_key = self.combo_preset.currentText()
        costs = self.cost_presets[preset_key]
        mainstats = {}
        cost_occurrence = {}
        cost_total = {c: costs.count(c) for c in set(costs)}
        
        for i, c in enumerate(costs):
            cost_occurrence[c] = cost_occurrence.get(c, 0) + 1
            if cost_total[c] == 1:
                key = str(c)
            else:
                key = f"{c}_{cost_occurrence[c]}"
            
            mainstat = self.slot_combos[i].currentText()
            if not mainstat:
                QMessageBox.critical(self, self.app.tr("error"), self.app.tr("echo_main_stat_unselected", i+1))
                return
            mainstats[key] = mainstat
            
        effweights = {}
        for cb, w_entry in zip(self.eff_combos, self.eff_weights):
            ename = cb.currentText()
            weight_s = w_entry.text()
            if ename:
                try:
                    effweights[ename] = float(weight_s)
                except ValueError:
                    effweights[ename] = 1.0
        
        if self.on_register_char:
            self.on_register_char(name, name_en, preset_key, mainstats, effweights)
            
        QMessageBox.information(self, self.app.tr("save_complete"), self.app.tr("save_msg", name))
        self.accept()


class CropLabel(QLabel):
    """QLabel with rubber band selection."""
    selection_changed = pyqtSignal(QRect)  # emitted on every drag move and release

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()
        self.current_rect = QRect()
        self.is_selecting = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
            self.is_selecting = True

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            rect = QRect(self.origin, event.pos()).normalized()
            self.rubberBand.setGeometry(rect)
            self.selection_changed.emit(rect)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = False
            self.current_rect = self.rubberBand.geometry()
            self.selection_changed.emit(self.current_rect)

    def get_selection(self):
        return self.current_rect

class CropDialog(QDialog):
    """Dialog for selecting and inputting image crop method (interactive)."""
    
    def __init__(self, parent, pil_image):
        super().__init__(parent)
        self.app = parent
        self.setWindowTitle(self.app.tr("crop_title"))
        self.resize(900, 700)
        self.result = None
        self.pil_image = pil_image
        self.scale_ratio = 1.0
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(self.app.tr("crop_instruction")))
        
        # Scroll Area for Image
        # Placeholder removed; QScrollArea usage will create its own widget when needed
        # Actually, let's put the CropLabel inside a QScrollArea
        
        self.scroll_area = QWidget() # Just a container? No, QScrollArea
        # We need a scroll area because the image might be large
        # But we also want to scale it down to fit if possible, like the original
        
        self.image_label = CropLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        # self.image_label.setScaledContents(False) # We will manually scale the pixmap
        
        # Load and display
        self._load_and_display_image()
        
        layout.addWidget(self.image_label) # If we want scrolling, wrap in QScrollArea
        # For now, let's assume the scaling fits the window as per original logic
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_reset = QPushButton(self.app.tr("reset"))
        btn_reset.clicked.connect(self._reset_selection)

        btn_ok = QPushButton(self.app.tr("ok"))
        btn_ok.clicked.connect(self._ok)

        btn_cancel = QPushButton(self.app.tr("cancel"))
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_reset)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        # Real-time coordinate display
        self.coord_label = QLabel(self.app.tr("crop_no_selection"))
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.coord_label)

        # Connect signal
        self.image_label.selection_changed.connect(self._on_selection_changed)

    def _load_and_display_image(self):
        if not self.pil_image or not is_pil_installed:
            return
            
        max_w, max_h = 850, 550
        w, h = self.pil_image.size
        
        scale_w = max_w / w
        scale_h = max_h / h
        self.scale_ratio = min(scale_w, scale_h, 1.0)
        
        new_w = int(w * self.scale_ratio)
        new_h = int(h * self.scale_ratio)
        
        # Ensure image is in a display-friendly mode and loaded
        if self.pil_image.mode != "RGBA" and self.pil_image.mode != "RGB":
             display_img = self.pil_image.convert("RGBA")
        else:
             display_img = self.pil_image

        resized = display_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.qim = ImageQt.ImageQt(resized)
        pixmap = QPixmap.fromImage(self.qim)
        
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(new_w, new_h) # Ensure label matches image size for correct coordinates

    def _on_selection_changed(self, display_rect: QRect) -> None:
        """Update coordinate label with original-image pixel coordinates."""
        if display_rect.isEmpty():
            self.coord_label.setText(self.app.tr("crop_no_selection"))
            return
        # Convert from display (scaled) coords to original image coords
        sr = self.scale_ratio if self.scale_ratio > 0 else 1.0
        x = int(display_rect.x() / sr)
        y = int(display_rect.y() / sr)
        w = int(display_rect.width() / sr)
        h = int(display_rect.height() / sr)
        self.coord_label.setText(f"x={x},  y={y}   |   {w} × {h} px")

    def _reset_selection(self):
        self.image_label.rubberBand.hide()
        self.image_label.current_rect = QRect()

    def _ok(self):
        rect = self.image_label.get_selection()
        if rect.isEmpty():
            # Entire image
            self.result = ('coords', 0, 0, self.pil_image.size[0], self.pil_image.size[1])
            self.accept()
            return
            
        # Convert coords
        x1 = rect.x()
        y1 = rect.y()
        x2 = rect.right()
        y2 = rect.bottom()
        
        orig_left = int(x1 / self.scale_ratio)
        orig_top = int(y1 / self.scale_ratio)
        orig_right = int(x2 / self.scale_ratio)
        orig_bottom = int(y2 / self.scale_ratio)
        
        # Limit
        orig_left = max(0, orig_left)
        orig_top = max(0, orig_top)
        orig_right = min(self.pil_image.size[0], orig_right)
        orig_bottom = min(self.pil_image.size[1], orig_bottom)
        
        if (orig_right - orig_left) < 5 or (orig_bottom - orig_top) < 5:
             QMessageBox.warning(self, self.app.tr("warning"), self.app.tr("crop_too_small"))
             return

        self.result = ('coords', orig_left, orig_top, orig_right, orig_bottom)
        self.accept()

class DisplaySettingsDialog(QDialog):
    """Dialog for display settings, including text color."""

    def __init__(self, parent):
        super().__init__(parent)
        self.app = parent
        self.setWindowTitle(self.app.tr("display_settings"))
        self.setMinimumSize(300, 150)
        
        # Store initial color
        # This will be fetched from app.app_config.text_color, which needs to be initialized
        self.initial_text_color = self.app.app_config.text_color if hasattr(self.app.app_config, 'text_color') else "#ffffff"
        self.selected_text_color = self.initial_text_color

        self.initial_background_image = self.app.app_config.background_image
        self.selected_background_image = self.initial_background_image
        
        self.initial_opacity = self.app.app_config.background_opacity
        self.selected_opacity = self.initial_opacity

        self.initial_theme = self.app._current_app_theme
        self.selected_theme = self.initial_theme

        self.initial_input_bg = self.app.app_config.custom_input_bg_color
        self.selected_input_bg = self.initial_input_bg

        self.initial_font = self.app.app_config.app_font
        self.selected_font = self.initial_font

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Text Color setting
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel(self.app.tr("text_color")))
        
        self.text_color_button = QPushButton(self.app.tr("select_color"))
        self.text_color_button.clicked.connect(self._pick_text_color)
        color_layout.addWidget(self.text_color_button)
        
        self.color_preview_label = QLabel()
        self.color_preview_label.setFixedSize(50, 20)
        self.color_preview_label.setStyleSheet(f"background-color: {self.selected_text_color}; border: 1px solid black;")
        color_layout.addWidget(self.color_preview_label)
        
        layout.addLayout(color_layout)
        
        # Input Background Color setting
        input_bg_layout = QHBoxLayout()
        input_bg_layout.addWidget(QLabel(self.app.tr("input_bg_color")))
        
        self.btn_input_bg = QPushButton(self.app.tr("select_color"))
        self.btn_input_bg.clicked.connect(self._pick_input_bg_color)
        input_bg_layout.addWidget(self.btn_input_bg)
        
        self.input_bg_preview = QLabel()
        self.input_bg_preview.setFixedSize(50, 20)
        # Display either custom color or "Theme Default" (transparent or generic color)
        bg_style = f"background-color: {self.selected_input_bg};" if self.selected_input_bg else "background-color: transparent;"
        self.input_bg_preview.setStyleSheet(f"{bg_style} border: 1px solid black;")
        input_bg_layout.addWidget(self.input_bg_preview)

        self.btn_reset_input_bg = QPushButton(self.app.tr("reset"))
        self.btn_reset_input_bg.clicked.connect(self._reset_input_bg_color)
        input_bg_layout.addWidget(self.btn_reset_input_bg)
        
        layout.addLayout(input_bg_layout)
        
        # Font Setting
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel(self.app.tr("font_settings")))
        
        self.combo_font = QComboBox()
        self.combo_font.addItem(self.app.tr("default_font"))
        
        fonts = self._get_compatible_fonts()
        self.combo_font.addItems(fonts)
        
        if self.initial_font and self.initial_font in fonts:
            self.combo_font.setCurrentText(self.initial_font)
        else:
            self.combo_font.setCurrentIndex(0) # Default
            
        self.combo_font.currentTextChanged.connect(self._update_selected_font)
        font_layout.addWidget(self.combo_font)
        
        layout.addLayout(font_layout)
        


        # Theme Setting
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel(self.app.tr("theme_settings")))
        
        self.combo_theme = QComboBox()
        # Internal names: dark, light, clear. Display: localized
        self.theme_map = {
            self.app.tr("dark_theme"): "dark",
            self.app.tr("light_theme"): "light",
            self.app.tr("clear_theme"): "clear"
        }
        # Invert map for setting initial text
        self.theme_map_inv = {v: k for k, v in self.theme_map.items()}
        
        self.combo_theme.addItems(list(self.theme_map.keys()))
        if self.initial_theme in self.theme_map_inv:
            self.combo_theme.setCurrentText(self.theme_map_inv[self.initial_theme])
            
        self.combo_theme.currentTextChanged.connect(self._update_selected_theme)
        theme_layout.addWidget(self.combo_theme)
        
        layout.addLayout(theme_layout)
        
        # Background Image Setting
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel(self.app.tr("background_image")))
        
        self.lbl_bg_path = QLabel(os.path.basename(self.selected_background_image) if self.selected_background_image else "None")
        bg_layout.addWidget(self.lbl_bg_path)
        
        btn_select_bg = QPushButton(self.app.tr("select_image"))
        btn_select_bg.clicked.connect(self._select_background_image)
        bg_layout.addWidget(btn_select_bg)
        
        btn_clear_bg = QPushButton(self.app.tr("clear_image"))
        btn_clear_bg.clicked.connect(self._clear_background_image)
        bg_layout.addWidget(btn_clear_bg)
        
        layout.addLayout(bg_layout)

        # Opacity Slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel(self.app.tr("bg_opacity")))
        
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(int(self.selected_opacity * 100))
        self.slider_opacity.valueChanged.connect(self._update_opacity_label)
        
        self.lbl_opacity_val = QLabel(f"{int(self.selected_opacity * 100)}%")
        self.lbl_opacity_val.setFixedWidth(40)
        
        opacity_layout.addWidget(self.slider_opacity)
        opacity_layout.addWidget(self.lbl_opacity_val)
        
        layout.addLayout(opacity_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_apply = QPushButton(self.app.tr("apply"))
        btn_apply.clicked.connect(self._apply_settings)
        
        btn_cancel = QPushButton(self.app.tr("cancel"))
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        
        # Help Button
        btn_help = QPushButton(self.app.tr("help_customization"))
        btn_help.clicked.connect(self._open_help)
        btn_layout.addWidget(btn_help)
        
        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_cancel)
        
        # Full Reset Button
        btn_full_reset = QPushButton(self.app.tr("full_reset"))
        btn_full_reset.clicked.connect(self._full_reset)
        btn_layout.addWidget(btn_full_reset)
        
        layout.addLayout(btn_layout)

    def _pick_text_color(self):
        current_color = QColor(self.selected_text_color)
        color = QColorDialog.getColor(current_color, self, self.app.tr("select_text_color"))
        
        if color.isValid():
            self.selected_text_color = color.name() # Returns color in #RRGGBB format
            self.color_preview_label.setStyleSheet(f"background-color: {self.selected_text_color}; border: 1px solid black;")

    def _select_background_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            self.app.tr("select_image"), 
            "", 
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            # Try to make relative path
            try:
                app_path = get_app_path()
                rel_path = os.path.relpath(file_path, app_path)
                # Check if it's actually shorter or reasonable (e.g. not going up too many levels if not needed, 
                # but usually relative is preferred for portability)
                self.selected_background_image = rel_path
                self.lbl_bg_path.setText(rel_path)
            except ValueError:
                # Different drives on Windows
                self.selected_background_image = file_path
                self.lbl_bg_path.setText(os.path.basename(file_path))

    def _clear_background_image(self):
        self.selected_background_image = ""
        self.lbl_bg_path.setText("None")

    def _update_selected_theme(self, text):
        if text in self.theme_map:
            self.selected_theme = self.theme_map[text]

    def _update_opacity_label(self, value):
        self.selected_opacity = value / 100.0
        self.lbl_opacity_val.setText(f"{value}%")

    def _apply_settings(self):
        if self.selected_text_color != self.initial_text_color:
            self.app.update_text_color(self.selected_text_color)
            
        if self.selected_background_image != self.initial_background_image:
            self.app.update_background_image(self.selected_background_image)
            
        if self.selected_opacity != self.initial_opacity:
            self.app.update_background_opacity(self.selected_opacity)

        if self.selected_theme != self.initial_theme:
            self.app.apply_theme(self.selected_theme)

        # Always update if it changed from initial, OR if full reset happened (which effectively changes selection)
        if self.selected_input_bg != self.initial_input_bg:
            self.app.update_input_bg_color(self.selected_input_bg)

        if self.selected_font != self.initial_font:
            self.app.update_app_font(self.selected_font)
        
        # Save configuration after all changes have been applied to the app_config instance
        self.app.config_manager.save()
        self.accept()

    def _pick_input_bg_color(self):
        current = QColor(self.selected_input_bg) if self.selected_input_bg else Qt.GlobalColor.white
        color = QColorDialog.getColor(current, self, self.app.tr("input_bg_color"))
        
        if color.isValid():
            self.selected_input_bg = color.name()
            self.input_bg_preview.setStyleSheet(f"background-color: {self.selected_input_bg}; border: 1px solid black;")

    def _reset_input_bg_color(self):
        self.selected_input_bg = ""
        self.input_bg_preview.setStyleSheet("background-color: transparent; border: 1px solid black;")

    def _full_reset(self):
        reply = QMessageBox.question(
            self, 
            self.app.tr("full_reset"), 
            self.app.tr("confirm_full_reset"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # defaults
            self.selected_text_color = "#ffffff"
            self.selected_background_image = ""
            self.selected_opacity = 1.0
            self.selected_theme = "dark"
            self.selected_input_bg = "#3c3c3c"
            self.selected_font = ""

            # Update UI to reflect resets
            self.color_preview_label.setStyleSheet(f"background-color: {self.selected_text_color}; border: 1px solid black;")
            self.lbl_bg_path.setText("None")
            self.slider_opacity.setValue(100)
            
            if "dark" in self.theme_map_inv:
                self.combo_theme.setCurrentText(self.theme_map_inv["dark"])
            
            self.input_bg_preview.setStyleSheet(f"background-color: {self.selected_input_bg}; border: 1px solid black;")
            self.combo_font.setCurrentIndex(0)
            
            # Apply and save the reset settings immediately
            self._apply_settings()
            self.app.config_manager.save() # Trigger config save after reset and apply

    def _get_compatible_fonts(self) -> list[str]:
        """Get list of fonts supporting Japanese."""
        # QFontDatabase methods are static in PyQt6
        families = QFontDatabase.families()
        compatible = []
        for family in families:
            # Check for Japanese writing system support
            if QFontDatabase.writingSystems(family) and QFontDatabase.WritingSystem.Japanese in QFontDatabase.writingSystems(family):
                compatible.append(family)
        return sorted(compatible)

    def _update_selected_font(self, font_name):
        if font_name == self.app.tr("default_font"):
            self.selected_font = ""
        else:
            self.selected_font = font_name

    def _open_help(self):
        """Open the HTML help file in default browser."""
        import webbrowser
        help_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appearance_help.html")
        if os.path.exists(help_path):
            webbrowser.open(f"file:///{help_path}")
        else:
            QMessageBox.warning(self, "Help Error", f"Help file not found at:\n{help_path}")

