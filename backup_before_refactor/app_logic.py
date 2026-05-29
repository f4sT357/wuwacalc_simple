"""
Application Logic Module (PyQt6)

Provides core application logic including OCR, data loading/saving, and character profile management.
"""

import os
import logging
import json
import re
import shutil
import time
from typing import Optional, Any

from PyQt6.QtWidgets import QMessageBox, QFileDialog, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QObject, pyqtSignal

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageQt
    is_pil_installed = True
except ImportError:
    is_pil_installed = False

try:
    import pytesseract
    is_pytesseract_installed = True
except ImportError:
    is_pytesseract_installed = False

from constants import (
    CHARACTER_STAT_WEIGHTS, STAT_ALIASES, TAB_CONFIGS,
    CHARACTER_MAIN_STATS, get_char_internal_name, get_char_japanese_name
)
from utils import get_app_path

class AppLogic(QObject):
    log_message = pyqtSignal(str)
    ocr_error = pyqtSignal(str, str)
    info_message = pyqtSignal(str, str)
    
    _tesseract_cmd_cached: Optional[str] = None # Class-level cache for tesseract_cmd

    def __init__(self, tr_func):
        super().__init__()
        self.tr = tr_func

    def _perform_ocr(self, image: Any) -> Optional[str]:
        start_time = time.time()
        if not is_pytesseract_installed:
            self.log_message.emit(self.tr("pytesseract_not_installed"))
            return None

        # Check cache first
        if AppLogic._tesseract_cmd_cached:
            pytesseract.pytesseract.tesseract_cmd = AppLogic._tesseract_cmd_cached
        else:
            # If not cached, try to find it
            current_tcmd = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
            if current_tcmd and (os.path.sep in str(current_tcmd) or os.path.isabs(str(current_tcmd))):
                if not os.path.isfile(current_tcmd):
                    found = shutil.which("tesseract")
                    if found:
                        pytesseract.pytesseract.tesseract_cmd = found
                        self.log_message.emit(self.tr("tesseract_found_path", found))
                    else:
                        self.log_message.emit(self.tr("ocr_tesseract_not_found", current_tcmd))
                        return None
                AppLogic._tesseract_cmd_cached = pytesseract.pytesseract.tesseract_cmd # Cache it
            else:
                found = shutil.which("tesseract")
                if found:
                    pytesseract.pytesseract.tesseract_cmd = found
                    self.log_message.emit(self.tr("tesseract_found_path", found))
                    AppLogic._tesseract_cmd_cached = found # Cache it
                else:
                    self.log_message.emit(self.tr("tesseract_not_found_sys"))
                    return None

        try:
            processed = self._preprocess_for_ocr(image)
            custom_config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
            ocr_text = pytesseract.image_to_string(processed, lang="jpn+eng", config=custom_config)
            end_time = time.time()
            self.log_message.emit(f"OCR process took {end_time - start_time:.2f} seconds.")
            return ocr_text
        except pytesseract.TesseractError as te:
            self.ocr_error.emit(self.tr("ocr_error_title"), self.tr("ocr_lang_data_error", te))
            self.log_message.emit(self.tr("ocr_lang_data_error_log", te))
        except FileNotFoundError as fnf:
            self.ocr_error.emit(self.tr("ocr_error_title"), self.tr("tesseract_exec_not_found", fnf))
            self.log_message.emit(self.tr("tesseract_exec_error_log", fnf))
        except Exception as ocr_error:
            self.ocr_error.emit(self.tr("ocr_error_title"), self.tr("ocr_process_error", ocr_error))
            self.log_message.emit(self.tr("ocr_process_error_log", ocr_error))
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
        """Parses substats from OCR text and returns data and log messages."""
        if not ocr_text or not ocr_text.strip():
            return [], []

        lines = [
            re.sub(r'^[\.\-・\s]+', '', line.strip())
            for line in ocr_text.strip().splitlines()
            if line.strip()
        ]
        last_five = lines[-5:] if len(lines) >= 5 else lines
        
        alias_pairs = []
        for stat, aliases in STAT_ALIASES.items():
            for alias in aliases:
                alias_pairs.append((stat, alias))
        
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
                
                # Use the translation system for logs
                stat_name_for_log = self.tr(stat_found)
                
                log_messages.append(self.tr("ocr_auto_fill_success", i+1, stat_name_for_log, num_found, "%" if is_percent else ""))
        
        return found_substats, log_messages

    def detect_cost_from_ocr(self, ocr_text: str) -> Optional[str]:
        """
        Detects the cost (4, 3, 1) from the OCR text.
        """
        if not ocr_text:
            return None
        
        # 1. Search for explicit "Cost" text
        # Patterns: "COST 4", "COST: 4", "Cost4", "コスト4", "コスト 4", etc.
        cost_pattern = re.compile(r'(?:COST|Cost|cost|コスト)[\s:.]*([134])')
        match = cost_pattern.search(ocr_text)
        if match:
            return match.group(1)
            
        # 2. Search for Class Name (Overlord, Elite, Common) if Cost is missed
        # Keywords based on likely OCR output for Class names
        # Overlord -> 4, Elite -> 3, Common -> 1
        # Japanese: 怒涛/海嘯 (4), 巨浪 (3), 軽波 (1) - Note: Class names might vary or be harder to detect cleanly
        # For now, sticking to explicit numbers or simple English class names if they appear.
        
        if "Overlord" in ocr_text or "怒涛" in ocr_text or "海嘯" in ocr_text: 
             return "4"
        if "Elite" in ocr_text or "巨浪" in ocr_text:
             return "3"
        if "Common" in ocr_text or "軽波" in ocr_text:
             return "1"
             
        return None

    def detect_main_stat_from_ocr(self, ocr_text: str) -> Optional[str]:
        """
        Attempts to detect the main stat from OCR text.
        Returns a canonical main stat string (as used in MAIN_STAT_OPTIONS)
        or None if not found.
        """
        if not ocr_text:
            return None

        text = ocr_text

        # Build candidate list from MAIN_STAT_OPTIONS
        try:
            from constants import MAIN_STAT_OPTIONS, STAT_ALIASES
        except Exception:
            MAIN_STAT_OPTIONS = {}
            STAT_ALIASES = {}

        candidates = []
        for v in MAIN_STAT_OPTIONS.values():
            candidates.extend(v)

        # Deduplicate while preserving order
        seen = set()
        uniq_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq_candidates.append(c)

        # First try direct / alias matches
        for cand in uniq_candidates:
            aliases = STAT_ALIASES.get(cand, []) if isinstance(STAT_ALIASES, dict) else []
            # check both canonical and aliases
            for a in (aliases + [cand]):
                if a and a in text:
                    return cand

        # Fallback heuristics for common stats
        if re.search(r'HP\s*%|HP%|体力%', text):
            return 'HP%'
        if re.search(r'\bHP\b|体力', text):
            return 'HP'
        if re.search(r'攻撃力\s*%|攻撃力%|攻撃%', text) or 'ATK' in text:
            return '攻撃力%'
        if re.search(r'攻撃力\b|こうげき', text):
            return '攻撃力'
        if re.search(r'防御力\s*%|防御%', text) or 'DEF' in text:
            return '防御力%'
        if re.search(r'防御力\b', text):
            return '防御力'
        if 'クリティカル率' in text or 'クリ率' in text or 'クリティカル' in text:
            return 'クリティカル率'
        if 'クリティカルダメージ' in text or 'クリダメ' in text:
            return 'クリティカルダメージ'

        return None

    character_profile_saved = pyqtSignal(str, str) # name, config_key

    def _save_character_profile(self, name: str, costkey: str, mainstats: dict, weights: dict) -> None:
        try:
            base_dir = get_app_path()
            folder_name = "character_settings_jsons"
            target_dir = os.path.join(base_dir, folder_name)
            os.makedirs(target_dir, exist_ok=True)
            
            japanese_name_for_file = get_char_japanese_name(name)
            safe_name = self._sanitize_filename(japanese_name_for_file) or "character"
            file_path = os.path.join(target_dir, f"{safe_name}_character.json")
            
            normalized_key = self._normalize_cost_key(costkey, "43311") # Pass a default
            
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
            
            self.log_message.emit(f"Character profile saved: {name} -> {file_path}")
            self.character_profile_saved.emit(name, normalized_key)
            
        except Exception as e:
            self.log_message.emit(f"Error saving character profile: {e}")

    def _load_character_profiles(self) -> tuple[dict[str, str], list[tuple[str, str]]]:
        """Loads character profiles and returns a config map and a list for the UI."""
        character_config_map = {}
        items_to_add = []

        try:
            base_dir = get_app_path()
            folder_name = "character_settings_jsons"

            # Search for character_settings_jsons in current and parent directories (up to 3 levels)
            target_dir = None
            search_dir = base_dir
            for _ in range(4):
                candidate = os.path.join(search_dir, folder_name)
                if os.path.exists(candidate):
                    target_dir = candidate
                    break
                # Move one level up
                parent = os.path.dirname(search_dir)
                if parent == search_dir:
                    break
                search_dir = parent

            if not target_dir:
                self.log_message.emit(f"Character settings folder not found: searched from {base_dir} upwards for '{folder_name}'")
                return {}, []
            else:
                self.log_message.emit(f"Character settings folder found: {target_dir}")

            # Add predefined characters first
            from constants import _CHAR_NAME_MAP_EN_TO_JP
            predefined_chars = [name for name in _CHAR_NAME_MAP_EN_TO_JP.keys() if name in CHARACTER_STAT_WEIGHTS]
            for char_name in predefined_chars:
                items_to_add.append((self.tr(char_name), char_name))

            # Load from JSONs
            for filename in os.listdir(target_dir):
                if not filename.endswith("_character.json"):
                    continue
                
                file_path = os.path.join(target_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    self.log_message.emit(f"DEBUG: _load_character_profiles - Processing file: {filename}")
                    char_name_en = data.get("character")
                    char_name_jp = data.get("character_jp")
                    self.log_message.emit(f"DEBUG: _load_character_profiles - Initial from JSON: EN='{char_name_en}', JP='{char_name_jp}'")

                    # Handle cases where character_jp might be missing or in an old format
                    # Attempt to infer missing names
                    if not char_name_en and char_name_jp:
                        self.log_message.emit(f"DEBUG: _load_character_profiles - EN missing, deriving from JP: '{char_name_jp}'")
                        char_name_en = get_char_internal_name(char_name_jp)
                        self.log_message.emit(f"DEBUG: _load_character_profiles - Derived EN: '{char_name_en}'")
                    elif not char_name_jp and char_name_en:
                        self.log_message.emit(f"DEBUG: _load_character_profiles - JP missing, deriving from EN: '{char_name_en}'")
                        derived_jp_name = get_char_japanese_name(char_name_en)
                        if derived_jp_name == char_name_en:
                            self.log_message.emit(f"DEBUG: _load_character_profiles - No specific JP mapping for '{char_name_en}', using self.tr for display.")
                            char_name_jp = self.tr(char_name_en)
                        else:
                            char_name_jp = derived_jp_name
                        self.log_message.emit(f"DEBUG: _load_character_profiles - Derived JP: '{char_name_jp}'")
                    
                    # Final validation
                    if not (char_name_en and char_name_jp):
                        self.log_message.emit(f"DEBUG: _load_character_profiles - Skipping invalid character file: {filename} (incomplete name data after processing). Final EN='{char_name_en}', JP='{char_name_jp}'")
                        continue
                    
                    # Add to data structures
                    CHARACTER_STAT_WEIGHTS[char_name_en] = data.get("character_weights", {})
                    CHARACTER_MAIN_STATS[char_name_en] = data.get("character_mainstats", {})
                    config = data.get("config", self._normalize_cost_key(data.get("costkey", "43311"), "43311"))
                    character_config_map[char_name_en] = config

                    # Add to UI list if not already there
                    if not any(item for item in items_to_add if item[1] == char_name_en):
                        self.log_message.emit(f"DEBUG: _load_character_profiles - Adding to UI list: (Display='{char_name_jp}', Internal='{char_name_en}')")
                        items_to_add.append((char_name_jp, char_name_en))
                    
                    self.log_message.emit(f"Loaded character file: {char_name_en} ({filename})")

                except Exception as e:
                    self.log_message.emit(f"Warning: Error loading character file ({filename}): {e}")
            
            # Sort the final list for display
            items_to_add.sort(key=lambda x: x[0])
            self.log_message.emit(f"Character list prepared: {len(items_to_add)} characters")
            return character_config_map, items_to_add
            
        except Exception as e:
            self.log_message.emit(f"Error loading character profiles: {e}")
            return {}, []

    def save_data(self, file_path: str, config_key: str, character_var: str, auto_apply: bool, score_mode: str, tabs_content: dict) -> None:
        """Builds and saves data to a file."""
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
                # Assuming content holds widgets, we need to extract text.
                # This is still a bit coupled. A better approach would be to pass plain data.
                # For now, we'll assume the caller extracts the text.
                # Let's redefine the expected structure for tabs_content.
                # The caller should pass data like:
                # {"tab_name": {"main_stat": "...", "substats": [{"stat": "...", "value": "..."}, ...]}}
                echo_data = {
                    "main_stat": content.get("main_stat", ""),
                    "substats": content.get("substats", [])
                }
                data["echoes"][tab_name] = echo_data
                
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.info_message.emit("Success", "Data saved successfully.")
            self.log_message.emit(f"Saved to: {file_path}")
        except Exception as e:
            self.info_message.emit("Error", f"Save failed: {e}")
            self.log_message.emit(f"Save error: {e}")

    def _load_data(self, file_path: str) -> Optional[dict]:
        """Loads and parses data from a file, returning a dictionary for the UI."""
        if not file_path:
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # --- Data Validation and Normalization ---
            self.log_message.emit(f"DEBUG: _load_data - Loading data from: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # --- Data Validation and Normalization ---
            character_name_jp = data.get('character_jp')
            character_name = data.get('character')
            self.log_message.emit(f"DEBUG: _load_data - Initial from JSON: EN='{character_name}', JP='{character_name_jp}'")
            
            # Ensure mappings are up-to-date with loaded data and handle missing names
            if character_name and character_name_jp:
                from constants import _CHAR_NAME_MAP_JP_TO_EN, _CHAR_NAME_MAP_EN_TO_JP
                if character_name_jp not in _CHAR_NAME_MAP_JP_TO_EN:
                    _CHAR_NAME_MAP_JP_TO_EN[character_name_jp] = character_name
                    self.log_message.emit(f"DEBUG: _load_data - Added mapping: JP='{character_name_jp}' -> EN='{character_name}'")
                if character_name not in _CHAR_NAME_MAP_EN_TO_JP:
                    _CHAR_NAME_MAP_EN_TO_JP[character_name] = character_name_jp
                    self.log_message.emit(f"DEBUG: _load_data - Added mapping: EN='{character_name}' -> JP='{character_name_jp}'")
            elif character_name and not character_name_jp:
                self.log_message.emit(f"DEBUG: _load_data - Only EN name found: '{character_name}', deriving JP name.")
                character_name_jp = get_char_japanese_name(character_name)
                self.log_message.emit(f"DEBUG: _load_data - Derived JP name: '{character_name_jp}'")
            elif character_name_jp and not character_name:
                self.log_message.emit(f"DEBUG: _load_data - Only JP name found: '{character_name_jp}', deriving EN name.")
                character_name = get_char_internal_name(character_name_jp)
                self.log_message.emit(f"DEBUG: _load_data - Derived EN name: '{character_name}'")
            
            # If after all derivations, either name is still missing, set a fallback or log.
            if not character_name and character_name_jp:
                self.log_message.emit(f"DEBUG: _load_data - EN still missing, deriving from JP: '{character_name_jp}'")
                character_name = get_char_internal_name(character_name_jp)
                self.log_message.emit(f"DEBUG: _load_data - Derived EN name: '{character_name}'")
            elif not character_name_jp and character_name:
                self.log_message.emit(f"DEBUG: _load_data - JP still missing, deriving from EN: '{character_name}'")
                character_name_jp = get_char_japanese_name(character_name)
                self.log_message.emit(f"DEBUG: _load_data - Derived JP name: '{character_name_jp}'")
            
            if not (character_name and character_name_jp):
                self.log_message.emit(f"Warning: Could not fully resolve character names from loaded data (EN: {character_name}, JP: {character_name_jp}). Using available or fallback.")
                # Fallback to character_name if character_name_jp is still missing
                if not character_name_jp and character_name:
                    character_name_jp = character_name
                # Fallback to character_name_jp if character_name is still missing
                if not character_name and character_name_jp:
                    character_name = character_name_jp
            self.log_message.emit(f"DEBUG: _load_data - Final resolved names: EN='{character_name}', JP='{character_name_jp}'")

            custom_weights = data.get("character_weights")
            if custom_weights and character_name:
                CHARACTER_STAT_WEIGHTS[character_name] = custom_weights

            custom_mainstats = data.get("character_mainstats")
            if custom_mainstats and character_name:
                CHARACTER_MAIN_STATS[character_name] = custom_mainstats

            config_value = data.get("config") or data.get("costkey") or "43311"
            normalized_config = self._normalize_cost_key(config_value, "43311")

            # --- Resolve Stat Names in Echoes Data ---
            echoes_data = data.get("echoes", {})
            for tab_name, echo_data in echoes_data.items():
                main_stat_raw = echo_data.get("main_stat", "")
                resolved_main_stat = self._resolve_stat_name(main_stat_raw)
                echo_data["main_stat"] = resolved_main_stat or main_stat_raw
                
                for substat in echo_data.get("substats", []):
                    stat_name_raw = substat.get("stat", "")
                    resolved_substat = self._resolve_stat_name(stat_name_raw)
                    substat["stat"] = resolved_substat or stat_name_raw

            # --- Prepare structured return data ---
            loaded_ui_data = {
                "character_name": character_name,
                "character_added": "custom" if custom_weights or custom_mainstats else None,
                "auto_apply": data.get("auto_apply", True),
                "score_mode": data.get("score_mode", "batch"),
                "config_key": normalized_config,
                "echoes": echoes_data,
                "force_apply_main_stats": bool(custom_mainstats) or not echoes_data
            }
            
            self.info_message.emit("Success", "Data loaded (required fields have been updated).")
            self.log_message.emit("Data loading complete.")
            return loaded_ui_data

        except Exception as e:
            self.info_message.emit("Error", f"Load failed: {e}")
            self.log_message.emit(f"Load error: {e}")
            return None

    def _resolve_stat_name(self, raw_name: str) -> Optional[str]:
        """Resolves a raw stat name (Japanese, alias, etc.) to the internal English name."""
        if not raw_name:
            return None
        for key, aliases in STAT_ALIASES.items():
            # The key itself is a valid name (usually the one we want)
            if raw_name == key or self.tr(key) == raw_name:
                return key
            # Check against all aliases
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
        return "43311" # Fallback to a default if all else fails

    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[^0-9A-Za-z一-龠ぁ-んァ-ヴー_-]', '_', name)
