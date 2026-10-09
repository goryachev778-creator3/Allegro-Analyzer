"""Persistent single-workspace analysis and import preferences."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import pandas as pd
from analyzer import INPUTS
from komertia_details import DETAILS, enrich_details


def database_path():
    return Path(os.environ.get('ALLEGRO_DB_PATH', Path(__file__).parent / 'data' / 'analysis.sqlite3'))


def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    return db


def external_url():
    value = os.environ.get('ALLEGRO_DATABASE_URL')
    if not value:
        try:
            import streamlit as st
            value = st.secrets.get('ALLEGRO_DATABASE_URL')
        except (FileNotFoundError, KeyError):
            pass
    return value


def is_external():
    return bool(external_url())


def state_connection():
    if not external_url():
        return connect()
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        settings = conninfo_to_dict(external_url())
        if settings.get('sslmode') in ('disable', 'allow', 'prefer'):
            raise ValueError('TLS required')
        settings.setdefault('sslmode', 'require')
        db = psycopg.connect(**settings, connect_timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS allegro_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        return db
    except Exception:
        raise RuntimeError('Внешняя база недоступна. Автосохранение не выполнено. Проверьте ALLEGRO_DATABASE_URL в Secrets.') from None


def read_from(db, key):
    table = 'allegro_state' if is_external() else 'state'
    placeholder = '%s' if is_external() else '?'
    row = db.execute(f'SELECT value FROM {table} WHERE key = {placeholder}', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def write_to(db, key, value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
    table = 'allegro_state' if is_external() else 'state'
    placeholders = '%s, %s' if is_external() else '?, ?'
    db.execute(f'INSERT INTO {table} VALUES ({placeholders}) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, payload))


def read(key):
    db = state_connection()
    try:
        with db:
            return read_from(db, key)
    finally:
        db.close()


def write(key, value):
    db = state_connection()
    try:
        with db:
            write_to(db, key, value)
    finally:
        db.close()


SALES = ['Цена Allegro PLN', 'Комиссия %', 'Комиссия PLN']


def save_analysis(frame):
    frame = ensure_ids(frame.reset_index(drop=True))
    records = frame.astype(object).where(pd.notna(frame), None).to_dict('records')
    db = state_connection()
    try:
        with db:
            prices = {canonical_id(k): v for k, v in (read_from(db, 'prices') or {}).items()}
            for row in records:
                prices[row['_position_id']] = {c: row[c] for c in SALES}
            write_to(db, 'prices', prices)
            write_to(db, 'analysis', records)
    finally:
        db.close()


def load_analysis():
    records = read('analysis')
    if records is None and is_external() and database_path().exists():
        local = sqlite3.connect(database_path())
        try:
            entry = local.execute("SELECT value FROM state WHERE key = 'analysis'").fetchone()
        finally:
            local.close()
        if entry:
            records = json.loads(entry[0])
            save_analysis(pd.DataFrame(records) if records else pd.DataFrame(columns=INPUTS))
    return None if records is None else ensure_ids(pd.DataFrame(records)) if records else pd.DataFrame(columns=INPUTS)


def restore_prices(frame):
    result = ensure_ids(frame.reset_index(drop=True))
    prices = {canonical_id(k): v for k, v in (read('prices') or {}).items()}
    for index, row in result.iterrows():
        if row['_position_id'] in prices:
            for col, value in prices[row['_position_id']].items():
                result.loc[index, col] = value
    return result


def backup_excel(frame):
    from io import BytesIO
    stream = BytesIO()
    records = ensure_ids(frame.reset_index(drop=True))
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        from komertia_details import excel_details
        excel_details(records, writer, 'Рабочие данные')
        for row in writer.sheets['Рабочие данные']:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
    return stream.getvalue()


def read_backup(data):
    from io import BytesIO
    from analyzer import calculate
    frame = pd.read_excel(BytesIO(data), sheet_name='Рабочие данные', dtype={'SKU': str, '_position_id': str}).fillna({'SKU': '', 'Товар': '', 'Produkt': '', 'Wariant': ''})
    from komertia_details import PHOTO
    frame = enrich_details(frame)
    workbook = pd.ExcelFile(BytesIO(data))
    if 'Фото данные' in workbook.sheet_names:
        chunks = pd.read_excel(workbook, sheet_name='Фото данные')
        for row, parts in chunks.groupby('row'):
            frame.loc[int(row), PHOTO] = ''.join(parts.sort_values('part')['data'])
    frame = enrich_details(frame)
    if not set(INPUTS + ['_position_id']).issubset(frame.columns):
        raise ValueError('В резервной копии отсутствуют поля или идентификаторы позиций.')
    if frame['_position_id'].isna().any() or frame['_position_id'].duplicated().any():
        raise ValueError('Идентификаторы резервной копии должны быть заполнены и уникальны.')
    if not frame.empty:
        calculate(frame)
    return frame


def product_key(row):
    def text(value):
        return '' if value is None or pd.isna(value) else str(value).strip()
    sku = text(row['SKU'])
    name = text(row['Товар'])
    return ('sku', sku) if sku else ('name', name.casefold()) if name else None


def text(value):
    return '' if value is None or pd.isna(value) else str(value).strip()


def identify_rows(raw, product_column, variant_column=None, source_id_column=None, stock_column=None):
    """Assign IDs before stock filtering; retain exported identities on roundtrip.

    Prefer a source row ID. Otherwise hash descriptive source columns; identical
    source rows are distinguished by occurrence in source order.
    """
    result = raw.copy()
    counts = {}
    from komertia_details import ALIASES
    ignored = {stock_column, '_position_id', *INPUTS[2:]}
    ignored.update(c for c in raw.columns if str(c).strip().casefold() in {a.casefold() for aliases in ALIASES.values() for a in aliases})
    from komertia import normalize
    ignored.update(c for c in raw.columns if normalize(c) in ('wartosc', 'razem', 'trclo', 'transportclo', 'odprawahs', 'hsodprawa', 'kosztydod', 'kosztdod', '1platnosc', '2platnosc', 'waga', 'objetosc'))
    ignored.update(c for c in raw.columns if any(term in str(c).casefold() for term in
                   ('cena', 'price', 'komis', 'commission', 'ilość', 'ilosc', 'quantity')))
    ids = []
    for _, row in raw.iterrows():
        exported = text(row.get('_position_id'))
        product = text(row[product_column])
        variant = text(row[variant_column]) if variant_column else ''
        source = text(row[source_id_column]) if source_id_column else ''
        details = sorted((str(c), text(row[c])) for c in raw.columns if c not in ignored)
        identity = [product, variant, source if source else details]
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        occurrence = counts.get(digest, 0)
        counts[digest] = occurrence + 1
        ids.append(exported or f'{digest}:{occurrence}')
    result['_position_id'] = ids
    result['Produkt'] = raw[product_column].map(text)
    result['Wariant'] = raw[variant_column].map(text) if variant_column else ''
    return result


def canonical_id(value):
    if text(value).startswith('komertia-screenshot-oct2026:'):
        payload = json.loads((Path(__file__).parent / 'assets' / 'komertia-screenshots.json').read_text())
        migration = {f"komertia-screenshot-oct2026:{r['source_row']}": r['position_id'] for r in payload['rows']}
        return migration.get(value, value)
    return value


def ensure_ids(frame):
    if frame is None:
        return None
    result = frame.copy()
    # Legacy analyses: retain SKU/name matching while allowing duplicate rows.
    counts = {}
    for index, row in result.iterrows():
        existing = text(row.get('_position_id'))
        if existing:
            result.loc[index, '_position_id'] = canonical_id(existing)
        key = json.dumps(product_key(row), ensure_ascii=False)
        occurrence = counts.get(key, 0)
        counts[key] = occurrence + 1
        if not existing:
            result.loc[index, '_position_id'] = f'legacy:{key}:{occurrence}'
    return result


def merge_import(imported, saved):
    imported = enrich_details(ensure_ids(imported.reset_index(drop=True)))
    saved = ensure_ids(saved.reset_index(drop=True)) if saved is not None else None
    if saved is None or saved.empty:
        return restore_prices(imported)
    existing = {text(row['_position_id']): row for _, row in saved.iterrows()}
    legacy = {}
    for _, row in saved.iterrows():
        if text(row['_position_id']).startswith('legacy:'):
            legacy.setdefault(product_key(row), []).append(row)
    incoming_counts = {}
    for _, row in imported.iterrows():
        key = product_key(row)
        incoming_counts[key] = incoming_counts.get(key, 0) + 1
    records = []
    for _, row in imported.iterrows():
        old = existing.get(text(row['_position_id']))
        candidates = legacy.get(product_key(row), [])
        if old is None and len(candidates) == 1 and incoming_counts[product_key(row)] == 1:
            old = candidates[0]
        record = row.to_dict()
        if old is not None:
            record.update({column: old[column] for column in INPUTS})
            for column in DETAILS:
                if text(old.get(column)):
                    record[column] = old[column]
        records.append(record)
    return restore_prices(pd.DataFrame(records, columns=imported.columns).reset_index(drop=True))


def profile_key(filename, sheet, columns):
    identity = json.dumps([filename, str(sheet), list(columns)], ensure_ascii=False)
    return 'mapping:' + hashlib.sha256(identity.encode()).hexdigest()


def filter_stock(raw, column):
    if not column:
        return raw.copy(), 0
    from analyzer import number
    quantities = raw[column].map(number)
    keep = quantities != 0
    return raw.loc[keep].reset_index(drop=True), int((~keep).sum())
