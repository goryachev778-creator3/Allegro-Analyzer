import copy
import pandas as pd
import pytest
import storage
from neon_delta import save, build_patch, PRICE_SQL
from benchmarks.neon_traffic import Meter


def records():
    frame = pd.DataFrame([{**dict.fromkeys(storage.INPUTS,0), 'Товар':f'Item {i}','SKU':str(i),
        '_position_id':f'id-{i}','Фото Komertia':'data:image/jpeg;base64,'+'A'*65536,
        '_archived_no_allegro_price':i==1} for i in range(3)])
    frame=storage.ensure_ids(frame)
    return frame, frame.to_dict('records')


def test_unchanged_snapshot_makes_zero_database_calls(monkeypatch):
    frame,base=records()
    monkeypatch.setattr(storage,'state_connection',lambda **kw:pytest.fail('No-op contacted database'))
    monkeypatch.setattr(storage,'is_external',lambda:True)
    digest,token,saved=save(frame,base,'version',storage.analysis_hash(base))
    assert saved==base and token=='version'


def test_cell_edit_transmits_only_delta_not_photos(monkeypatch):
    frame,base=records();db=Meter(base)
    monkeypatch.setattr(storage,'state_connection',db.connection)
    monkeypatch.setattr(storage,'is_external',lambda:True)
    frame.loc[0,'Цена Allegro PLN']=77
    digest,token,saved=save(frame,base,db.token(),storage.analysis_hash(base))
    assert db.state['analysis']==saved
    assert db.state['analysis'][1]==base[1]  # Archived record and photo unchanged.
    assert db.queries==3 and db.connections==1
    assert db.requests<5000 and db.responses==32
    assert db.state['prices']['id-0']['Цена Allegro PLN']==77


def test_concurrent_edit_rejected_without_overwriting_or_losing_cache(monkeypatch):
    frame,base=records();db=Meter(base);old_token=db.token()
    monkeypatch.setattr(storage,'state_connection',db.connection)
    monkeypatch.setattr(storage,'is_external',lambda:True)
    frame.loc[0,'Цена Allegro PLN']=77
    save(frame,base,old_token,storage.analysis_hash(base))
    committed=copy.deepcopy(db.state)
    second=frame.copy();second.loc[1,'Цена Allegro PLN']=88
    with pytest.raises(ValueError,match='Автосохранение остановлено'):
        save(second,base,old_token,storage.analysis_hash(base))
    assert db.state==committed
    assert base[0]['Цена Allegro PLN']==0


def test_failed_prices_update_rolls_back_delta(monkeypatch):
    frame,base=records();db=Meter(base);old_token=db.token();before=copy.deepcopy(db.state)
    execute=db.execute
    def fail(sql,args=()):
        if sql==PRICE_SQL:raise RuntimeError('injected fault')
        return execute(sql,args)
    db.execute=fail
    monkeypatch.setattr(storage,'state_connection',db.connection)
    monkeypatch.setattr(storage,'is_external',lambda:True)
    frame.loc[0,'Цена Allegro PLN']=77
    with pytest.raises(RuntimeError):save(frame,base,old_token,storage.analysis_hash(base))
    assert db.state==before and db.token()==old_token


def test_structural_change_uses_guarded_replace_keeps_price_cache(monkeypatch):
    frame,base=records();db=Meter(base)
    db.state['prices']['temporarily_removed']={'Цена Allegro PLN':99}
    monkeypatch.setattr(storage,'state_connection',db.connection)
    monkeypatch.setattr(storage,'is_external',lambda:True)
    frame=frame.iloc[::-1].reset_index(drop=True)
    _,_,saved=save(frame,base,db.token(),storage.analysis_hash(base))
    assert db.state['analysis']==saved
    assert db.state['prices']['temporarily_removed']=={'Цена Allegro PLN':99}


def test_field_removal_and_non_price_change_dont_rewrite_prices(monkeypatch):
    frame,base=records();base[0]['obsolete']='old';frame=pd.DataFrame(base)
    frame.loc[0,'Доп. расходы PLN']=2
    frame=frame.drop(columns=['obsolete'])
    frame=frame.astype(object).where(frame.notna(),None)
    # Other records have an absent optional field; removal is safe by JSON key.
    db=Meter(base)
    monkeypatch.setattr(storage,'state_connection',db.connection)
    monkeypatch.setattr(storage,'is_external',lambda:True)
    _,_,saved=save(frame,base,db.token(),storage.analysis_hash(base))
    assert db.writes==1
    assert 'obsolete' not in db.state['analysis'][0]
    assert db.state['analysis']==saved


def test_preview_cache_expires_and_never_crosses_session(monkeypatch):
    import komertia_import_ui as ui
    calls=[];clock=[0]
    monkeypatch.setattr(ui.st,'session_state',{})
    monkeypatch.setattr(ui.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(ui,'snapshot',lambda:(calls.append('read') or [{'id':'one'}],[]))
    assert ui.projected_preview('quote1')==[{'id':'one'}]
    ui.projected_preview('quote1');assert len(calls)==1
    clock[0]=31;ui.projected_preview('quote1');assert len(calls)==2
    ui.projected_preview('quote2');assert len(calls)==3
    monkeypatch.setattr(ui.st,'session_state',{})
    ui.projected_preview('quote2');assert len(calls)==4


def test_journal_refresh_does_not_download_analysis(monkeypatch):
    from komertia_import_service import operation_log
    _,base=records();db=Meter(base)
    monkeypatch.setattr(storage,'state_connection',db.connection)
    monkeypatch.setattr(storage,'is_external',lambda:True)
    assert operation_log()==[]
    assert db.responses==0
    assert db.queries==1 and db.connections==1


def test_monthly_projection_keeps_full_photo_load_for_every_new_session():
    from benchmarks.neon_traffic import monthly_projection
    measured={'scenario':{'analysis_bytes':5_000_000},
              'before':{'responses':60_000_000},'after':{'responses':64}}
    projected=monthly_projection(measured,10)
    assert projected['before_gb']==19.5
    assert projected['after_gb']==1.500019
    assert projected['saved_gb']==17.999981
    # Refreshing the browser ten times costs ten full snapshots, not one.
    assert monthly_projection(measured,1)['after_gb']==0.150002
    assert monthly_projection(measured,0)['after_gb']==0
    with pytest.raises(ValueError):monthly_projection(measured,-1)
