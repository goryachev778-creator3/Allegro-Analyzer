import base64,json,zlib
import pandas as pd
import pytest
from private_link_import import decode_quote,save_quote
import storage


def token(rows=None):
    data={'order':'NEW-ORDER','rows':rows if rows is not None else [[1,'Original name','black',2,'12.345'],[2,'Skipped','white',0,'3']]}
    return base64.urlsafe_b64encode(zlib.compress(json.dumps(data).encode())).decode().rstrip('=')


def test_private_quote_preserves_source_and_skips_zero():
    frame,skipped=decode_quote(token())
    assert skipped==1 and len(frame)==1
    assert frame.iloc[0]['Закупка PLN']==12.345
    assert frame.iloc[0]['Цена Allegro PLN']==0
    assert frame.iloc[0]['source_row']==1


def test_reimport_does_not_replace_prices_or_photos():
    frame,_=decode_quote(token())
    result,added,skipped=save_quote(frame)
    assert added==1 and skipped==0
    result.loc[0,'Цена Allegro PLN']=40
    result.loc[0,'Фото Komertia']='existing-photo'
    storage.save_analysis(result)
    original=storage.read('analysis')
    _,added,skipped=save_quote(frame)
    assert added==0 and skipped==1
    assert storage.read('analysis')==original


@pytest.mark.parametrize('rows',[[[1,'x','v',1,2],[1,'x','v',1,2]],[[1,'x','v',-1,2]],[[1,'x','v',1,-2]]])
def test_invalid_payload_rejected(rows):
    with pytest.raises(ValueError):decode_quote(token(rows))


def test_oversized_decompression_rejected():
    large=base64.urlsafe_b64encode(zlib.compress(b' '*128002)).decode().rstrip('=')
    with pytest.raises(ValueError):decode_quote(large)
