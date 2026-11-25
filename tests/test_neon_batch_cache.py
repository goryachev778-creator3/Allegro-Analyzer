"""Prevent regression to one full Neon transfer for every price edit."""
from pathlib import Path


def read_app():
    return (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")


def test_shared_cache_bounded_and_signature_keyed():
    app = read_app()
    assert "@st.cache_data(ttl=900, max_entries=2, show_spinner=False)" in app
    assert "def shared_analysis_snapshot(snapshot_signature, connection_identity):" in app
    assert "shared_analysis_snapshot(snapshot_signature, neon_connection_identity())" in app
    assert "if not has_cached:" in app


def test_editor_saves_once_per_explicit_submission():
    app = read_app()
    assert 'with st.form("allegro_editor_batch", clear_on_submit=False):' in app
    assert 'submit_editor_changes = st.form_submit_button("Сохранить изменения", type="primary")' in app
    assert "if submit_editor_changes and not edited.equals(working):" in app
    assert "elif not submit_editor_changes:" in app


def test_outage_remains_fail_closed():
    app = read_app()
    assert 'st.session_state["neon_verified"] = neon_status["status"] == "OK"' in app
    assert "if not st.session_state.get(\"storage_ready\"):" in app
    assert "st.stop()" in app
    assert "require_storage_ready()" in app
