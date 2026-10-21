import pytest
import psycopg
import storage
from neon_connection import connection_settings
from neon_health import check_neon_health, _safe_error

URL = 'postgresql://test:PRIVATE_TEST_VALUE@ep-example-pooler.eu.neon.tech/neondb?sslmode=require&connect_timeout=7&channel_binding=require'


def test_url_timeout_is_passed_exactly_once_and_tls_preserved(monkeypatch):
    calls=[]
    monkeypatch.setattr(storage,'external_url',lambda:URL)
    monkeypatch.setattr(psycopg,'connect',lambda **kw:calls.append(kw) or object())
    storage.state_connection()
    assert len(calls)==1
    assert calls[0]['connect_timeout']=='7'
    assert calls[0]['sslmode']=='require'
    assert calls[0]['channel_binding']=='require'
    assert 'options' not in calls[0]


@pytest.mark.parametrize('mode',['disable','allow','prefer'])
def test_insecure_tls_modes_rejected(mode):
    with pytest.raises(ValueError):
        connection_settings('postgresql://test@localhost/neondb?sslmode='+mode)


def test_pooled_health_read_only_and_108_positions(monkeypatch):
    sql=[]
    class DB:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,q,args=()):
            sql.append(q)
            self.result=('public.allegro_state',) if 'to_regclass' in q else (108,)
            return self
        def fetchone(self):return self.result
    def connect(**settings):
        assert 'options' not in settings
        assert settings['connect_timeout']=='7'
        return DB()
    monkeypatch.setattr(storage,'external_url',lambda:URL)
    monkeypatch.setattr(psycopg,'connect',connect)
    result=check_neon_health()
    assert result['status']=='OK' and result['positions']==108
    assert sql[0]=='SET TRANSACTION READ ONLY'
    assert all(q.startswith(('SET TRANSACTION READ ONLY','SELECT')) for q in sql)


@pytest.mark.parametrize('error,code',[
    ('unsupported startup parameter: options','POOLER_STARTUP_PARAMETER'),
    ('could not translate host name','DNS_FAILED'),
    ('connection timeout expired','NETWORK_UNAVAILABLE'),
    ('SSL certificate verify failed','TLS_FAILURE'),
    ('password authentication failed','AUTH_FAILED'),
])
def test_safe_actionable_failure_categories(error,code):
    result=_safe_error(psycopg.OperationalError(error+' '+URL))
    assert result[0]==code
    assert 'PRIVATE_TEST_VALUE' not in str(result)
    assert 'ep-example' not in str(result)


def test_app_stays_fail_closed_when_live_connection_is_unavailable():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
    assert not app.exception
    assert not app.get('data_editor')
    assert not any(b.label=='Подтвердить импорт' for b in app.button)
    assert any('Режим защиты' in w.value for w in app.warning)
