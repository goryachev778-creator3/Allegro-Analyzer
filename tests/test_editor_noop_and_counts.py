"""Regression checks for safe table metrics and no-op editor reruns."""
from pathlib import Path


def test_editor_writes_only_when_modified():
    app = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert 'if not edited.equals(working):\n        if replace_analysis(edited):' in app
    assert 'save_analysis(edited)\n        st.session_state["products"]' not in app


def test_count_breakdown_is_read_only():
    app = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert 'all_records = len(working)' in app
    assert 'total_product_count = all_records - order_totals_count' in app
    assert 'inactive_count = total_product_count - int(product_rows.sum())' in app
    assert 'Всего записей в Neon:' in app
