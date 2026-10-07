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
    merged = merge_import(duplicate, frame)
    assert len(merged) == 3
    assert merged['_position_id'].nunique() == 3
    save_analysis(pd.DataFrame(columns=INPUTS))
    assert load_analysis().empty


def test_komertia_variants_duplicate_skus_reorder_and_zero_stock():
    from storage import identify_rows
    raw = pd.DataFrame({
        'Produkt': ['A1632'] * 4,
        'Wariant': ['Red', 'Blue', 'Red', 'Zero'],
        'SKU': ['same'] * 4,
        'Kod wariantu': ['R1', 'B1', 'R2', 'Z1'],
        'Ilość': ['2', '3', '5', '0'],
    })
    def imported(source):
        tagged = identify_rows(source, 'Produkt', 'Wariant', stock_column='Ilość')
        tagged, _ = filter_stock(tagged, 'Ilość')
        rows = pd.concat([products().iloc[[0]]] * len(tagged), ignore_index=True)
        rows['Товар'] = 'A1632'
        rows['SKU'] = 'same'
        for col in ('Produkt', 'Wariant', '_position_id'):
            rows[col] = tagged[col]
        return rows
    initial = merge_import(imported(raw), None)
    assert len(initial) == 3
    assert initial['_position_id'].nunique() == 3
    initial['Цена Allegro PLN'] = [111, 222, 333]
    initial['Комиссия %'] = [11, 22, 33]
    initial['Комиссия PLN'] = [1, 2, 3]
    save_analysis(initial)
    reordered = raw.iloc[[2, 1, 3, 0]].copy()
    reordered.loc[0, 'Ilość'] = '7'
    restored = merge_import(imported(reordered), load_analysis())
    assert list(restored['Цена Allegro PLN']) == [333, 222, 111]
    assert list(restored['Комиссия %']) == [33, 22, 11]
    assert list(restored['Комиссия PLN']) == [3, 2, 1]
    assert 'Zero' not in list(restored['Wariant'])


def test_identical_combination_and_stock_filter_have_stable_distinct_ids():
    from storage import identify_rows
    raw = pd.DataFrame({'Produkt': ['A1632'] * 3, 'Wariant': ['Red'] * 3, 'Ilość': [0, 2, 3]})
    first = identify_rows(raw, 'Produkt', 'Wariant', stock_column='Ilość')
    filtered, _ = filter_stock(first, 'Ilość')
    raw['Ilość'] = [1, 2, 3]
    second = identify_rows(raw, 'Produkt', 'Wariant', stock_column='Ilość')
    assert first['_position_id'].nunique() == 3
    assert list(filtered['_position_id']) == list(second['_position_id'].iloc[1:])
