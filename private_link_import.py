"""Import owner-supplied quote data from a URL fragment, never from public source."""
import base64
import json
import re
import zlib
from pathlib import Path
import pandas as pd
from analyzer import INPUTS, number
from komertia_details import enrich_details
from product_archive import MODE, FLAG


def decode_quote(token):
    if not isinstance(token,str) or len(token)>32000 or not re.fullmatch(r'[A-Za-z0-9_-]+',token):
        raise ValueError('Некорректная ссылка импорта.')
    try:
        compressed=base64.urlsafe_b64decode(token+'='*(-len(token)%4))
        decoder=zlib.decompressobj()
        raw=decoder.decompress(compressed,128001)
        if len(raw)>128000 or not decoder.eof or decoder.unused_data:
            raise ValueError('Размер данных превышен.')
        payload=json.loads(raw)
        order=payload['order']
        if not isinstance(order,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',order):
            raise ValueError('Некорректный номер заказа.')
        if not isinstance(payload['rows'],list) or not 1<=len(payload['rows'])<=200:
            raise ValueError('Некорректный список товаров.')
        rows=[]
        seen=set()
        excluded=0
        for source in payload['rows']:
            lp,product,variant,quantity,purchase=source
            if isinstance(lp,bool) or not isinstance(lp,int) or lp<=0 or lp in seen:
                raise ValueError('Исходные LP должны быть уникальными положительными числами.')
            seen.add(lp)
            if not isinstance(product,str) or not product.strip() or len(product)>2000 or not isinstance(variant,str) or len(variant)>2000:
                raise ValueError('Некорректные исходные названия.')
            quantity=number(quantity)
            if quantity!=int(quantity):
                raise ValueError('Количество должно быть целым.')
            if not quantity:
                excluded+=1
                continue
            row=dict.fromkeys(INPUTS,0.)
            row.update({'Товар':product,'Produkt':product,'Wariant':variant,'SKU':f'{order}:LP:{lp:02}',
                'Ilość':int(quantity),'source_order':order,'source_row':lp,
                '_position_id':f'komertia:{order}:LP:{lp:02}', 'Закупка PLN':number(purchase),
                MODE:True,FLAG:False,'_komertia_final_cost':True,
                'Komertia: status kosztów':'prognoza'})
            rows.append(row)
        if not rows:
            raise ValueError('Нет товаров с положительным количеством.')
        return enrich_details(pd.DataFrame(rows)), excluded
    except (KeyError,TypeError,zlib.error,UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('Не удалось прочитать данные ссылки импорта.') from exc


def save_quote(frame):
    import storage
    from product_duplicates import checked_import
    db=storage.state_connection()
    try:
        with db:
            if storage.is_external():
                db.execute('SELECT key FROM allegro_state WHERE key = %s FOR UPDATE',('analysis',))
            else:
                db.execute('BEGIN IMMEDIATE')
            existing=storage.read_from(db,'analysis') or []
            old=pd.DataFrame(existing) if existing else pd.DataFrame(columns=frame.columns)
            merged,skipped=checked_import(frame,old)
            added=merged.iloc[len(existing):].astype(object).where(pd.notna(merged.iloc[len(existing):]),None).to_dict('records')
            # Existing dictionaries, including all photos/prices, remain byte-for-byte values.
            updated=existing+added
            prices=storage.read_from(db,'prices') or {}
            for row in added:
                prices.setdefault(row['_position_id'],{c:row[c] for c in storage.SALES})
            storage.write_to(db,'analysis',updated)
            storage.write_to(db,'prices',prices)
        frame = pd.DataFrame(updated)
        frame.attrs['analysis_hash'] = storage.analysis_hash(updated)
        return frame,len(added),skipped
    finally:
        db.close()


def render():
    import streamlit as st
    import streamlit.components.v1 as components
    component=components.declare_component('allegro_private_import',path=str(Path(__file__).parent/'link_import'))
    token=component(key='private_import_token',default=None,clear=st.session_state.get('private_import_done',False))
    if st.session_state.get('private_import_success'):
        st.success(st.session_state['private_import_success'])
    if not token or st.session_state.get('private_import_done'):
        return
    try:
        frame,excluded=decode_quote(token)
        order=frame['source_order'].iloc[0]
        st.subheader(f'Готов к добавлению заказ {order}')
        st.caption(f"Позиций: {len(frame)} · единиц: {int(frame['Ilość'].sum())} · себестоимость прогнозная. Цены Allegro и комиссии нужно заполнить после импорта.")
        st.dataframe(frame[['source_row','Produkt','Wariant','Ilość','Закупка PLN']],hide_index=True)
        if st.button('Добавить товары в Neon',key='confirm_private_import',type='primary'):
            updated,added,skipped=save_quote(frame)
            st.session_state['products']=updated
            st.session_state['analysis_expected_hash']=updated.attrs.get('analysis_hash')
            st.session_state['editor_revision']=st.session_state.get('editor_revision',0)+1
            destination='Neon PostgreSQL' if __import__('storage').is_external() else 'локальную базу (Neon не подключён)'
            st.session_state['private_import_success']=f'Добавлено: {added}. Пропущено повторов: {skipped}. Сохранено в {destination}. Прежние товары сохранены.'
            st.session_state['private_import_done']=True
            st.rerun()
    except (ValueError,RuntimeError) as exc:
        st.error(str(exc))
