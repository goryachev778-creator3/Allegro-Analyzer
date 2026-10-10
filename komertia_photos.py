"""Original Komertia LP photo import. Never match display row numbers."""
import csv
import json
import re
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from komertia_details import PHOTO, uploaded_photo, value


def read_photo_zip(data):
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('Максимальный размер ZIP — 32 МБ.')
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 100 or sum(e.file_size for e in entries) > 64 * 1024 * 1024:
                raise ValueError('ZIP превышает допустимый размер распаковки.')
            if len({e.filename for e in entries}) != len(entries):
                raise ValueError('В ZIP повторяются имена файлов.')
            photos = {}
            for item in entries:
                match = re.fullmatch(r'Komertia_LP_(\d+)\.(png|jpg|jpeg|webp)', item.filename, re.I)
                if not match:
                    continue
                lp = int(match[1])
                if lp <= 0 or lp in photos or item.file_size > 5 * 1024 * 1024:
                    raise ValueError('Некорректный LP или повторная фотография одного LP.')
                photos[lp] = uploaded_photo(archive.read(item))
            if not photos:
                raise ValueError('В ZIP нет фотографий Komertia_LP_01.png и аналогичных.')
            if 'mapowanie_LP.csv' in archive.namelist():
                for row in csv.DictReader(StringIO(archive.read('mapowanie_LP.csv').decode('utf-8-sig'))):
                    lp = int(row['LP Komertia'])
                    filename = row['Zdjęcie']
                    match = re.fullmatch(r'Komertia_LP_(\d+)\.(png|jpg|jpeg|webp)', filename, re.I)
                    if not match or int(match[1]) != lp or filename not in archive.namelist() or lp not in photos:
                        raise ValueError('CSV сопоставления противоречит номерам LP фотографий.')
            return photos
    except (zipfile.BadZipFile, KeyError, UnicodeError) as exc:
        raise ValueError('Не удалось прочитать ZIP или таблицу LP.') from exc


def source_lp(row):
    from komertia_details import _source_key, NAME_PL
    assets = Path(__file__).parent / 'assets'
    catalog = json.loads((assets / 'komertia-screenshots.json').read_text())['rows']
    titles = json.loads((assets / 'polish-names.json').read_text())
    position = value(row.get('_position_id')).strip()
    identities = [r for r in catalog if position in
                  (r['position_id'], f"komertia-screenshot-oct2026:{r['source_row']}")]
    explicit = value(row.get('source_row')).strip()
    lp = None
    if explicit:
        try:
            numeric = float(explicit)
            if numeric <= 0 or numeric != int(numeric):
                raise ValueError()
            lp = int(numeric)
        except ValueError:
            raise ValueError('Некорректный исходный LP Komertia.') from None
    if identities:
        original_lp = identities[0]['source_row']
        if lp is not None and lp != original_lp:
            raise ValueError('Исходный LP противоречит постоянному ID первоначального импорта.')
        return original_lp
    if lp is not None:
        return lp
    # Ordinary LP/№ columns can contain renumbered display rows. Ignore them.
    sources = {_source_key(row.get(c)) for c in ('Produkt', 'Товар')} - {''}
    if position.startswith('legacy:'):
        try:
            key = json.loads(position[len('legacy:'):].rsplit(':', 1)[0])
            if key and key[0] == 'name':
                sources.add(_source_key(key[1]))
        except (ValueError, TypeError, IndexError):
            pass
    candidates = [r for r in catalog if _source_key(r['Produkt']) in sources]
    if not candidates and value(row.get(NAME_PL)).strip():
        title = _source_key(row[NAME_PL])
        candidates = [r for r in catalog if _source_key(titles.get(r['position_id'])) == title]
    variant = _source_key(row.get('Wariant'))
    if variant and candidates:
        candidates = [r for r in candidates if _source_key(r['Wariant']) == variant]
    if len(candidates) > 1:
        quantity = next((value(row.get(c)).strip() for c in ('Ilość', 'ilosc', 'Количество', 'quantity') if value(row.get(c)).strip()), '')
        if quantity:
            from analyzer import number
            candidates = [r for r in candidates if number(r['Ilość']) == number(quantity)]
    if len(candidates) != 1:
        raise ValueError('Не удалось однозначно восстановить исходный LP по первоначальным Produkt, Wariant и количеству. Номер строки не используется.')
    return candidates[0]['source_row']


def recover_source_lps(records, strict=False):
    updated = []
    for row in records:
        result = dict(row)
        try:
            result['source_row'] = source_lp(row)
        except ValueError:
            if strict:
                raise
        updated.append(result)
    return updated


def apply_lp_photos(records, photos):
    result = []
    matched = []
    for row in records:
        lp = source_lp(row)
        if lp not in photos:
            raise ValueError(f'В ZIP нет фотографии LP {lp}. Ничего не сохранено.')
        updated = dict(row)
        updated[PHOTO] = photos[lp]
        result.append(updated)
        matched.append(lp)
    return result, matched


def save_zip_photos(data):
    from storage import state_connection, is_external, read_from, write_to
    photos = read_photo_zip(data)
    db = state_connection()
    try:
        with db:
            if is_external():
                db.execute('SELECT key FROM allegro_state WHERE key = %s FOR UPDATE', ('analysis',))
            records = read_from(db, 'analysis')
            if not records:
                raise ValueError('В базе нет текущих товаров. Импорт фотографий не создаёт и не заменяет товары.')
            records = recover_source_lps(records, strict=True)
            updated, matched = apply_lp_photos(records, photos)
            write_to(db, 'analysis', updated)
        return updated, matched
    finally:
        db.close()


def save_manual_zip_photos(data, selections, expected_ids):
    """Change photos only, matching explicit selections by saved position ID."""
    import pandas as pd
    from storage import state_connection, is_external, read_from, write_to, ensure_ids
    photos = read_photo_zip(data)
    if not selections:
        raise ValueError('Выберите хотя бы одну фотографию.')
    db = state_connection()
    try:
        with db:
            if is_external():
                db.execute('SELECT key FROM allegro_state WHERE key = %s FOR UPDATE', ('analysis',))
            records = read_from(db, 'analysis')
            if not records:
                raise ValueError('В базе нет текущих товаров.')
            ids = ensure_ids(pd.DataFrame(records))['_position_id'].tolist()
            if len(set(ids)) != len(ids) or set(ids) != set(expected_ids) or len(ids) != len(expected_ids):
                raise ValueError('Состав товаров изменился. Обновите страницу и повторите сопоставление.')
            if not set(selections).issubset(ids):
                raise ValueError('Выбранный товар больше не существует.')
            if any(not isinstance(lp, int) or isinstance(lp, bool) or lp not in photos for lp in selections.values()):
                raise ValueError('Выбранной фотографии нет в ZIP.')
            updated = []
            for position, row in zip(ids, records):
                record = dict(row)
                if position in selections:
                    record[PHOTO] = photos[selections[position]]
                updated.append(record)
            write_to(db, 'analysis', updated)
        return updated
    finally:
        db.close()
