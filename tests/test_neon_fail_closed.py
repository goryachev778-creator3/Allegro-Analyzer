"""Regression tests: a Neon outage may never destroy the analysis."""
import inspect
import pytest
import storage


def test_no_implicit_local_restore_on_neon_load(monkeypatch):
    monkeypatch.setattr(storage, "read", lambda key: None)
    assert storage.load_analysis() is None
    source = inspect.getsource(storage.load_analysis)
    assert "save_analysis(" not in source
    assert "sqlite3.connect" not in source


def test_no_silent_saved_message():
    source = inspect.getsource(storage.save_analysis)
    assert "expected_hash is None" in source
    assert "if not current" in source


def test_main_ui_blocks_write_screens_on_outage():
    from pathlib import Path
    app = Path(__file__).resolve().parents[1].joinpath("app.py").read_text()
    assert "if not st.session_state.get(\"storage_ready\"):" in app
    assert "st.stop()" in app.split('if not st.session_state.get("storage_ready"):', 1)[1].split("import private_link_import", 1)[0]
    assert 'st.session_state["neon_verified"] = neon_status["status"] == "OK"' in app
