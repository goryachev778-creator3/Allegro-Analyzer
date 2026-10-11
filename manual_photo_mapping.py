"""Explicit photo choices, independent of missing original LP metadata."""
import base64
import hashlib
import pandas as pd
import streamlit as st
from komertia_details import NAME_PL, enrich_details
from komertia_photos import read_photo_zip, save_manual_zip_photos, auto_photo_preview, save_confirmed_auto_photos
from storage import ensure_ids, is_external


def render_manual_mapping(payload, frame):
    photos = read_photo_zip(payload)
    revision = hashlib.sha256(payload).hexdigest()[:16]
    if st.button('Автоматически сопоставить все фото', key='auto_match_all_photos'):
        st.session_state['auto_photo_preview'] = {'zip_revision': revision, 'plan': auto_photo_preview(frame, photos)}
    saved_preview = st.session_state.get('auto_photo_preview')
    if saved_preview and saved_preview['zip_revision'] == revision:
        plan = saved_preview['plan']
        st.subheader('Предварительный результат автоматического сопоставления')
        st.caption(f"Сопоставлено: {len(plan['matches'])} · без однозначного совпадения: {len(plan['unresolved'])} · исключено с количеством 0: {len(plan['excluded'])}")
        preview_table = pd.DataFrame([{'Nazwa produktu': r['name'], 'Исходный LP Komertia': r['lp'], 'Фото Komertia': r['photo']} for r in plan['matches']])
        if not preview_table.empty:
            st.dataframe(preview_table, column_config={'Фото Komertia': st.column_config.ImageColumn('Фото Komertia', width='medium'), 'Nazwa produktu': st.column_config.TextColumn('Nazwa produktu', width='large')}, hide_index=True, width='stretch', height=500)
        if plan['unresolved']:
            st.warning('Некоторым товарам не хватает исходных данных. Выберите их фото вручную ниже; после сохранения ручных фото автоматическое сопоставление сможет использовать точные изображения из ZIP.')
            for item in plan['unresolved']:
                st.write(item['name'] or 'Nazwa nieuzupełniona')
                st.caption(item['error'])
        if st.button('Подтвердить и сохранить автоматически сопоставленные фото в Neon', disabled=bool(plan['unresolved']) or not plan['matches'], key='confirm_auto_photos'):
            try:
                if not is_external():
                    raise ValueError('Подключение Neon не настроено. Фотографии не сохранены локально.')
                records = save_confirmed_auto_photos(payload, plan)
                st.session_state['products'] = pd.DataFrame(records)
                st.session_state['editor_revision'] = st.session_state.get('editor_revision', 0) + 1
                st.session_state['lp_photo_success'] = f"Сохранено подтверждённых фото в Neon: {len(plan['matches'])}. Названия, цены и порядок товаров сохранены."
                st.session_state.pop('auto_photo_preview', None)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
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
