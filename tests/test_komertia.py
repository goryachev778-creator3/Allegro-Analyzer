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


def test_final_cena_szt_overrides_raw_costs_without_double_counting():
    raw = pd.DataFrame({'Cena szt.': [7.67], 'Cena': [4.75], 'Ilość': [30], 'Razem': [229.97]})
    frame = pd.DataFrame([['Item', '1', 4.75, 2, 10, 3, 4, 5, 20, 11, 1]], columns=INPUTS)
    row = calculate(apply_costs(frame, raw)).iloc[0]
    assert row['Закупка PLN'] == 7.67
    assert row['Себестоимость PLN'] == 7.67
    assert row['Прибыль PLN'] == pytest.approx(20 - 7.67 - 2.2 - 1)


def test_saved_cost_migration_is_idempotent_and_preserves_sale_prices():
    from komertia import migrate_screenshot_costs
    frame = pd.DataFrame([['Item', '1', 1.15, 1.12, 0, .3, .344, 0, 12.67, 11, 0]], columns=INPUTS)
    frame['_position_id'] = 'komertia-screenshot-oct2026:1'
    migrated = migrate_screenshot_costs(frame)
    assert migrated.iloc[0]['Закупка PLN'] == pytest.approx(2.914)
    assert migrated.iloc[0]['Цена Allegro PLN'] == 12.67
    assert migrated.iloc[0]['Комиссия %'] == 11
    assert migrate_screenshot_costs(migrated).equals(migrated)
    assert calculate(migrated).iloc[0]['Прибыль PLN'] == pytest.approx(calculate(frame).iloc[0]['Прибыль PLN'])
