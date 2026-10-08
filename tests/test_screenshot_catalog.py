import pytest
from analyzer import calculate
from screenshot_catalog import load_catalog


def test_screenshot_totals_and_restored_prices():
    frame = load_catalog()
    assert len(frame) == 29
    assert frame['Ilość'].sum() == 648
    assert (frame['Ilość'] > 0).all()
    assert frame['_position_id'].nunique() == 29
    result = calculate(frame)
    # Displayed line totals differ from the displayed grand total by 0.01 PLN.
    assert (result['Себестоимость PLN'] * result['Ilość']).sum() == pytest.approx(4675.35)
    first = result.set_index('source_row').loc[1]
    assert first['Себестоимость PLN'] == pytest.approx(2.914)
    assert first['Цена Allegro PLN'] == 12.67
    assert first['Комиссия %'] == 11
    grouped = result[result['source_row'].isin([17,18,19])]
    assert (grouped['Себестоимость PLN'] * grouped['Ilość']).sum() == pytest.approx(167.20)


def test_screenshot_button_loads_working_analysis():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from storage import load_analysis
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    next(b for b in app.button if b.label == 'Загрузить товары из скриншотов Komertia').click().run()
    next(b for b in app.button if b.label == 'Подтвердить загрузку').click().run()
    assert not app.exception
    assert len(load_analysis()) == 29
    assert load_analysis().iloc[0]['Цена Allegro PLN'] == 12.67
