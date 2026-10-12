from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def test_demo_workflow_and_margin_setting():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    next(b for b in app.button if b.label == 'Открыть демонстрационный пример').click().run()
    assert not app.exception
    assert [m.value for m in app.metric] == ['3', '1', '1', '0']
    assert len(app.dataframe) == 1
    app.sidebar.number_input[0].set_value(40.0).run()
    assert not app.exception
    assert app.metric[1].value == '0'
    app.text_input[0].set_value('ORG-01').run()
    assert not app.exception
    assert list(app.dataframe[0].value['SKU']) == ['ORG-01']


def test_editor_autosaves_reload_and_demo_confirmation():
    from storage import load_analysis
    app = AppTest.from_file(APP).run()
    next(b for b in app.button if b.label == 'Открыть демонстрационный пример').click().run()
    app.session_state['editor_1'] = {
        'edited_rows': {0: {'Цена Allegro PLN': 123.0, 'Комиссия %': 17.0}},
        'added_rows': [], 'deleted_rows': [],
    }
    app.run()
    assert not app.exception
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 123
    assert load_analysis().iloc[0]['Комиссия %'] == 17
    refreshed = AppTest.from_file(APP).run()
    assert not refreshed.exception
    assert refreshed.dataframe[0].value.iloc[0]['Цена Allegro PLN'] == 123
    next(b for b in refreshed.button if b.label == 'Открыть демонстрационный пример').click().run()
    assert not refreshed.exception
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 123
    next(b for b in refreshed.button if b.label == 'Отмена').click().run()
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 123
    next(b for b in refreshed.button if b.label == 'Сбросить текущий анализ').click().run()
    assert not load_analysis().empty
    next(b for b in refreshed.button if b.label == 'Подтвердить сброс').click().run()
    assert not refreshed.exception
    assert load_analysis().empty


def test_opening_preserves_all_existing_rows_and_ids():
    import pandas as pd
    from analyzer import INPUTS
    from storage import save_analysis, load_analysis
    rows = pd.DataFrame([
        ['Item', 'same', 10, 0, 0, 0, 0, 0, 30, 10, 0],
        ['Item', 'same', 10, 0, 0, 0, 0, 0, 30, 10, 0],
        ['Item', 'same', 10, 0, 0, 0, 0, 0, 30, 10, 0],
        ['Zero', 'zero', 10, 0, 0, 0, 0, 0, 30, 10, 0],
    ], columns=INPUTS)
    rows['Wariant'] = ['Red', 'Red', 'Blue', 'Red']
    rows['_position_id'] = ['r1', 'r2', 'b1', 'z1']
    rows['Ilość'] = [2, 2, 2, 0]
    save_analysis(rows)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert list(load_analysis()['_position_id']) == ['r1', 'r2', 'b1', 'z1']
    assert len(app.dataframe[0].value) == 4


def test_display_order_numbers_and_saved_values():
    app = AppTest.from_file(APP).run()
    next(b for b in app.button if b.label == 'Открыть демонстрационный пример').click().run()
    assert not app.exception
    displayed = app.dataframe[0].value
    assert list(displayed['№']) == [1, 2, 3]
    assert list(displayed['Produkt']) == list(displayed['Товар'])
    import json
    order = list(app.dataframe[0].proto.column_order)
    assert order[:6] == ['№', 'Фото Komertia', 'Nazwa produktu', 'Закупка PLN', 'Цена Allegro PLN', 'Комиссия %']
    assert not {'Produkt', 'Wariant', 'Товар', 'Полное название Komertia'} & set(order)
    app.session_state['editor_1'] = {'edited_rows': {0: {'Цена Allegro PLN': 150.0, 'Комиссия %': 9.0}}, 'added_rows': [], 'deleted_rows': []}
    app.run()
    assert not app.exception
    refreshed = AppTest.from_file(APP).run()
    assert refreshed.dataframe[0].value.iloc[0]['Цена Allegro PLN'] == 150
    assert refreshed.dataframe[0].value.iloc[0]['Комиссия %'] == 9
    assert list(refreshed.dataframe[0].value['№']) == [1, 2, 3]



def test_single_main_table_filters_preserve_hidden_rows_and_prices():
    from screenshot_catalog import load_catalog
    from storage import save_analysis, load_analysis
    from komertia_details import NAME_PL, PHOTO, enrich_details
    import pandas as pd
    rows = enrich_details(load_catalog().iloc[:26])
    rows[PHOTO] = ['https://example.com/' + str(i) + '.png' for i in range(26)]
    rows[NAME_PL] = ['Produkt testowy ' + str(i) for i in range(26)]
    rows['SKU'] = ['sku-' + str(i) for i in range(26)]
    save_analysis(rows)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert [t.label for t in app.tabs] == ['Главная', 'Настройки и импорт']
    assert len(app.dataframe) == 1
    order = list(app.dataframe[0].proto.column_order)
    assert 'Прибыль PLN' in order and 'Маржа %' in order
    assert len(app.dataframe[0].value) == 26
    before = load_analysis()
    next(t for t in app.text_input if t.label == 'Поиск по названию или SKU').set_value('sku-25').run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    pd.testing.assert_frame_equal(load_analysis(), before)
    key = next(k for k in app.session_state.filtered_state if k.startswith('editor_') and '_0_' in k)
    app.session_state[key] = {'edited_rows': {0: {'Цена Allegro PLN': 99.0}}, 'added_rows': [], 'deleted_rows': []}
    app.run()
    assert not app.exception
    saved = load_analysis()
    assert len(saved) == 26
    assert saved['_position_id'].tolist() == before['_position_id'].tolist()
    assert saved[PHOTO].tolist() == before[PHOTO].tolist()
    assert saved[NAME_PL].tolist() == before[NAME_PL].tolist()
    assert saved.iloc[25]['Цена Allegro PLN'] == 99
    assert saved.iloc[:25]['Цена Allegro PLN'].tolist() == before.iloc[:25]['Цена Allegro PLN'].tolist()
