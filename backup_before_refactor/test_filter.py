import json, os, sys

# Ensure the module can be imported
sys.path.append(os.path.dirname(__file__))
from wuwacalc17 import ScoreCalculatorApp

# Note: For proper testing, character config files should either be pre-existing
# or mocked, rather than created directly in the test script.
# Assuming character config files exist for the purpose of this test.

app = ScoreCalculatorApp()
# Load profiles and apply filtering
app._load_character_profiles()
print('Character config map:', app._character_config_map)
# Test filtering for 43311
app.current_config_key = '43311' # Assuming current_config_key is a direct attribute, not a Tkinter variable
app._filter_characters_by_config()
print('Filtered values for 43311:', app.charcombo.model().stringList()) # Accessing PyQt6 QComboBox items
# Test filtering for 44111
app.current_config_key = '44111'
app._filter_characters_by_config()
print('Filtered values for 44111:', app.charcombo.model().stringList())
