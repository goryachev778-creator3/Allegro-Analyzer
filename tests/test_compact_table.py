from compact_table import widths, LABELS


def test_desktop_columns_fit_and_have_requested_short_labels():
    for available in (818, 978, 1458):
        sizes = widths(available)
        assert sum(sizes.values()) <= available - 50
        assert sizes['№'] == 35 and sizes['Фото Komertia'] == 50
        assert sizes['Produkt'] > sizes['Wariant'] > sizes['Маржа %']
    assert list(LABELS.values()) == ['Закупка', 'Allegro', 'Ком. %', 'Ком. zł', 'Прибыль', 'Маржа %']
