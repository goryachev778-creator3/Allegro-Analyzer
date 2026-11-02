import pytest
import apify_review


def test_review_offers_filters_duplicates_and_non_allegro():
    items = [
        {"url":"https://allegro.pl/oferta/abc-123", "title":"Fotel", "price": "599", "currency":"PLN", "sellerLogin":"seller"},
        {"url":"https://allegro.pl/oferta/abc-123", "title":"Same", "price": 300, "currency":"PLN"},
        {"url":"https://evil.example/oferta/abc", "title":"Phishing", "price": 100, "currency":"PLN"},
        {"url":"https://allegro.pl/oferta/abc-124", "price": 100, "currency":"EUR"},
    ]
    result=apify_review.review_offers(items)
    assert len(result)==1 and result[0]["Цена brutto PLN"]==599
    assert result[0]["Сопоставление"]=="ТРЕБУЕТ ПРОВЕРКИ"


def test_dataset_id_validation_happens_before_network():
    with pytest.raises(ValueError):
        apify_review.fetch_dataset("../foo", "token")


def test_no_api_token_in_url_and_no_paid_runs():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/"apify_review.py").read_text()
    assert '"Authorization": "Bearer " + token' in text
    assert "/runs" not in text and "run-sync" not in text
    assert "token=" not in text
