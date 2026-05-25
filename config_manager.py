"""
Configuration Management Module

A module for centrally managing application settings.
Provides unified access for loading, saving, and accessing settings.
"""

import json
import os
import logging
from dataclasses import dataclass, asdict, field
from typing import Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class UIConfig:
    """UI dimensions and layout settings."""
    window_width: int = 1000
    window_height: int = 950
    right_top_height: int = 600
    log_min_height: int = 100
    log_default_height: int = 150
    image_preview_max_width: int = 600
    image_preview_max_height: int = 260


@dataclass
class AppConfig:
    """Application settings."""
    # Language setting
    language: str = "en"
    
    # Crop settings
    crop_mode: str = "drag"
    crop_top_percent: float = 0.0
    crop_right_percent: float = 0.0
    
    # Application state
    current_config_key: str = "43311"
    character_var: str = "General"
    mode_var: str = "manual"
    score_mode_var: str = "batch"
    auto_apply_main_stats: bool = True
    
    # Calculation method selection
    enabled_calc_methods: dict = field(default_factory=lambda: {
        "normalized": True,
        "ratio": True,
        "roll": True,
        "effective": True,
        "cv": True
    })
    
    # Theme setting
    theme: str = "light"
    
    # UI settings (nested settings)
    ui: UIConfig = field(default_factory=UIConfig)
    
    # Text Color setting
    text_color: str = "#ffffff"
    
    # Background Image setting
    background_image: str = ""
    background_opacity: float = 0.9
    
    # Custom Input Background Color
    custom_input_bg_color: str = ""
    
    # Font setting
    app_font: str = ""

    def validate(self) -> bool:
        """Validate the setting values.
        
        Returns:
            True: All settings are valid, False: There are invalid settings.
        """
        # Validate language setting
        if self.language not in ["ja", "en"]:
            logger.warning(f"Invalid language: {self.language}, using 'en'")
            self.language = "en"
        
        # Validate crop settings (0-100%)
        if not (0 <= self.crop_top_percent <= 100):
            logger.warning(f"Invalid crop_top_percent: {self.crop_top_percent}, resetting to 0")
            self.crop_top_percent = 0.0
        
        if not (0 <= self.crop_right_percent <= 100):
            logger.warning(f"Invalid crop_right_percent: {self.crop_right_percent}, resetting to 0")
            self.crop_right_percent = 0.0
        
        # Validate crop mode
        if self.crop_mode not in ["drag", "percent"]:
            logger.warning(f"Invalid crop_mode: {self.crop_mode}, using 'drag'")
            self.crop_mode = "drag"
        
        # Validate input mode
        if self.mode_var not in ["manual", "ocr"]:
            logger.warning(f"Invalid mode_var: {self.mode_var}, using 'manual'")
            self.mode_var = "manual"
        
        # Validate calculation mode
        if self.score_mode_var not in ["batch", "single"]:
            logger.warning(f"Invalid score_mode_var: {self.score_mode_var}, using 'batch'")
        if self.score_mode_var not in ["batch", "single"]:
            logger.warning(f"Invalid score_mode_var: {self.score_mode_var}, using 'batch'")
            self.score_mode_var = "batch"
            
        # Validate enabled calculation methods
        if not isinstance(self.enabled_calc_methods, dict):
            logger.warning("Invalid enabled_calc_methods type, resetting to defaults")
            self.enabled_calc_methods = {
                "normalized": True, "ratio": True, "roll": True, "effective": True, "cv": True
            }
        else:
            # Ensure all method keys exist
            default_methods = {"normalized", "ratio", "roll", "effective", "cv"}
            for method in default_methods:
                if method not in self.enabled_calc_methods:
                    self.enabled_calc_methods[method] = True
            
            # Ensure at least one method is enabled
            if not any(self.enabled_calc_methods.values()):
                logger.warning("No calculation methods enabled, enabling all methods")
                for method in self.enabled_calc_methods:
                    self.enabled_calc_methods[method] = True
            
        # Validate background opacity
        if not (0.0 <= self.background_opacity <= 1.0):
            logger.warning(f"Invalid background_opacity: {self.background_opacity}, resetting to 0.9")
            self.background_opacity = 0.9
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format (without expanding UI settings)."""
        data = asdict(self)
        # Keep UIConfig nested
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Create AppConfig from a dictionary."""
        # Separate UI settings
        ui_data = data.get('ui', {})
        ui_config = UIConfig(**ui_data) if ui_data else UIConfig()
        
        # Get settings other than UI
        app_data = {k: v for k, v in data.items() if k != 'ui'}
        
        config = cls(**app_data, ui=ui_config)
        # Run validation after creation
        config.validate()
        return config


class ConfigManager:
    """Configuration management class.
    
    Manages application and UI settings,
    and provides file saving and loading.
    """
    
    def __init__(self, config_path: str):
        """
        Args:
            config_path: Path to the configuration file.
        """
        self.config_path = config_path
        self.config = AppConfig()
    
    def load(self) -> bool:
        """Load from the configuration file.
        
        Returns:
            True: Load successful, False: File does not exist or load failed.
        """
        if not os.path.exists(self.config_path):
            logger.info(f"Configuration file not found. Using default settings: {self.config_path}")
            return False
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Backward compatibility: Convert from old (flat) to new (nested) format
            if 'ui' not in data:
                # Extract UI settings from the flat structure
                ui_keys = {
                    'window_width', 'window_height', 'right_top_height',
                    'log_min_height', 'log_default_height',
                    'image_preview_max_width', 'image_preview_max_height'
                }
                ui_data = {k: data.pop(k) for k in ui_keys if k in data}
                if ui_data:
                    data['ui'] = ui_data
            
            self.config = AppConfig.from_dict(data)
            logger.info(f"Settings loaded from: {self.config_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in configuration file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            return False
    
    def save(self) -> bool:
        """Save settings to a file.
        
        Returns:
            True: Save successful, False: Save failed.
        """
        try:
            # Validate before saving
            self.config.validate()
            
            # Create directory if it does not exist
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Settings saved to: {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False
    
    def get_app_config(self) -> AppConfig:
        """Get application settings.
        
        Returns:
            AppConfig instance.
        """
        return self.config
    
    def get_ui_config(self) -> UIConfig:
        """Get UI settings.
        
        Returns:
            UIConfig instance.
        """
        return self.config.ui
    
    def update_app_setting(self, key: str, value: Any) -> None:
        """Update an application setting.
        
        Args:
            key: The setting key.
            value: The setting value.
        """
        if hasattr(self.config, key):
            setattr(self.config, key, value)
        else:
            logger.warning(f"Unknown setting key: {key}")
    
    def update_ui_setting(self, key: str, value: Any) -> None:
        """Update a UI setting.
        
        Args:
            key: The setting key.
            value: The setting value.
        """
        if hasattr(self.config.ui, key):
            setattr(self.config.ui, key, value)
        else:
            logger.warning(f"Unknown UI setting key: {key}")
