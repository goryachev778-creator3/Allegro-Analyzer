import pytest
from silentflow_import import normalize_silentflow_offers, DatasetFormatError


def offer():
    return {
        "id": "123", "dataType": "offer",
        "url": "https://allegro.pl/oferta/test-123",
        "title": "Fotel składany", "price": 599, "currency": "PLN",
        "categoryId": "20285", "categoryPath": "Dom i Ogród > Meble > Salon > Fotele",
        "parameters": {"Szerokość mebla": "63 cm", "Materiał korpusu": "metal"},
        "scrapedAt": "2026-10-21T17:14:24Z", "status": "ACTIVE",
    }


def test_review_rows_are_not_automatic_prices():
    row = normalize_silentflow_offers([offer()])[0]
    assert row["price_brutto_pln"] == 599
    assert row["match_status"] == "NEEDS_REVIEW"
    assert row["dimensions"] == {"Szerokość mebla": "63 cm"}
    assert row["construction"] == {"Materiał korpusu": "metal"}
    assert "commission_percent" not in row
    assert "_position_id" not in row


def test_rejects_unknown_domain():
    x = offer()
    x["url"] = "https://example.com/oferta/test-123"
    with pytest.raises(DatasetFormatError):
        normalize_silentflow_offers([x])


def test_deduplicates_offers():
    assert len(normalize_silentflow_offers([offer(), offer()])) == 1
