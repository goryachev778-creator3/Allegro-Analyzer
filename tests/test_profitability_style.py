from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from analyzer import INPUTS
from storage import save_analysis, load_analysis


def test_editor_receives_three_colours_and_keeps_inputs():
    rows=[]
    for index,price in enumerate((30.,11.,5.)):
        rows.append(dict.fromkeys(INPUTS,0) | {'Товар':f'Produkt {index}', 'Produkt':f'Produkt {index}',
            'Wariant':'czarny', '_position_id':f'p{index}', 'SKU':'', 'Закупка PLN':10., 'Цена Allegro PLN':price})
    source=pd.DataFrame(rows)
    save_analysis(source)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
    assert not app.exception
    table=next(d for d in app.dataframe if '№' in d.value.columns)
    css=table.proto.arrow_data.styler.styles
    for color in ('DCFCE7','FEF3C7','FEE2E2'):
        assert color in css
    pd.testing.assert_frame_equal(source,load_analysis()[source.columns],check_dtype=False)
