import json
import pytest
from free_offer_import import parse_offers, match_report

URL = "https://allegro.pl/oferta/zestaw-123456"

def test_csv_valid_aliases():
    raw = ("nazwa;cena;link\\nZestaw narzedzi demontaz tapicerki;58,24;" + URL + "\\n").replace("\\n", "\n").encode()
    parsed = parse_offers(raw, "offers.csv")
    assert len(parsed) == 1
    assert parsed[0]["Цена brutto PLN"] == 58.24

def test_json_invalid_website_dropped():
    raw = json.dumps([{"title": "demo", "price": 50, "currency": "PLN", "url": "https://evil.test/oferta/1"}]).encode()
    assert parse_offers(raw, "offers.json") == []

def test_refuses_oversized_file():
    with pytest.raises(ValueError):
        parse_offers(b"x"*2_000_001, "offers.csv")

def test_does_not_infer_commission():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "free_offer_import.py").read_text()
    assert "save_analysis(" not in src
    assert "urlopen(" not in src
    assert "actors/" not in src
