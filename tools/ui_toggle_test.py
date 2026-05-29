import sys
import os
# Ensure project root is in sys.path so imports work when running from tools/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PyQt6.QtWidgets import QApplication, QComboBox, QWidget, QVBoxLayout
from PyQt6.QtCore import QObject
from ui_components import UIComponents

class DummyApp(QObject):
    def __init__(self):
        super().__init__()
        self.tr = lambda k,*a: k
        self.current_config_key = '43311'
        self.language = 'ja'
        self.mode_var = 'manual'
        self.score_mode_var = 'batch'
        self.auto_apply_main_stats = True
        class AppConfig:
            enabled_calc_methods = {"normalized":True,"ratio":True,"roll":True,"effective":True,"cv":True}
        self.app_config = AppConfig()
        import logging
        self.logger = logging.getLogger('dummy')
        def gui_log(m): print('GUI_LOG:',m)
        self.gui_log = gui_log
        self.charcombo = QComboBox()
        self.crop_top_percent_var = 50
        self.crop_right_percent_var = 30
        self.crop_mode_var = 'percent'
        self.result_text = None
        self.log_text = None
        self.notebook = None
        self.score_calc = None
        self.export_result_to_txt = lambda : None
        self.clear_all = lambda : None
        self.clear_current_tab = lambda : None
        self.opencharsetting = lambda : None
        self._open_readme = lambda : None
        self.open_display_settings = lambda : None
        # Event handler stubs used by UIComponents
    def on_config_change(self, text):
        pass
    def on_character_change(self, text):
        pass
    def on_language_change(self, text):
        pass
    def on_mode_change(self, mode):
        # reflect mode_var similar to real app
        self.mode_var = mode
    def on_auto_main_change(self, checked):
        self.auto_apply_main_stats = checked
    def on_score_mode_change(self, mode):
        self.score_mode_var = mode
    def on_crop_mode_change(self, mode):
        self.crop_mode_var = mode
    def on_crop_percent_change(self, text):
        try:
            self.crop_top_percent_var = float(text)
        except Exception:
            pass
    def on_calc_method_changed(self):
        pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dummy = DummyApp()
    ui = UIComponents(dummy)
    w = QWidget()
    layout = QVBoxLayout(w)
    ui.create_settings_frame(layout, dummy.charcombo)

    # Initial states
    print('Initial states: manual=', ui.rb_manual.isChecked(), 'ocr=', ui.rb_ocr.isChecked(), 'batch=', ui.rb_batch.isChecked(), 'single=', ui.rb_single.isChecked())

    # Toggle actions to simulate user clicks
    ui.rb_manual.setChecked(True)
    ui.rb_batch.setChecked(True)
    ui.rb_ocr.setChecked(True)
    ui.rb_single.setChecked(True)

    print('Final states: manual=', ui.rb_manual.isChecked(), 'ocr=', ui.rb_ocr.isChecked(), 'batch=', ui.rb_batch.isChecked(), 'single=', ui.rb_single.isChecked())
    print('Test finished')
