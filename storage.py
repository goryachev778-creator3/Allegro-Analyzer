"""Persistent single-workspace analysis and import preferences."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import pandas as pd
from analyzer import INPUTS


def database_path():
    return Path(os.environ.get('ALLEGRO_DB_PATH', Path(__file__).parent / 'data' / 'analysis.sqlite3'))


def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    return db


def read(key):
    with connect() as db:
        row = db.execute('SELECT value FROM state WHERE key = ?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def write(key, value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
    with connect() as db:
        db.execute('INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, payload))


def save_analysis(frame):
    # Empty cells remain empty; do not discard invalid edits before validation.
    records = frame.astype(object).where(pd.notna(frame), None).to_dict('records')
    if read('analysis') != records:
        write('analysis', records)


def load_analysis():
    records = read('analysis')
    return None if records is None else pd.DataFrame(records) if records else pd.DataFrame(columns=INPUTS)


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
    ignored = {stock_column, '_position_id', *INPUTS[2:]}
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


def ensure_ids(frame):
    if frame is None:
        return None
    result = frame.copy()
    # Legacy analyses: retain SKU/name matching while allowing duplicate rows.
    counts = {}
    for index, row in result.iterrows():
        existing = text(row.get('_position_id'))
        key = json.dumps(product_key(row), ensure_ascii=False)
        occurrence = counts.get(key, 0)
        counts[key] = occurrence + 1
        if not existing:
            result.loc[index, '_position_id'] = f'legacy:{key}:{occurrence}'
    return result


def merge_import(imported, saved):
    imported = ensure_ids(imported.reset_index(drop=True))
    saved = ensure_ids(saved.reset_index(drop=True)) if saved is not None else None
    if saved is None or saved.empty:
        return imported
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
        records.append(record)
    return pd.DataFrame(records, columns=imported.columns).reset_index(drop=True)


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
