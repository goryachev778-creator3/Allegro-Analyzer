from io import BytesIO
import importlib
import komertia_details
import storage
import komertia_photos
# Streamlit reruns keep imported modules cached after a source update.
# Refresh the pure metadata/storage definitions before binding their functions.
importlib.reload(komertia_details)
importlib.reload(komertia_photos)
importlib.reload(storage)
from komertia_details import PHOTO, FULL_NAME, NAME_PL, DETAILS, ALIASES, enrich_details, import_details, uploaded_photo, full_table
from photo_grid import photo_grid, apply_photo_event
from screenshot_catalog import load_catalog
from komertia import columns as komertia_columns, apply_costs
import pandas as pd
import streamlit as st
from storage import load_analysis, save_analysis, merge_import, profile_key, read, write, filter_stock, identify_rows, is_external, backup_excel, read_backup
from analyzer import INPUTS, NUMERIC, COLORS, calculate, export_excel, number, read_upload

st.set_page_config(page_title="Allegro Analyzer", page_icon="📊", layout="wide")
st.title("Allegro Analyzer")
st.caption("От закупки в Китае до прибыли на Allegro · все расчёты на одну единицу товара")
save_indicator = st.empty()

def show_saved():
    if is_external():
        save_indicator.success("Сохранено во внешней базе")
    else:
        save_indicator.warning("Сохранено только локально. Защита от потери при новом деплое НЕ настроена. Скачайте резервную копию Excel; подключите ALLEGRO_DATABASE_URL в Secrets.")

try:
    if "products" not in st.session_state:
        restored = load_analysis()
        migrated = enrich_details(restored)
        if restored is not None and not migrated.equals(restored):
            save_analysis(migrated)
        restored = migrated
        if restored is not None:
            st.session_state["products"] = restored
    show_saved()
except Exception as exc:
    save_indicator.error(f"Есть несохранённые изменения · хранилище недоступно: {exc}")
    if "products" not in st.session_state:
        st.session_state["products"] = pd.DataFrame(columns=INPUTS)


def replace_analysis(frame):
    try:
        save_analysis(frame)
    except Exception as exc:
        save_indicator.error(f"Есть несохранённые изменения · ошибка сохранения: {exc}")
        return False
    st.session_state["products"] = frame.copy()
    st.session_state["editor_revision"] = st.session_state.get("editor_revision", 0) + 1
    st.session_state.pop("pending_action", None)
    show_saved()
    return True

with st.expander("Восстановить данные из резервной копии Excel"):
    backup_file = st.file_uploader("Резервная копия рабочего анализа", type=["xlsx"], key="restore_backup")
    confirm_restore = st.checkbox("Заменить рабочий анализ данными резервной копии")
    if st.button("Восстановить резервную копию", disabled=not backup_file or not confirm_restore):
        try:
            restored_backup = read_backup(backup_file.getvalue())
            if replace_analysis(restored_backup):
                st.rerun()
        except Exception:
            st.error("Не удалось восстановить копию. Проверьте формат файла и доступность хранилища.")

with st.sidebar:
    st.header("Параметры анализа")
    weak = st.number_input("Порог выгодной маржи, %", 0.0, 100.0, 15.0, 1.0)
    st.markdown("🟢 Выгодный · 🟡 Слабая прибыль · 🔴 Убыточный · ⚪ Без цены")
    st.info("Расходы на партию разделите на количество единиц. Возмещаемый НДС не включайте в себестоимость. Закупку и продажу указывайте на одинаковой базе НДС.")

with st.expander("Методика расчёта"):
    st.markdown("""**Пошлина** = (закупка + доставка) × ставка пошлины.

**Себестоимость** = закупка + доставка + пошлина + оформление + дополнительные расходы + невозмещаемый НДС.

**Прибыль** = цена Allegro − себестоимость − процентная и фиксированная комиссии.

**Маржа** = прибыль / цена продажи × 100%. **ROI** = прибыль / себестоимость × 100%.

Ставку пошлины укажите по коду товара. Логистику, возвраты и другие расходы при необходимости включите в дополнительные расходы. При нулевом знаменателе маржа или ROI не определены. Расчёт служит для сравнения товаров и не заменяет налоговый учёт.""")

