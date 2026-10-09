"""Startup regression checks for mixed Streamlit module versions."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_photo_module_import_does_not_register_component():
    script = '''
import streamlit.components.v1 as components
from unittest.mock import patch
with patch.object(components, 'declare_component', side_effect=AssertionError('eager registration')):
    import photo_grid
    assert callable(photo_grid.photo_grid)
    assert callable(photo_grid.apply_photo_event)
'''
    subprocess.run([sys.executable, '-c', script], cwd=ROOT, check=True, capture_output=True, text=True)


def test_startup_with_old_product_details_in_module_cache():
    script = '''
import sys, types
sys.modules['product_details'] = types.ModuleType('product_details')
from streamlit.testing.v1 import AppTest
app = AppTest.from_file('app.py').run()
assert not app.exception, list(app.exception)
assert app.title[0].value == 'Allegro Analyzer'
'''
    subprocess.run([sys.executable, '-c', script], cwd=ROOT, check=True, capture_output=True, text=True)


def test_compatibility_exports_share_canonical_metadata():
    import komertia_details
    import product_details
    assert product_details.NAME_PL == komertia_details.NAME_PL
    assert product_details.uploaded_photo is komertia_details.uploaded_photo
    assert product_details.enrich_details is komertia_details.enrich_details
