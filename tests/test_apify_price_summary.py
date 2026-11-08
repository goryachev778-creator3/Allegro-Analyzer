from apify_price_summary import price_report

def test_all_41_categories_appear_even_when_actor_has_no_matches():
    rows = price_report([])
    assert len(rows) == 41
    assert len({r["Группа"] for r in rows}) == 41
    assert all(r["Цена для Neon"] is None for r in rows)
    assert all(r["Комиссия для Neon %"] is None for r in rows)

def test_unverified_or_wrong_sized_offers_do_not_set_prices():
    data = [
        {"Группа товара": 69, "Цена конкурента brutto PLN": 22, "Статус": "ПРЕДВАРИТЕЛЬНЫЙ КАНДИДАТ"},
        {"Группа товара": 69, "Цена конкурента brutto PLN": 19, "Статус": "ОТКЛОНИТЬ — несовпадение размера"},
        {"Группа товара": 70, "Цена конкурента brutto PLN": 58, "Статус": "ТРЕБУЕТ ПРОВЕРКИ"}
    ]
    summary = price_report(data)
    group69 = next(s for s in summary if s["Группа"] == 69)
    assert group69["Медиана конкурентов PLN"] == 22
    assert group69["Цена для Neon"] is None
    group70 = next(s for s in summary if s["Группа"] == 70)
    assert group70["Медиана конкурентов PLN"] is None

def test_no_database_write_or_paid_actor():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "apify_price_summary.py").read_text()
    assert "save_analysis(" not in src
    assert "urlopen(" not in src
    assert "/runs" not in src
