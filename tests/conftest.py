import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLEGRO_DB_PATH', str(tmp_path / 'analysis.sqlite3'))
