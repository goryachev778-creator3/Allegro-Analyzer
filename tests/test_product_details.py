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
