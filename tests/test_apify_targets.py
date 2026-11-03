"""No paid jobs and no writes: only generate an unpriced queue."""
import pandas as pd
from apify_targets import words, dimensions, target_queue, candidate_matches


def test_dimensions_normalize_and_distinguish():
    assert dimensions("Sofa 120x200 cm") == {"120x200"}
    assert dimensions("Sofa 90x200 cm") != dimensions("Sofa 120x200 cm")


def test_queue_excludes_priced_and_preserves_id(monkeypatch):
    import product_archive
    monkeypatch.setattr(product_archive, "active_mask", lambda frame: pd.Series([True, True], index=frame.index))
    table = pd.DataFrame([
        {"_position_id": "first", "Produkt": "Wysuwany fotel", "Wariant": "czarny", "Цена Allegro PLN": None, "Закупка PLN": 20},
        {"_position_id": "second", "Produkt": "Stolik", "Wariant": "duzy", "Цена Allegro PLN": 60, "Закупка PLN": 30},
    ])
    target = target_queue(table)
    assert len(target) == 1 and target[0]["_position_id"] == "first"
    assert target[0]["№ в базе"] == 1


def test_contradictory_dimensions_rejected():
    target = {"Товар": "sofa rozkladana 120x200 cm", "Вариант": "pianka"}
    offers = [
        {"Название предложения": "sofa rozkladana pianka 90x200 cm", "Цена brutto PLN": 500, "Ссылка Allegro": "https://allegro.pl/oferta/1"}
    ]
    assert candidate_matches(target, offers) == []


def test_no_write_or_actor_start():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "apify_targets.py").read_text()
    assert "save_analysis(" not in source
    assert "fetch_dataset(" not in source
    assert "/runs" not in source
