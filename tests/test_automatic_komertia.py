"""Synthetic source quotes only: no customer orders, credentials or photos in Git."""
import base64
import copy
import io
import json
import plistlib
from decimal import Decimal
import pytest
from PIL import Image
from komertia_quote import parse_quote, QuoteError
from komertia_import_service import confirm_import, plan_import, ImportErrorSafe, LOG_KEY
import storage

ORDER = '00000000-0000-4000-8000-000000000001'
URL = 'https://www.komertia.com/client/orders/' + ORDER


def quote_file(shared=False, cost='10.00', quantity=1, total='10.00', zero=False, unsafe=False):
    out = io.BytesIO(); Image.new('RGB', (800,800), 'white').save(out, format='JPEG')
    proxy='https://www.komertia.com/api/image-proxy?url=https%3A%2F%2Fexample.com%2Foriginal.jpg'
    link='javascript:alert(1)' if unsafe else '/product/12345'
    def row(lp, variant, qty, group=False):
        td=[str(lp), f'<img src="{proxy}">', f'<a href="{link}">Full product name</a>', variant,
            str(qty), '4.00 zł', ('4.00 zł' if qty else '0.00 zł'), '0.00 zł', ('4.00 zł' if qty else '0.00 zł')]
        start='<tr id="product-row-'+str(lp)+'">'+''.join('<td>'+c+'</td>' for c in td)
        if not group:
            start+=''.join(f'<td rowspan="{2 if shared else 1}">{c}</td>' for c in ['1 kg','0.1 m³','5.00 zł','1.00 zł','6.00 zł',f'{total} zł'])
        return start+f'<td>{cost if qty else "0"} zł</td></tr>'
    nodes=row(1,'Red',quantity)
    if shared:nodes+=row(2,'Blue',quantity,True)
    if zero:nodes+=row(3,'Zero',0)
    qty_total=quantity*(2 if shared else 1)
    footer=f'<tr><td colspan="4">Razem</td><td>{qty_total}</td><td></td><td></td><td></td><td>{8 if shared else 4}.00 zł</td><td></td><td></td><td></td><td></td><td>6.00 zł</td><td>{total} zł</td><td></td></tr>'
    page=('<table><tr><th>Cena szt.</th></tr>'+nodes+footer+'</table>').encode()
    archive={'WebMainResource':{'WebResourceURL':URL,'WebResourceData':page},'WebSubresources':[{'WebResourceURL':proxy,'WebResourceData':out.getvalue()}]}
    return plistlib.dumps(archive)


def test_parse_original_photo_and_blank_sale():
    quote=parse_quote(quote_file(), 'quote.webarchive','2026-10-19')
    r=quote.records[0]
    assert r['Фото Komertia'].startswith('data:image/jpeg;base64,')
    assert r['_source_photo_dimensions']==[800,800]
    assert r['Цена Allegro PLN'] is None and r['Комиссия %'] is None
    assert quote.report['quantity']==1
    assert r['Закупка PLN']==10
    assert r['Доставка PLN']==r['Пошлина %']==r['Оформление PLN']==0


def test_shared_cells_counted_once_and_zero_positions_excluded():
    q=parse_quote(quote_file(shared=True,cost='7',total='14.00'),'a.webarchive','2026-10-19')
    assert len(q.records)==2
    assert q.report['quantity']==2 and q.report['second_payment']=='6.00'
    assert q.records[0]['_position_id']!=q.records[1]['_position_id']


def test_source_rounding_is_reported_not_silently_changed():
    q=parse_quote(quote_file(cost='9.99'),'a.webarchive','2026-10-19')
    assert q.report['rounding_difference']=='0.01'
    assert q.records[0]['Закупка PLN']==9.99
    with pytest.raises(QuoteError, match='Расхождение'):
        parse_quote(quote_file(cost='5'),'a.webarchive','2026-10-19')


def test_invalid_file_or_link_is_rejected():
    with pytest.raises(QuoteError):parse_quote(b'bad','x.webarchive','2026-10-19')
    with pytest.raises(QuoteError):parse_quote(quote_file(unsafe=True),'x.webarchive','2026-10-19')
    with pytest.raises(QuoteError):parse_quote(b'x'* (25*1024*1024+1),'x.webarchive','2026-10-19')


class Cursor:
    def __init__(self, rows=()):self.rows=rows
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


