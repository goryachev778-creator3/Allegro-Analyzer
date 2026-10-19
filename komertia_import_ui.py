"""Streamlit quote preview/confirmation. Does not write until explicitly confirmed."""
from datetime import date
import pandas as pd
import streamlit as st
import storage
from komertia_details import PHOTO
from komertia_quote import parse_quote, QuoteError
from komertia_import_service import snapshot, plan_import, confirm_import, ImportErrorSafe


def render():
    st.subheader('Импорт Komertia')
    st.caption('Загрузите сохранённую выценку Komertia. Названия, варианты и оригинальные фото извлекаются из файла; копировать SQL не требуется.')
    if not storage.is_external():
        st.warning('Neon не подключён. Предпросмотр доступен, запись отключена. Подключение ALLEGRO_DATABASE_URL задаётся только в Streamlit Secrets.')
    batch = st.date_input('Дата партии', value=date.today(), key='komertia_batch_date').isoformat()
    upload = st.file_uploader('Файл выцены Komertia', type=['webarchive','html','htm'], key='komertia_quote_upload', help='В Safari: ⌘S → Веб-архив. XLSX/CSV остаются в прежней вкладке настроек.')
    if upload:
        source = st.text_input('Ссылка на заказ Komertia', key='komertia_html_source') if upload.name.lower().endswith(('.html','.htm')) else ''
        try:
            quote = parse_quote(upload.getvalue(), upload.name, batch, source)
            st.session_state['komertia_last_validation_error'] = ''
        except (QuoteError, ValueError, TypeError, OverflowError):
            st.error('Файл не прошёл проверку: проверьте структуру выцены, исходную ссылку, фотографии, количество и итоговые суммы. Импорт не выполнялся.')
            quote = None
        if quote:
            report = quote.report
            a,b,c,d = st.columns(4)
            a.metric('Активных позиций', report['active_positions'])
            b.metric('Штук', report['quantity'])
            c.metric('Итог выцены, PLN', report['quote_total'])
            d.metric('Округление, PLN', report['rounding_difference'])
            st.caption(f"Исходных строк: {report['source_positions']}; исключено нулевых: {report['zero_positions']}. Первая оплата: {report['first_payment']} PLN; вторая: {report['second_payment']} PLN. Cena szt. × количество: {report['unit_price_total']} PLN.")
            st.info('Закупка — окончательная Cena szt. Доставка и таможня повторно не добавляются. Цена Allegro и комиссия новых позиций не заданы; ставку нужно проверить по категории.')
            if report['incomplete_variant_lps']:
                st.warning('В самой Komertia сокращены варианты строк: ' + ', '.join(map(str, report['incomplete_variant_lps'])) + '. Текст сохранится без выдуманных дополнений.')
            if report['remote_photos']:
                st.warning(f"Для {report['remote_photos']} позиций фото представлено внешней ссылкой. Для хранения оригиналов в Neon загрузите веб-архив с изображениями.")
            preview = pd.DataFrame(quote.records)
            can_save = False
            try:
                if storage.is_external():
                    existing, log = snapshot()
                    additions, states, archived = plan_import(existing, quote)
                    preview['Проверка'] = states
                    st.caption(f'Будет добавлено: {len(additions)}. Уже есть: {len(states)-len(additions)}. Архивных совпадений: {archived}; они останутся в архиве.')
                    can_save = True
            except ImportErrorSafe as exc:
                st.error(str(exc))
            columns = [PHOTO,'Produkt','Wariant','Ilość','Закупка PLN','Партия']
            if 'Проверка' in preview:
                columns.append('Проверка')
            st.dataframe(preview[columns], hide_index=True, height=500, column_config={PHOTO:st.column_config.ImageColumn('Оригинал фото')})
            acknowledged = st.checkbox('Проверены позиции, фото, варианты и расхождение округления. Подтверждаю добавление без изменения старых товаров.', key='komertia_ack_'+quote.digest)
            if st.button('Подтвердить импорт', type='primary', disabled=not (acknowledged and can_save)):
                try:
                    # Reparse at the actual confirmation, never trust editable preview values.
                    checked = parse_quote(upload.getvalue(), upload.name, batch, source)
                    records, event = confirm_import(checked, acknowledged=acknowledged)
                    st.session_state['products'] = storage.ensure_ids(pd.DataFrame(records))
                    st.session_state['analysis_expected_hash'] = storage.analysis_hash(records)
                    st.session_state['editor_revision'] = st.session_state.get('editor_revision',0)+1
                    st.session_state['komertia_import_success'] = f"Добавлено: {event['added']}. Пропущено существующих: {event['skipped']}. Транзакция подтверждена в Neon."
                    st.rerun()
                except (ImportErrorSafe, QuoteError) as exc:
                    st.error(str(exc))
    if st.session_state.get('komertia_import_success'):
        st.success(st.session_state['komertia_import_success'])
    with st.expander('Журнал операций импорта'):
        if st.button('Обновить журнал импорта', disabled=not storage.is_external()):
            try:
                _, log = snapshot()
                rows = [{k:e.get(k) for k in ('time','batch','order_id','status','added','skipped','archived_untouched')} for e in reversed(log)]
                st.dataframe(pd.DataFrame(rows), hide_index=True)
            except ImportErrorSafe as exc:
                st.error(str(exc))
