"""Shared libpq settings; no secrets are returned in errors or logs."""


def connection_settings(url):
    from psycopg.conninfo import conninfo_to_dict
    settings = conninfo_to_dict(url)
    if settings.get('sslmode') in ('disable', 'allow', 'prefer'):
        raise ValueError('NEON_TLS_REQUIRED')
    settings.setdefault('sslmode', 'require')
    # One source of truth: a URL may already specify this keyword.
    settings.setdefault('connect_timeout', '15')
    return settings


def connect_neon(url):
    import psycopg
    return psycopg.connect(**connection_settings(url))
