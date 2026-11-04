"""Confirm prepaid Apify Free plan entitlement without starting Actors.

Only GET /v2/users/me, parse plan.tier and monthlyUsageCreditsUsd.
Combine with existing /limits monthlyUsageUsd to estimate prepaid remaining.
No private account attributes are returned to UI.
"""
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json

def _decimal(value):
    try:
        val = Decimal(str(value))
        return val if val.is_finite() and val >= 0 else None
    except (ValueError, TypeError, InvalidOperation):
        return None

def parse_entitlement(payload):
    data = payload.get("data") if isinstance(payload, dict) else None
    plan = data.get("plan") if isinstance(data, dict) else None
    if not isinstance(plan, dict):
        raise ValueError("Apify не вернул данные о тарифе.")
    tier = str(plan.get("tier") or "").strip().upper()
    credits = _decimal(plan.get("monthlyUsageCreditsUsd"))
    if not tier or credits is None:
        raise ValueError("Apify не вернул тип тарифа и включённые кредиты.")
    return {"tier": tier, "included_usd": credits}

def fetch_entitlement(token):
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Нет API-токена Apify.")
    req = Request("https://api.apify.com/v2/users/me", headers={
        "Authorization": "Bearer " + token.strip(),
        "Accept": "application/json",
        "User-Agent": "AllegroAnalyzer/1.0",
    }, method="GET")
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read(500_001)
        if len(raw) > 500_000:
            raise ValueError("Слишком большой ответ Apify.")
        return parse_entitlement(json.loads(raw))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("Apify отклонил токен для проверки тарифа.") from None
        raise ValueError("Apify не ответил на запрос тарифа.") from None
    except (URLError, TimeoutError):
        raise ValueError("Apify временно недоступен.") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Apify вернул неподдерживаемый ответ.") from None

def prepaid_status(entitlement, spent, estimated_cost):
    spent = _decimal(spent)
    price = _decimal(estimated_cost)
    if spent is None or price is None:
        raise ValueError("Недоступны корректные суммы.")
    free = entitlement["tier"] == "FREE"
    prepaid = entitlement["included_usd"]
    remaining = max(Decimal("0"), prepaid - spent)
    return {
        "free": free, "tier": entitlement["tier"], "included": prepaid,
        "remaining": remaining, "fits": free and remaining >= price,
    }