sample = pd.DataFrame([
    ["Органайзер", "ORG-01", 20, 5, 6, 2, 3, 0, 65, 12, 0],
    ["Лампа", "LAMP-02", 40, 10, 4, 3, 5, 0, 75, 12, 0],
    ["Чехол", "CASE-03", 15, 4, 6, 2, 3, 0, 20, 12, 0],
], columns=INPUTS)
st.download_button("Скачать шаблон CSV", sample.to_csv(index=False, sep=";").encode("utf-8-sig"), "allegro-template.csv", "text/csv")
upload = st.file_uploader("Загрузите выгрузку Komertia или готовый анализ", type=["csv", "xlsx"], help="Excel .xlsx или CSV UTF-8 / Windows-1250. Названия колонок можно сопоставить вручную.")
if upload:
    payload = upload.getvalue()
    try:
        sheet = 0
        if upload.name.lower().endswith(".xlsx"):
            sheets = pd.ExcelFile(BytesIO(payload)).sheet_names
            sheet = st.selectbox("Лист Excel", sheets)
        raw = read_upload(payload, upload.name, sheet)
        if raw.empty or not len(raw.columns):
            st.warning("Файл не содержит строк товаров.")
            st.stop()
        st.caption(f"Прочитано строк: {len(raw)}")
        with st.expander("Предпросмотр выгрузки", expanded=False):
            st.dataframe(raw.head(10), hide_index=True)
        profile = profile_key(upload.name, sheet, raw.columns)
        preferences = read(profile) or {}
        with st.form("mapping_" + profile):
            st.subheader("Сопоставление колонок")
            st.caption("Необязательные поля можно оставить пустыми: будут использованы значения по умолчанию. Закупку в валюте пересчитаем в PLN.")
            aliases = {
                "Товар": ["name", "product name", "nazwa", "nazwa produktu", "наименование", "название", "товар", "produkt"],
                "SKU": ["sku", "код", "артикул", "symbol", "kod"],
                "Закупка PLN": ["purchase price", "cena zakupu", "закупочная цена", "закупка"],
                "Цена Allegro PLN": ["sale price", "cena sprzedaży", "цена продажи"],
            }
            options = ["— Не задано —"] + list(raw.columns)
            mapping = {}
            defaults = {}
            cols = st.columns(3)
            for i, field in enumerate(INPUTS):
                match = next((c for c in raw.columns if str(c).strip().lower() in [field.lower()] + aliases.get(field, [])), None)
                remembered = preferences.get("mapping", {}).get(field)
                if remembered in options:
                    match = remembered
                with cols[i % 3]:
                    mapping[field] = st.selectbox(field, options, index=options.index(match) if match else 0, key=f"{profile}_map_{field}")
                    if field in NUMERIC:
                        defaults[field] = st.number_input(f"По умолчанию: {field}", min_value=0.0, value=float(preferences.get("defaults", {}).get(field, 0.0)), key=f"{profile}_default_{field}")
            for field in DETAILS:
                match = next((c for c in raw.columns if str(c).strip().casefold() in [a.casefold() for a in ALIASES[field]]), None)
                remembered = preferences.get("mapping", {}).get(field)
                if remembered in options:
                    match = remembered
                mapping[field] = st.selectbox(field + " · исходная колонка", options, index=options.index(match) if match else 0, key=profile + field)
            st.caption("Укажите только оригинальные фото и полные названия Komertia. Сокращённые названия не дополняются автоматически.")
            rate = st.number_input("Курс закупки: PLN за 1 единицу валюты (для PLN = 1)", min_value=0.000001, value=float(preferences.get("rate", 1.0)), format="%.6f", key=profile + "_rate")
            st.caption("Курс применяется только к закупке. Доставку и остальные расходы вводите в PLN.")
            stock_match = next((c for c in raw.columns if str(c).strip().casefold() in ("ilość", "ilosc", "количество", "quantity")), None)
            stock_match = preferences.get("stock", stock_match)
            stock = st.selectbox("Остаток / Ilość (нулевые позиции исключаются)", options, index=options.index(stock_match) if stock_match in options else 0, key=profile + "_stock")
            identity_columns = {}
            for label in ("Produkt", "Wariant"):
                detected = next((c for c in raw.columns if str(c).strip().casefold() == label.casefold()), None)
                remembered = preferences.get(label, detected)
                identity_columns[label] = st.selectbox(label + " · идентификатор варианта", options, index=options.index(remembered) if remembered in options else 0, key=profile + label)
            detected_id = next((c for c in raw.columns if str(c).strip().casefold() in ("id", "row id", "variant id", "id wariantu", "id pozycji")), None)
            remembered_id = preferences.get("row_id", detected_id)
            row_id = st.selectbox("Стабильный ID строки (если есть)", options, index=options.index(remembered_id) if remembered_id in options else 0, key=profile + "row_id")
            detected_costs = komertia_columns(raw)
            is_komertia = bool(detected_costs["final_unit"] or (detected_costs["quantity"] and detected_costs["total"]))
            use_komertia = st.checkbox("Окончательная закупка Komertia: Cena szt. (или Razem ÷ Ilość)", value=is_komertia, disabled=not is_komertia, key=profile + "komertia_costs")
            st.caption("В «Закупка PLN» записывается окончательная стоимость штуки с доставкой и таможней. Включённые расходы повторно не начисляются. Цены Allegro и комиссии сохраняются.")
            apply = st.form_submit_button("Загрузить в таблицу", type="primary")
        if apply:
            write(profile, {"mapping": mapping, "defaults": defaults, "rate": rate, "stock": stock, **identity_columns, "row_id": row_id})
            if mapping["Товар"] != options[0]:
                product_col = identity_columns["Produkt"] if identity_columns["Produkt"] != options[0] else mapping["Товар"]
                raw = identify_rows(raw, product_col, identity_columns["Wariant"] if identity_columns["Wariant"] != options[0] else None, row_id if row_id != options[0] else None, stock if stock != options[0] else None)
            raw, skipped = filter_stock(raw, None if stock == options[0] else stock)
            if skipped:
                st.info(f"Исключено позиций с нулевым остатком: {skipped}")
            if mapping["Товар"] == options[0]:
                st.error("Выберите колонку с названием товара.")
            else:
                frame = pd.DataFrame(index=raw.index)
                errors = []
                for field in INPUTS:
                    source = mapping[field]
                    values = raw[source] if source != options[0] else pd.Series(defaults.get(field, ""), index=raw.index)
                    if field in NUMERIC:
                        parsed = []
                        for pos, value in enumerate(values, start=2):
                            try:
                                parsed.append(number(value))
                            except (ValueError, TypeError):
                                errors.append(f"Строка {pos}, {field}: некорректное число")
                                parsed.append(0)
                        frame[field] = parsed
                    else:
                        frame[field] = values.astype(str)
                for metadata in ("Produkt", "Wariant", "_position_id"):
                    if metadata in raw:
                        frame[metadata] = raw[metadata]
                frame = import_details(frame, raw, mapping)
                frame["Закупка PLN"] *= rate
                if use_komertia and not errors:
                    frame = apply_costs(frame, raw)
                if errors:
                    st.error("Исправьте данные перед импортом: " + "; ".join(errors[:10]))
                elif (frame["Комиссия %"] > 100).any():
                    st.error("Комиссия Allegro не может превышать 100%.")
                else:
                    merged = merge_import(frame, load_analysis())
                    if use_komertia:
                        for cost in NUMERIC:
                            if cost not in ("Цена Allegro PLN", "Комиссия %", "Комиссия PLN"):
                                merged[cost] = frame[cost].to_numpy()
                    if replace_analysis(merged):
                        st.success("Товары загружены. Сохранённые поля существующих товаров сохранены; новые товары добавлены.")
    except Exception as exc:
        st.error(f"Не удалось прочитать файл: {exc}")

