"""No live Neon required: protect diagnostic error handling."""
from neon_health import check_neon_health


def test_health_missing_secret(monkeypatch):
    import storage
    monkeypatch.setattr(storage, "external_url", lambda: None)
    outcome = check_neon_health()
    assert outcome["status"] == "MISSING_SECRET"
    assert "password" not in str(outcome).lower()


def test_health_does_not_echo_malformed_secret(monkeypatch):
    import storage
    monkeypatch.setattr(storage, "external_url", lambda: "postgresql://bad:TOP_SECRET_PASSWORD@")
    outcome = check_neon_health()
    assert outcome["status"] != "OK"
    assert "TOP_SECRET_PASSWORD" not in str(outcome)


def test_health_is_read_only_in_source():
    import inspect
    import neon_health
    src = inspect.getsource(neon_health.check_neon_health).lower()
    assert "set transaction read only" in src
    assert "create table" not in src.split("with connect_neon", 1)[-1].split("except exception", 1)[0]
