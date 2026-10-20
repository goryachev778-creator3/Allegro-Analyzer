import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLEGRO_DB_PATH', str(tmp_path / 'analysis.sqlite3'))
    # Tests must never inherit a real database binding or deployment Secrets.
    monkeypatch.setenv('ALLEGRO_DATABASE_URL', '')
    import streamlit
    monkeypatch.setattr(streamlit, 'secrets', {})
