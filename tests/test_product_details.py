from io import BytesIO
import pandas as pd
import pytest
from PIL import Image
from analyzer import INPUTS, NUMERIC, calculate
from product_details import PHOTO, FULL_NAME, enrich_details, import_details, uploaded_photo, full_table
from storage import save_analysis, load_analysis, backup_excel, read_backup, merge_import
from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_missing_details_and_original_import():
    raw = pd.DataFrame({'title': ['Original ' + 'long ' * 100, 'Cut…'], 'image': ['https://example.com/a.png', '']})
    frame = import_details(pd.DataFrame({'Товар': ['a', 'b']}), raw, {FULL_NAME: 'title', PHOTO: 'image'})
    assert frame[FULL_NAME].tolist() == [raw.title[0], '']
    assert frame[PHOTO].tolist() == raw.image.tolist()
    empty = enrich_details(pd.DataFrame({'Produkt': ['Cut…']}))
    assert empty[PHOTO][0] == empty[FULL_NAME][0] == ''
    table = full_table(frame, [PHOTO, FULL_NAME])
    assert raw.title[0] in table
    assert '<img' in table
    assert '&lt;script&gt;' in full_table(pd.DataFrame({FULL_NAME: ['<script>']}), [FULL_NAME])


def test_26_positions_prices_calculations_and_manual_metadata_survive_reload():
    frame = pd.DataFrame([['Item', '', 10, 2, 5, 1, 3, 0, 50, 11, 1]] * 26, columns=INPUTS)
    frame['_position_id'] = [f'position-{i}' for i in range(26)]
    frame['Produkt'] = 'Original name ' + 'word ' * 80
    frame['Wariant'] = 'Original variant ' + 'word ' * 80
    save_analysis(frame)
    before = calculate(frame)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert not app.exception
    restored = load_analysis()
    assert len(restored) == 26
    pd.testing.assert_frame_equal(restored[NUMERIC], frame[NUMERIC])
    pd.testing.assert_frame_equal(calculate(restored)[before.columns], before)
    image = BytesIO()
    Image.new('RGB', (100, 100)).save(image, format='PNG')
    restored.loc[0, PHOTO] = uploaded_photo(image.getvalue())
    restored.loc[0, FULL_NAME] = 'Exact manually pasted original title'
    save_analysis(restored)
    merged = merge_import(frame, load_analysis())
    assert merged.loc[0, PHOTO] == restored.loc[0, PHOTO]
    assert merged.loc[0, FULL_NAME] == restored.loc[0, FULL_NAME]
    pd.testing.assert_frame_equal(merged[NUMERIC], frame[NUMERIC])


def test_large_photo_backup_is_lossless():
    frame = pd.DataFrame([['Item', '', 10, 0, 0, 0, 0, 0, 50, 10, 0]], columns=INPUTS)
    frame['_position_id'] = ['original-position']
    frame[PHOTO] = 'data:image/png;base64,' + 'A' * 100000
    frame[FULL_NAME] = 'Full original name'
    restored = read_backup(backup_excel(frame))
    assert restored.loc[0, PHOTO] == frame.loc[0, PHOTO]
    assert restored.loc[0, FULL_NAME] == frame.loc[0, FULL_NAME]
    with pytest.raises(ValueError):
        uploaded_photo(b'not an image')


def test_polish_titles_preserve_all_originals_and_26_positions():
    from product_details import NAME_PL
    from screenshot_catalog import load_catalog
    frame = load_catalog().iloc[:26].copy()
    frame[FULL_NAME] = 'Oryginalna pełna nazwa Komertia'
    before = frame.copy()
    enriched = enrich_details(frame)
    assert len(enriched) == 26 and enriched[NAME_PL].str.len().gt(0).all()
    assert not enriched[NAME_PL].str.contains(r'[А-Яа-яЁё]|…', regex=True).any()
    pd.testing.assert_frame_equal(enriched[before.columns], before)
    assert '50 kg' in enriched.iloc[2][NAME_PL]
    assert '20 × 20 cm' in enriched.iloc[6][NAME_PL]
    enriched.loc[0, NAME_PL] = 'Pokrowiec na ubrania, własna nazwa'
    save_analysis(enriched)
    reimported = merge_import(frame, load_analysis())
    assert reimported.loc[0, NAME_PL] == enriched.loc[0, NAME_PL]
    pd.testing.assert_frame_equal(reimported[NUMERIC], before[NUMERIC])


def test_pasted_photo_targets_id_and_survives_storage_and_backup():
    from photo_grid import apply_photo_event
    from screenshot_catalog import load_catalog
    frame = enrich_details(load_catalog().iloc[:26])
    image = BytesIO()
    Image.new('RGB', (15, 20), 'red').save(image, format='PNG')
    photo = uploaded_photo(image.getvalue())
    position = frame.iloc[10]['_position_id']
    event = {'position_id': position, 'event_id': 'paste-event-1', 'data': photo}
    updated = apply_photo_event(frame.iloc[::-1], event)
    assert updated.loc[updated['_position_id'].eq(position), PHOTO].item() == photo
    pd.testing.assert_frame_equal(updated.drop(columns=PHOTO), frame.iloc[::-1].drop(columns=PHOTO))
    save_analysis(updated)
    restored = read_backup(backup_excel(load_analysis()))
    assert restored.loc[restored['_position_id'].eq(position), PHOTO].item() == photo
    assert len(restored) == 26
    with pytest.raises(ValueError):
        apply_photo_event(frame, {**event, 'position_id': 'missing'})
    with pytest.raises(ValueError):
        apply_photo_event(frame, {**event, 'data': 'data:image/png;base64,not-image'})
