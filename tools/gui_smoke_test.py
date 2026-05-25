import sys
import os
import logging
from PyQt6.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from wuwacalc17 import ScoreCalculatorApp

logging.basicConfig(level=logging.INFO)

def run():
    QApplication(sys.argv)
    window = ScoreCalculatorApp()
    # Do not show window; exercise non-interactive flows
    try:
        window._load_character_profiles()
        window._filter_characters_by_config()
        logging.info("Character map: %s", getattr(window, '_character_config_map', {}))

        # Test calculation logic
        sc = window.score_calculator
        tabs = {
            'tab1': {'substats': {'a': 1, 'b': 2}, 'weights': {'x': 1, 'y': 2}, 'methods': None},
            'tab2': {'substats': {'a': 3, 'b': 4}, 'weights': {'x': 0.5, 'y': 0.5}, 'methods': None}
        }
        res = sc.calculate_batch_scores(tabs)
        logging.info('Batch calc result: %s', res)

        # Theme application
        try:
            window.apply_theme(window.config_manager.get_app_config().theme)
            logging.info('Applied theme')
        except Exception as e:
            logging.exception('apply_theme failed: %s', e)

        print('SMOKE_TEST_OK')
    except Exception as e:
        logging.exception('GUI smoke test failed: %s', e)

if __name__ == '__main__':
    run()
