"""Safe, read-only Neon health diagnostics; never print database URLs or passwords."""
from __future__ import annotations


def classify_connection_failure(exc):
    """Map psycopg connection errors to safe, actionable messages."""
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    if "authentication failed" in text or "password authentication failed" in text:
        return "AUTH_FAILED: Check Neon database credentials in Streamlit Secrets."
    if "does not exist" in text and ("database" in text or "role" in text):
        return "DATABASE_OR_ROLE_MISSING: Verify database and role in Neon connection details."
    if "could not translate host name" in text or "name or service not known" in text:
        return "DNS_FAILED: Check database hostname or DNS connectivity."
    if "connection refused" in text or "timeout" in text or "timed out" in text:
        return "NETWORK_UNAVAILABLE: Database endpoint may be sleeping, blocked or unreachable."
    if "ssl" in text or "tls" in text:
        return "TLS_FAILURE: Use a Neon URL with sslmode=require."
    if "invalid" in text and ("dsn" in text or "conninfo" in text or "uri" in text):
        return "INVALID_CONNECTION_STRING: Verify ALLEGRO_DATABASE_URL syntax."
    if "operationalerror" in name:
        return "CONNECTION_ERROR: Verify database status and Streamlit Secrets."
    return "DATABASE_ERROR: Inspect private server logs; never publish credentials."


def check_neon_health():
    """Read-only check; caller may display returned status but not the exception."""
    from storage import external_url
    if not external_url():
        return {"status": "MISSING_SECRET", "details": "ALLEGRO_DATABASE_URL is absent."}
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        settings = conninfo_to_dict(external_url())
        if settings.get("sslmode") in ("disable", "allow", "prefer"):
            return {"status": "TLS_CONFIGURATION", "details": "Require TLS: sslmode=require."}
        settings.setdefault("sslmode", "require")
        with psycopg.connect(**settings, connect_timeout=8) as conn:
            exists = conn.execute("SELECT to_regclass('public.allegro_state')").fetchone()[0]
            if not exists:
                return {"status": "TABLE_MISSING", "details": "public.allegro_state not found; do not recreate data blindly."}
            row = conn.execute("SELECT jsonb_array_length(value::jsonb) FROM public.allegro_state WHERE key = %s", ("analysis",)).fetchone()
            return {"status": "OK", "positions": row[0] if row else 0}
    except Exception as exc:
        return {"status": "ERROR", "details": classify_connection_failure(exc)}
