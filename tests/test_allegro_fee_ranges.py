from allegro_fee_ranges import fee_range, with_fee_ranges

def test_category_range_not_exact():
    d=fee_range("Motoryzacja > Wyposażenie samochodu")
    assert d["Prowizja netto — min %"] == 4.5
    assert d["Prowizja netto — max %"] == 16.0
    assert d["Prowizja z VAT — max %"] == 19.68
    assert "NIE WPISYWAĆ" in d["Status opłaty"]

def test_unknown_category_fails_closed():
    d=fee_range("")
    assert d["Prowizja netto — min %"] is None
    assert d["Prowizja z VAT — max %"] is None

def test_never_replaces_verified_fee():
    original=[{"Категория Allegro (из предложения)":"Elektronika > RTV",
               "Комиссия %":None, "Цена конкурента brutto PLN":49}]
    result=with_fee_ranges(original)
    assert result[0]["Комиссия %"] is None
    assert result[0]["Prowizja netto — max %"] == 8
    assert original[0].get("Status opłaty") is None

def test_no_neon_writes_or_scraping():
    from pathlib import Path
    src=(Path(__file__).resolve().parents[1]/"allegro_fee_ranges.py").read_text()
    assert "save_analysis(" not in src and "urlopen(" not in src
