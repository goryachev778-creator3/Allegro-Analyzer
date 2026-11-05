"""Single capped SilentFlow batch for 32 queryable product groups.

Explicit on-click only. Fails closed if the user is not on the Free plan or
prepaid credits are insufficient. No writes to Neon; all results require review.
"""
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import re

import apify_usage
import apify_free_credits
import apify_batch_queries

CAP = Decimal("1.60")  # pilot was capped at $0.06; combined caps < $1.70 authorization
MAX_RESULTS = 480
RUN_ID = re.compile(r"^[A-Za-z0-9]{8,64}$")
ACTOR = "silentflow~allegro-scraper"

def check_free_budget(token):
    limits = apify_usage.fetch_limits(token)
    entitlement = apify_free_credits.fetch_entitlement(token)
    prepaid = apify_free_credits.prepaid_status(entitlement, limits["spent"], CAP)
    if not prepaid["fits"] or limits["headroom"] < CAP:
        raise ValueError("Не подтверждены свободные кредиты Free и месячный лимит на $1,60. Запуск заблокирован.")
    return prepaid

def _api(url, token, payload=None):
    req = Request(url, data=json.dumps(payload).encode("utf-8") if payload is not None else None,
                  method="POST" if payload is not None else "GET",
                  headers={"Authorization": "Bearer " + token.strip(),
                           "Accept": "application/json",
                           "Content-Type": "application/json",
                           "User-Agent": "AllegroAnalyzer/1.0"})
    try:
        with urlopen(req, timeout=40) as resp:
            raw = resp.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError("Ответ Apify слишком большой.")
        return json.loads(raw)
    except HTTPError as exc:
        raise ValueError(f"Apify ответил HTTP {exc.code}. Проверьте Runs перед повтором.") from None
    except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Не удалось получить ответ Apify. Не запускайте повторно, пока не проверите Runs.") from None

def start_batch(token):
    check_free_budget(token)
    params = urlencode({"maxItems": MAX_RESULTS, "maxTotalChargeUsd": str(CAP),
                        "restartOnError": "false"})
    request = {"searchQueries": apify_batch_queries.queries(), "country": "pl", "maxItems": MAX_RESULTS}
    response = _api("https://api.apify.com/v2/acts/" + ACTOR + "/runs?" + params, token, request)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or not RUN_ID.fullmatch(str(data.get("id") or "")):
        raise ValueError("Статус запуска неизвестен. Не повторяйте его без проверки Runs.")
    return {"id": data["id"], "status": data.get("status", "UNKNOWN"),
            "dataset": data.get("defaultDatasetId") or ""}

def check_batch(token, run_id):
    if not RUN_ID.fullmatch(str(run_id)):
        raise ValueError("Неверный Run ID.")
    response = _api("https://api.apify.com/v2/actor-runs/" + str(run_id), token)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Нет статуса Apify.")
    return {"id": str(run_id), "status": str(data.get("status") or "UNKNOWN"),
            "dataset": str(data.get("defaultDatasetId") or ""), "usage": data.get("usageTotalUsd")}

def read_batch(token, dataset, total=MAX_RESULTS):
    if not RUN_ID.fullmatch(str(dataset)):
        raise ValueError("Неверный Dataset ID.")
    if not 1 <= total <= MAX_RESULTS:
        raise ValueError("Слишком большой объём.")
    items = []
    for offset in range(0, total, 40):
        count = min(40, total - offset)
        url = ("https://api.apify.com/v2/datasets/" + dataset + "/items?" +
               urlencode({"format":"json", "clean":"true", "offset":offset, "limit":count}))
        page = _api(url, token)
        if not isinstance(page, list):
            raise ValueError("Неверный формат результатов.")
        items.extend(page)
        if len(page) < count:
            break
    return items

def batch_review(items):
    from apify_targets import words, dimensions
    from urllib.parse import urlparse
    from strict_38_review import review_38_piece
    query_index = {q.casefold(): (n, q) for n, q in apify_batch_queries.SEARCHES}
    results, seen = [], set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        query = str(raw.get("searchQuery") or "").strip().casefold()
        pair = query_index.get(query)
        if not pair:
            continue
        number, original = pair
        title = str(raw.get("title") or "")
        link = str(raw.get("url") or "")
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname not in ("allegro.pl", "www.allegro.pl") or not parsed.path.startswith("/oferta/"):
            continue
        if str(raw.get("currency") or "").upper() != "PLN":
            continue
        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 0 or not (price < float("inf")):
            continue
        if (number, link) in seen:
            continue
        seen.add((number, link))
        a, b = set(words(original)), set(words(title))
        overlap = len(a & b)
        dims_a, dims_b = dimensions(original), dimensions(title)
        mismatch = bool(dims_a and dims_b and dims_a.isdisjoint(dims_b))
        state = ("ОТКЛОНИТЬ — несовпадение размера" if mismatch else
                 "ПРЕДВАРИТЕЛЬНЫЙ КАНДИДАТ" if overlap >= 2 else
                 "НЕПОДТВЕРЖДЁННОЕ СОВПАДЕНИЕ")
        if number == 70:
            passed, rejected, unsure = review_38_piece([{"Название предложения": title}])
            if rejected:
                state = "ОТКЛОНИТЬ — не 38 предметов"
            elif unsure:
                state = "ТРЕБУЕТ ПРОВЕРКИ — число предметов не указано"
        results.append({
            "Группа товара": number, "Запрос": original,
            "Предложение Allegro": title, "Цена конкурента brutto PLN": price,
            "Категория Allegro (из предложения)": str(raw.get("categoryPath") or raw.get("categoryName") or ""),
            "Категория ID": str(raw.get("categoryId") or ""),
            "Ссылка Allegro": link, "Статус": state,
            "Комиссия %": None,
            "Примечание": "Категория конкурента НЕ определяет нашу комиссию без выбора категории собственной оферты",
        })
    return sorted(results, key=lambda r: (r["Группа товара"], r["Цена конкурента brutto PLN"]))
