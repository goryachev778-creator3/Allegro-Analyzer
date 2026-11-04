from decimal import Decimal
import pytest
from apify_usage import parse_limits, _usd

def test_limit_is_not_free_balance():
    data = {"data": {"limits": {"maxMonthlyUsageUsd": 5},
                     "current": {"monthlyUsageUsd": 1.2},
                     "monthlyUsageCycle": {"startAt": "2026-11-01", "endAt": "2026-11-30"}}}
    result = parse_limits(data)
    assert result["headroom"] == Decimal("3.8")
    assert "free_balance" not in result

def test_missing_limit_rejected():
    with pytest.raises(ValueError):
        parse_limits({"data": {"limits": {}, "current": {"monthlyUsageUsd": 1}}})

def test_invalid_numeric_rejected():
    assert _usd("-1") is None
    assert _usd("NaN") is None

def test_no_mutating_api_calls():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "apify_usage.py").read_text()
    assert "method=\"GET\"" in source
    assert "method=\"POST\"" not in source
    assert "save_analysis(" not in source
    assert "/runs" not in source
