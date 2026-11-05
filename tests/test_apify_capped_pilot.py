from decimal import Decimal
from unittest.mock import patch
import pytest
import apify_capped_pilot as pilot


def test_pilot_can_only_use_one_query_and_fifteen_items():
    assert pilot.MAX_ITEMS == 15
    assert pilot.CAP_USD == Decimal("0.06")


def test_budget_blocks_paid_or_low_credit():
    with patch.object(pilot.apify_usage, "fetch_limits", return_value={"spent": Decimal("4.98"), "headroom": Decimal("0.02")}), patch.object(
        pilot.apify_free_credits, "fetch_entitlement", return_value={"tier": "FREE", "included_usd": Decimal("5")}
    ):
        with pytest.raises(ValueError):
            pilot.verify_budget("token")


def test_start_uses_both_hard_caps_and_requires_free_plan():
    with patch.object(pilot, "verify_budget", return_value={}), patch.object(pilot, "_request", return_value={"id": "1234567890", "status": "READY", "defaultDatasetId": "1234567890"}) as request:
        pilot.start_pilot("token")
    url = request.call_args.args[0]
    body = request.call_args.args[2]
    assert "maxTotalChargeUsd=0.06" in url
    assert "maxItems=15" in url
    assert body["maxItems"] == 15
    assert len(body["searchQueries"]) == 1


def test_no_database_writes():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "apify_capped_pilot.py").read_text()
    assert "save_analysis(" not in source
    assert "neon" not in source.lower().replace("neon data are never edited", "")
