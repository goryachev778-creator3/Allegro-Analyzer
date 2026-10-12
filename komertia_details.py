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


def original_record(row):
    """Recover exact original text; preserve all unrelated saved fields."""
    from pathlib import Path
    import json
    result = dict(row)
    if is_order_total(row):
        return result
    for target in ('Produkt', 'Wariant'):
        aliases = sorted([c for c in row if str(c).strip().casefold() == target.casefold()], key=lambda c: str(c) != target.upper())
        source = next((row[c] for c in aliases if value(row[c]).strip()), '')
        if value(source).strip():
            result[target] = value(source)
    catalog = json.loads((Path(__file__).parent / 'assets' / 'komertia-screenshots.json').read_text())['rows']
    position = value(row.get('_position_id'))
    lp = value(row.get('source_row')).strip()
    candidates = [r for r in catalog if position in (r['position_id'], f"komertia-screenshot-oct2026:{r['source_row']}")]
    if not candidates and lp:
        try:
            candidates = [r for r in catalog if float(lp) == r['source_row']]
        except ValueError:
            pass
    if not candidates:
        source = value(result.get('Produkt')) or value(row.get('Товар'))
        if source:
            candidates = [r for r in catalog if _source_key(r['Produkt']) == _source_key(source) and (not value(result.get('Wariant')).strip() or _source_key(r['Wariant']) == _source_key(result['Wariant']))]
    if lp and candidates:
        try:
            candidates = [r for r in candidates if float(lp) == r['source_row']]
        except ValueError:
            candidates = []
    if len(candidates) == 1:
        for column in ('Produkt', 'Wariant'):
            if not value(result.get(column)).strip():
                result[column] = candidates[0][column]
    for column in ('Produkt', 'Wariant'):
        result.setdefault(column, '')
    return result


def original_label(row):
    return ' · '.join(value(row.get(c)) for c in ('Produkt', 'Wariant') if value(row.get(c)).strip())


def polish_name(row):
    # Compatibility only: never translate or invent product names.
    return original_label(original_record(row))


def enrich_details(frame):
    if frame is None:
        return None
    result = frame.copy()
    for field in DETAILS:
        if field not in result:
            result[field] = ''
        else:
            result[field] = result[field].map(value)
    for column in ('Produkt', 'Wariant'):
        if column not in result:
            result[column] = ''
    for index, row in result.iterrows():
        original = original_record(row)
        for column in ('Produkt', 'Wariant'):
            result.loc[index, column] = original[column]
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


def is_order_total(row):
    """The order footer is not a product; keep its stored record intact."""
    fields = ('Produkt', 'PRODUKT', 'Товар', NAME_PL)
    labels = {_source_key(row.get(c)) for c in fields}
    labels.add(_source_key(original_label(row)))
    labels.add(_source_key(' '.join(value(row.get(c)) for c in ('Produkt', 'Wariant'))))
    return 'итого a1632' in labels
