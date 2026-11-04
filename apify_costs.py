"""Apify SilentFlow cost estimator: no API access and no paid Actor starts.

Prices checked 2026-11-04 from the official Actor Pricing page:
Free $2.75 per 1,000 offers + $0.005 per run.
Does not assert a user's remaining credit balance.
"""
from decimal import Decimal, ROUND_HALF_UP

UNIT_COST_USD = Decimal("0.00275")
RUN_COST_USD = Decimal("0.005")
MONTHLY_FREE_CREDITS_USD = Decimal("5.00")
UPDATED = "2026-11-04"


def cost_estimate(products, offers_each, runs=1, remaining_credits=None):
    if not (1 <= products <= 500 and 1 <= offers_each <= 100 and 1 <= runs <= 100):
        raise ValueError("Введите допустимое число товаров, предложений и запусков.")
    offers = products * offers_each
    total = (UNIT_COST_USD * offers + RUN_COST_USD * runs)
    if remaining_credits is not None:
        credit = Decimal(str(remaining_credits))
        if not credit.is_finite() or credit < 0:
            raise ValueError("Остаток кредитов должен быть неотрицательным.")
        extra = max(Decimal("0"), total - credit)
        fully_free = total <= credit
    else:
        extra = None
        fully_free = None
    return {
        "offers": offers,
        "cost_usd": total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "exact_cost_usd": total,
        "out_of_pocket_usd": extra.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if extra is not None else None,
        "fully_covered": fully_free,
    }