class MemoryPostgres:
    """Transactional adapter to inject read/write faults into service tests."""
    def __init__(self):
        self.state={'analysis':[{'_position_id':'old','Цена Allegro PLN':88,'Фото Komertia':'original','_archived_no_allegro_price':True}], 'prices':{'old':{'Цена Allegro PLN':88}}}
        self.fail_key=None; self.corrupt_key=None; self.closed=False
    def __enter__(self):self.before=copy.deepcopy(self.state);return self
    def __exit__(self,t,v,b):
        if t:self.state=self.before
    def close(self):self.closed=True
    def execute(self,sql,args=()):
        if sql=='SELECT current_database()':return Cursor([('neondb',)])
        if sql.startswith('SELECT value FROM'):
            key=args[0];value=self.state.get(key)
            if self.corrupt_key==key and key in self.state:value={}
            return Cursor([(json.dumps(value),)]) if value is not None else Cursor()
        if sql.startswith('INSERT INTO'):
            key,payload=args
            if key==self.fail_key:raise RuntimeError('password=NEVER_PRINT_THIS')
            self.state[key]=json.loads(payload)
        return Cursor()


@pytest.fixture
def pg(monkeypatch):
    db=MemoryPostgres()
    monkeypatch.setattr(storage,'is_external',lambda:True)
    monkeypatch.setattr(storage,'state_connection',lambda **kw:db)
    return db


def test_transaction_append_repeat_and_existing_archive_untouched(pg):
    q=parse_quote(quote_file(),'a.webarchive','2026-10-19')
    old=copy.deepcopy(pg.state)
    combined,event=confirm_import(q,True)
    assert event['added']==1 and combined[0]==old['analysis'][0]
    assert pg.state['prices']['old']==old['prices']['old']
    pg.state['analysis'][1]['Цена Allegro PLN']=123
    combined,event=confirm_import(q,True)
    assert event['added']==0 and len(combined)==2
    assert combined[1]['Цена Allegro PLN']==123
    assert len(pg.state[LOG_KEY])==2


def test_archived_same_identity_is_skipped_not_revived(pg):
    q=parse_quote(quote_file(),'a.webarchive','2026-10-19')
    old=copy.deepcopy(q.records[0]);old['_archived_no_allegro_price']=True
    new,states,count=plan_import([old],q)
    assert not new and count==1 and 'Архив' in states[0]


def test_failure_rolls_back_analysis_prices_and_log_without_exposing_password(pg):
    old=copy.deepcopy(pg.state);pg.fail_key='prices'
    with pytest.raises(ImportErrorSafe) as e:confirm_import(parse_quote(quote_file(),'a.webarchive','2026-10-19'),True)
    assert 'NEVER_PRINT' not in str(e.value)
    assert pg.state['analysis']==old['analysis']
    assert pg.state['prices']==old['prices']
    assert pg.state[LOG_KEY][-1]['status']=='failed'


def test_confirmation_and_external_database_are_required(monkeypatch):
    q=parse_quote(quote_file(),'a.webarchive','2026-10-19')
    with pytest.raises(ImportErrorSafe):confirm_import(q,False)
    monkeypatch.setattr(storage,'is_external',lambda:False)
    with pytest.raises(ImportErrorSafe,match='SQLite'):confirm_import(q,True)


def test_stale_autosave_cannot_overwrite_new_import():
    import pandas as pd
    from analyzer import INPUTS
    frame=pd.DataFrame([['Item','001',1,0,0,0,0,0,10,10,0]],columns=INPUTS)
    token=storage.save_analysis(frame)
    records=storage.read('analysis')
    records.append(dict(records[0],_position_id='imported'))
    storage.write('analysis',records)
    with pytest.raises(ValueError,match='другой сессии'):
        storage.save_analysis(frame,expected_hash=token)
    assert len(storage.read('analysis'))==2


def test_read_after_write_failure_rolls_back(pg):
    old = copy.deepcopy(pg.state)
    pg.corrupt_key = LOG_KEY
    with pytest.raises(ImportErrorSafe, match='Проверка записи'):
        confirm_import(parse_quote(quote_file(),'a.webarchive','2026-10-19'),True)
    assert pg.state['analysis'] == old['analysis']
    assert pg.state['prices'] == old['prices']


def test_wrong_database_is_refused_without_writes(pg):
    old = copy.deepcopy(pg.state)
    execute = pg.execute
    def wrong(sql,args=()):
        return Cursor([('other_database',)]) if sql=='SELECT current_database()' else execute(sql,args)
    pg.execute = wrong
    with pytest.raises(ImportErrorSafe, match='neondb'):
        confirm_import(parse_quote(quote_file(),'a.webarchive','2026-10-19'),True)
    assert pg.state == old


def test_changed_existing_cost_is_not_overwritten(pg):
    q = parse_quote(quote_file(),'a.webarchive','2026-10-19')
    confirm_import(q,True)
    pg.state['analysis'][1]['Закупка PLN'] = 99
    with pytest.raises(ImportErrorSafe, match='себестоимости'):
        confirm_import(q,True)
    assert pg.state['analysis'][1]['Закупка PLN'] == 99
