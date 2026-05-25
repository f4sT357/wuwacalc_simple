import os, sys

# Ensure the module can be imported
sys.path.append(os.path.dirname(__file__))
from wuwacalc17 import ScoreCalculatorApp

def run_manual_test():
	"""Manual test runner for interactive use only.

	This function intentionally does not run on import to keep the module
	import-safe. Run this script directly to perform the GUI-backed checks.
	"""
	from PyQt6.QtWidgets import QApplication
	_qt_app = QApplication(sys.argv)
	assert _qt_app is not None
	app = ScoreCalculatorApp()
	# Load profiles and apply filtering
	app._load_character_profiles()
	print('Character config map:', app._character_config_map)
	# Test filtering for 43311
	app.current_config_key = '43311'
	app._filter_characters_by_config()
	try:
		items = [app.charcombo.itemText(i) for i in range(app.charcombo.count())]
	except Exception:
		items = []
	print('Filtered values for 43311:', items)
	# Test filtering for 44111
	app.current_config_key = '44111'
	app._filter_characters_by_config()
	try:
		items = [app.charcombo.itemText(i) for i in range(app.charcombo.count())]
	except Exception:
		items = []
	print('Filtered values for 44111:', items)


if __name__ == '__main__':
	run_manual_test()
