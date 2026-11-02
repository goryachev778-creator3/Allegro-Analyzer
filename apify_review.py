"""Read-only Apify dataset retrieval and conservative offer validation.

This module NEVER starts paid Actor runs and NEVER writes to Neon.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

DATASET_PATTERN = re.compile(r"^[A-Za-z0-9]{8,64}$")


def fetch_dataset(dataset_id: str, token: str, limit: int = 50):
    """Fetch existing dataset; no Actor execution or paid scraping."""
    if not DATASET_PATTERN.fullmatch(dataset_id):
        raise ValueError("Неверный идентификатор набора Apify.")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("APIFY_TOKEN не настроен в Streamlit Secrets.")
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Допустимо 1–100 предложений.")
    url = ("https://api.apify.com/v2/datasets/" + dataset_id + "/items?"
           + urlencode({"format": "json", "clean": "true", "limit": limit}))
    request = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "AllegroAnalyzer/1.0",
    })
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError("Ответ Apify превышает 5 МБ; уменьшите число предложений.")
            items = json.loads(raw)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("Apify отклонил токен. Проверьте APIFY_TOKEN в Secrets.") from None
        if exc.code == 404:
            raise ValueError("Набор Apify не найден или недоступен.") from None
        raise ValueError("Не удалось прочитать Apify (HTTP ошибка).") from None
    except (URLError, TimeoutError):
        raise ValueError("Сервис Apify временно недоступен.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Apify вернул неподдерживаемые данные.") from None
    if not isinstance(items, list):
        raise ValueError("Ожидался массив предложений Apify.")
    return items


def _price(raw):
    try:
        result = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if result.is_finite() and result > 0:
        return float(result)
    return None


def review_offers(items):
    """Public, minimal view. Every record is unverified, no auto-price fills."""
    offers, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        link = str(item.get("url") or "")
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname not in ("allegro.pl", "www.allegro.pl") or not parsed.path.startswith("/oferta/"):
            continue
        price = _price(item.get("price"))
        if price is None or str(item.get("currency") or "").upper() != "PLN":
            continue
        if link in seen:
            continue
        seen.add(link)
        offers.append({
            "Название предложения": str(item.get("title") or "")[:250],
            "Цена brutto PLN": price,
            "Продавец": str(item.get("sellerLogin") or "")[:70],
            "Ссылка Allegro": link,
            "Сопоставление": "ТРЕБУЕТ ПРОВЕРКИ",
        })
    return offers
