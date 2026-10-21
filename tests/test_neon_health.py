from neon_health import classify_connection_failure


class FakeOperationalError(Exception):
    pass


def test_does_not_echo_passwords():
    secret = "postgresql://name:very_secret_password@db.example/db"
    result = classify_connection_failure(FakeOperationalError("connection refused " + secret))
    assert secret not in result and "very_secret_password" not in result


def test_categories():
    assert classify_connection_failure(FakeOperationalError("password authentication failed for user abc")).startswith("AUTH_FAILED")
    assert classify_connection_failure(FakeOperationalError("could not translate host name")).startswith("DNS_FAILED")
    assert classify_connection_failure(FakeOperationalError("connection timed out")).startswith("NETWORK_UNAVAILABLE")
