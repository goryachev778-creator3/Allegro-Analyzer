"""Transform SilentFlow Apify datasets into auditable Allegro offer candidates.

No prices are written to the analyser here. Review and verify product equivalence
first; commissions are supplied separately from verified Allegro tariffs.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse


class DatasetFormatError(ValueError):
    pass


def _price(value):
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DatasetFormatError("Invalid offer price") from None
    if not v.is_finite() or v <= 0:
        raise DatasetFormatError("Offer price must be positive")
    return float(v)


def normalize_silentflow_offers(items):
    """Return review-ready rows; omit seller identity and contact details."""
    if not isinstance(items, list):
        raise DatasetFormatError("Expected a JSON array of offers")
    seen = set()
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get("dataType") != "offer":
            continue
        url = str(item.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "allegro.pl" or not parsed.path.startswith("/oferta/"):
            raise DatasetFormatError("Invalid Allegro offer URL")
        offer_id = str(item.get("id") or "")
        if not offer_id or offer_id in seen:
            continue
        seen.add(offer_id)
        if item.get("currency") != "PLN":
            raise DatasetFormatError("Unexpected currency")
        ts = item.get("scrapedAt")
        try:
            datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise DatasetFormatError("Missing or invalid scrape timestamp") from None
        params = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        result.append({
            "offer_id": offer_id,
            "offer_title": str(item.get("title") or ""),
            "price_brutto_pln": _price(item.get("price")),
            "lowest_delivery_pln": item.get("lowestDeliveryPrice"),
            "category_id": str(item.get("categoryId") or ""),
            "category_path": str(item.get("categoryPath") or ""),
            "dimensions": {key: value for key, value in params.items()
                           if any(word in key.lower() for word in ("długość", "szerokość", "wysokość", "głębokość", "rozmiar"))},
            "construction": {key: value for key, value in params.items()
                             if any(word in key.lower() for word in ("korpus", "materiał", "rodzaj"))},
            "status": item.get("status"),
            "sponsored": bool(item.get("isSponsored")),
            "search_query": str(item.get("searchQuery") or ""),
            "source_url": url,
            "scraped_at": ts,
            "match_status": "NEEDS_REVIEW",
        })
    return result
