"""Read-only Apify account monthly usage and hard spending limit.

GET /v2/users/me/limits is documented by Apify. A hard-limit remainder
is NOT necessarily the remaining prepaid or free credit balance.
Never starts Actors, updates account limits, or writes Neon.
"""
import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://api.apify.com/v2/users/me/limits"


def _usd(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def fetch_limits(token):
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Токен Apify не настроен.")
    request = Request(API_URL, headers={
        "Authorization": "Bearer " + token.strip(),
        "Accept": "application/json",
        "User-Agent": "AllegroAnalyzer/1.0",
    }, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(500_001)
            if len(raw) > 500_000:
                raise ValueError("Слишком большой ответ Apify.")
            payload = json.loads(raw)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("Apify отклонил токен или недостаточно прав.") from None
        raise ValueError("Apify вернул HTTP ошибку при проверке лимитов.") from None
    except (URLError, TimeoutError):
        raise ValueError("Apify временно недоступен.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Неверный ответ Apify.") from None
    return parse_limits(payload)


def parse_limits(payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Нет данных о лимитах Apify.")
    current, limits, cycle = (
        data.get("current", {}), data.get("limits", {}),
        data.get("monthlyUsageCycle", {}),
    )
    if not isinstance(current, dict) or not isinstance(limits, dict):
        raise ValueError("Неверный формат лимитов Apify.")
    spent = _usd(current.get("monthlyUsageUsd"))
    ceiling = _usd(limits.get("maxMonthlyUsageUsd"))
    if spent is None or ceiling is None:
        raise ValueError("Apify не предоставил сумму расходов или месячный лимит.")
    headroom = max(Decimal("0"), ceiling - spent)
    return {
        "spent": spent,
        "limit": ceiling,
        "headroom": headroom,
        "cycle_start": str(cycle.get("startAt", "")) if isinstance(cycle, dict) else "",
        "cycle_end": str(cycle.get("endAt", "")) if isinstance(cycle, dict) else "",
    }
