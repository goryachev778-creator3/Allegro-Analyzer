"""Komertia metadata, without guessing missing source content."""
import base64
import html
import re
from urllib.parse import urlsplit
import pandas as pd

PHOTO = 'Фото Komertia'
FULL_NAME = 'Полное название Komertia'
NAME_PL = 'Nazwa produktu'
DETAILS = [PHOTO, FULL_NAME, NAME_PL]
ALIASES = {
    NAME_PL: [NAME_PL, 'Nazwa PL', 'Короткое польское название'],
    PHOTO: [PHOTO, 'Zdjęcie', 'Zdjecie', 'Zdjęcie URL', 'Photo', 'Image URL', 'Фото'],
    FULL_NAME: [FULL_NAME, 'Pełna nazwa', 'Pelna nazwa', 'Nazwa produktu', 'Full product name'],
}


def value(item):
    return '' if item is None or pd.isna(item) else str(item)


def complete_name(item):
    content = value(item)
    return '' if '…' in content or '...' in content else content


def photo_source(item):
    content = value(item).strip()
    if re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+', content):
        return content
    parsed = urlsplit(content)
    return content if parsed.scheme in ('http', 'https') and parsed.netloc else ''


def _source_key(item):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFKC', value(item)).casefold().replace('...', '…').split())


def polish_name(row):
    from pathlib import Path
    import json
    assets = Path(__file__).parent / 'assets'
    names = json.loads((assets / 'polish-names.json').read_text())
    catalog = json.loads((assets / 'komertia-screenshots.json').read_text())['rows']
    position = value(row.get('_position_id'))
    known = names.get(position)
    if not known and position.startswith('komertia-screenshot-oct2026:'):
        original = next((r for r in catalog if str(r['source_row']) == position.split(':')[-1]), None)
        if original:
            known = names.get(original['position_id'])
    if known:
        return known
    # Historical saved analyses can have hash/legacy IDs instead of catalog UUIDs.
    # Match original text, never row order, costs or prices. Identical source
    # descriptions may share a title; conflicting variant titles are ambiguous.
    sources = {_source_key(row.get(c)) for c in ('Produkt', 'Товар', FULL_NAME)} - {''}
    variant = _source_key(row.get('Wariant'))
    exact = {names[r['position_id']] for r in catalog
             if _source_key(r['Produkt']) in sources
             and _source_key(r['Wariant']) == variant}
    if len(exact) == 1:
        return exact.pop()
    if not variant or variant == '—':
        candidates = {names[r['position_id']] for r in catalog if _source_key(r['Produkt']) in sources}
        if len(candidates) == 1:
            return candidates.pop()
    # Source text is never overwritten. Unknown products need a supplied Polish title.
    source = value(row.get('Produkt')) or value(row.get('Товар'))
    translations = {'Органайзер': 'Organizer', 'Лампа': 'Lampa', 'Чехол': 'Pokrowiec'}
    if source in translations:
        return translations[source]
    if re.search(r'[А-Яа-яЁё]', source) or '…' in source or '...' in source:
        return ''
    variant = complete_name(row.get('Wariant'))
    if re.search(r'[А-Яа-яЁё]', variant) or variant.strip() == '—':
        variant = ''
    return ', '.join(part for part in (source, variant) if part)


def enrich_details(frame):
    if frame is None:
        return None
    result = frame.copy()
    for field in DETAILS:
        if field not in result:
            result[field] = ''
        else:
            result[field] = result[field].map(value)
    for index, row in result.iterrows():
        if not value(row[NAME_PL]).strip():
            result.loc[index, NAME_PL] = polish_name(row)
    return result


def import_details(frame, raw, mapping):
    result = enrich_details(frame)
    for field in DETAILS:
        source = mapping.get(field)
        if source in raw.columns:
            convert = photo_source if field == PHOTO else complete_name
            result[field] = raw[source].map(convert)
    return result


def uploaded_photo(data):
    from PIL import Image
    from io import BytesIO
    if len(data) > 5 * 1024 * 1024:
        raise ValueError('Максимальный размер фото — 5 МБ.')
    try:
        image = Image.open(BytesIO(data))
        image.verify()
        mime = {'PNG': 'png', 'JPEG': 'jpeg', 'WEBP': 'webp'}[image.format]
    except Exception:
        raise ValueError('Загрузите корректное фото PNG, JPEG или WebP.') from None
    return f'data:image/{mime};base64,' + base64.b64encode(data).decode('ascii')


def full_table(frame, fields):
    """An HTML table wraps every source character; canvas grids clip long text."""
    parts = ['<div class="komertia-table"><table><thead><tr>']
    parts += [f'<th>{html.escape(c)}</th>' for c in fields]
    parts.append('</tr></thead><tbody>')
    for _, row in frame.iterrows():
        from analyzer import COLORS
        color = COLORS.get(row.get('Статус'))
        parts.append(f'<tr style="background-color:#{color};color:#172554">' if color else '<tr>')
        for field in fields:
            content = value(row.get(field))
            if field == PHOTO:
                source = photo_source(content)
                content = f'<img src="{html.escape(source, quote=True)}" alt="Фото Komertia" loading="lazy">' if source else ''
            else:
                if field.endswith((' PLN', ' %')) and isinstance(row.get(field), (int, float)):
                    content = '—' if pd.isna(row[field]) else f'{row[field]:.2f}'
                content = html.escape(content)
            parts.append(f'<td>{content}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return ''.join(parts)


def excel_details(frame, writer, sheet):
    """Excel cells cap text at 32767 chars; keep embedded photos losslessly."""
    result = frame.copy()
    chunks = []
    if PHOTO in result:
        for index, item in enumerate(result[PHOTO]):
            content = value(item)
            if len(content) > 30000:
                for part, start in enumerate(range(0, len(content), 30000)):
                    chunks.append({'row': index, 'part': part, 'data': content[start:start + 30000]})
                result.iloc[index, result.columns.get_loc(PHOTO)] = ''
    result.to_excel(writer, sheet_name=sheet, index=False)
    if chunks:
        pd.DataFrame(chunks).to_excel(writer, sheet_name='Фото данные', index=False)
