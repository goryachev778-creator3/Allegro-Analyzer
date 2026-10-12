import json
import os
import subprocess
import sys
from pathlib import Path
import pandas as pd
from screenshot_catalog import load_catalog
from komertia_details import NAME_PL, PHOTO, FULL_NAME, polish_name
from storage import save_analysis, load_analysis, read


def test_all_26_historical_ids_recover_and_survive_process_restart():
    # Saved positions need not have the UUIDs embedded in the source catalog.
    frame = load_catalog().iloc[:26].iloc[::-1].reset_index(drop=True)
    frame['_position_id'] = [f'historical-saved-id-{i}' for i in range(26)]
    frame[NAME_PL] = ''
    frame[PHOTO] = [f'https://example.com/original-{i}.png' for i in range(26)]
    frame[FULL_NAME] = 'Oryginalny pełny tekst pozostaje bez zmian'
    frame.loc[0, NAME_PL] = 'Zapisana polska nazwa użytkownika'
    save_analysis(frame)
    originals = read('analysis')
    prices = read('prices')
    restored = load_analysis()
    assert len(restored) == 26
    assert restored['Produkt'].tolist() == frame['Produkt'].tolist()
    assert restored['Wariant'].tolist() == frame['Wariant'].tolist()
    assert restored[NAME_PL].tolist() == frame[NAME_PL].tolist()
    assert restored.loc[0, NAME_PL] == frame.loc[0, NAME_PL]
    for old, new in zip(originals, read('analysis')):
        assert {k: v for k, v in new.items() if k != NAME_PL} == {k: v for k, v in old.items() if k != NAME_PL}
    assert read('prices') == prices
    pd.testing.assert_frame_equal(restored.drop(columns=NAME_PL), frame.drop(columns=NAME_PL))
    script = "from storage import load_analysis; from komertia_details import NAME_PL; import json; f=load_analysis(); print(json.dumps(f[['_position_id',NAME_PL]].to_dict('records')))"
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(), capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == restored[['_position_id', NAME_PL]].to_dict('records')


def test_source_matching_does_not_guess_color_for_ambiguous_variants():
    row = load_catalog().iloc[13].to_dict()
    row['_position_id'] = 'different-id'
    assert polish_name(row) == row['Produkt'] + ' · ' + row['Wariant']
    row['Wariant'] = ''
    row.pop('source_row')
    # Both emerald and white exist: no guessed color/model is assigned.
    assert polish_name(row) == row['Produkt']


def test_legacy_catalog_identity_and_source_text_without_uuid():
    row = load_catalog().iloc[2].to_dict()
    row['_position_id'] = 'komertia-screenshot-oct2026:4'
    assert polish_name(row) == '50kg przenośny bagaż · hak sekcji bat…'
    row['_position_id'] = 'hash-from-an-old-import'
    row.pop('Produkt')
    assert polish_name(row) == '50kg przenośny bagaż · hak sekcji bat…'


def test_original_uppercase_fields_and_lp_restoration_preserve_all_saved_values():
    frame = load_catalog().iloc[:26].iloc[::-1].reset_index(drop=True)
    originals = frame[['Produkt', 'Wariant']].copy()
    frame = frame.rename(columns={'Produkt': 'PRODUKT', 'Wariant': 'WARIANT'})
    frame['_position_id'] = [f'old-id-{i}' for i in range(26)]
    frame[PHOTO] = [f'https://example.com/confirmed-{i}.png' for i in range(26)]
    frame[NAME_PL] = 'Previously saved label must remain archived'
    save_analysis(frame)
    before = read('analysis')
    prices = read('prices')
    restored = load_analysis()
    assert restored['Produkt'].tolist() == originals['Produkt'].tolist()
    assert restored['Wariant'].tolist() == originals['Wariant'].tolist()
    for old, new in zip(before, read('analysis')):
        assert {k:v for k,v in new.items() if k not in ('Produkt','Wariant')} == old
    assert read('prices') == prices
    assert restored[PHOTO].tolist() == frame[PHOTO].tolist()
    assert restored['Ilość'].tolist() == frame['Ilość'].tolist()
    # Separate process confirms stored original fields survive restart.
    script = "from storage import load_analysis; import json; f=load_analysis(); print(json.dumps(f[['Produkt','Wariant']].to_dict('records')))"
    out = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == originals.to_dict('records')


def test_missing_originals_are_recovered_by_lp_not_current_row_or_translated_title():
    from komertia_details import original_record
    row = {'source_row': 4, '№': 1, '_position_id':'historical-id', NAME_PL:'Invented previous display title', PHOTO:'saved-photo', 'Закупка PLN':99, 'Ilość':3}
    restored = original_record(row)
    assert restored['Produkt'] == '50kg przenośny bagaż'
    assert restored['Wariant'] == 'hak sekcji bat…'
    assert {k:v for k,v in restored.items() if k not in ('Produkt','Wariant')} == row
    unknown = original_record({'№':4, NAME_PL:'Waga bagażowa z hakiem, 50 kg'})
    assert unknown['Produkt'] == unknown['Wariant'] == ''
