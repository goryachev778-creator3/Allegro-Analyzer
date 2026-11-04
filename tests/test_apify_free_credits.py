from decimal import Decimal
import pytest
from apify_free_credits import parse_entitlement, prepaid_status

def test_free_included_credits_cover_estimate():
    entitlement = parse_entitlement({"data": {"plan": {"tier": "FREE", "monthlyUsageCreditsUsd": 5}}})
    result = prepaid_status(entitlement, Decimal("0.02"), Decimal("1.70"))
    assert result["free"] is True
    assert result["remaining"] == Decimal("4.98")
    assert result["fits"] is True

def test_paid_plan_never_marked_free():
    entitlement = parse_entitlement({"data": {"plan": {"tier": "STARTER", "monthlyUsageCreditsUsd": 19}}})
    assert prepaid_status(entitlement, 0, 1)["fits"] is False

def test_unknown_plan_fails_closed():
    with pytest.raises(ValueError):
        parse_entitlement({"data": {"plan": {"tier": "FREE"}}})

def test_no_paid_actions_or_neon_writes():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "apify_free_credits.py").read_text()
    assert 'method="GET"' in src
    assert "save_analysis(" not in src
    assert "/runs" not in src
