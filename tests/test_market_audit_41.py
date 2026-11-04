from market_audit_41 import audit_unpriced

def test_canonical_dedup_and_price_is_not_a_sale_price():
    rows = [
        {"№ в базе": 29, "Товар": "skrót", "Вариант": "X", "Закупка PLN": 3},
        {"№ в базе": 70, "Товар": "zestaw tapicerki 38", "Вариант": "Czerwony", "Закупка PLN": 3},
        {"№ в базе": 68, "Товар": "wzrost nowych mebli", "Вариант": "", "Закупка PLN": 2},
    ]
    out = audit_unpriced(rows)
    assert len(out) == 2
    assert out[1]["Группа"] == 70
    assert out[1]["Товар"] == "zestaw tapicerki 38"
    assert out[1]["Статус"] == "РЫНОЧНЫЙ ОРИЕНТИР — НЕ ПЕРЕНОСИТЬ"
    assert out[0]["Статус"] == "НЕОПОЗНАННЫЙ ТОВАР"

def test_no_autowrite_or_paid_actor():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "market_audit_41.py").read_text()
    assert "save_analysis(" not in source
    assert "urlopen(" not in source
    assert "actors/" not in source
