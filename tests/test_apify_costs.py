from decimal import Decimal
from apify_costs import cost_estimate

def test_41_products_15_offers():
    res = cost_estimate(41, 15)
    assert res["offers"] == 615
    assert res["exact_cost_usd"] == Decimal("1.69625")
    assert res["cost_usd"] == Decimal("1.70")
    assert res["fully_covered"] is None

def test_only_known_credits_are_subtracted():
    assert cost_estimate(41, 15, remaining_credits=1)["fully_covered"] is False
    assert cost_estimate(41, 15, remaining_credits=5)["fully_covered"] is True
    assert cost_estimate(41, 15, remaining_credits=1)["out_of_pocket_usd"] == Decimal("0.70")

def test_not_an_actor_or_neon_write():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "apify_costs.py").read_text()
    assert "save_analysis(" not in source
    assert "urlopen(" not in source
    assert "actor_runs" not in source
