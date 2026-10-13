import pandas as pd
import pytest
from analyzer import INPUTS, NUMERIC, calculate, export_excel
from komertia_details import PHOTO
from product_duplicates import review, checked_import, without_confirmed_duplicates, fingerprint, confirm_duplicates
import storage


def item(id, variant='czarny XL', **fields):
    return dict.fromkeys(INPUTS, 0) | {'_position_id': id, 'Produkt': 'Torba model A', 'Wariant': variant, 'Товар': 'Torba model A', 'SKU': '', PHOTO: '', **fields}


def test_preview_no_removal_and_merge_complementary_fields():
    frame = pd.DataFrame([item('a', **{'Цена Allegro PLN': 35}), item('b', **{PHOTO: 'photo', 'Комиссия %': 11}), item('c', 'biały XL')])
    original = frame.copy(deep=True)
    assert len(review(frame)) == 1
    pd.testing.assert_frame_equal(frame, original)
    result, removed = without_confirmed_duplicates(frame)
    assert removed == 1
    assert list(result['_position_id']) == ['a', 'c']
    assert result.iloc[0]['Цена Allegro PLN'] == 35
    assert result.iloc[0]['Комиссия %'] == 11
    assert result.iloc[0][PHOTO] == 'photo'
    assert export_excel(calculate(result, 15))


@pytest.mark.parametrize('field,value', [('Wariant','biały XL'), ('model','B'), ('size','M'), ('color','white'), ('kit','2'), ('quantity',2)])
def test_distinct_characteristics_remain(field, value):
    first = item('a', model='A', size='XL', color='black', kit='1', quantity=1)
    second = first | {'_position_id':'b', field:value}
    assert not review(pd.DataFrame([first, second]))


def test_cropped_labels_other_lp_not_proof():
    first = item('a') | {'Produkt':'Torba...', 'source_row':17}
    second = first | {'_position_id':'b', 'source_row':18}
    assert review(pd.DataFrame([first, second]))[0]['conflicts']
    assert without_confirmed_duplicates(pd.DataFrame([first, second]))[1] == 0


def test_conflicting_prices_and_photos_not_deleted():
    frame = pd.DataFrame([item('a', **{'Цена Allegro PLN':10, PHOTO:'a'}), item('b', **{'Цена Allegro PLN':20, PHOTO:'b'})])
    assert review(frame)[0]['conflicts'] == ['Фото Komertia', 'Цена Allegro PLN']
    result, removed = without_confirmed_duplicates(frame)
    assert removed == 0 and len(result) == 2


def test_import_preserves_all_existing_records_and_fields():
    saved = pd.DataFrame([item('a', **{'Цена Allegro PLN':35, 'Закупка PLN':20, PHOTO:'original'}), item('b', 'biały XL')])
    incoming = pd.DataFrame([item('new-id', **{'Закупка PLN':99}), item('c','czerwony XL'), item('d','czerwony XL')])
    result, skipped = checked_import(incoming, saved)
    assert skipped == 2
    assert list(result['_position_id']) == ['a','b','c']
    pd.testing.assert_frame_equal(result.iloc[:2].reset_index(drop=True), saved, check_dtype=False)


def test_confirmation_atomic_and_restart_and_stale_review(tmp_path, monkeypatch):
    monkeypatch.setenv('ALLEGRO_DB_PATH', str(tmp_path/'data.sqlite'))
    monkeypatch.setenv('ALLEGRO_DATABASE_URL','')
    frame = pd.DataFrame([item('a', **{'Цена Allegro PLN':35}), item('b', **{PHOTO:'original'})])
    storage.save_analysis(frame)
    expected = fingerprint(frame)
    assert len(storage.load_analysis()) == 2
    result, count = confirm_duplicates(expected)
    assert count == 1 and result.iloc[0][PHOTO] == 'original'
    assert storage.load_analysis().iloc[0]['Цена Allegro PLN'] == 35
    with pytest.raises(ValueError, match='Данные изменились'):
        confirm_duplicates(expected)
    assert len(storage.load_analysis()) == 1


def test_streamlit_requires_explicit_confirmation_and_persists():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    storage.save_analysis(pd.DataFrame([item('a', **{'Цена Allegro PLN':35}), item('b', **{PHOTO:'original'})]))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
    assert not app.exception
    button = next(b for b in app.button if b.label == 'Подтвердить удаление дубликатов и сохранить')
    assert button.disabled
    assert len(storage.load_analysis()) == 2
    next(c for c in app.checkbox if c.label.startswith('Подтверждаю объединение')).check().run()
    next(b for b in app.button if b.label == 'Подтвердить удаление дубликатов и сохранить').click().run()
    assert not app.exception
    assert len(storage.load_analysis()) == 1
    assert storage.load_analysis().iloc[0][PHOTO] == 'original'
    restarted = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
    assert not restarted.exception
    assert len(storage.load_analysis()) == 1