demo_col, reset_col = st.columns(2)
if demo_col.button("Открыть демонстрационный пример"):
    if "products" in st.session_state and not st.session_state["products"].empty:
        st.session_state["pending_action"] = "demo"
    else:
        replace_analysis(sample)
if reset_col.button("Сбросить текущий анализ"):
    st.session_state["pending_action"] = "reset"

if st.button("Загрузить товары из скриншотов Komertia"):
    st.session_state["pending_action"] = "screenshots"

pending = st.session_state.get("pending_action")
if pending:
    if pending == "screenshots":
        st.info("Загрузить 29 позиций из ваших скриншотов? Нулевые остатки исключены. Общие расходы распределены по количеству. Названия сокращены как на снимках; строка Komertia указана отдельно. Текущие данные заменяются, а сохранённые правки ранее загруженных позиций этого набора сохраняются.")
    st.warning("Заменить текущий анализ демонстрационным примером?" if pending == "demo" else "Загрузить таблицу из скриншотов?" if pending == "screenshots" else "Удалить все товары из текущего анализа? Это действие нельзя отменить.")
    yes, no = st.columns(2)
    if yes.button("Подтвердить загрузку" if pending == "screenshots" else "Подтвердить замену" if pending == "demo" else "Подтвердить сброс"):
        target = merge_import(load_catalog(), load_analysis()) if pending == "screenshots" else sample if pending == "demo" else pd.DataFrame(columns=INPUTS)
        if replace_analysis(target):
            st.rerun()
    if no.button("Отмена"):
        st.session_state.pop("pending_action", None)
        st.rerun()

