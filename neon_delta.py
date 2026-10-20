"""Wire-efficient, CAS-protected edits of existing allegro_state JSON records."""
import json


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def wire_token(db):
    row = db.execute("SELECT md5(value::text) FROM public.allegro_state WHERE key='analysis'").fetchone()
    return row[0] if row else None


def build_patch(baseline, records):
    """Return cell changes only; structural changes use a guarded full replacement."""
    if baseline is None:
        return None
    old_ids = [r.get('_position_id') for r in baseline]
    new_ids = [r.get('_position_id') for r in records]
    if old_ids != new_ids or len(set(old_ids)) != len(old_ids):
        return None
    patch = {}
    for old, new in zip(baseline, records):
        changed = {k:v for k,v in new.items() if k not in old or old[k] != v}
        removed = [k for k in old if k not in new]
        if changed or removed:
            patch[new['_position_id']] = {'set': changed, 'remove': removed}
    return patch


PATCH_SQL = '''WITH patch AS (SELECT %s::jsonb AS data), updated AS (
    SELECT coalesce(jsonb_agg(
      (item - ARRAY(SELECT jsonb_array_elements_text(coalesce(patch.data->(item->>'_position_id')->'remove','[]'::jsonb))))
      || coalesce(patch.data->(item->>'_position_id')->'set','{}'::jsonb)
      ORDER BY ord), '[]'::jsonb) AS data
    FROM public.allegro_state s CROSS JOIN patch,
      jsonb_array_elements(s.value::jsonb) WITH ORDINALITY AS entries(item,ord)
    WHERE s.key='analysis'
)
UPDATE public.allegro_state SET value=
 (jsonb_populate_record(NULL::public.allegro_state,jsonb_build_object('value',updated.data))).value
FROM updated WHERE key='analysis' AND md5(value::text)=%s RETURNING md5(value::text)'''

REPLACE_SQL = '''UPDATE public.allegro_state SET value=
 (jsonb_populate_record(NULL::public.allegro_state,jsonb_build_object('value',%s::jsonb))).value
 WHERE key='analysis' AND md5(value::text)=%s RETURNING md5(value::text)'''

PRICE_SQL = '''INSERT INTO public.allegro_state(key,value)
 SELECT 'prices',(jsonb_populate_record(NULL::public.allegro_state,jsonb_build_object('value',%s::jsonb))).value
 ON CONFLICT(key) DO UPDATE SET value=(jsonb_populate_record(NULL::public.allegro_state,
 jsonb_build_object('value',public.allegro_state.value::jsonb || excluded.value::jsonb))).value'''


def save(frame, baseline=None, expected_token=None, expected_hash=None):
    import storage
    frame = storage.ensure_ids(frame.reset_index(drop=True))
    records = frame.astype(object).where(frame.notna(), None).to_dict('records')
    digest = storage.analysis_hash(records)
    if baseline is not None and records == baseline:
        # The session's last confirmed snapshot, not a shared cache. No DB call.
        return digest, expected_token, records
    if not storage.is_external() or baseline is None or expected_token is None:
        digest, token = storage.save_analysis(frame, expected_hash=expected_hash, return_token=True)
        return digest, token, records
    patch = build_patch(baseline, records)
    old = {r['_position_id']:r for r in baseline}
    prices = {r['_position_id']:{c:r.get(c) for c in storage.SALES} for r in records
              if r['_position_id'] not in old or any(r.get(c) != old[r['_position_id']].get(c) for c in storage.SALES)}
    db = storage.state_connection(ensure_table=False)
    try:
        with db:
            db.execute('SELECT pg_advisory_xact_lock(%s)', (190102026,))
            # CAS itself obtains the row lock. All edits roll back if any operation fails.
            row = db.execute(PATCH_SQL if patch is not None else REPLACE_SQL,
                             (json_text(patch if patch is not None else records), expected_token)).fetchone()
            if not row:
                raise ValueError('Данные изменились в другой сессии или после импорта. Автосохранение остановлено: скачайте резервную копию и обновите страницу.')
            if prices:
                db.execute(PRICE_SQL, (json_text(prices),))
            token = row[0]
        return digest, token, records
    except ValueError:
        raise
    except Exception:
        raise RuntimeError('Не удалось сохранить изменения. Транзакция отменена; реквизиты подключения скрыты.') from None
    finally:
        db.close()
