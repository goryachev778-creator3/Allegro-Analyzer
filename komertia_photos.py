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
    catalog = json.loads((Path(__file__).parent / 'assets' / 'komertia-screenshots.json').read_text())['rows']
    candidates = set()
    for field in ('source_row', 'LP Komertia', 'LP', 'Lp', 'lp'):
        content = value(row.get(field)).strip()
        if content:
            try:
                numeric = float(content)
                if numeric <= 0 or numeric != int(numeric):
                    raise ValueError()
                candidates.add(int(numeric))
            except ValueError:
                raise ValueError('Некорректный исходный LP Komertia.') from None
    position = value(row.get('_position_id'))
    for original in catalog:
        if position == original['position_id'] or position == f"komertia-screenshot-oct2026:{original['source_row']}":
            candidates.add(original['source_row'])
    if len(candidates) != 1:
        raise ValueError('Исходный LP отсутствует или противоречив. Номер строки таблицы не используется вместо LP.')
    return candidates.pop()


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
            updated, matched = apply_lp_photos(records, photos)
            write_to(db, 'analysis', updated)
        return updated, matched
    finally:
        db.close()