if "products" not in st.session_state or st.session_state["products"].empty:
    st.info("Загрузите файл или откройте пример, чтобы начать анализ.")
    st.stop()

with st.expander("Импорт фотографий Komertia по исходным LP из ZIP"):
    photos_zip = st.file_uploader("ZIP с файлами Komertia_LP_01.png–Komertia_LP_38.png", type=["zip"], key="lp_photo_zip")
    st.caption("Фото сопоставляются по исходному LP Komertia, а не по текущему номеру строки. Названия, цены, расчёты и порядок товаров сохраняются.")
    if st.button("Сохранить фотографии ZIP в Neon", disabled=photos_zip is None):
        try:
            if not is_external():
                raise ValueError("Подключение Neon не настроено. Фотографии не сохранены локально.")
            from komertia_photos import save_zip_photos
            records, matched = save_zip_photos(photos_zip.getvalue())
            st.session_state["products"] = pd.DataFrame(records)
            st.session_state["editor_revision"] = st.session_state.get("editor_revision", 0) + 1
            st.session_state["lp_photo_success"] = f"Сохранено фото в Neon: {len(matched)}. Исходные LP: " + ", ".join(map(str, matched))
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
if st.session_state.get("lp_photo_success"):
    st.success(st.session_state["lp_photo_success"])

st.subheader("Товары и расходы")
st.info("Закупка и расходы — на 1 штуку. Укажите цену продажи Allegro и комиссию: прибыль, маржа и ROI рассчитываются автоматически.")
st.markdown("""<style>
/* Keep native grid scrolling and prevent scroll chaining onto the page. */
[data-testid="stDataFrame"] .dvn-scroller {
    overscroll-behavior: contain;
}
</style>""", unsafe_allow_html=True)
st.caption("Введите цены продажи и комиссии. Прокручивайте таблицу по вертикали и горизонтали; Shift + колесо прокручивает вбок. Можно добавить или удалить строки. Расчёты обновляются автоматически; выгрузка содержит текущий анализ.")
config = {c: st.column_config.NumberColumn(c, min_value=0.0, max_value=100.0 if c == "Комиссия %" else None, format="%.2f", width="medium") for c in NUMERIC}
editor_frame = enrich_details(st.session_state["products"]).drop(columns=["№"], errors="ignore").copy()
if "Produkt" not in editor_frame:
    editor_frame["Produkt"] = editor_frame["Товар"]
