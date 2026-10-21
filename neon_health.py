"""Read-only diagnostics of Allegro Analyzer's Neon connection.

No passwords, URLs, database hostnames, or original exception messages are shown.
This module does not create or modify database tables, even on first use.
"""
from __future__ import annotations


def _safe_error(exc):
    code = getattr(exc, "sqlstate", None)
    if code == "28P01":
        return "AUTH_FAILED", "Ошибка авторизации Neon. Проверьте пароль в Streamlit Secrets."
    if code == "3D000":
        return "DATABASE_MISSING", "Указанная база Neon не найдена."
    if code == "28000":
        return "ROLE_INVALID", "Указанная роль Neon не имеет доступа."
    if code == "42501":
        return "PERMISSION_DENIED", "Недостаточно прав для чтения таблицы."
    from psycopg import OperationalError
    if isinstance(exc, OperationalError):
        return "CONNECTION_FAILED", "Не удалось подключиться к Neon: проверьте статус базы, адрес и параметры подключения."
    return "CHECK_FAILED", "Не удалось проверить базу. Подробности смотрите в закрытых журналах Streamlit."


def check_neon_health():
    """Return public-safe status. Never echoes any secret or raw exception."""
    from storage import external_url
    url = external_url()
    if not url:
        return {"status": "MISSING_SECRET", "message": "Не найден ALLEGRO_DATABASE_URL в Streamlit Secrets."}
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        settings = conninfo_to_dict(url)
        if settings.get("sslmode") in ("disable", "allow", "prefer"):
            return {"status": "TLS_REQUIRED", "message": "Для Neon необходимо sslmode=require."}
        settings.setdefault("sslmode", "require")
        settings["connect_timeout"] = 8
        # Read-only session, no automatic CREATE TABLE from storage.state_connection().
        with psycopg.connect(**settings, options="-c default_transaction_read_only=on") as db:
            found = db.execute("SELECT to_regclass('public.allegro_state')").fetchone()[0]
            if found is None:
                return {"status": "TABLE_MISSING", "message": "Таблица allegro_state отсутствует. Не создавайте новую базу поверх старой."}
            row = db.execute(
                "SELECT jsonb_array_length(value::jsonb) FROM public.allegro_state WHERE key = %s",
                ("analysis",),
            ).fetchone()
            if row is None:
                return {"status": "ANALYSIS_MISSING", "message": "Подключение работает, но запись analysis не найдена."}
            return {"status": "OK", "message": "Подключение к Neon работает.", "positions": int(row[0])}
    except Exception as exc:
        try:
            status, message = _safe_error(exc)
        except Exception:
            status, message = "CHECK_FAILED", "Проверка Neon завершилась ошибкой."
        return {"status": status, "message": message}
