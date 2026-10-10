"""Explicit photo choices, independent of missing original LP metadata."""
import base64
import hashlib
import pandas as pd
import streamlit as st
from komertia_details import NAME_PL, enrich_details
from komertia_photos import read_photo_zip, save_manual_zip_photos
from storage import ensure_ids, is_external


def render_manual_mapping(payload, frame):
    photos = read_photo_zip(payload)
    revision = hashlib.sha256(payload).hexdigest()[:16]
    st.subheader('Ручное сопоставление фотографий')
    st.caption('Сначала просмотрите фото из ZIP. Затем выберите LP фотографии для каждого товара. «Без изменения» сохраняет текущее фото. Названия, цены и порядок строк не меняются.')
    with st.expander('Все фотографии из ZIP', expanded=True):
        columns = st.columns(6)
        for index, lp in enumerate(sorted(photos)):
            with columns[index % 6]:
                st.image(base64.b64decode(photos[lp].split(',', 1)[1]), caption=f'LP {lp:02}', width=120)
    current = enrich_details(ensure_ids(frame.reset_index(drop=True)))
    selections = {}
    for index, row in current.iterrows():
        name, choice, preview = st.columns([3, 2, 1])
        name.write(f"{index + 1}. {row[NAME_PL] or 'Nazwa nieuzupełniona'}")
        lp = choice.selectbox(f'Фото для товара {index + 1}', [None] + sorted(photos), format_func=lambda item: 'Без изменения' if item is None else f'LP {item:02}', key=f'manual_photo_{revision}_{row["_position_id"]}')
        if lp is not None:
            selections[row['_position_id']] = lp
            preview.image(base64.b64decode(photos[lp].split(',', 1)[1]), width=100)
    st.caption(f'Товаров: {len(current)} · выбрано фото: {len(selections)}')
    if st.button('Сохранить выбранные фотографии в Neon', disabled=not selections, key='save_manual_photos'):
        try:
            if not is_external():
                raise ValueError('Подключение Neon не настроено. Фотографии не сохранены локально.')
            records = save_manual_zip_photos(payload, selections, current['_position_id'].tolist())
            st.session_state['products'] = pd.DataFrame(records)
            st.session_state['editor_revision'] = st.session_state.get('editor_revision', 0) + 1
            st.session_state['lp_photo_success'] = f'Сохранено выбранных фото в Neon: {len(selections)}. Остальные данные товаров не изменены.'
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