if "Wariant" not in editor_frame:
    editor_frame["Wariant"] = ""
editor_frame.insert(0, "№", range(1, len(editor_frame) + 1))
hidden_source = ["Товар", "Produkt", "Wariant", FULL_NAME, "_position_id", "_komertia_final_cost"]
first_columns = ["№", PHOTO, NAME_PL, "Закупка PLN", "Цена Allegro PLN", "Комиссия %"]
column_order = first_columns + [c for c in NUMERIC if c not in first_columns] + ["SKU"]
column_order += [c for c in editor_frame if c not in column_order and c not in hidden_source]
config["№"] = st.column_config.NumberColumn("№", width=55, disabled=True, format="%d", pinned=True)
config[PHOTO] = st.column_config.ImageColumn(PHOTO, width="medium")
config[NAME_PL] = st.column_config.TextColumn(NAME_PL, width="large", help="Короткое польское название: модель, размер, цвет, комплектация, если известны из источника.")
config.update({c: st.column_config.TextColumn(c, width=150 if c == "Produkt" else 120) for c in ("Товар", "SKU", "Produkt", "Wariant")})
for c in ("Закупка PLN", "Цена Allegro PLN", "Комиссия %"):
    config[c] = st.column_config.NumberColumn(c, min_value=0.0, max_value=100.0 if c == "Комиссия %" else None, format="%.2f", width=140)
edited = st.data_editor(
    editor_frame, column_order=column_order,
    column_config={**config, **{c: None for c in hidden_source}},
    disabled=["№", PHOTO, "Produkt", "Wariant", "_position_id"],
    num_rows="dynamic", hide_index=True, height=600, width="stretch",
    key=f"editor_{st.session_state.get('editor_revision', 0)}",
).drop(columns=["№"])
# Regenerate display numbers after additions/deletions without persisting them.
if len(edited) != len(editor_frame):
    if replace_analysis(edited.reset_index(drop=True)):
        st.rerun()
try:
    save_analysis(edited)
    st.session_state["products"] = edited.copy()
    show_saved()
except Exception as exc:
    save_indicator.error(f"Есть несохранённые изменения · ошибка сохранения: {exc}")
st.markdown("""<style>
.komertia-table {overflow-x:auto; max-height:650px; overflow-y:auto;}
.komertia-table table {border-collapse:collapse; width:100%;}
.komertia-table th,.komertia-table td {padding:10px; border:1px solid #8885; text-align:left; vertical-align:top; white-space:pre-wrap; overflow-wrap:anywhere; min-width:120px;}
.komertia-table img {width:100px; height:100px; object-fit:contain;}
</style>""", unsafe_allow_html=True)
st.subheader("Фото и названия товаров")
st.caption("Одно польское название на товар. Указаны только известные характеристики; отсутствующие параметры не дополняются. Оригинальные данные Komertia сохранены отдельно.")
from storage import ensure_ids
photo_frame = ensure_ids(edited)
photo_event = photo_grid(photo_frame, st.session_state.get("photo_error", ""))
if photo_event and photo_event.get("event_id") != st.session_state.get("last_photo_event"):
    try:
        updated = apply_photo_event(photo_frame, photo_event)
        if replace_analysis(updated):
            st.session_state["last_photo_event"] = photo_event["event_id"]
            st.session_state.pop("photo_error", None)
            st.rerun()
    except ValueError as exc:
        st.session_state["last_photo_event"] = photo_event.get("event_id")
        st.session_state["photo_error"] = str(exc)
        st.error(str(exc))
