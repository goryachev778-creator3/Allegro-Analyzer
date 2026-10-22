"""Read-only diagnostics of Allegro Analyzer's Neon connection.

No passwords, URLs, database hostnames, or original exception messages are shown.
This module does not create or modify database tables, even on first use.
"""
from __future__ import annotations


def _safe_error(exc):
    """Categorise connection failures without exposing hosts, users or secrets."""
    code = getattr(exc, "sqlstate", None)
    if code == "28P01":
        return "AUTH_FAILED", "Neon отклонил пароль пользователя."
    if code == "3D000":
        return "DATABASE_MISSING", "Указанная база Neon не найдена."
    if code == "28000":
        return "ROLE_INVALID", "Neon отклонил пользователя или роль."
    if code == "42501":
        return "PERMISSION_DENIED", "Недостаточно прав для чтения таблицы."
    from psycopg import OperationalError
    if isinstance(exc, OperationalError):
        # Match phrases privately; never show the exception itself.
        message = str(exc).lower()
        if "password authentication failed" in message or "authentication failed" in message:
            return "AUTH_FAILED", "Неверный пароль Neon или пользователь базы."
        if "could not translate host name" in message or "name or service not known" in message or "nodename nor servname provided" in message or "temporary failure in name resolution" in message:
            return "DNS_FAILED", "Streamlit не может разрешить имя сервера Neon. Проверьте hostname в Secrets."
        if "timeout" in message or "timed out" in message:
            return "TIMEOUT", "Соединение с Neon превышает время ожидания."
        if "connection refused" in message or "server closed the connection" in message:
            return "CONNECTION_REFUSED", "Neon не принимает соединение по указанному адресу/порту."
        if "certificate verify failed" in message or "ssl" in message or "tls" in message:
            return "TLS_FAILED", "Ошибка защищённого SSL/TLS соединения с Neon."
        if "database" in message and "does not exist" in message:
            return "DATABASE_MISSING", "Указанная база Neon не существует."
        return "CONNECTION_FAILED", "Ошибка соединения с Neon. Проверьте статус проекта и строку подключения."
    return "CHECK_FAILED", "Не удалось выполнить проверку. Пароли и адреса скрыты."


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
