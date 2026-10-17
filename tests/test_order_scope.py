import pandas as pd
import pytest
from analyzer import INPUTS
from order_scope import order_labels
from product_archive import active_mask, MODE
from komertia_details import original_record
from komertia_photos import auto_photo_preview
from product_duplicates import checked_import


def item(order,lp,name):
    return dict.fromkeys(INPUTS,0.)|{'Товар':name,'SKU':'','Produkt':name,'Wariant':'black',
      'source_order':order,'source_row':lp,'_position_id':f'{order}:{lp}',MODE:True,'Ilość':2}


def test_new_order_visible_without_price_and_stable_on_reimport():
    old=pd.DataFrame([item('A1632',1,'old')])
    new=pd.DataFrame([item('NEW-ORDER',1,'new')])
    merged,skipped=checked_import(new,old)
    assert len(merged)==2 and skipped==0
    assert list(active_mask(merged))==[False,True]
    repeated,skipped=checked_import(new,merged)
    assert len(repeated)==2 and skipped==1
    assert original_record(new.iloc[0])['Produkt']=='new'


def test_photo_lp_is_scoped_to_order():
    frame=pd.DataFrame([item('A1632',1,'old'),item('NEW-ORDER',1,'new')])
    with pytest.raises(ValueError,match='заказ'):
        auto_photo_preview(frame,{1:'photo'})
    preview=auto_photo_preview(frame,{1:'photo'},scope_order='NEW-ORDER')
    assert [r['position_id'] for r in preview['matches']]==['NEW-ORDER:1']
    assert list(order_labels(frame))==['A1632','NEW-ORDER']
