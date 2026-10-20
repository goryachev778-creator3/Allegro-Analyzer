"""Offline request/response payload meter. Never opens a network connection.

Counts explicit SQL statements, connections, and UTF-8 SQL/parameter/result bytes;
not TLS/framing/compression, and not live Neon billing telemetry.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import storage
import neon_delta


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Cursor:
    def __init__(self, row=None): self.row = row
    def fetchone(self): return self.row


class Meter:
    def __init__(self, records):
        self.state = {'analysis':copy.deepcopy(records), 'prices':{r['_position_id']:{c:r[c] for c in storage.SALES} for r in records}}
        self.requests = self.responses = self.queries = self.connections = self.writes = 0
    def token(self): return hashlib.md5(dumps(self.state['analysis']).encode()).hexdigest()
    def connection(self, ensure_table=True):
        self.connections += 1
        if ensure_table:self.execute('CREATE TABLE IF NOT EXISTS public.allegro_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        return self
    def __enter__(self):self.before=copy.deepcopy(self.state);return self
    def __exit__(self,t,v,b):
        if t:self.state=self.before
    def close(self):pass
    def reply(self, row=None):
        if row:
            self.responses += sum(len((v if isinstance(v,str) else dumps(v)).encode()) for v in row)
        return Cursor(row)
    def execute(self,sql,args=()):
        self.queries += 1
        self.requests += len(sql.encode()) + sum(len((a if isinstance(a,str) else dumps(a)).encode()) for a in args)
        if sql.startswith('SELECT value FROM'):
            v=self.state.get(args[0]);return self.reply((dumps(v),) if v is not None else None)
        if sql.startswith('SELECT md5(value::text)'):return self.reply((self.token(),))
        if sql.startswith('INSERT INTO') and 'prices' not in sql.split('SELECT')[0] and 'excluded.value::jsonb' not in sql:
            self.state[args[0]]=json.loads(args[1]);self.writes+=1;return self.reply()
        if sql==neon_delta.PRICE_SQL:
            self.state['prices'].update(json.loads(args[0]));self.writes+=1;return self.reply()
        if sql in (neon_delta.PATCH_SQL,neon_delta.REPLACE_SQL):
            if self.token()!=args[1]:return self.reply()
            payload=json.loads(args[0])
            if sql==neon_delta.REPLACE_SQL:self.state['analysis']=payload
            else:
                for r in self.state['analysis']:
                    patch=payload.get(r['_position_id'])
                    if patch:
                        for key in patch['remove']:r.pop(key,None)
                        r.update(patch['set'])
            self.writes+=1;return self.reply((self.token(),))
        return self.reply()
    def report(self):
        return {k:getattr(self,k) for k in ('queries','connections','writes','requests','responses')}


def measure(rows=41, photo_kib=128, reruns=10, edits=2, baseline='e37265e', webarchive=None):
    frame=pd.DataFrame([{**dict.fromkeys(storage.INPUTS,0), 'Товар':f'Product {i}', 'SKU':str(i),
        '_position_id':f'synthetic-{i}', 'Produkt':f'Product {i}', 'Wariant':'Red',
        'Фото Komertia':'data:image/jpeg;base64,'+'A'*(photo_kib*1024)} for i in range(rows)])
    if webarchive:
        from komertia_quote import parse_quote
        source=Path(webarchive)
        quote=parse_quote(source.read_bytes(),source.name,'2026-10-19')
        frame=pd.DataFrame(quote.records)
        rows=len(frame)
    frame=storage.ensure_ids(frame);records=frame.astype(object).where(frame.notna(),None).to_dict('records')
    source=subprocess.check_output(['git','show',f'{baseline}:storage.py'],text=True)
    old=types.ModuleType('storage_before');old.__file__=storage.__file__;exec(compile(source,'storage_before.py','exec'),old.__dict__)
    old_meter=Meter(records);old.is_external=lambda:True;old.state_connection=old_meter.connection
    current=frame.copy();expected=old.analysis_hash(records)
    for _ in range(reruns):expected=old.save_analysis(current,expected_hash=expected)
    for i in range(edits):
        current.loc[i%rows,'Цена Allegro PLN']=100+i
        expected=old.save_analysis(current,expected_hash=expected)
    after=Meter(records)
    factory,external=storage.state_connection,storage.is_external
    storage.state_connection=after.connection;storage.is_external=lambda:True
    try:
        current=frame.copy();base=records;token=after.token();expected=storage.analysis_hash(records)
        for _ in range(reruns):expected,token,base=neon_delta.save(current,base,token,expected)
        for i in range(edits):
            current.loc[i%rows,'Цена Allegro PLN']=100+i
            expected,token,base=neon_delta.save(current,base,token,expected)
    finally:storage.state_connection,storage.is_external=factory,external
    assert after.state==old_meter.state
    return {'scenario':{'rows':rows,'photo_kib_per_row':photo_kib if not webarchive else None,'source':'provided_archive' if webarchive else 'synthetic','unchanged_reruns':reruns,'cell_edits':edits,
                        'analysis_bytes':len(dumps(records).encode()),'baseline':baseline},
            'before':old_meter.report(),'after':after.report(),
            'response_reduction_percent':round((1-after.responses/old_meter.responses)*100,6),
            'request_reduction_percent':round((1-after.requests/old_meter.requests)*100,6)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',default='e37265e');parser.add_argument('--output');parser.add_argument('--webarchive')
    args=parser.parse_args();result=measure(baseline=args.baseline,webarchive=args.webarchive)
    output=json.dumps(result,indent=2)
    print(output)
    if args.output:Path(args.output).write_text(output+'\n')
