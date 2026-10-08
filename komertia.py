"""Convert Komertia's batch quote into per-unit PLN costs."""
import re
import unicodedata
from analyzer import number


def normalize(label):
    label = str(label).lower().replace('ł', 'l')
    label = ''.join(c for c in unicodedata.normalize('NFKD', label) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', label)


def columns(raw):
    names = {normalize(c): c for c in raw.columns}
    aliases = {
        'quantity': ['ilosc'], 'price': ['cena'], 'value': ['wartosc'],
        'extra': ['kosztdod', 'kosztydod', 'kosztdodatkowy', 'kosztydodatkowe'],
        'shipping': ['trclo', 'transportclo'], 'customs': ['odprawahs', 'hsodprawa'],
        'total': ['razem'],
    }
    return {key: next((names[n] for n in choices if n in names), None) for key, choices in aliases.items()}


def apply_costs(frame, raw):
    detected = columns(raw)
    if not detected['quantity'] or not detected['total']:
        raise ValueError('Для полной себестоимости Komertia нужны колонки Ilość и Razem.')
    result = frame.copy()
    qty = raw[detected['quantity']].map(number)
    if (qty <= 0).any():
        raise ValueError('Нулевые позиции должны быть исключены до расчёта расходов.')
    def amount(key):
        return raw[detected[key]].map(number) / qty if detected[key] else qty * 0
    purchase = amount('value') if detected['value'] else raw[detected['price']].map(number) if detected['price'] else result['Закупка PLN']
    total = amount('total')
    shipping, customs = amount('shipping'), amount('customs')
    residual = total - purchase - shipping - customs
    if (residual < -0.02).any():
        raise ValueError('Расходы превышают Razem. Проверьте суммы выгрузки Komertia.')
    result['Закупка PLN'] = purchase
    result['Доставка PLN'] = shipping  # Includes duty already; do not charge it again.
    result['Пошлина %'] = 0.0
    result['Оформление PLN'] = customs
    result['Доп. расходы PLN'] = residual.clip(lower=0)
    result['Невозмещаемый НДС PLN'] = 0.0
    return result
