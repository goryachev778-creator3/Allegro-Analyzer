from io import BytesIO
import compact_table
import importlib
importlib.reload(compact_table)
from compact_table import available_width, widths, LABELS
import komertia_details
import storage
import order_scope
importlib.reload(order_scope)
import product_archive
importlib.reload(product_archive)
import product_duplicates
importlib.reload(product_duplicates)
import photo_enhancement
importlib.reload(photo_enhancement)
import komertia_photos
# Streamlit reruns keep imported modules cached after a source update.
# Refresh the pure metadata/storage definitions before binding their functions.
importlib.reload(komertia_details)
importlib.reload(komertia_photos)
import manual_photo_mapping
importlib.reload(manual_photo_mapping)
importlib.reload(storage)
from komertia_details import PHOTO, FULL_NAME, NAME_PL, DETAILS, ALIASES, enrich_details, import_details, uploaded_photo, full_table, original_label, is_order_total
import photo_grid as photo_grid_module
importlib.reload(photo_grid_module)
from photo_grid import photo_grid, apply_photo_event
from screenshot_catalog import load_catalog
from komertia import columns as komertia_columns, apply_costs
import pandas as pd
import streamlit as st
from storage import load_analysis, save_analysis as _save_analysis, merge_import, profile_key, read, write, filter_stock, identify_rows, is_external, backup_excel, read_backup
from analyzer import INPUTS, NUMERIC, COLORS, calculate, export_excel, number, read_upload
from profitability_style import profitability_style

st.set_page_config(page_title="Allegro Analyzer", page_icon="📊", layout="wide")
st.title("Allegro Analyzer")
save_indicator = st.empty()

def show_saved():
    # A configured URL is not proof of a successful save. Show this message
    # only after a successful database health check (and successful load/save).
    if st.session_state.get("neon_verified") and st.session_state.get("storage_ready"):
        save_indicator.success("Подключено к Neon PostgreSQL. Данные загружены из базы.")
    else:
        save_indicator.error("Сохранение недоступно. Данные Neon не подтверждены.")


def require_storage_ready():
    if not st.session_state.get("neon_verified") or not st.session_state.get("storage_ready"):
        raise RuntimeError("Neon недоступен: запись заблокирована для защиты существующих товаров.")

def save_analysis(frame):
    require_storage_ready()
    token = _save_analysis(frame, expected_hash=st.session_state.get("analysis_expected_hash"))
    st.session_state["analysis_expected_hash"] = token

# Every rerun performs a read-only preflight, including when a session previously
# loaded products. Losing Neon access must immediately disable *all* editing.
from neon_health import check_neon_health
neon_status = check_neon_health()
st.session_state["neon_verified"] = neon_status["status"] == "OK"
st.session_state["storage_ready"] = False
storage_problem = None
if not st.session_state["neon_verified"]:
    storage_problem = neon_status["message"]
else:
    try:
        # Prefer a fresh snapshot rather than stale browser state after an outage.
        restored = load_analysis()
        if restored is None or restored.empty:
            raise RuntimeError("В Neon отсутствует рабочий анализ. Не создавайте новую таблицу.")
        st.session_state["analysis_expected_hash"] = restored.attrs.get("analysis_hash")
        st.session_state["products"] = restored
        st.session_state["storage_ready"] = True
        show_saved()
    except Exception:
        storage_problem = "Не удалось прочитать сохранённый анализ Neon. Изменения заблокированы."
        st.session_state["storage_ready"] = False

if storage_problem:
    save_indicator.error("Neon недоступен. Сохранение и импорт ЗАБЛОКИРОВАНЫ: " + storage_problem)


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

with st.sidebar:
    with st.expander("🔎 Диагностика Neon", expanded=False):
        st.caption("Проверка только читает данные. Пароли и строка подключения не выводятся.")
        if st.button("Проверить подключение Neon", key="neon_health_check"):
            from neon_health import check_neon_health
            health = check_neon_health()
            if health["status"] == "OK":
                st.success(f'{health["message"]} Позиций в базе: {health["positions"]}.')
            else:
                st.error(f'{health["status"]}: {health["message"]}')

    st.header("Параметры анализа")
    weak = st.number_input("Порог выгодной маржи, %", 0.0, 100.0, 50.0, 1.0)
    st.markdown(f"🟢 Маржа ≥ {weak:g}% и прибыль > 0  \n🟡 Прибыль ≥ 0 и маржа < {weak:g}%; также нулевая прибыль  \n🔴 Прибыль < 0  \n⚪ Цена не задана")


