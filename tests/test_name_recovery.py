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
    assert restored[NAME_PL].str.strip().str.len().gt(0).all()
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
    assert 'szmaragdowy' in polish_name(row)
    row['Wariant'] = ''
    # Both emerald and white exist: no guessed color/model is assigned.
    assert polish_name(row) == ''


def test_legacy_catalog_identity_and_source_text_without_uuid():
    row = load_catalog().iloc[2].to_dict()
    row['_position_id'] = 'komertia-screenshot-oct2026:4'
    assert polish_name(row) == 'Waga bagażowa z hakiem, 50 kg'
    row['_position_id'] = 'hash-from-an-old-import'
    row.pop('Produkt')
    assert polish_name(row) == 'Waga bagażowa z hakiem, 50 kg'
