"""
UI Construction Module (PyQt6)

Provides UI construction for the main window and tab management.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QTabWidget, QScrollArea, QTextEdit, QLabel, 
                             QPushButton, QComboBox, QCheckBox, QRadioButton, 
                             QGroupBox, QSplitter, QFrame, QSizePolicy, QLineEdit)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage

from constants import TAB_CONFIGS, MAIN_STAT_OPTIONS, SUBSTAT_MAX_VALUES

class UIComponents:
    """Class responsible for UI construction."""
    
    # Constants
    RIGHT_TOP_HEIGHT = 350
    LOG_MIN_HEIGHT = 80
    LOG_DEFAULT_HEIGHT = 150
    
    def __init__(self, app):
        """
        Initialization
        
        Args:
            app: The main application instance.
        """
        self.app = app
        self.main_widget = None
    
    def create_main_layout(self) -> None:
        """Create the main window's entire UI."""
        self.main_widget = QWidget()
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Main Splitter (Left: Settings/Tabs, Right: Image/Log/Result)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # Left Container
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.create_left_pane(left_layout, self.app.charcombo)
        self.main_splitter.addWidget(left_container)
        
        # Right Container
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.create_right_pane(right_layout)
        self.main_splitter.addWidget(right_container)
        
        # Set initial sizes (approximate)
        self.main_splitter.setSizes([500, 400])
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)

    def create_left_pane(self, parent_layout: QVBoxLayout, charcombo: QComboBox) -> None:
        """Create the UI for the left pane (settings/input)."""
        self.create_settings_frame(parent_layout, charcombo)
        self.create_buttons_frame(parent_layout)
        
        # Tabs
        self.app.notebook = QTabWidget()
        self.app.notebook.blockSignals(True) # Block signals during initial setup
        self.app.notebook.currentChanged.connect(self.app.on_tab_changed)
        self.app.notebook.blockSignals(False) # Unblock signals after setup
        parent_layout.addWidget(self.app.notebook)
        
        self.create_result_frame(parent_layout)
    
    def create_settings_frame(self, parent_layout: QVBoxLayout, charcombo: QComboBox) -> None:
        """Create the UI for the basic settings area."""
        from constants import CHARACTER_STAT_WEIGHTS
        
        self.settings_group = QGroupBox(self.app.tr("basic_settings"))
        settings_layout = QGridLayout(self.settings_group)
        parent_layout.addWidget(self.settings_group)
        
        # Row 0
        self.lbl_cost_config = QLabel(self.app.tr("cost_config"))
        settings_layout.addWidget(self.lbl_cost_config, 0, 0)
        self.app.config_combo = QComboBox()
        self.app.config_combo.addItems(list(TAB_CONFIGS.keys()))
        self.app.config_combo.blockSignals(True) # Block signals during initial setup
        self.app.config_combo.setCurrentText(self.app.current_config_key)
        self.app.config_combo.blockSignals(False) # Unblock signals after setup
        self.app.config_combo.currentTextChanged.connect(self.app.on_config_change)
        settings_layout.addWidget(self.app.config_combo, 0, 1)
        
        self.lbl_character = QLabel(self.app.tr("character"))
        settings_layout.addWidget(self.lbl_character, 0, 2)
        # charcomboは外部から渡されたものを使用
        charcombo.setObjectName("CharComboBox")
        charcombo.currentTextChanged.connect(self.app.on_character_change)
        settings_layout.addWidget(charcombo, 0, 3)
        
        self.lbl_language = QLabel(self.app.tr("language"))
        settings_layout.addWidget(self.lbl_language, 0, 4)
        lang_combo = QComboBox()
        lang_combo.addItems(["ja", "en", "zh-TW"])
        lang_combo.setCurrentText(self.app.language)
        lang_combo.currentTextChanged.connect(self.app.on_language_change)
        settings_layout.addWidget(lang_combo, 0, 5)
        
        # Row 1: Input Mode
        self.lbl_input_mode = QLabel(self.app.tr("input_mode"))
        settings_layout.addWidget(self.lbl_input_mode, 1, 0)
        mode_layout = QHBoxLayout()
        
        self.rb_manual = QRadioButton(self.app.tr("manual"))
        self.rb_ocr = QRadioButton(self.app.tr("ocr"))
        
        # Group radio buttons
        self.mode_group = QGroupBox() # Invisible group logic handled by Qt auto-exclusive
        self.mode_group.setLayout(QHBoxLayout()) # Just a container
        # Actually, just adding them to layout works if they share parent, but let's be explicit if needed.
        # For simple layout:
        mode_layout.addWidget(self.rb_manual)
        mode_layout.addWidget(self.rb_ocr)
        
        if self.app.mode_var == "manual":
            self.rb_manual.setChecked(True)
        else:
            self.rb_ocr.setChecked(True)
            
        self.rb_manual.toggled.connect(lambda c: self.app.on_mode_change("manual") if c else None)
        self.rb_ocr.toggled.connect(lambda c: self.app.on_mode_change("ocr") if c else None)
        
        settings_layout.addLayout(mode_layout, 1, 1, 1, 3)
        
        # Auto Main & Theme
        right_sub_layout = QVBoxLayout()
        self.cb_auto_main = QCheckBox(self.app.tr("auto_main"))
        self.cb_auto_main.setChecked(self.app.auto_apply_main_stats)
        self.cb_auto_main.toggled.connect(self.app.on_auto_main_change)
        right_sub_layout.addWidget(self.cb_auto_main)
        
        # Theme button moved to display settings
        # btn_theme = QPushButton(self.app.tr("theme"))
        # btn_theme.clicked.connect(self.app.events.cycle_theme)
        # right_sub_layout.addWidget(btn_theme)
        
        settings_layout.addLayout(right_sub_layout, 1, 4, 1, 2)
        
        self.lbl_calc_mode = QLabel(self.app.tr("calc_mode"))
        settings_layout.addWidget(self.lbl_calc_mode, 2, 0)
        calc_mode_layout = QHBoxLayout()
        self.rb_batch = QRadioButton(self.app.tr("batch"))
        self.rb_single = QRadioButton(self.app.tr("single_only"))
        
        if self.app.score_mode_var == "batch":
            self.rb_batch.setChecked(True)
        else:
            self.rb_single.setChecked(True)
            
            self.rb_batch.toggled.connect(lambda c: self.app.on_score_mode_change("batch") if c else None)
            self.rb_single.toggled.connect(lambda c: self.app.on_score_mode_change("single") if c else None)
        
        calc_mode_layout.addWidget(self.rb_batch)
        calc_mode_layout.addWidget(self.rb_single)
        settings_layout.addLayout(calc_mode_layout, 2, 1, 1, 3)
        
        # Row 3: Calculation Methods Selection
        self.lbl_calc_methods = QLabel(self.app.tr("calc_methods"))
        settings_layout.addWidget(self.lbl_calc_methods, 3, 0)
        
        methods_layout = QHBoxLayout()
        
        # Create checkboxes for each calculation method
        self.app.cb_method_normalized = QCheckBox(self.app.tr("method_normalized"))
        self.app.cb_method_ratio = QCheckBox(self.app.tr("method_ratio"))
        self.app.cb_method_roll = QCheckBox(self.app.tr("method_roll"))
        self.app.cb_method_effective = QCheckBox(self.app.tr("method_effective"))
        self.app.cb_method_cv = QCheckBox(self.app.tr("method_cv"))
        
        # Initialize checkbox states from config
        enabled_methods = self.app.app_config.enabled_calc_methods
        self.app.logger.info(f"Initializing calc method checkboxes with: {enabled_methods}")
        self.app.cb_method_normalized.setChecked(enabled_methods.get("normalized", True))
        self.app.cb_method_ratio.setChecked(enabled_methods.get("ratio", True))
        self.app.cb_method_roll.setChecked(enabled_methods.get("roll", True))
        self.app.cb_method_effective.setChecked(enabled_methods.get("effective", True))
        self.app.cb_method_cv.setChecked(enabled_methods.get("cv", True))
        
        # Connect to event handler
        self.app.cb_method_normalized.toggled.connect(lambda: self.app.on_calc_method_changed())
        self.app.cb_method_ratio.toggled.connect(lambda: self.app.on_calc_method_changed())
        self.app.cb_method_roll.toggled.connect(lambda: self.app.on_calc_method_changed())
        self.app.cb_method_effective.toggled.connect(lambda: self.app.on_calc_method_changed())
        self.app.cb_method_cv.toggled.connect(lambda: self.app.on_calc_method_changed())
        
        # Add checkboxes to layout
        methods_layout.addWidget(self.app.cb_method_normalized)
        methods_layout.addWidget(self.app.cb_method_ratio)
        methods_layout.addWidget(self.app.cb_method_roll)
        methods_layout.addWidget(self.app.cb_method_effective)
        methods_layout.addWidget(self.app.cb_method_cv)
        methods_layout.addStretch()
        
        settings_layout.addLayout(methods_layout, 3, 1, 1, 5)

    def create_buttons_frame(self, parent_layout: QVBoxLayout) -> None:
        """Create the UI for the button area."""
        self.app.button_frame = QFrame()
        btn_layout = QHBoxLayout(self.app.button_frame)
        btn_layout.setContentsMargins(0, 5, 0, 5)
        parent_layout.addWidget(self.app.button_frame)
        
        buttons = [
            ("calculate", self.app.score_calc.calculate_all_scores),
            ("export_txt", self.app.export_result_to_txt),
            ("clear_all", self.app.clear_all),
            ("clear_tab", self.app.clear_current_tab),
            ("char_setting", self.app.opencharsetting),
            ("help", self.app._open_readme),
            ("display_settings", self.app.open_display_settings)
        ]
        self.action_buttons = {}
        for key, command in buttons:
            btn = QPushButton(self.app.tr(key))
            btn.clicked.connect(command)
            btn_layout.addWidget(btn)
            self.action_buttons[key] = btn
        
        btn_layout.addStretch() # Push buttons to left

    def create_right_pane(self, parent_layout: QVBoxLayout) -> None:
        """Create the UI for the right pane (results, log, image)."""
        # Vertical Splitter for Image vs Log
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        parent_layout.addWidget(right_splitter)
        
        # Image Area
        self.image_container = QWidget()
        image_layout = QVBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.create_image_frame(image_layout)
        right_splitter.addWidget(self.image_container)
        
        # Log Area
        self.log_group = QGroupBox(self.app.tr("log"))
        log_layout = QVBoxLayout(self.log_group)
        self.app.log_text = QTextEdit()
        self.app.log_text.setReadOnly(True)
        log_layout.addWidget(self.app.log_text)
        right_splitter.addWidget(self.log_group)
        
        right_splitter.setSizes([350, 150])

    def create_image_frame(self, parent_layout: QVBoxLayout) -> None:
        """Create the UI for the image preview area."""
        self.app.image_frame = QGroupBox(self.app.tr("ocr_image"))
        layout = QVBoxLayout(self.app.image_frame)
        parent_layout.addWidget(self.app.image_frame)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton(self.app.tr("load_image"))
        # Connect to image processor if available, otherwise fall back to app-level handler
        if hasattr(self.app, "image_proc") and self.app.image_proc is not None:
            self.btn_load.clicked.connect(self.app.image_proc.import_image)
        elif hasattr(self.app, "import_image"):
            self.btn_load.clicked.connect(self.app.import_image)
        self.btn_paste = QPushButton(self.app.tr("paste_clipboard"))
        if hasattr(self.app, "image_proc") and self.app.image_proc is not None:
            self.btn_paste.clicked.connect(self.app.image_proc.paste_from_clipboard)
        elif hasattr(self.app, "paste_from_clipboard"):
            self.btn_paste.clicked.connect(self.app.paste_from_clipboard)
        self.btn_crop = QPushButton(self.app.tr("perform_crop"))
        if hasattr(self.app, "image_proc") and self.app.image_proc is not None:
            self.btn_crop.clicked.connect(self.app.image_proc.perform_crop)
        elif hasattr(self.app, "perform_crop"):
            self.btn_crop.clicked.connect(self.app.perform_crop)
        
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_paste)
        btn_layout.addWidget(self.btn_crop)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Crop Settings
        crop_layout = QHBoxLayout()
        self.lbl_crop_mode = QLabel(self.app.tr("crop_mode"))
        crop_layout.addWidget(self.lbl_crop_mode)
        
        self.rb_crop_drag = QRadioButton(self.app.tr("drag"))
        self.rb_crop_percent = QRadioButton(self.app.tr("percent"))
        
        if self.app.crop_mode_var == "drag":
            self.rb_crop_drag.setChecked(True)
        else:
            self.rb_crop_percent.setChecked(True)
            
        self.rb_crop_drag.toggled.connect(lambda c: self.app.on_crop_mode_change("drag") if c else None)
        self.rb_crop_percent.toggled.connect(lambda c: self.app.on_crop_mode_change("percent") if c else None)
        
        crop_layout.addWidget(self.rb_crop_drag)
        crop_layout.addWidget(self.rb_crop_percent)
        
        self.lbl_top_percent = QLabel(self.app.tr("top_percent"))
        crop_layout.addWidget(self.lbl_top_percent)
        self.entry_top_p = QLineEdit(str(self.app.crop_top_percent_var))
        self.entry_top_p.setFixedWidth(50)
        self.entry_top_p.textChanged.connect(self.app.on_crop_percent_change)
        crop_layout.addWidget(self.entry_top_p)
        
        self.lbl_right_percent = QLabel(self.app.tr("right_percent"))
        crop_layout.addWidget(self.lbl_right_percent)
        self.entry_right_p = QLineEdit(str(self.app.crop_right_percent_var))
        self.entry_right_p.setFixedWidth(50)
        self.entry_right_p.textChanged.connect(self.app.on_crop_percent_change)
        crop_layout.addWidget(self.entry_right_p)
        
        crop_layout.addStretch()
        layout.addLayout(crop_layout)
        
        # Image Label (Scroll Area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.app.image_label = QLabel(self.app.tr("no_image"))
        self.app.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self.app.image_label)
        layout.addWidget(scroll)

    def create_result_frame(self, parent_layout: QVBoxLayout) -> None:
        """Create the UI for the result display area."""
        self.result_group = QGroupBox(self.app.tr("calc_result"))
        layout = QVBoxLayout(self.result_group)
        parent_layout.addWidget(self.result_group)
        
        self.app.result_text = QTextEdit()
        self.app.result_text.setReadOnly(True)
        layout.addWidget(self.app.result_text)
        
        # Configure tags/styles? QTextEdit uses HTML/CSS
        # We'll handle styling in the output generation or via simple HTML insertion

    def update_tabs(self) -> None:
        """Update tabs based on configuration."""
        if self.app.notebook is None:
            return
            
        self.app._updating_tabs = True
        try:
            config_key = self.app.current_config_key
            if config_key not in TAB_CONFIGS:
                self.app.gui_log(f"Invalid cost key '{config_key}' detected, falling back to 43311")
                config_key = "43311"
                self.app.current_config_key = config_key
                if self.app.config_combo:
                    self.app.config_combo.setCurrentText(config_key)
            
            new_config_tab_names = TAB_CONFIGS[config_key]
            
            # Save existing data
            old_data = {}
            for tab_name, content in self.app.tabs_content.items():
                main_val = content["main_widget"].currentText()
                sub_vals = []
                for stat_widget, val_widget in content["sub_entries"]:
                    sub_vals.append((stat_widget.currentText(), val_widget.text()))
                old_data[tab_name] = {
                    "main_stat": main_val,
                    "substats": sub_vals
                }
            
            # Clear all tabs
            self.app.notebook.clear()
            self.app.tabs_content = {}
            
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
                main_group = QGroupBox(self.app.tr("main_stat"))
                main_layout = QVBoxLayout(main_group)
                page_layout.addWidget(main_group)
                
                fallback_main_stats = [self.app.tr("HP"), self.app.tr("ATK"), self.app.tr("DEF")]
                translated_main_options = [self.app.tr(s) for s in MAIN_STAT_OPTIONS.get(cost_num, fallback_main_stats)]
                
                main_combo = QComboBox()
                main_combo.addItems(translated_main_options)
                main_layout.addWidget(main_combo)
                
                # Substats
                sub_group = QGroupBox(self.app.tr("substats"))
                sub_layout = QGridLayout(sub_group)
                page_layout.addWidget(sub_group)
                
                sub_entries = []
                translated_sub_options = [""] + [self.app.tr(s) for s in list(SUBSTAT_MAX_VALUES.keys())]
                
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
                # Translate Tab Name
                # Expected format: "costX_echo" or "costX_echo_Y"
                tab_label = tab_name
                if "cost" in tab_name:
                    try:
                        parts = tab_name.split('_')
                        # parts[0] is like "cost4"
                        c_num = parts[0].replace("cost", "")
                        base_label = self.app.tr("cost_echo", c_num)
                        
                        suffix = ""
                        # If there's a numbered suffix like _1, _2
                        if len(parts) >= 3 and parts[2].isdigit():
                            suffix = f" {parts[2]}"
                        
                        tab_label = f"{base_label}{suffix}"
                    except Exception:
                        pass # Fallback to raw tab_name

                self.app.notebook.addTab(page, tab_label)
                
                # Store references
                self.app.tabs_content[tab_name] = {
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
            self.app.gui_log(f"Tab update error: {e}")
        finally:
            self.app._updating_tabs = False

    def update_ui_mode(self) -> None:
        """Update the UI mode (OCR vs Manual)."""
        mode = self.app.mode_var
        if mode == "ocr":
            self.app.image_frame.setVisible(True)
        else:
            self.app.image_frame.setVisible(False)

    def retranslate_ui(self) -> None:
        """Update all UI text based on the current language."""
        # Settings
        if hasattr(self, "settings_group"): self.settings_group.setTitle(self.app.tr("basic_settings"))
        if hasattr(self, "lbl_cost_config"): self.lbl_cost_config.setText(self.app.tr("cost_config"))
        if hasattr(self, "lbl_character"): self.lbl_character.setText(self.app.tr("character"))
        if hasattr(self, "lbl_language"): self.lbl_language.setText(self.app.tr("language"))
        if hasattr(self, "lbl_input_mode"): self.lbl_input_mode.setText(self.app.tr("input_mode"))
        if hasattr(self, "rb_manual"): self.rb_manual.setText(self.app.tr("manual"))
        if hasattr(self, "rb_ocr"): self.rb_ocr.setText(self.app.tr("ocr"))
        if hasattr(self, "cb_auto_main"): self.cb_auto_main.setText(self.app.tr("auto_main"))
        if hasattr(self, "lbl_calc_mode"): self.lbl_calc_mode.setText(self.app.tr("calc_mode"))
        if hasattr(self, "rb_batch"): self.rb_batch.setText(self.app.tr("batch"))
        if hasattr(self, "rb_single"): self.rb_single.setText(self.app.tr("single_only"))
        if hasattr(self, "lbl_calc_methods"): self.lbl_calc_methods.setText(self.app.tr("calc_methods"))
        
        # Calc Methods Checkboxes
        if hasattr(self.app, "cb_method_normalized"): self.app.cb_method_normalized.setText(self.app.tr("method_normalized"))
        if hasattr(self.app, "cb_method_ratio"): self.app.cb_method_ratio.setText(self.app.tr("method_ratio"))
        if hasattr(self.app, "cb_method_roll"): self.app.cb_method_roll.setText(self.app.tr("method_roll"))
        if hasattr(self.app, "cb_method_effective"): self.app.cb_method_effective.setText(self.app.tr("method_effective"))
        if hasattr(self.app, "cb_method_cv"): self.app.cb_method_cv.setText(self.app.tr("method_cv"))
        
        # Image Area
        if hasattr(self.app, "image_frame"): self.app.image_frame.setTitle(self.app.tr("ocr_image"))
        if hasattr(self, "btn_load"): self.btn_load.setText(self.app.tr("load_image"))
        if hasattr(self, "btn_paste"): self.btn_paste.setText(self.app.tr("paste_clipboard"))
        if hasattr(self, "btn_crop"): self.btn_crop.setText(self.app.tr("perform_crop"))
        if hasattr(self, "lbl_crop_mode"): self.lbl_crop_mode.setText(self.app.tr("crop_mode"))
        if hasattr(self, "rb_crop_drag"): self.rb_crop_drag.setText(self.app.tr("drag"))
        if hasattr(self, "rb_crop_percent"): self.rb_crop_percent.setText(self.app.tr("percent"))
        if hasattr(self, "lbl_top_percent"): self.lbl_top_percent.setText(self.app.tr("top_percent"))
        if hasattr(self, "lbl_right_percent"): self.lbl_right_percent.setText(self.app.tr("right_percent"))
        
        # Results & Logs
        if hasattr(self, "result_group"): self.result_group.setTitle(self.app.tr("calc_result"))
        if hasattr(self, "log_group"): self.log_group.setTitle(self.app.tr("log"))
        
        # Buttons Frame
        if hasattr(self, "action_buttons"):
            for key, btn in self.action_buttons.items():
                btn.setText(self.app.tr(key))
        
        # Update character list (this will re-translate character names in the dropdown)
        self.app._filter_characters_by_config()
        
        # Update tabs
        self.update_tabs()
