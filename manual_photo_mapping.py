"""Explicit photo choices, independent of missing original LP metadata."""
import base64
import hashlib
import pandas as pd
import streamlit as st
from komertia_details import NAME_PL, enrich_details, original_label, is_order_total
from komertia_photos import read_photo_zip, save_manual_zip_photos, auto_photo_preview, save_confirmed_auto_photos
from storage import ensure_ids, is_external


def render_manual_mapping(payload, frame):
    photos = read_photo_zip(payload)
    revision = hashlib.sha256(payload).hexdigest()[:16]
    from order_scope import order_labels
    labels = order_labels(frame)
    scope_order = st.selectbox('Заказ, которому принадлежат фотографии ZIP', list(dict.fromkeys(labels)))
    revision += '_' + scope_order
    if st.button('Автоматически сопоставить все фото', key='auto_match_all_photos'):
        st.session_state['auto_photo_preview'] = {'zip_revision': revision, 'plan': auto_photo_preview(frame, photos, scope_order=scope_order)}
    saved_preview = st.session_state.get('auto_photo_preview')
    if saved_preview and saved_preview['zip_revision'] == revision:
        plan = saved_preview['plan']
        st.subheader('Предварительный результат автоматического сопоставления')
        st.caption(f"Сопоставлено: {len(plan['matches'])} · без однозначного совпадения: {len(plan['unresolved'])} · исключено с количеством 0: {len(plan['excluded'])} · итоговых строк: {len(plan.get('totals', []))}")
        preview_table = pd.DataFrame([{'Produkt': r['product'], 'Wariant': r['variant'], 'Исходный LP Komertia': r['lp'], 'Фото Komertia': r['photo']} for r in plan['matches']])
        if not preview_table.empty:
            st.dataframe(preview_table, column_config={'Фото Komertia': st.column_config.ImageColumn('Фото Komertia', width='medium'), 'Produkt': st.column_config.TextColumn('Produkt', width='large'), 'Wariant': st.column_config.TextColumn('Wariant', width='large')}, hide_index=True, width='stretch', height=500)
        if plan.get('protected'):
            st.info(f"Существующие фотографии сохранены без замены: {len(plan['protected'])}")
        if plan['unresolved']:
            st.warning('Найденные совпадения можно сохранить сейчас. Для остальных товаров выберите фото вручную ниже; существующие фотографии останутся на месте.')
            for item in plan['unresolved']:
                st.write(item['name'] or 'Nazwa nieuzupełniona')
                st.caption(item['error'])
        if st.button('Подтвердить и сохранить автоматически сопоставленные фото в Neon', disabled=not plan['matches'], key='confirm_auto_photos'):
            try:
                if not is_external():
                    raise ValueError('Подключение Neon не настроено. Фотографии не сохранены локально.')
                records = save_confirmed_auto_photos(payload, plan)
                st.session_state['products'] = pd.DataFrame(records)
                st.session_state['analysis_expected_hash'] = __import__('storage').analysis_hash(records)
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
    expected_ids = current['_position_id'].tolist()
    current = current.loc[~current.apply(is_order_total, axis=1) & order_labels(current).eq(scope_order)].reset_index(drop=True)
    selections = {}
    for index, row in current.iterrows():
        name, choice, preview = st.columns([3, 2, 1])
        name.write(f"{index + 1}. {original_label(row) or 'Brak nazwy w danych źródłowych'}")
        lp = choice.selectbox(f'Фото для товара {index + 1}', [None] + sorted(photos), format_func=lambda item: 'Без изменения' if item is None else f'LP {item:02}', key=f'manual_photo_{revision}_{row["_position_id"]}')
        if lp is not None:
            selections[row['_position_id']] = lp
            preview.image(base64.b64decode(photos[lp].split(',', 1)[1]), width=100)
    st.caption(f'Товаров: {len(current)} · выбрано фото: {len(selections)}')
    if st.button('Сохранить выбранные фотографии в Neon', disabled=not selections, key='save_manual_photos'):
        try:
            if not is_external():
                raise ValueError('Подключение Neon не настроено. Фотографии не сохранены локально.')
            records = save_manual_zip_photos(payload, selections, expected_ids)
            st.session_state['products'] = pd.DataFrame(records)
            st.session_state['analysis_expected_hash'] = __import__('storage').analysis_hash(records)
            st.session_state['editor_revision'] = st.session_state.get('editor_revision', 0) + 1
            st.session_state['lp_photo_success'] = f'Сохранено выбранных фото в Neon: {len(selections)}. Остальные данные товаров не изменены.'
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
