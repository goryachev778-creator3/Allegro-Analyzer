"""Explicit, capped Apify SilentFlow pilot.

Never runs on import. The caller must require a button press and a confirmed
FREE subscription. One 15-offer search and at most USD 0.06 of event charges.
Neon data are never edited.
"""
import json
import re
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import apify_usage
import apify_free_credits

ACTOR = "silentflow~allegro-scraper"
CAP_USD = Decimal("0.06")
MAX_ITEMS = 15
QUERY = "zestaw ściągaczy tapicerki demontaż radia samochodowego 38 elementów"
RUN_ID = re.compile(r"^[A-Za-z0-9]{8,64}$")


def verify_budget(token):
    limits = apify_usage.fetch_limits(token)
    entitlement = apify_free_credits.fetch_entitlement(token)
    remaining = apify_free_credits.prepaid_status(entitlement, limits["spent"], CAP_USD)
    if not remaining["fits"] or limits["headroom"] < CAP_USD:
        raise ValueError("Запуск запрещён: тариф Free или доступные бесплатные кредиты/лимит не подтверждены.")
    return remaining


def _request(url, token, payload=None):
    headers = {"Authorization": "Bearer " + token.strip(),
               "User-Agent": "AllegroAnalyzer/1.0",
               "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=json.dumps(payload).encode("utf-8") if payload is not None else None,
                  headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(req, timeout=40) as response:
            raw = response.read(500_001)
        if len(raw) > 500_000:
            raise ValueError("Слишком большой ответ Apify.")
        obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get("data"), dict):
            raise ValueError("Apify вернул неверную структуру ответа.")
        return obj["data"]
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("Apify отклонил токен или доступ к парсеру.") from None
        raise ValueError(f"Apify отклонил операцию (HTTP {exc.code}).") from None
    except (URLError, TimeoutError):
        raise ValueError("Нет ответа Apify; проверьте запуски в кабинете, прежде чем повторять.") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Apify вернул неверный ответ; прежде чем повторять, проверьте запуски.") from None


def start_pilot(token):
    verify_budget(token)
    # Both controls are necessary: maxItems alone does not cap PPE expenses,
    # while maxTotalChargeUsd may not cap PPR.
    params = urlencode({"maxItems": MAX_ITEMS, "maxTotalChargeUsd": "0.06",
                        "restartOnError": "false"})
    body = {"searchQueries": [QUERY], "country": "pl", "maxItems": MAX_ITEMS}
    run = _request("https://api.apify.com/v2/acts/" + ACTOR + "/runs?" + params, token, body)
    run_id = str(run.get("id") or "")
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Запуск отправлен, но Apify не вернул ID. Не повторяйте его.")
    return {"id": run_id, "status": str(run.get("status") or "UNKNOWN"),
            "dataset": str(run.get("defaultDatasetId") or "")}


def check_pilot(token, run_id):
    if not RUN_ID.fullmatch(str(run_id)):
        raise ValueError("Неверный идентификатор запуска.")
    run = _request("https://api.apify.com/v2/actor-runs/" + run_id, token)
    return {"status": str(run.get("status") or "UNKNOWN"),
            "dataset": str(run.get("defaultDatasetId") or "")}
