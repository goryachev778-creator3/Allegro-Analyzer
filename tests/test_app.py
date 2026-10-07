from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def test_demo_workflow_and_margin_setting():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert [m.value for m in app.metric] == ['3', '1', '1', '0']
    assert len(app.dataframe) == 2
    app.sidebar.number_input[0].set_value(40.0).run()
    assert not app.exception
    assert app.metric[1].value == '0'
    app.text_input[0].set_value('ORG-01').run()
    assert not app.exception
    assert len(app.dataframe[1].value) == 1


def test_editor_autosaves_reload_and_demo_confirmation():
    from storage import load_analysis
    app = AppTest.from_file(APP).run()
    app.button[0].click().run()
    app.session_state['editor_1'] = {
        'edited_rows': {0: {'Цена Allegro PLN': 123.0, 'Комиссия %': 17.0}},
        'added_rows': [], 'deleted_rows': [],
    }
    app.run()
    assert not app.exception
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 123
    refreshed = AppTest.from_file(APP).run()
    assert not refreshed.exception
    assert refreshed.dataframe[0].value.iloc[0]['Цена Allegro PLN'] == 123
    refreshed.button[0].click().run()
    assert not refreshed.exception
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 123
    next(b for b in refreshed.button if b.label == 'Отмена').click().run()
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 123
    next(b for b in refreshed.button if b.label == 'Сбросить текущий анализ').click().run()
    assert not load_analysis().empty
    next(b for b in refreshed.button if b.label == 'Подтвердить сброс').click().run()
    assert not refreshed.exception
    assert load_analysis().empty
