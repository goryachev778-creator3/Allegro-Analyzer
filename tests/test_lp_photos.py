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