if not edited.empty:
    with st.expander("Фото, польское название и исходные данные Komertia"):
        from storage import ensure_ids
        detail_frame = ensure_ids(edited)
        positions = list(detail_frame['_position_id'])
        labels = {row['_position_id']: f"{i + 1}. {row[NAME_PL] or 'Uzupełnij nazwę po polsku'}" for i, row in detail_frame.iterrows()}
        selected = st.selectbox("Товар и вариант", positions, format_func=lambda item: labels[item], key="detail_position")
        row_index = positions.index(selected)
        row = detail_frame.iloc[row_index]
        st.text("Оригинальный Produkt: " + str(row.get("Produkt", "")))
        st.text("Оригинальный Wariant: " + str(row.get("Wariant", "")))
        with st.form("details_" + selected + "_" + str(st.session_state.get("editor_revision", 0))):
            polish_title = st.text_area(NAME_PL, value=row[NAME_PL], help="Короткое название на польском языке с известными характеристиками.")
            name = st.text_area(FULL_NAME, value=row[FULL_NAME], help="Вставьте оригинальное полное название. Пустое поле остаётся пустым.")
            photo = st.file_uploader(PHOTO, type=["png", "jpg", "jpeg", "webp"], help="Оригинальное фото до 5 МБ; хранится вместе с товаром в существующей базе.")
            save_details = st.form_submit_button("Сохранить фото и название")
        if save_details:
            try:
                if __import__("re").search(r"[А-Яа-яЁё]", polish_title):
                    raise ValueError("Введите короткое название на польском языке.")
                detail_frame.loc[row_index, NAME_PL] = polish_title
                detail_frame.loc[row_index, FULL_NAME] = name
                if photo is not None:
                    detail_frame.loc[row_index, PHOTO] = uploaded_photo(photo.getvalue())
                if replace_analysis(detail_frame):
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))
st.download_button("Скачать резервную копию Excel", backup_excel(edited), "allegro-backup.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", help="Рабочие поля и постоянные идентификаторы. Позволяет восстановить цены и комиссии после пересборки.")
if edited.empty:
    st.info("Добавьте хотя бы один товар.")
    st.stop()
try:
    result = calculate(edited.fillna({"Товар": "", "SKU": ""}), weak)
except (ValueError, TypeError) as exc:
    st.error(f"Проверьте значения в таблице: {exc}")
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Товаров", len(result))
b.metric("Выгодных", int((result["Статус"] == "Выгодный").sum()))
c.metric("Убыточных", int((result["Статус"] == "Убыточный").sum()))
d.metric("Без цены", int((result["Статус"] == "Без цены").sum()))
st.subheader("Анализ прибыльности")
st.caption("По убыванию прибыли в PLN на единицу. Пустой ROI или маржа означает нулевой знаменатель.")
left, right = st.columns(2)
search = left.text_input("Поиск по названию или SKU")
statuses = right.multiselect("Статус", list(COLORS), default=list(COLORS))
visible = result[result["Статус"].isin(statuses)]
if search:
    visible = visible[visible[NAME_PL].str.contains(search, case=False, regex=False, na=False) | visible["SKU"].str.contains(search, case=False, regex=False, na=False) | visible[FULL_NAME].str.contains(search, case=False, regex=False, na=False) | visible["Wariant"].str.contains(search, case=False, regex=False, na=False)]
summary = ["SKU", "Статус", "Себестоимость PLN", "Цена Allegro PLN", "Комиссия всего PLN", "Прибыль PLN", "Маржа %", "ROI %"]
summary = [PHOTO, NAME_PL] + summary
summary = [c for c in summary if c in visible]
def row_style(row):
    return [f"background-color: #{COLORS[row['Статус']]}; color: #172554" for _ in row]
st.markdown(full_table(visible, summary), unsafe_allow_html=True)
st.download_button("Экспорт полного анализа в Excel", export_excel(result, weak), "allegro-analysis.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", help="Экспортируются все товары, включая скрытые фильтром, расходы и методика.")
st.caption("При настроенной внешней базе изменения сохраняются между деплоями. Локальная SQLite не гарантирует сохранность при пересборке. Изменения сохраняются в SQLite и восстанавливаются после обновления страницы и перезапуска приложения. Это один общий рабочий анализ для этой установки; экспорт Excel сохраняет отдельную копию.")
