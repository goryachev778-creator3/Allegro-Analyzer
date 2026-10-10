from io import BytesIO
import zipfile
import pytest
from PIL import Image
from komertia_photos import read_photo_zip, apply_lp_photos, save_zip_photos
from komertia_details import PHOTO
from screenshot_catalog import load_catalog
from storage import save_analysis, read, load_analysis


def archive_for(lps):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        for lp in lps:
            picture = BytesIO()
            Image.new('RGB', (2, 2), (lp, 0, 0)).save(picture, format='PNG')
            z.writestr(f'Komertia_LP_{lp:02}.png', picture.getvalue())
    return output.getvalue()


def test_26_lp_photos_preserve_all_other_values_and_reload():
    frame = load_catalog().iloc[:26].iloc[::-1].reset_index(drop=True)
    save_analysis(frame)
    before = read('analysis')
    prices = read('prices')
    data = archive_for(range(1, 39))
    photos = read_photo_zip(data)
    updated, matched = save_zip_photos(data)
    assert matched == frame['source_row'].tolist()
    assert len(updated) == 26
    for old, new in zip(before, updated):
        assert new[PHOTO] == photos[old['source_row']]
        assert {k:v for k,v in new.items() if k != PHOTO} == {k:v for k,v in old.items() if k != PHOTO}
    assert read('prices') == prices
    assert load_analysis()[PHOTO].tolist() == [r[PHOTO] for r in updated]


def test_missing_lp_is_atomic_and_display_numbers_never_used():
    frame = load_catalog().iloc[:26]
    save_analysis(frame)
    before = read('analysis')
    with pytest.raises(ValueError):
        save_zip_photos(archive_for([1]))
    assert read('analysis') == before
    with pytest.raises(ValueError):
        apply_lp_photos([{'№':1}], read_photo_zip(archive_for([1])))


def test_recover_26_original_lps_without_catalog_ids_preserves_order_and_neon_fields():
    from komertia_photos import source_lp
    from komertia_details import NAME_PL
    frame = load_catalog().iloc[:26].iloc[::-1].reset_index(drop=True)
    expected_lps = frame['source_row'].tolist()
    frame = frame.drop(columns='source_row')
    frame['_position_id'] = [f'old-import-hash-{i}' for i in range(26)]
    frame['№'] = list(range(1, 27))
    frame['LP'] = frame['№']  # display numbering is not original Komertia LP
    frame[NAME_PL] = ['Zachowana nazwa ' + str(i) for i in range(26)]
    frame[PHOTO] = ['https://example.com/photo-' + str(i) for i in range(26)]
    assert [source_lp(row) for row in frame.to_dict('records')] == expected_lps
    save_analysis(frame)
    original = read('analysis')
    prices = read('prices')
    restored = load_analysis()
    assert restored['source_row'].tolist() == expected_lps
    for old, new in zip(original, read('analysis')):
        assert {k:v for k,v in new.items() if k != 'source_row'} == old
    assert read('prices') == prices
    assert load_analysis()['source_row'].tolist() == expected_lps
    # ZIP now succeeds for the formerly missing provenance, in the same order.
    updated, matched = save_zip_photos(archive_for(range(1, 39)))
    assert matched == expected_lps and len(updated) == 26
    assert [r[NAME_PL] for r in updated] == frame[NAME_PL].tolist()


def test_ambiguous_original_variants_not_guessed_and_legacy_name_identity_used():
    import json
    from komertia_photos import source_lp
    row = load_catalog().iloc[10].to_dict()
    expected = row.pop('source_row')
    original_name = row.pop('Produkt')
    row.pop('Товар')
    row['_position_id'] = 'legacy:' + json.dumps(['name', original_name.casefold()], ensure_ascii=False) + ':1'
    assert source_lp(row) == expected
    row.pop('Ilość')
    with pytest.raises(ValueError):
        source_lp(row)
    row = load_catalog().iloc[0].to_dict()
    row['№'] = row['LP'] = 25
    assert source_lp(row) == 1
    row['source_row'] = 25
    with pytest.raises(ValueError):
        source_lp(row)
