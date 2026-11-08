"""Guarded application of independently verified Allegro price and commission.

Never invent a fee, derive it from a competing seller's category, or use a
keyword similarity score as identity verification. The caller must provide an
explicitly verified source-offer URL, unit price, category commission and
per-row confirmation. Only two monetary columns can change.
"""
from __future__ import annotations
from urllib.parse import urlparse
import math
import pandas as pd
from analyzer import number
from komertia_details import is_order_total

PRICE = "Цена Allegro PLN"
FEE = "Комиссия %"

def _finite(value, *, allow_zero=False):
    try:
        x = float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        raise ValueError("Неверное число цены или комиссии.")
    if not math.isfinite(x) or x < 0 or (not allow_zero and x == 0):
        raise ValueError("Цена и комиссия должны быть допустимыми числами.")
    return x

def build_review_rows(frame, raw_report, targets):
    """One representative offer per matching actual target row, never per blind group.
    
    The candidate is NOT checked until a person inspects title, photo, variant,
    and the chosen selling category. Pre-existing prices are never offered.
    """
    by_group = {}
    for offer in raw_report:
        if offer.get("Статус") != "ПРЕДВАРИТЕЛЬНЫЙ КАНДИДАТ":
            continue
        group = offer.get("Группа товара")
        if isinstance(group, str) and group.isdecimal():
            group = int(group)
        if not isinstance(group, int):
            continue
        by_group.setdefault(group, []).append(offer)
    rows = []
    for target in targets:
        pos = int(target["№ в базе"])
        # Canonical groups have two variants in this workspace (row n and n+41).
        # Never silently copy a result into both variants: display only
        # exact candidate row, with full original ID and row number.
        canonical = pos if pos >= 68 else pos + 41
        candidates = by_group.get(canonical, [])
        if not candidates or pos < 68:
            continue
        if number(frame.iloc[pos-1].get(PRICE)) != 0:
            continue
        # Pick lowest candidate only for preview; never auto-save it.
        item = min(candidates, key=lambda e: e["Цена конкурента brutto PLN"])
        rows.append({
            "№": pos,
            "_position_id": str(frame.iloc[pos-1].get("_position_id") or ""),
            "Товар": str(target.get("Товар") or ""),
            "Вариант": str(target.get("Вариант") or ""),
            "Предложение Allegro": item["Предложение Allegro"],
            "Ссылка Allegro": item["Ссылка Allegro"],
            "Цена-кандидат PLN": item["Цена конкурента brutto PLN"],
            "Цена продажи PLN": None,
            "Комиссия %": None,
            "Товар, комплект и категория проверены": False,
            "Комиссия проверена по тарифу Allegro": False,
        })
    return rows

def apply_verified(frame, decisions, expected_count=108):
    """Fail-closed immutable copy. Existing records, order and all other columns preserved."""
    if len(frame) != expected_count or PRICE not in frame or FEE not in frame or "_position_id" not in frame:
        raise ValueError("Состав Neon не совпадает с ожидаемыми 108 строками; запись отменена.")
    result = frame.copy(deep=True)
    seen = set()
    changed = 0
    for decision in decisions:
        if not decision.get("Товар, комплект и категория проверены") or not decision.get("Комиссия проверена по тарифу Allegro"):
            continue
        position = int(decision["№"])
        identity = str(decision.get("_position_id") or "")
        if position < 1 or position > len(result) or not identity:
            raise ValueError("Отсутствует идентификатор строки. Запись отменена.")
        if position in seen:
            raise ValueError("Повтор одного товара в решениях. Запись отменена.")
        seen.add(position)
        index = result.index[position-1]
        original = result.iloc[position-1]
        if is_order_total(original) or str(original.get("_position_id")) != identity:
            raise ValueError("Строка заказа или идентификатор изменились. Запись отменена.")
        if number(original.get(PRICE)) != 0 or number(original.get(FEE)) != 0:
            raise ValueError("В Neon уже есть цена или комиссия. Перезапись заблокирована.")
        link = str(decision.get("Ссылка Allegro") or "")
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname not in ("allegro.pl", "www.allegro.pl") or not parsed.path.startswith("/oferta/"):
            raise ValueError("Нет подтверждённой ссылки на Allegro. Запись отменена.")
        sale = _finite(decision.get("Цена продажи PLN"))
        fee = _finite(decision.get("Комиссия %"), allow_zero=True)
        if fee > 100:
            raise ValueError("Комиссия не может превышать 100%.")
        result.at[index, PRICE] = sale
        result.at[index, FEE] = fee
        changed += 1
    # There must be a real, deliberate change before writing to the database.
    if not changed:
        raise ValueError("Нет подтверждённых цен и комиссий для записи.")
    assert len(result) == len(frame)
    assert list(result["_position_id"]) == list(frame["_position_id"])
    return result, changed
