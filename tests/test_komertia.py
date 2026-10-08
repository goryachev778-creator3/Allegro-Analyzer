import pandas as pd
import pytest
from analyzer import INPUTS, calculate
from komertia import apply_costs


def test_complete_komertia_cost_per_unit_no_double_duty():
    raw = pd.DataFrame({'Ilość': [50], 'Cena': [1.15], 'Wartość': [57.68], 'Koszty dod.': [16.96], 'Tr.+Cło': [56.05], 'Odprawa+HS': [15], 'Razem': [145.70]})
    frame = pd.DataFrame([['Item', '1', 1.15, 0, 6, 0, 0, 0, 12.67, 11, 0]], columns=INPUTS)
    updated = apply_costs(frame, raw)
    row = calculate(updated).iloc[0]
    assert row['Себестоимость PLN'] == pytest.approx(2.914)
    assert row['Пошлина PLN'] == 0
    assert row['Цена Allegro PLN'] == 12.67
    assert row['Комиссия %'] == 11
    assert row['Прибыль PLN'] == pytest.approx(12.67 - 2.914 - 12.67 * .11)
