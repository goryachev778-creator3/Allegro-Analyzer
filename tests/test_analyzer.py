from io import BytesIO
import pandas as pd
import pytest
from openpyxl import load_workbook
from analyzer import INPUTS, calculate, export_excel, number, read_upload


def test_cost_profit_and_ranking():
    frame = pd.DataFrame([
        ["Loss", "1", 100, 20, 10, 5, 3, 0, 100, 10, 2],
        ["Profit", "2", 100, 20, 10, 5, 3, 0, 200, 10, 2],
    ], columns=INPUTS)
    result = calculate(frame)
    good = result.iloc[0]
    assert good["Товар"] == "Profit"
    assert good["Пошлина PLN"] == 12
    assert good["Себестоимость PLN"] == 140
    assert good["Прибыль PLN"] == 38
    assert good["Маржа %"] == 19
    assert good["ROI %"] == pytest.approx(38 / 140 * 100)
    assert list(result["Статус"]) == ["Выгодный", "Убыточный"]


def test_empty_price_zero_cost_and_threshold():
    frame = pd.DataFrame([
        ["Pending", "", 10, 0, 0, 0, 0, 0, 0, 0, 0],
        ["Free", "", 0, 0, 0, 0, 0, 0, 100, 0, 0],
        ["Weak", "", 90, 0, 0, 0, 0, 0, 100, 0, 0],
    ], columns=INPUTS)
    result = calculate(frame).set_index("Товар")
    assert result.loc["Pending", "Статус"] == "Без цены"
    assert pd.isna(result.loc["Pending", "Маржа %"])
    assert pd.isna(result.loc["Free", "ROI %"])
    assert result.loc["Weak", "Статус"] == "Слабая прибыль"


@pytest.mark.parametrize("value, expected", [("1 234,50", 1234.5), ("1,234.50", 1234.5), ("1.234,50", 1234.5), ("", 0)])
def test_number(value, expected):
    assert number(value) == expected


@pytest.mark.parametrize("value", ["abc", "-1", "inf", "NaN"])
def test_invalid_numbers(value):
    with pytest.raises(ValueError):
        number(value)


def test_import_export_roundtrip_and_formula_safety():
    source = 'Товар;SKU;Цена\nЧехол;001;12,50\n'.encode('utf-8-sig')
    raw = read_upload(source, 'komertia.csv')
    assert raw.iloc[0]['SKU'] == '001'
    assert number(raw.iloc[0]['Цена']) == 12.5
    result = calculate(pd.DataFrame([["=1+1", "001", 10, 0, 0, 0, 0, 0, 20, 0, 0]], columns=INPUTS))
    data = export_excel(result)
    workbook = load_workbook(BytesIO(data))
    assert workbook['Анализ']['A2'].data_type == 's'
    assert workbook['Анализ']['A2'].value == '=1+1'
    assert workbook['Анализ']['A2'].fill.fgColor.rgb == '00DCFCE7'
    loaded = read_upload(data, 'analysis.xlsx')
    assert loaded.iloc[0]['SKU'] == '001'
    assert calculate(loaded[INPUTS]).iloc[0]['Прибыль PLN'] == 10
