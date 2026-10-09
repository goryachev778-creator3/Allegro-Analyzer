"""Clipboard/file uploads addressed by immutable product IDs."""
import base64
from pathlib import Path
import streamlit.components.v1 as components
from komertia_details import PHOTO, NAME_PL, uploaded_photo, photo_source, value

def _photo_component():
    # Register only inside the running Streamlit script, after page configuration.
    return components.declare_component('komertia_photo_grid', path=str(Path(__file__).parent / 'photo_grid'))


def photo_grid(frame, error=''):
    rows = [{'id': value(row['_position_id']), 'name': value(row[NAME_PL]), 'photo': photo_source(row[PHOTO])} for _, row in frame.iterrows()]
    return _photo_component()(rows=rows, error=error, key='komertia_photos', default=None)


def apply_photo_event(frame, event):
    if not isinstance(event, dict) or not isinstance(event.get('event_id'), str):
        raise ValueError('Некорректная вставка фото.')
    position = event.get('position_id')
    matches = frame['_position_id'].eq(position)
    if int(matches.sum()) != 1:
        raise ValueError('Товар не найден. Обновите таблицу и повторите вставку.')
    content = event.get('data')
    if not isinstance(content, str) or len(content) > 7 * 1024 * 1024:
        raise ValueError('Максимальный размер фото — 5 МБ.')
    try:
        prefix, encoded = content.split(',', 1)
        if prefix not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
            raise ValueError()
        data = base64.b64decode(encoded, validate=True)
    except Exception:
        raise ValueError('Вставьте изображение PNG, JPEG или WebP.') from None
    result = frame.copy()
    result.loc[matches, PHOTO] = uploaded_photo(data)
    return result
