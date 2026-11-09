"""Official Allegro.pl main-category commission ranges (NET, 2026-11-09).

Ranges from https://help.allegro.com/pl/fees/pl?marketplaceId=allegro-pl.
These are NOT exact subcategory fees; no automated write to Neon.
Gross fee includes standard 23% Polish VAT on platform fees for a seller
who cannot deduct that VAT. Fee bases may include buyer-paid delivery,
and promotions, caps and category-specific mechanics may alter totals.
"""
from __future__ import annotations
import re
import unicodedata

RANGES = {
    "dom i ogrod": (4.5, 11.0),
    "dziecko": (5.0, 11.5),
    "elektronika": (2.5, 8.0),
    "firma i uslugi": (4.5, 10.5),
    "kolekcje i sztuka": (3.0, 14.0),
    "kultura i rozrywka": (5.0, 8.5),
    "moda": (None, 11.5), # tiered: do not claim a fixed minimum
    "motoryzacja": (4.5, 16.0),
    "sport i turystyka": (8.0, 11.5),
    "supermarket": (5.0, 10.5),
    "uroda": (8.0, 10.0),
    "zdrowie": (1.0, 13.0),
    "pozostale i akcesoria": (13.0, 17.0),
}

def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(c for c in value if not unicodedata.combining(c)).strip()

def fee_range(category, value_pln=None):
    """Return a range of advertised NET fee rates, not an exact calculation."""
    root = normalize(category).split(">")[0].strip()
    if root not in RANGES:
        return {"Dział Allegro": root or "BRAK KATEGORII",
                "Prowizja netto — min %": None, "Prowizja netto — max %": None,
                "Prowizja z VAT — min %": None, "Prowizja z VAT — max %": None,
                "Status opłaty": "BRAK ZIDENTYFIKOWANEJ KATEGORII"}
    lo, hi = RANGES[root]
    return {"Dział Allegro": root,
            "Prowizja netto — min %": lo,
            "Prowizja netto — max %": hi,
            "Prowizja z VAT — min %": round(lo * 1.23, 3) if lo is not None else None,
            "Prowizja z VAT — max %": round(hi * 1.23, 3),
            "Status opłaty": "ZAKRES OGÓLNY — NIE WPISYWAĆ DO NEON"}

def with_fee_ranges(report):
    """Enrich current candidate quotes with informational official fee ranges."""
    return [{**row, **fee_range(row.get("Категория Allegro (из предложения)"))}
            for row in report]
