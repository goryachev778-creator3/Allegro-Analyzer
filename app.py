from io import BytesIO
import pandas as pd
import streamlit as st
from storage import load_analysis, save_analysis, merge_import, profile_key, read, write, filter_stock, identify_rows
from analyzer import INPUTS, NUMERIC, COLORS, calculate, export_excel, number, read_upload

st.set_page_config(page_title="Allegro Analyzer", page_icon="📊", layout="wide")
st.title("Allegro Analyzer")
st.caption("От закупки в Китае до прибыли на Allegro · все расчёты на одну единицу товара")
save_indicator = st.empty()
try:
    if "products" not in st.session_state:
        restored = load_analysis()
        if restored is not None:
            st.session_state["products"] = restored
    save_indicator.success("Сохранено")
except Exception as exc:
    save_indicator.error(f"Есть несохранённые изменения · хранилище недоступно: {exc}")
    st.stop()


def replace_analysis(frame):
    try:
        save_analysis(frame)
    except Exception as exc:
        save_indicator.error(f"Есть несохранённые изменения · ошибка сохранения: {exc}")
        return False
    st.session_state["products"] = frame.copy()
    st.session_state["editor_revision"] = st.session_state.get("editor_revision", 0) + 1
    st.session_state.pop("pending_action", None)
    save_indicator.success("Сохранено")
    return True

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
                frame["Закупка PLN"] *= rate
                if errors:
                    st.error("Исправьте данные перед импортом: " + "; ".join(errors[:10]))
                elif (frame["Комиссия %"] > 100).any():
                    st.error("Комиссия Allegro не может превышать 100%.")
                else:
                    merged = merge_import(frame, load_analysis())
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

pending = st.session_state.get("pending_action")
if pending:
    st.warning("Заменить текущий анализ демонстрационным примером?" if pending == "demo" else "Удалить все товары из текущего анализа? Это действие нельзя отменить.")
    yes, no = st.columns(2)
    if yes.button("Подтвердить замену" if pending == "demo" else "Подтвердить сброс"):
        if replace_analysis(sample if pending == "demo" else pd.DataFrame(columns=INPUTS)):
            st.rerun()
    if no.button("Отмена"):
        st.session_state.pop("pending_action", None)
        st.rerun()

if "products" not in st.session_state or st.session_state["products"].empty:
    st.info("Загрузите файл или откройте пример, чтобы начать анализ.")
    st.stop()

st.subheader("Товары и расходы")
st.caption("Введите цены продажи и комиссии. Можно добавить или удалить строки. Расчёты обновляются автоматически; выгрузка содержит текущий анализ.")
config = {c: st.column_config.NumberColumn(c, min_value=0.0, max_value=100.0 if c == "Комиссия %" else None, format="%.2f") for c in NUMERIC}
edited = st.data_editor(st.session_state["products"], column_config={**config, "_position_id": None}, disabled=[c for c in ("Produkt", "Wariant", "_position_id") if c in st.session_state["products"]], num_rows="dynamic", hide_index=True, width="stretch", key=f"editor_{st.session_state.get('editor_revision', 0)}")
try:
    save_analysis(edited)
    save_indicator.success("Сохранено")
except Exception as exc:
    save_indicator.error(f"Есть несохранённые изменения · ошибка сохранения: {exc}")
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
    visible = visible[visible["Товар"].str.contains(search, case=False, regex=False, na=False) | visible["SKU"].str.contains(search, case=False, regex=False, na=False)]
summary = ["Товар", "SKU", "Статус", "Себестоимость PLN", "Цена Allegro PLN", "Комиссия всего PLN", "Прибыль PLN", "Маржа %", "ROI %"]
if "Wariant" in visible:
    summary.insert(2, "Wariant")
def row_style(row):
    return [f"background-color: #{COLORS[row['Статус']]}; color: #172554" for _ in row]
st.dataframe(visible[summary].style.apply(row_style, axis=1).format({c: "{:.2f}" for c in summary if c not in ("Товар", "SKU", "Wariant", "Статус")}, na_rep="—"), hide_index=True, width="stretch")
st.download_button("Экспорт полного анализа в Excel", export_excel(result, weak), "allegro-analysis.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", help="Экспортируются все товары, включая скрытые фильтром, расходы и методика.")
st.caption("Изменения автоматически сохраняются в локальную SQLite и восстанавливаются после обновления страницы и перезапуска приложения. Это один общий рабочий анализ для этой установки; экспорт Excel сохраняет отдельную копию.")
