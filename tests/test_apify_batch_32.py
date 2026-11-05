from decimal import Decimal
from unittest.mock import patch
import apify_batch_32 as batch
import apify_batch_queries as queries
import pytest

def test_queries_cover_41_distinct_groups_and_skip_pilot():
    assert len(queries.SEARCHES) == 32
    assert len(queries.NOT_IDENTIFIABLE) == 9
    assert set(x[0] for x in queries.SEARCHES).isdisjoint(queries.NOT_IDENTIFIABLE)
    assert batch.MAX_RESULTS == 465
    assert batch.CAP == Decimal("1.60")

def test_budget_rejects_paid_or_insufficient():
    with patch.object(batch.apify_usage, "fetch_limits", return_value={"headroom": Decimal("1.59"), "spent": Decimal("0.10")}), patch.object(batch.apify_free_credits, "fetch_entitlement", return_value={"tier": "FREE", "included_usd": Decimal("5")}):
        with pytest.raises(ValueError):
            batch.check_free_budget("token")

def test_start_one_capped_run_without_repeating_pilot():
    with patch.object(batch, "check_free_budget", return_value={}), patch.object(batch, "_api", return_value={"data":{"id":"1234567890", "status":"READY", "defaultDatasetId":"abc123456789"}}) as called:
        result = batch.start_batch("token")
    url, _, inp = called.call_args.args
    assert result["id"] == "1234567890"
    assert "maxTotalChargeUsd=1.60" in url
    assert "maxItems=465" in url
    assert inp["maxItems"] == 465
    assert len(inp["searchQueries"]) == 31
    assert queries.SEARCHES[1][1] not in inp["searchQueries"]

def test_review_keeps_categories_but_not_commissions():
    fake = [{
        "searchQuery": queries.SEARCHES[0][1],
        "title": "Zestaw wierteł wykrętaki do uszkodzonych śrub",
        "url": "https://allegro.pl/oferta/test-123",
        "price": 21.99,
        "currency": "PLN",
        "categoryPath": "Dom i Ogród > Narzędzia",
        "categoryId": "123",
    }]
    report = batch.batch_review(fake)
    assert len(report) == 1
    assert report[0]["Komisja %" if "Komisja %" in report[0] else "Комиссия %"] is None
    assert "Narzędzia" in report[0]["Категория Allegro (из предложения)"]
    assert "ПРЕДВАРИТЕЛЬНЫЙ" in report[0]["Статус"]

def test_no_neon_writes():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"apify_batch_32.py").read_text()
    assert "save_analysis(" not in source
    assert "neon" not in source.lower().replace("no writes to neon; all results require review.", "")
