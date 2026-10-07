from io import BytesIO
import pandas as pd
import pytest
from analyzer import INPUTS, read_upload
from storage import save_analysis, load_analysis, merge_import, profile_key, read, write, filter_stock


def products():
    return pd.DataFrame([
        ['Item', '001', 10, 2, 0, 0, 0, 0, 0, 0, 0],
        ['No SKU', '', 5, 0, 0, 0, 0, 0, 0, 0, 0],
    ], columns=INPUTS)


def test_excel_edit_reload_and_reimport():
    output = BytesIO()
    products().to_excel(output, index=False)
    imported = read_upload(output.getvalue(), 'komertia.xlsx')[INPUTS]
    edited = imported.copy()
    edited.loc[0, ['Цена Allegro PLN', 'Комиссия %', 'Комиссия PLN', 'Доставка PLN']] = [99, 12, 3, 8]
    edited.loc[1, 'Цена Allegro PLN'] = 44
    save_analysis(edited)
    # New connection, independent of any Streamlit session.
    restored = load_analysis()
    assert restored.iloc[0]['Цена Allegro PLN'] == 99
    assert restored.iloc[1]['Цена Allegro PLN'] == 44
    merged = merge_import(imported, restored)
    assert merged.iloc[0]['Доставка PLN'] == 8
    assert merged.iloc[0]['Комиссия %'] == 12
    assert merged.iloc[0]['Комиссия PLN'] == 3
    assert merged.iloc[1]['Цена Allegro PLN'] == 44
    save_analysis(merged)
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 99


def test_new_items_zero_stock_and_mapping():
    raw = products()
    raw['Ilość'] = ['0', '2']
    filtered, skipped = filter_stock(raw, 'Ilość')
    assert skipped == 1
    assert list(filtered['Товар']) == ['No SKU']
    key = profile_key('komertia.xlsx', 'Sheet1', raw.columns)
    settings = {'mapping': {'Товар': 'Товар'}, 'stock': 'Ilość', 'rate': 4.1}
    write(key, settings)
    assert read(key) == settings
    assert read(profile_key('other.xlsx', 'Sheet1', raw.columns)) is None
    merged = merge_import(filtered[INPUTS], products())
    assert list(merged['Товар']) == ['No SKU']


def test_duplicates_not_silently_merged_and_reset():
    frame = products()
    duplicate = pd.concat([frame, frame.iloc[[0]]])
    with pytest.raises(ValueError, match='Повторяющиеся'):
        merge_import(duplicate, frame)
    save_analysis(pd.DataFrame(columns=INPUTS))
    assert load_analysis().empty
