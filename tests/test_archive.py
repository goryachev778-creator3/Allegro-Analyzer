from io import BytesIO
from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from analyzer import INPUTS, calculate, export_excel
from komertia_details import PHOTO
from product_archive import prepare, active_mask, totals, TARGETS, FLAG
import storage


def order():
    rows=[]
    for n in range(1,26):
        rows.append(dict.fromkeys(INPUTS,0) | {'Товар':f'Produkt {n}', 'Produkt':f'Produkt {n}', 'Wariant':'czarny' if n%2 else 'biały',
            'SKU':'', '_position_id':f'item-{n}', PHOTO:'', 'Закупка PLN':10., 'Доставка PLN':8., 'Пошлина %':20.,
            'Оформление PLN':2., 'Невозмещаемый НДС PLN':3., 'Доп. расходы PLN':1.,
            'Цена Allegro PLN':0. if n in TARGETS else 30., 'Комиссия %':10., 'Комиссия PLN':7.})
    return pd.DataFrame(rows)


def test_archive_preserves_every_original_field_and_order():
    original=order()
    archived,notice=prepare(original)
    assert not notice
    pd.testing.assert_frame_equal(original,archived[original.columns])
    assert list(archived.loc[archived[FLAG], '_position_id']) == ['item-12','item-13','item-15','item-17']
    assert active_mask(archived).sum()==21
    reordered=archived.iloc[::-1].reset_index(drop=True)
    repeated,notice=prepare(reordered)
    pd.testing.assert_frame_equal(repeated,reordered)
    assert active_mask(repeated).sum()==21


def test_unsafe_number_mapping_does_not_archive():
    frame=order()
    frame.loc[11,'Цена Allegro PLN']=50
    result,notice=prepare(frame)
    assert notice
    pd.testing.assert_frame_equal(result,frame)
    result,notice=prepare(frame.iloc[:-1])
    assert notice and FLAG not in result


def test_landed_formula_totals_excel_and_unchanged_input():
    frame,_=prepare(order())
    original=frame.copy(deep=True)
    result=calculate(frame.loc[active_mask(frame)],landed_purchase=True)
    assert (result['Комиссия всего PLN']==3).all()
    assert (result['Прибыль PLN']==16).all()
    assert result['Маржа %'].iloc[0]==pytest.approx(16/30*100)
    assert totals(result).iloc[0]['Прибыль PLN']==336
    assert totals(result).iloc[0]['Маржа %']==pytest.approx(16/30*100)
    workbook=pd.ExcelFile(BytesIO(export_excel(result,landed_purchase=True)))
    assert 'Итоги' in workbook.sheet_names
    assert len(pd.read_excel(workbook,sheet_name='Анализ'))==21
    pd.testing.assert_frame_equal(original,frame)


def test_streamlit_restart_preserves_25_database_rows_and_21_active():
    storage.save_analysis(order())
    app_path=str(Path(__file__).resolve().parents[1]/'app.py')
    app=AppTest.from_file(app_path).run()
    assert not app.exception
    assert app.metric[0].value=='21'
    table=next(d.value for d in app.dataframe if '№' in d.value.columns)
    assert len(table)==21
    assert (table['Комиссия PLN']==3).all()
    saved=storage.load_analysis()
    assert len(saved)==25
    assert (saved['Комиссия PLN']==7).all()
    pd.testing.assert_frame_equal(order(),saved[order().columns],check_dtype=False)
    restarted=AppTest.from_file(app_path).run()
    assert not restarted.exception
    assert restarted.metric[0].value=='21'
    assert len(storage.load_analysis())==25