# Keep the diagnostic sidebar visible, but hide ALL write-enabled screens
# while database access or the existing analysis cannot be verified.
if not st.session_state.get("storage_ready"):
    st.warning("Режим защиты: все операции записи отключены. Не импортируйте товары повторно.")
    st.stop()

import private_link_import
importlib.reload(private_link_import)
private_link_import.render()

main_tab, settings_tab, komertia_tab = st.tabs(["Главная", "Настройки и импорт", "Импорт Komertia"])
with komertia_tab:
    from komertia_import_ui import render as render_komertia_import
    render_komertia_import()

with settings_tab:
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

    with st.expander("Методика расчёта"):
        st.markdown("""**Пошлина** = (закупка + доставка) × ставка пошлины.

    **Для рабочего анализа из 25 записей:** закупка уже включает транспорт и таможню.

    **Комиссия** = цена Allegro × комиссия % / 100.

    **Прибыль** = цена Allegro − закупка − комиссия − дополнительные расходы.

    **Маржа %** = прибыль / цена Allegro × 100.

    **Для старых примеров и других наборов:** себестоимость = закупка + доставка + пошлина + оформление + дополнительные расходы + невозмещаемый НДС.

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
                detected_lp = next((c for c in raw.columns if str(c).strip().casefold() in ("lp", "lp komertia", "source_row")), None)
                remembered_lp = preferences.get("source_lp", detected_lp)
                source_lp_column = st.selectbox("Исходный LP Komertia", options, index=options.index(remembered_lp) if remembered_lp in options else 0, key=profile + "source_lp")
                detected_costs = komertia_columns(raw)
                is_komertia = bool(detected_costs["final_unit"] or (detected_costs["quantity"] and detected_costs["total"]))
                use_komertia = st.checkbox("Окончательная закупка Komertia: Cena szt. (или Razem ÷ Ilość)", value=is_komertia, disabled=not is_komertia, key=profile + "komertia_costs")
                st.caption("В «Закупка PLN» записывается окончательная стоимость штуки с доставкой и таможней. Включённые расходы повторно не начисляются. Цены Allegro и комиссии сохраняются.")
                apply = st.form_submit_button("Загрузить в таблицу", type="primary")
            if apply:
                write(profile, {"mapping": mapping, "defaults": defaults, "rate": rate, "stock": stock, **identity_columns, "row_id": row_id, "source_lp": source_lp_column})
                if mapping["Товар"] != options[0]:
                    product_col = identity_columns["Produkt"] if identity_columns["Produkt"] != options[0] else mapping["Товар"]
                    raw = identify_rows(raw, product_col, identity_columns["Wariant"] if identity_columns["Wariant"] != options[0] else None, row_id if row_id != options[0] else source_lp_column if source_lp_column != options[0] else None, stock if stock != options[0] else None)
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
                    for metadata in ("Produkt", "Wariant", "_position_id", "source_order", "Ilość", "Komertia: status kosztów", "Komertia: uwagi"):
                        if metadata in raw:
                            frame[metadata] = raw[metadata]
                    if source_lp_column != options[0]:
                        source_lps = raw[source_lp_column].map(number)
                        if (source_lps <= 0).any() or (source_lps != source_lps.astype(int)).any():
                            errors.append("Исходные LP должны быть положительными целыми числами.")
                        else:
                            frame['source_row'] = source_lps.astype(int)
                    # Preserve source specifications so different models/colours/sizes cannot collapse.
                    for column in raw.columns:
                        normalized_column = str(column).strip().casefold()
                        if normalized_column in {"kolor", "color", "цвет", "rozmiar", "size", "размер", "model", "модель", "komplet", "комплектация", "zestaw"}:
                            frame[column] = raw[column].to_numpy()
                    frame = import_details(frame, raw, mapping)
                    frame["Закупка PLN"] *= rate
                    if use_komertia and not errors:
                        frame = apply_costs(frame, raw)
                    if errors:
                        st.error("Исправьте данные перед импортом: " + "; ".join(errors[:10]))
                    elif (frame["Комиссия %"] > 100).any():
                        st.error("Комиссия Allegro не может превышать 100%.")
                    else:
                        merged, skipped = product_duplicates.checked_import(frame, load_analysis())
                        if replace_analysis(merged):
                            st.success(f"Товары загружены. Обнаружено и пропущено дубликатов: {skipped}. Существующие поля сохранены.")
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
            st.info("Загрузить 29 позиций из ваших скриншотов? Нулевые остатки исключены. Общие расходы распределены по количеству. Названия сокращены как на снимках; строка Komertia указана отдельно. Существующие товары и правки сохраняются, повторные позиции пропускаются.")
        st.warning("Заменить текущий анализ демонстрационным примером?" if pending == "demo" else "Загрузить таблицу из скриншотов?" if pending == "screenshots" else "Удалить все товары из текущего анализа? Это действие нельзя отменить.")
        yes, no = st.columns(2)
        if yes.button("Подтвердить загрузку" if pending == "screenshots" else "Подтвердить замену" if pending == "demo" else "Подтвердить сброс"):
            if pending == "screenshots":
                target, skipped_duplicates = product_duplicates.checked_import(load_catalog(), load_analysis())
                st.session_state["import_duplicate_count"] = skipped_duplicates
            else:
                target = sample if pending == "demo" else pd.DataFrame(columns=INPUTS)
            if replace_analysis(target):
                st.rerun()
        if no.button("Отмена"):
            st.session_state.pop("pending_action", None)
            st.rerun()

if "products" not in st.session_state or st.session_state["products"].empty:
    st.info("Загрузите файл или откройте пример, чтобы начать анализ.")
    st.stop()

with settings_tab:
    if "import_duplicate_count" in st.session_state:
        st.success(f"Импорт: обнаружено и пропущено дубликатов: {st.session_state['import_duplicate_count']}.")
    with st.expander("Проверка дубликатов товаров"):
        try:
            duplicate_result = product_duplicates.render_review(st.session_state["products"])
            if duplicate_result is not None:
                deduplicated, removed = duplicate_result
                st.session_state["products"] = deduplicated
                st.session_state["analysis_expected_hash"] = deduplicated.attrs.get("analysis_hash")
                st.session_state["editor_revision"] = st.session_state.get("editor_revision", 0) + 1
                st.session_state["duplicate_success"] = f"Удалено повторных строк: {removed}. Заполненные данные сохранены."
                st.rerun()
            if st.session_state.get("duplicate_success"):
                st.success(st.session_state["duplicate_success"])
        except Exception as exc:
            st.error(str(exc))
    with st.expander("Импорт фотографий Komertia по исходным LP из ZIP"):
        photos_zip = st.file_uploader("ZIP с файлами Komertia_LP_01.png–Komertia_LP_38.png", type=["zip"], key="lp_photo_zip")
        st.caption("Фото сопоставляются по исходному LP Komertia, а не по текущему номеру строки. Названия, цены, расчёты и порядок товаров сохраняются.")
        if photos_zip is not None:
            try:
                manual_photo_mapping.render_manual_mapping(photos_zip.getvalue(), st.session_state["products"])
            except ValueError as exc:
                st.error(str(exc))
    if st.session_state.get("lp_photo_success"):
        st.success(st.session_state["lp_photo_success"])

from storage import ensure_ids
working = ensure_ids(enrich_details(st.session_state["products"]).drop(columns=["№"], errors="ignore"))
if "Produkt" not in working:
    working["Produkt"] = ""
if "Wariant" not in working:
    working["Wariant"] = ""
with settings_tab:
    show_expenses = st.checkbox("Дополнительные расходы товара", value=False)
    if show_expenses and not working.empty:
        expense_ids = working.loc[~working.apply(is_order_total, axis=1), '_position_id'].tolist()
        expense_labels = {row['_position_id']: original_label(row) for _, row in working.iterrows()}
        expense_position = st.selectbox("Товар для редактирования расходов", expense_ids, format_func=lambda item: expense_labels[item], key="expense_product")
        expense_row = working.loc[working['_position_id'].eq(expense_position)].iloc[0]
        with st.form("extra_expenses"):
            expense_values = {}
            for column in NUMERIC:
                if column not in ("Закупка PLN", "Цена Allegro PLN", "Комиссия %", "Комиссия PLN"):
                    expense_values[column] = st.number_input(column, min_value=0.0, value=float(number(expense_row[column])))
            save_expenses = st.form_submit_button("Сохранить расходы")
        if save_expenses:
            updated_expenses = working.copy()
            for column, value in expense_values.items():
                updated_expenses.loc[updated_expenses['_position_id'].eq(expense_position), column] = value
            if replace_analysis(updated_expenses):
                st.rerun()
with main_tab:
    st.subheader("Анализ прибыльности")
    order_labels = order_scope.order_labels(working)
    selected_order = "Все заказы"
    if order_labels.nunique() > 1:
        selected_order = st.selectbox("Заказ Komertia", ["Все заказы"] + list(dict.fromkeys(order_labels)))
    order_mask = order_labels.eq(selected_order) if selected_order != "Все заказы" else pd.Series(True,index=working.index)
    metrics = st.columns(4)
    metric_slots = [column.empty() for column in metrics]
    left, right = st.columns(2)
    search = left.text_input("Поиск по названию или SKU")
    statuses = right.multiselect("Статус", list(COLORS), default=list(COLORS))
    try:
        calculated = calculate(working, weak, landed_purchase=product_archive.enabled(working)).set_index("_position_id").reindex(working["_position_id"])
        calculated.index = working.index
        calculated = calculated.reset_index(drop=True)
    except (ValueError, TypeError) as exc:
        st.error(f"Проверьте значения в таблице: {exc}")
        calculated = working.copy()
        calculated["Статус"] = "Без цены"
        calculated["Прибыль PLN"] = float("nan")
        calculated["Маржа %"] = float("nan")
    product_rows = product_archive.active_mask(working)
    mask = calculated["Статус"].isin(statuses) & product_rows & order_mask
    if search:
        matches = pd.Series(False, index=working.index)
        for column in ("Produkt", "SKU", FULL_NAME, "Wariant"):
            if column in working:
                matches |= working[column].astype(str).str.contains(search, case=False, regex=False, na=False)
        mask &= matches
    editor_frame = working.copy()
    editor_frame["Партия"] = working["Партия"].fillna(order_labels) if "Партия" in working else order_labels

    for column in ("Прибыль PLN", "Маржа %", "Статус"):
        editor_frame[column] = calculated[column].to_numpy()
    if product_archive.enabled(working):
        editor_frame["Комиссия PLN"] = calculated["Комиссия всего PLN"].to_numpy()
    editor_frame.insert(0, "№", range(1, len(editor_frame) + 1))
    editor_frame = editor_frame.loc[mask].reset_index(drop=True)
    editor_frame[PHOTO] = editor_frame.apply(photo_enhancement.best_available_original, axis=1) if not editor_frame.empty else editor_frame[PHOTO]
    st.markdown("<style>.gdg-clip-region img{min-width:0!important;min-height:0!important;width:auto!important;height:auto!important;max-width:100%!important;max-height:70vh!important;object-fit:contain!important}</style>", unsafe_allow_html=True)
    st.subheader("Товары")
    st.caption(f"Показано: {len(editor_frame)} из {int(product_rows.sum())}")
    resolutions = [photo_enhancement.original_resolution(photo) for photo in editor_frame[PHOTO]]
    low_resolution = sum(1 for size in resolutions if size and max(size) < 800)
    if low_resolution:
        st.caption(f"Фото с низким исходным разрешением: {low_resolution}. Наведите на фото для просмотра оригинала и его размера; маленькие исходники не растягиваются.")
    column_order = ["№", PHOTO, "Produkt", "Wariant", "Партия", "Закупка PLN", "Цена Allegro PLN", "Комиссия %", "Комиссия PLN", "Прибыль PLN", "Маржа %"]
    config = {c: st.column_config.NumberColumn(c, min_value=0.0, max_value=100.0 if c == "Комиссия %" else None, format="%.2f", width="medium") for c in NUMERIC}
    sizes = widths(available_width())
    config["№"] = st.column_config.NumberColumn("№", width=sizes["№"], disabled=True, format="%d", pinned=True)
    config[PHOTO] = st.column_config.ImageColumn("Фото", width=sizes[PHOTO])
    config["Produkt"] = st.column_config.TextColumn("Produkt", width=sizes["Produkt"], disabled=True)
    config["Партия"] = st.column_config.TextColumn("Партия", width=120, disabled=True)
    config["Wariant"] = st.column_config.TextColumn("Wariant", width=sizes["Wariant"], disabled=True)
    for column, label in LABELS.items():
        config[column] = st.column_config.NumberColumn(label, width=sizes[column], format="%.2f",
            disabled=column in ("Прибыль PLN", "Маржа %"),
            min_value=None if column in ("Прибыль PLN", "Маржа %") else 0.0,
            max_value=100.0 if column == "Комиссия %" else None)
    config.update({c: None for c in editor_frame.columns if c not in column_order})
    filtered = not bool(mask.all())
    editor_key = f"editor_{st.session_state.get('editor_revision', 0)}"
    if filtered:
        import hashlib
        editor_key += "_" + hashlib.sha256(str((search, statuses, selected_order)).encode()).hexdigest()[:12]
    visible_edits = st.data_editor(profitability_style(editor_frame), column_order=column_order, column_config=config,
        disabled=(["Комиссия PLN"] if product_archive.enabled(working) else []) + ["№", PHOTO, "Produkt", "Wariant", "Партия", "Прибыль PLN", "Маржа %", "Статус", "_position_id"],
        num_rows="fixed" if filtered else "dynamic", hide_index=True, row_height=38, height=600, width="stretch", key=editor_key)
    changed = visible_edits.drop(columns=["№", "Прибыль PLN", "Маржа %", "Статус"], errors="ignore")
    if "Партия" not in working:
        changed = changed.drop(columns=["Партия"], errors="ignore")
    changed = photo_enhancement.restore_original_photos(changed, working)
    if product_archive.enabled(working):
        original_commissions = working.set_index("_position_id")["Комиссия PLN"]
        changed["Комиссия PLN"] = changed["_position_id"].map(original_commissions)
    if filtered:
        edited = working.copy()
        for _, row in changed.iterrows():
            location = edited["_position_id"].eq(row["_position_id"])
            for column in working.columns:
                if column in row:
                    edited.loc[location, column] = row[column]
    else:
        edited = changed.reset_index(drop=True)
    try:
        save_analysis(edited)
        st.session_state["products"] = edited.copy()
        show_saved()
    except Exception as exc:
        save_indicator.error(f"Есть несохранённые изменения · ошибка сохранения: {exc}")
    if len(edited) != len(working):
        if replace_analysis(edited):
            st.rerun()
    if not edited.equals(working):
        st.session_state["editor_revision"] = st.session_state.get("editor_revision", 0) + 1
        st.rerun()
    if edited.empty:
        st.info("Добавьте товар.")
    else:
        try:
            result = calculate(edited.loc[product_archive.active_mask(edited) & order_mask], weak, landed_purchase=product_archive.enabled(edited))
            metric_slots[0].metric("Товаров", len(result))
            metric_slots[1].metric("Выгодных", int((result["Статус"] == "Выгодный").sum()))
            metric_slots[2].metric("Убыточных", int((result["Статус"] == "Убыточный").sum()))
            metric_slots[3].metric("Без цены", int((result["Статус"] == "Без цены").sum()))
            if product_archive.enabled(edited):
                st.dataframe(product_archive.totals(result), hide_index=True)
                if result["Цена Allegro PLN"].map(number).eq(0).any():
                    st.caption("Итоги рассчитаны только для товаров с ценой Allegro. Для новых позиций укажите цену и комиссию категории; нули означают, что данные ещё не заданы.")
                if order_labels.nunique() == 1 and len(result) != 21:
                    st.warning(f"С заполненной ценой Allegro осталось {len(result)} товаров вместо ожидаемых 21. Цены не изменены; остальные записи доступны в архиве.")
            st.download_button("Экспорт полного анализа в Excel", export_excel(result, weak, landed_purchase=product_archive.enabled(edited)), "allegro-analysis.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        except (ValueError, TypeError) as exc:
            st.error(f"Проверьте значения в таблице: {exc}")

with settings_tab:
    with st.expander("Архив товаров"):
        if st.session_state.get("archive_notice"):
            st.info(st.session_state["archive_notice"])
        archived_rows = edited.loc[~product_archive.active_mask(edited) & ~edited.apply(is_order_total, axis=1)]
        st.caption(f"В архиве: {len(archived_rows)}. Все {len(edited)} исходных записей сохраняются в базе.")
        if not archived_rows.empty:
            st.dataframe(archived_rows[[c for c in (PHOTO, "Produkt", "Wariant", "Закупка PLN", "Цена Allegro PLN", "_position_id") if c in archived_rows]], hide_index=True, column_config={PHOTO: st.column_config.ImageColumn("Фото")})
    st.subheader("Фото и исходные данные Komertia")
    st.caption("Оригинальные Produkt и Wariant сохранены без перевода.")
    from storage import ensure_ids
    photo_frame = ensure_ids(edited)
    photo_frame = photo_frame.loc[~photo_frame.apply(is_order_total, axis=1)].reset_index(drop=True)
    photo_event = photo_grid(photo_frame, st.session_state.get("photo_error", ""))
    if photo_event and photo_event.get("event_id") != st.session_state.get("last_photo_event"):
        try:
            updated = apply_photo_event(ensure_ids(edited), photo_event)
            if replace_analysis(updated):
                st.session_state["last_photo_event"] = photo_event["event_id"]
                st.session_state.pop("photo_error", None)
                st.rerun()
        except ValueError as exc:
            st.session_state["last_photo_event"] = photo_event.get("event_id")
            st.session_state["photo_error"] = str(exc)
            st.error(str(exc))
    if not edited.empty:
        with st.expander("Фото и исходные данные Komertia"):
            from storage import ensure_ids
            detail_frame = ensure_ids(edited)
            detail_frame = detail_frame.loc[~detail_frame.apply(is_order_total, axis=1)].reset_index(drop=True)
            positions = list(detail_frame['_position_id'])
            labels = {row['_position_id']: f"{i + 1}. {original_label(row) or 'Brak nazwy w danych źródłowych'}" for i, row in detail_frame.iterrows()}
            selected = st.selectbox("Товар и вариант", positions, format_func=lambda item: labels[item], key="detail_position")
            row_index = positions.index(selected)
            row = detail_frame.iloc[row_index]
            st.text("Оригинальный Produkt: " + str(row.get("Produkt", "")))
            st.text("Оригинальный Wariant: " + str(row.get("Wariant", "")))
            with st.form("details_" + selected + "_" + str(st.session_state.get("editor_revision", 0))):
                name = st.text_area(FULL_NAME, value=row[FULL_NAME], help="Вставьте оригинальное полное название. Пустое поле остаётся пустым.")
                photo = st.file_uploader(PHOTO, type=["png", "jpg", "jpeg", "webp"], help="Оригинальное фото до 5 МБ; хранится вместе с товаром в существующей базе.")
                save_details = st.form_submit_button("Сохранить фото и название")
            if save_details:
                try:
                    detail_frame.loc[row_index, FULL_NAME] = name
                    if photo is not None:
                        detail_frame.loc[row_index, PHOTO] = uploaded_photo(photo.getvalue())
                    combined = ensure_ids(edited).copy()
                    selected_row = detail_frame.iloc[row_index]
                    for column in detail_frame.columns:
                        combined.loc[combined['_position_id'].eq(selected), column] = selected_row[column]
                    if replace_analysis(combined):
                        st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.download_button("Скачать резервную копию Excel", backup_excel(edited), "allegro-backup.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", help="Рабочие поля и постоянные идентификаторы. Позволяет восстановить цены и комиссии после пересборки.")
    photo_enhancement.render_enhancement(ensure_ids(edited))
