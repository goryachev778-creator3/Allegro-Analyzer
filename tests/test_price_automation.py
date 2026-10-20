import pandas as pd
import pytest
from price_automation import preview_updates, ProposalError

def sample():
    return pd.DataFrame([
        {"_position_id": "a", "Закупка PLN": 326.14, "Цена Allegro PLN": 0, "Комиссия %": 0},
        {"_position_id": "b", "Закупка PLN": 25, "Цена Allegro PLN": 99, "Комиссия %": 10},
    ])

def proposal(key="a"):
    return {"_position_id": key, "price_brutto_pln": 549, "commission_percent": 11.07,
            "source_url": "https://allegro.pl/oferta/example", "category": "Fotele",
            "checked_at": "2026-10-20", "verified": True}

def test_preserves_positions_and_costs():
    before = sample()
    after, audit = preview_updates(before, [proposal()])
    assert len(after) == len(before)
    assert after["_position_id"].tolist() == before["_position_id"].tolist()
    assert after["Закупка PLN"].equals(before["Закупка PLN"])
    assert after.loc[0, "Цена Allegro PLN"] == 549
    assert after.loc[0, "Комиссия %"] == 11.07
    assert before.loc[0, "Цена Allegro PLN"] == 0
    assert audit[0]["status"] == "ready"

def test_does_not_overwrite_old_prices():
    after, audit = preview_updates(sample(), [proposal("b")])
    assert after.loc[1, "Цена Allegro PLN"] == 99
    assert audit[0]["status"] == "skipped_existing"

def test_rejects_unknown_ids_and_duplicate_proposals():
    with pytest.raises(ProposalError):
        preview_updates(sample(), [proposal("missing")])
    with pytest.raises(ProposalError):
        preview_updates(sample(), [proposal(), proposal()])

def test_requires_evidence():
    p = proposal()
    p["source_url"] = "https://example.com/"
    with pytest.raises(ProposalError):
        preview_updates(sample(), [p])
