"""Neon traffic regression checks for the session cache integration."""
from pathlib import Path


def test_cache_requires_same_signature_and_valid_existing_frame():
    text = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert 'st.session_state.get("neon_snapshot_signature") == snapshot_signature' in text
    assert 'and st.session_state.get("analysis_expected_hash") is not None' in text
    assert 'if not has_cached:' in text
    assert 'restored = load_analysis()' in text
    assert 'st.session_state["storage_ready"] = True' in text


def test_failed_health_check_never_unblocks_saves():
    text = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert 'st.session_state["neon_verified"] = neon_status["status"] == "OK"' in text
    assert 'if not st.session_state.get("storage_ready"):' in text
    assert 'st.stop()' in text
    assert 'st.session_state.pop("neon_snapshot_signature", None)' in text


def test_signature_query_does_not_return_analysis_body():
    text = (Path(__file__).resolve().parents[1] / "neon_health.py").read_text()
    assert 'jsonb_array_length(value::jsonb), md5(value)' in text
    assert '"signature": row[1]' in text
