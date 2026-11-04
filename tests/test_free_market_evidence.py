import free_market_evidence as evidence

def test_prices_are_positive_and_explicitly_unverified():
    rows = [{"№ в базе": 70, "Товар": "Zestaw ściągaczy"}, {"№ в базе": 99, "Товар": "PDR"}]
    result = evidence.market_leads(rows)
    assert result
    assert all(x["Цена brutto PLN"] > 0 for x in result)
    assert all(x["Статус"].startswith("ОРИЕНТИР") for x in result)
    assert all(x["Дата проверки"] == "2026-11-04" for x in result)

def test_no_rows_outside_queue():
    assert evidence.market_leads([]) == []

def test_no_persistence_or_paid_actor():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "free_market_evidence.py").read_text()
    assert "save_analysis(" not in src
    assert "actors/" not in src
    assert "urlopen(" not in src
