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
    records = frame[INPUTS].astype(object).where(pd.notna(frame[INPUTS]), None).to_dict('records')
    if read('analysis') != records:
        write('analysis', records)


def load_analysis():
    records = read('analysis')
    return None if records is None else pd.DataFrame(records, columns=INPUTS)


def product_key(row):
    def text(value):
        return '' if value is None or pd.isna(value) else str(value).strip()
    sku = text(row['SKU'])
    name = text(row['Товар'])
    return ('sku', sku) if sku else ('name', name.casefold()) if name else None


def merge_import(imported, saved):
    """Keep every edited field for matching items; append genuinely new items.

    Rows absent from a refreshed export are removed (including zero-stock rows).
    Ambiguous duplicate identifiers are rejected rather than silently mixed.
    """
    for frame in (imported, saved):
        if frame is None:
            continue
        keys = [product_key(row) for _, row in frame.iterrows()]
        nonempty = [key for key in keys if key is not None]
        if len(nonempty) != len(set(nonempty)):
            raise ValueError('Повторяющиеся SKU или названия без SKU: исправьте дубликаты перед объединением.')
    if saved is None or saved.empty:
        return imported.copy().reset_index(drop=True)
    existing = {product_key(row): row for _, row in saved.iterrows() if product_key(row) is not None}
    return pd.DataFrame([existing.get(product_key(row), row).to_dict() for _, row in imported.iterrows()], columns=INPUTS).reset_index(drop=True)


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
