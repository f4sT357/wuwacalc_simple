import importlib
import traceback
import sys
import os

# Ensure project root is on sys.path so local modules can be imported when
# running this script from the tools/ directory.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

modules = [
    'constants', 'config_manager', 'utils', 'create_wrappers',
    'languages', 'test_filter', 'reproduce_score', 'echo_data',
    'dialogs', 'build', 'reproduce_rubberband'
]

print('Running module import checks...')
for m in modules:
    try:
        mod = importlib.import_module(m)
        print(f'OK import: {m}')
        # module-specific lightweight checks
        if m == 'config_manager':
            try:
                cm = mod.ConfigManager(os.path.join(os.getcwd(), 'config.json'))
                loaded = cm.load()
                print(f'  ConfigManager.load() returned: {loaded}')
                print(f'  Language: {cm.get_app_config().language}')
            except Exception:
                print('  ConfigManager self-check failed:')
                traceback.print_exc()
        if m == 'utils':
            try:
                if hasattr(mod, 'setup_tesseract'):
                    mod.setup_tesseract()
                    print('  setup_tesseract() invoked')
            except Exception:
                print('  setup_tesseract failed:')
                traceback.print_exc()
        if m == 'languages':
            try:
                ok = 'ja' in getattr(mod, 'TRANSLATIONS', {})
                print(f'  TRANSLATIONS has ja: {ok}')
            except Exception:
                print('  languages check failed:')
                traceback.print_exc()
        if m == 'constants':
            try:
                print('  TAB_CONFIGS keys:', list(mod.TAB_CONFIGS.keys()))
            except Exception:
                print('  constants check failed:')
                traceback.print_exc()
    except Exception as e:
        print(f'ERROR importing {m}: {e}')
        traceback.print_exc()

print('Module checks complete.')
