"""Create a transparent candidate-price summary from existing Apify offers.

This is not a verified selling-price or fee calculator. Data and Neon untouched.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median
from apify_batch_queries import SEARCHES, NOT_IDENTIFIABLE

def price_report(rows):
    groups = defaultdict(list)
    for row in rows:
        try:
            n = int(row.get("Группа товара"))
            val = Decimal(str(row.get("Цена конкурента brutto PLN")))
        except (ValueError, TypeError, InvalidOperation):
            continue
        if n not in {x[0] for x in SEARCHES} or not val.is_finite() or val <= 0:
            continue
        if row.get("Статус") != "ПРЕДВАРИТЕЛЬНЫЙ КАНДИДАТ":
            continue
        groups[n].append(float(val))
    summary = []
    for number, query in SEARCHES:
        vals = sorted(groups[number])
        summary.append({
            "Группа": number, "Поисковый запрос": query,
            "Кандидатов по названию": len(vals),
            "Минимум конкурентов PLN": round(vals[0],2) if vals else None,
            "Медиана конкурентов PLN": round(median(vals),2) if vals else None,
            "Максимум конкурентов PLN": round(vals[-1],2) if vals else None,
            "Цена для Neon": None,
            "Комиссия для Neon %": None,
            "Результат": "ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ ХАРАКТЕРИСТИК" if vals else "НЕТ ПОДТВЕРЖДЁННОГО АНАЛОГА",
        })
    for n in NOT_IDENTIFIABLE:
        summary.append({
            "Группа": n, "Поисковый запрос": "Не хватает данных о модели",
            "Кандидатов по названию": 0,
            "Минимум конкурентов PLN": None,
            "Медиана конкурентов PLN": None,
            "Максимум конкурентов PLN": None,
            "Цена для Neon": None,
            "Комиссия для Neon %": None,
            "Результат": "НУЖНО ФОТО / ХАРАКТЕРИСТИКИ",
        })
    return sorted(summary, key=lambda x:x["Группа"])
