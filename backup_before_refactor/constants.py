SUBSTAT_MAX_VALUES = {
    "クリティカル率": 10.5, "クリティカルダメージ": 21.0, "攻撃力%": 11.6, "攻撃力": 60,
    "HP%": 11.6, "HP": 580, "防御力%": 11.6, "防御力": 60, "共鳴効率": 12.4,
    "通常攻撃ダメージアップ": 11.6, "重撃ダメージアップ": 11.6, "共鳴スキルダメージアップ": 11.6, "共鳴解放ダメージアップ": 11.6
}

MAIN_STAT_OPTIONS = {
    "4": ["攻撃力%", "HP%", "防御力%", "クリティカル率", "クリティカルダメージ", "共鳴効率",
          "焦熱ダメージアップ", "凝縮ダメージアップ", "電導ダメージアップ",
          "気動ダメージアップ", "回折ダメージアップ", "消滅ダメージアップ"],
    "3": ["攻撃力%", "HP%", "防御力%", "焦熱ダメージアップ", "凝縮ダメージアップ",
          "電導ダメージアップ", "気動ダメージアップ", "回折ダメージアップ", "消滅ダメージアップ",
          "HP回復効果アップ"],
    "1": ["HP", "攻撃力", "防御力"]
}

MAIN_STAT_MULTIPLIER = 15.0

SUBSTAT_TYPES = {
    "HP": "Flat",
    "HP%": "Percent",
    "攻撃力": "Flat",
    "攻撃力%": "Percent",
    "防御力": "Flat",
    "防御力%": "Percent",
}

CHARACTER_STAT_WEIGHTS = {
    "Changli": {
        "クリティカル率": 2.3,
        "クリティカルダメージ": 2.3,
        "攻撃力%": 1.3,
        "攻撃力": 0.9,
        "HP%": 0.1,
        "HP": 0.1,
        "防御力%": 0.1,
        "防御力": 0.1,
        "共鳴効率": 1.0,
        "共鳴スキルダメージアップ": 1.1,
        "焦熱ダメージアップ": 1.2,
        "共鳴解放ダメージアップ": 0.8,
    }
}
CHARACTER_STAT_WEIGHTS["General"] = {
    "クリティカル率": 2.0,
    "クリティカルダメージ": 1.5,
    "攻撃力%": 1.0,
    "攻撃力": 0.5,
    "HP%": 0.2,
    "HP": 0.1,
    "防御力%": 0.1,
    "防御力": 0.1,
    "共鳴効率": 0.5,
    "重撃ダメージアップ": 0.5,
    "通常攻撃ダメージアップ": 0.5,
    "共鳴スキルダメージアップ": 0.5,
    "共鳴解放ダメージアップ": 0.5,
}

CHARACTER_MAIN_STATS = {
    "Changli": {
        "cost4_echo": "共鳴効率",
        "cost3_echo_1": "共鳴スキルダメージアップ", 
        "cost3_echo_2": "焦熱ダメージアップ",
        "cost1_echo_1": "クリティカル率",
        "cost1_echo_2": "クリティカルダメージ"
    },
    "General": {
        "cost4_echo": "共鳴効率",
        "cost3_echo_1": "攻撃力%",
        "cost3_echo_2": "攻撃力%", 
        "cost1_echo_1": "クリティカル率",
        "cost1_echo_2": "クリティカルダメージ"
    }
}

STAT_ALIASES = {
    "クリティカル率": ["クリティカル率", "クリ率", "クリティカル"],
    "クリティカルダメージ": ["クリティカルダメージ", "クリダメ", "クリダメージ"],
    "攻撃力%": ["攻撃力%", "攻撃力％", "攻撃力(%)", "攻撃%"],
    "攻撃力": ["攻撃力", "ATK", "こうげき"],
    "HP%": ["HP%", "HP％", "HP(%)", "体力%"],
    "HP": ["HP", "体力"],
    "防御力%": ["防御力%", "防御力％", "防御%"],
    "防御力": ["防御力", "DEF"],
    "共鳴効率": ["共鳴効率", "効率", "エネルギー効率"],
    "通常攻撃ダメージアップ": ["通常攻撃ダメージアップ", "通常攻撃up", "通常攻撃ダメージ", "通常ダメージ"],
    "重撃ダメージアップ": ["重撃ダメージアップ", "重撃up", "重撃ダメージ"],
    "共鳴スキルダメージアップ": ["共鳴スキルダメージアップ", "共鳴スキルup", "スキルダメージ"],
    "共鳴解放ダメージアップ": ["共鳴解放ダメージアップ", "共鳴解放up", "解放ダメージ"],
}

