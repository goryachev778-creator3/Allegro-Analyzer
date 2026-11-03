"""Read-only queue of unpriced Allegro Analyzer products, with cautious matches.

No database writes or paid Apify Actor starts.
"""
from __future__ import annotations
import re
import unicodedata
from urllib.parse import quote
from analyzer import number
from komertia_details import is_order_total
import product_archive

STOPWORDS = {
    "do", "na", "bez", "dla", "oraz", "pod", "nad", "od", "z", "w", "i",
    "the", "with", "for", "new", "nowy", "nowa", "nowe", "transgraniczna",
    "transgraniczny", "cross", "border", "amazon", "najlepiej",
    "sprzedajaca", "sie", "kolor", "czarny", "bialy", "czarna", "biala",
}
DIMENSIONS = re.compile(r"(?<!\\d)\\d{1,4}(?:[.,]\\d+)?\\s*(?:cm|mm|m|kg|g|l|ml|x\\s*\\d{1,4})(?!\\w)", re.I)


def words(value):
    txt = unicodedata.normalize("NFKD", str(value or "")).casefold()
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", txt) if len(w) > 2 and w not in STOPWORDS]


def dimensions(value):
    txt = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return set(re.sub(r"\\s+", "", m.group()) for m in DIMENSIONS.finditer(txt))


def target_queue(frame):
    """Preserve original row order and identity; never include order-total rows."""
    active = product_archive.active_mask(frame)
    results = []
    for idx, row in frame.iterrows():
        if not bool(active.loc[idx]) or is_order_total(row):
            continue
        if number(row.get("Цена Allegro PLN")) != 0:
            continue
        name = str(row.get("Produkt") or "").strip()
        variant = str(row.get("Wariant") or "").strip()
        terms = words(name)
        # Search is based on product attributes, not wholesale supplier noise.
        query = " ".join(terms[:7] + words(variant)[:3])
        results.append({
            "№ в базе": idx + 1,
            "_position_id": row.get("_position_id"),
            "Товар": name,
            "Вариант": variant,
            "Закупка PLN": row.get("Закупка PLN"),
            "Запрос Allegro": query,
            "Поиск Allegro": "https://allegro.pl/listing?string=" + quote(query),
            "Статус": "ЦЕНА НЕ УСТАНОВЛЕНА",
        })
    return results


def candidate_matches(target, offers):
    """Propose candidates, not verified product equivalents or sell prices.

    Reject obvious measurement contradictions; title-only overlap is insufficient
    to confirm construction, size, material and package quantity.
    """
    source = (target.get("Товар", "") + " " + target.get("Вариант", ""))
    source_terms = set(words(source))
    source_dimensions = dimensions(source)
    matches = []
    for offer in offers:
        title = str(offer.get("Название предложения") or "")
        title_terms = set(words(title))
        if not source_terms or not title_terms:
            continue
        common = source_terms & title_terms
        if len(common) < 2:
            continue
        offer_dimensions = dimensions(title)
        if source_dimensions and offer_dimensions and source_dimensions.isdisjoint(offer_dimensions):
            continue
        score = round(len(common) / max(1, len(source_terms | title_terms)), 3)
        matches.append({
            "Товар": target["Товар"],
            "Предложение Allegro": title,
            "Цена brutto PLN": offer["Цена brutto PLN"],
            "Ссылка Allegro": offer["Ссылка Allegro"],
            "Совпадение слов": score,
            "Проверка": "НЕ ПОДТВЕРЖДЕНО — сверить размеры, материал, конструкцию, комплект",
        })
    return sorted(matches, key=lambda r: r["Совпадение слов"], reverse=True)
