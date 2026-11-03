"""Free import of already-known Allegro offers, without paid scraping.

Never requests Allegro URLs or modifies Neon. Candidates are NOT validated prices.
"""
import io
import json
import pandas as pd
from apify_review import review_offers
from apify_targets import candidate_matches, dimensions

MAX_BYTES = 2_000_000
MAX_ROWS = 1000

ALIASES = {
    "title": ("Название предложения", "title", "name", "nazwa", "tytul", "tytuł"),
    "url": ("Ссылка Allegro", "url", "link", "oferta", "offer_url"),
    "price": ("Цена brutto PLN", "price", "cena", "cena brutto", "price_pln"),
    "currency": ("currency", "waluta"),
}

def _field(row, variants):
    canon = {str(k).strip().casefold(): v for k, v in row.items()}
    for key in variants:
        if key.casefold() in canon:
            return canon[key.casefold()]
    return None

def parse_offers(data, filename):
    """Validate a bounded user-supplied CSV or JSON and reuse Apify URL/price validation."""
    if len(data) > MAX_BYTES:
        raise ValueError("Файл больше 2 МБ.")
    if filename.lower().endswith(".json"):
        try:
            rows = json.loads(data.decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("Неверный JSON.") from exc
        if not isinstance(rows, list):
            raise ValueError("JSON должен содержать список предложений.")
        if len(rows) > MAX_ROWS:
            raise ValueError("Слишком много строк (максимум 1000).")
    elif filename.lower().endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", dtype=str,
                             keep_default_na=False, nrows=MAX_ROWS + 1,
                             encoding="utf-8-sig")
        except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
            raise ValueError("Неподдерживаемый формат CSV (нужен UTF-8).") from exc
        if len(df) > MAX_ROWS:
            raise ValueError("Слишком много строк (максимум 1000).")
        rows = df.to_dict(orient="records")
    else:
        raise ValueError("Допустимы CSV и JSON.")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _field(row, ALIASES["url"])
        title = _field(row, ALIASES["title"])
        price = _field(row, ALIASES["price"])
        currency = _field(row, ALIASES["currency"]) or "PLN"
        normalized.append({"url": url, "title": title, "price": price, "currency": currency})
    return review_offers(normalized)


def match_report(targets, offers):
    """Return candidates for manual comparison; never silently accept same-title offers."""
    result = []
    seen = set()
    for target in targets:
        for matched in candidate_matches(target, offers)[:3]:
            pair = (target.get("_position_id") or target["№ в базе"], matched["Ссылка Allegro"])
            if pair in seen:
                continue
            seen.add(pair)
            result.append({
                "№ в базе": target["№ в базе"],
                "Товар": target["Товар"],
                "Вариант": target["Вариант"],
                "Название предложения": matched["Предложение Allegro"],
                "Цена brutto PLN": matched["Цена brutto PLN"],
                "Ссылка Allegro": matched["Ссылка Allegro"],
                "Совпадение слов": matched["Совпадение слов"],
                "Размеры в названии товара": ", ".join(sorted(dimensions(target["Товар"] + " " + target["Вариант"]))),
                "Размеры в предложении": ", ".join(sorted(dimensions(matched["Предложение Allegro"]))),
                "Статус": "НЕ ПРОВЕРЕНО — цена не переносилась",
            })
    return result
