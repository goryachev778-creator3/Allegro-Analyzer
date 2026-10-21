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
    text = str(exc).lower()  # Classify privately; never return raw exception text.
    if 'unsupported startup parameter' in text:
        return 'POOLER_STARTUP_PARAMETER', 'Pooled endpoint отклонил стартовый параметр. Удалите options из URL; проверьте pooled URL в Neon Connect.'
    if 'password authentication failed' in text or 'authentication failed' in text:
        return 'AUTH_FAILED', 'Проверьте актуальные реквизиты роли в Streamlit Secrets.'
    if 'could not translate host name' in text or 'name or service not known' in text or 'nodename nor servname' in text:
        return 'DNS_FAILED', 'Адрес Neon не разрешается. Сверьте hostname с Neon Connect.'
    if 'timeout' in text or 'timed out' in text or 'connection refused' in text or 'network is unreachable' in text:
        return 'NETWORK_UNAVAILABLE', 'Проверьте статус compute Neon и доступ Streamlit Cloud к endpoint:5432.'
    if 'ssl' in text or 'tls' in text or 'certificate' in text or 'channel binding' in text:
        return 'TLS_FAILURE', 'Ошибка TLS или channel binding. Используйте параметры из Neon Connect; не отключайте SSL.'
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
        from neon_connection import connect_neon
        # Read-only transaction works with transaction poolers too: no injected
        # startup options, no SET SESSION, no automatic schema creation.
        with connect_neon(url) as db:
            db.execute('SET TRANSACTION READ ONLY')
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
