"""Validate external Allegro price proposals before applying them to an analysis frame.

This module has NO network calls and NEVER commits to Neon by itself.
An external collector (Apify / n8n) must provide verified price proposals.
Each proposal must carry the original stable _position_id from the analysis.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import pandas as pd

PRICE = "Цена Allegro PLN"
COMMISSION = "Комиссия %"
POSITION = "_position_id"


class ProposalError(ValueError):
    pass


def _decimal(value, name, maximum=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ProposalError(f"Invalid {name}") from None
    if not result.is_finite() or result < 0 or (maximum is not None and result > maximum):
        raise ProposalError(f"Out-of-range {name}")
    return float(result)


def preview_updates(frame: pd.DataFrame, proposals: list[dict], *, replace_existing=False):
    """Return (updated frame, audit records). Do not save; caller controls commit.

    Required fields: _position_id, price_brutto_pln, commission_percent,
    source_url, category, checked_at, verified (must be True).
    Commission is expressed as a percent *inclusive of any unrecoverable VAT*
    on the Allegro commission; it is NOT a fraction between 0 and 1.
    """
    if POSITION not in frame or frame[POSITION].isna().any():
        raise ProposalError("Missing stable position IDs")
    result = frame.copy(deep=True)
    ids = result[POSITION].astype(str)
    if ids.duplicated().any():
        raise ProposalError("Duplicate IDs in source analysis")
    lookup = {key: index for index, key in zip(result.index, ids)}
    seen = set()
    audit = []
    for p in proposals:
        key = str(p.get(POSITION, ""))
        if not key or key not in lookup:
            raise ProposalError(f"Unknown position ID: {key}")
        if key in seen:
            raise ProposalError(f"Duplicate proposal: {key}")
        seen.add(key)
        if p.get("verified") is not True:
            audit.append({"id": key, "status": "skipped_unverified"})
            continue
        if not all(p.get(field) for field in ("source_url", "category", "checked_at")):
            raise ProposalError(f"Missing evidence: {key}")
        url = str(p["source_url"])
        if not url.startswith("https://allegro.pl/"):
            raise ProposalError(f"Source must be allegro.pl: {key}")
        price = _decimal(p.get("price_brutto_pln"), PRICE)
        commission = _decimal(p.get("commission_percent"), COMMISSION, 100)
        if price <= 0:
            raise ProposalError(f"Zero price: {key}")
        idx = lookup[key]
        original_price = pd.to_numeric(pd.Series([result.at[idx, PRICE]]), errors="coerce").iloc[0]
        original_comm = pd.to_numeric(pd.Series([result.at[idx, COMMISSION]]), errors="coerce").iloc[0]
        if not replace_existing and ((pd.notna(original_price) and original_price > 0)
                                     or (pd.notna(original_comm) and original_comm > 0)):
            audit.append({"id": key, "status": "skipped_existing"})
            continue
        result.at[idx, PRICE] = price
        result.at[idx, COMMISSION] = commission
        audit.append({"id": key, "status": "ready", "price": price,
                      "commission": commission, "source_url": url,
                      "checked_at": p["checked_at"], "category": p["category"]})
    if len(result) != len(frame) or not result[POSITION].astype(str).equals(ids):
        raise ProposalError("Position count/order changed")
    untouched = [c for c in frame.columns if c not in (PRICE, COMMISSION)]
    if not result[untouched].equals(frame[untouched]):
        raise ProposalError("Protected columns changed")
    return result, audit