TAB_CONFIGS = {
    "43311": ["cost4_echo", "cost3_echo_1", "cost3_echo_2", "cost1_echo_1", "cost1_echo_2"],
    "カンタレラ": "Cantarella",
    "ツバキ": "Tsubaki",
    "長離": "Changli",
    "汎用": "General",
}

# Character name mapping: Japanese -> English internal identifier
_CHAR_NAME_MAP_JP_TO_EN = {
    "カンタレラ": "Cantarella",
    "ツバキ": "Tsubaki",
    "長離": "Changli",
    "汎用": "General",
}

_CHAR_NAME_MAP_EN_TO_JP = {v: k for k, v in _CHAR_NAME_MAP_JP_TO_EN.items()}

def _sanitize_name_for_internal_use(name: str) -> str:
    """Sanitize a name to create a consistent internal English identifier."""
    # This is a very basic sanitization. For more robust solutions, consider transliteration libraries.
    # For now, replace non-alphanumeric (and non-underscore) with underscore, and ensure it's ASCII-safe.
    # Also, remove common Japanese suffixes like 'New' if they are just descriptive.
    name = name.replace('New', '') # Remove specific suffixes if they are just descriptors
    sanitized = ''.join(c if c.isalnum() else '_' for c in name).strip('_')
    if not sanitized:
        sanitized = "UnknownChar"
    return sanitized

def get_char_internal_name(japanese_name: str) -> str:
    """
    Gets the internal English identifier for a Japanese character name.
    If the mapping doesn't exist, it creates a new one dynamically.
    """
    if japanese_name in _CHAR_NAME_MAP_JP_TO_EN:
        return _CHAR_NAME_MAP_JP_TO_EN[japanese_name]
    
    # Generate a new internal name if not found
    internal_name = _sanitize_name_for_internal_use(japanese_name)
    
    # Ensure uniqueness (e.g., if two Japanese names sanitize to the same string)
    original_internal_name = internal_name
    counter = 1
    while internal_name in _CHAR_NAME_MAP_EN_TO_JP:
        internal_name = f"{original_internal_name}{counter}"
        counter += 1
            
    _CHAR_NAME_MAP_JP_TO_EN[japanese_name] = internal_name
    _CHAR_NAME_MAP_EN_TO_JP[internal_name] = japanese_name
    return internal_name

def get_char_japanese_name(internal_name: str) -> str:
    """
    Gets the Japanese name from an internal English identifier.
    Returns the internal_name if no mapping is found (fallback).
    """
    return _CHAR_NAME_MAP_EN_TO_JP.get(internal_name, internal_name)

THEME_COLORS = {
    "dark": {
        "background": "#2e2e2e",
        "input_bg": "#202020",
        "border": "#5a5a5a",
        "button_bg": "#5a5a5a",
        "button_text": "#ffffff",
        "button_hover": "#6a6a6a",
        "tab_bg": "#3e3e3e",
        "tab_text": "#ffffff",
        "tab_selected": "#4a90e2",
        "group_border": "#5a5a5a"
    },
    "light": {
        "background": "#f0f0f0",
        "input_bg": "#ffffff",
        "border": "#c0c0c0",
        "button_bg": "#e0e0e0",
        "button_text": "#000000",
        "button_hover": "#d0d0d0",
        "tab_bg": "#e0e0e0",
        "tab_text": "#000000",
        "tab_selected": "#a0c0e0",
        "group_border": "#c0c0c0"
    },
    "clear": {
        "background": "#eefeff",
        "input_bg": "#ffffff",
        "border": "#b0d0e0",
        "button_bg": "#d0efff",
        "button_text": "#000000",
        "button_hover": "#b0e0ff",
        "tab_bg": "#d0efff",
        "tab_text": "#000000",
        "tab_selected": "#80d0ff",
        "group_border": "#b0d0e0"
    }
}

LOG_FILENAME = 'wuwacalc.log'
CONFIG_FILENAME = 'config.json'
