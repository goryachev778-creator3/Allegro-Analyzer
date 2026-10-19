"""Conservative duplicate review; existing rows are removed only on confirmation."""
import hashlib
import json
import re
import pandas as pd
from analyzer import INPUTS, NUMERIC
from komertia_details import PHOTO, FULL_NAME, NAME_PL, is_order_total
from storage import ensure_ids, text


def normalized(value):
    return re.sub(r'\s+', ' ', text(value)).strip().casefold()


def records(frame):
    return frame.astype(object).where(pd.notna(frame), None).to_dict('records')


def fingerprint(frame):
    return hashlib.sha256(json.dumps(records(frame), ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def identity(row):
    product = normalized(row.get('Produkt', row.get('PRODUKT', '')))
    variant = normalized(row.get('Wariant', row.get('WARIANT', '')))
    if not product or is_order_total(row):
        return None
    # Cropped source labels cannot prove that different source positions are identical.
    source = ''
    if any(mark in product + variant for mark in ('…', '...')):
        source = normalized(row.get('source_row'))
        if not source:
            source = normalized(row.get('_position_id'))
            if source.startswith('legacy:'):
                return None
    ignored = set(INPUTS) | {PHOTO, FULL_NAME, NAME_PL, 'Produkt', 'Wariant', 'PRODUKT', 'WARIANT',
        '_position_id', 'source_row', '№', 'LP', 'lp', 'Прибыль PLN', 'Маржа %', 'Статус', 'ROI %'}
    # Unknown descriptive fields are significant: differing specifications never collapse.
    details = tuple(sorted((str(c), normalized(v)) for c, v in row.items()
                           if c not in ignored and not str(c).startswith('_') and text(v)))
    return product, variant, source, normalized(row.get('SKU')), details


def filled(value, column):
    return bool(text(value)) and not (column in NUMERIC and float(value or 0) == 0)


def combine(rows):
    result = rows[0].copy()
    conflicts = []
    for row in rows[1:]:
        for column in set(result) | set(row):
            if column in {'_position_id', 'source_row', '№'}:
                continue
            old, new = result.get(column), row.get(column)
            if not filled(new, column):
                continue
            if not filled(old, column):
                result[column] = new
            elif normalized(old) != normalized(new):
                conflicts.append(column)
    return result, sorted(set(conflicts))


def review(frame):
    frame = ensure_ids(frame.reset_index(drop=True))
    grouped = {}
    for index, row in enumerate(records(frame)):
        key = identity(row)
        if key is not None:
            grouped.setdefault((key[0], key[1], key[3], key[4]), []).append(index)
    groups = []
    for indexes in grouped.values():
        if len(indexes) > 1:
            merged, conflicts = combine([records(frame.iloc[indexes])[i] for i in range(len(indexes))])
            sources = {identity(records(frame)[i])[2] for i in indexes}
            if len(sources) > 1:
                conflicts.append('Сокращённые исходные названия разных LP: требуется проверка оригиналов')
            groups.append({'indexes': indexes, 'merged': merged, 'conflicts': conflicts})
    return groups


def without_confirmed_duplicates(frame):
    frame = ensure_ids(frame.reset_index(drop=True))
    rows = records(frame)
    removed = set()
    for group in review(frame):
        if not group['conflicts']:
            rows[group['indexes'][0]] = group['merged']
            removed.update(group['indexes'][1:])
    return pd.DataFrame([row for i, row in enumerate(rows) if i not in removed], columns=frame.columns), len(removed)


def checked_import(imported, saved):
    """Append new items; never replace any field of an existing item."""
    incoming = ensure_ids(imported.reset_index(drop=True))
    saved = ensure_ids(saved.reset_index(drop=True)) if saved is not None else pd.DataFrame(columns=incoming.columns)
    rows = records(saved)
    keys = {identity(row) for row in rows if identity(row) is not None}
    ids = {text(row.get('_position_id')): row for row in rows}
    skipped = 0
    for row in records(incoming):
        key = identity(row)
        old = ids.get(text(row.get('_position_id')))
        if old is not None and (normalized(old.get('Produkt')) != normalized(row.get('Produkt')) or normalized(old.get('Wariant')) != normalized(row.get('Wariant'))):
            raise ValueError('Одинаковый идентификатор у разных вариантов. Проверьте исходные данные импорта.')
        if old is not None or (key is not None and key in keys):
            skipped += 1
            continue
        rows.append(row)
        ids[text(row.get('_position_id'))] = row
        if key is not None:
            keys.add(key)
    return pd.DataFrame(rows, columns=list(dict.fromkeys([*saved.columns, *incoming.columns]))).fillna(''), skipped


def confirm_duplicates(expected):
    """Lock and compare the actual stored review, then atomically save analysis/prices."""
    import storage
    db = storage.state_connection()
    try:
        with db:
            if storage.is_external():
                db.execute('SELECT key FROM allegro_state WHERE key = %s FOR UPDATE', ('analysis',))
            else:
                db.execute('BEGIN IMMEDIATE')
            current = ensure_ids(pd.DataFrame(storage.read_from(db, 'analysis') or []))
            if fingerprint(current) != expected:
                raise ValueError('Данные изменились. Обновите список дубликатов и подтвердите заново.')
            result, count = without_confirmed_duplicates(current)
            prices = storage.read_from(db, 'prices') or {}
            for row in records(result):
                prices[row['_position_id']] = {c: row.get(c, 0) for c in storage.SALES}
            storage.write_to(db, 'prices', prices)
            storage.write_to(db, 'analysis', records(result))
        result.attrs['analysis_hash'] = storage.analysis_hash(records(result))
        return result, count
    finally:
        db.close()


def render_review(frame):
    import streamlit as st
    groups = review(frame)
    detected = sum(len(g['indexes']) - 1 for g in groups)
    removable = sum(len(g['indexes']) - 1 for g in groups if not g['conflicts'])
    st.caption(f'Обнаружено повторов: {detected}. Можно объединить без потери заполненных данных: {removable}.')
    if not groups:
        st.info('Подтверждённых полных дубликатов не найдено. Сокращённые названия разных LP не объединяются.')
        return None
    preview = []
    for group in groups:
        for index in group['indexes']:
            row = frame.iloc[index]
            preview.append({'Строка': index + 1, 'Produkt': row.get('Produkt', ''), 'Wariant': row.get('Wariant', ''),
                'LP': row.get('source_row', ''), **{c: row.get(c, '') for c in NUMERIC}, PHOTO: row.get(PHOTO, ''),
                'Результат': 'Конфликт: ' + ', '.join(group['conflicts']) if group['conflicts'] else
                'Оставить и дополнить' if index == group['indexes'][0] else 'Удалить после подтверждения'})
    st.dataframe(pd.DataFrame(preview), hide_index=True, column_config={PHOTO: st.column_config.ImageColumn('Фото')})
    token = fingerprint(ensure_ids(frame.reset_index(drop=True)))
    approved = st.checkbox(f'Подтверждаю объединение и удаление {removable} повторных строк из показанного списка', key='duplicate_confirm_' + token)
    if st.button('Подтвердить удаление дубликатов и сохранить', disabled=not approved or not removable):
        return confirm_duplicates(token)
    return None
