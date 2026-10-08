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
        'total': ['razem'], 'final_unit': ['cenaszt', 'cenasztpln', 'cenazaszt', 'cenazasztuke'],
    }
    return {key: next((names[n] for n in choices if n in names), None) for key, choices in aliases.items()}


def apply_costs(frame, raw):
    detected = columns(raw)
    result = frame.copy()
    if detected['final_unit']:
        final = raw[detected['final_unit']].map(number)
    elif detected['quantity'] and detected['total']:
        qty = raw[detected['quantity']].map(number)
        if (qty <= 0).any():
            raise ValueError('Нулевые позиции должны быть исключены до расчёта расходов.')
        final = raw[detected['total']].map(number) / qty
    else:
        raise ValueError('Нужна окончательная Cena szt. либо Ilość и Razem.')
    result['Закупка PLN'] = final
    for column in ('Доставка PLN', 'Пошлина %', 'Оформление PLN', 'Доп. расходы PLN', 'Невозмещаемый НДС PLN'):
        result[column] = 0.0
    result['_komertia_final_cost'] = True
    return result


def migrate_screenshot_costs(frame):
    """Fold the previous saved screenshot breakdown once, preserving profit."""
    if frame is None or frame.empty or '_position_id' not in frame:
        return frame
    from analyzer import number
    result = frame.copy()
    from screenshot_catalog import load_catalog
    eligible = result['_position_id'].isin(load_catalog()['_position_id']) | result['_position_id'].fillna('').astype(str).str.startswith('komertia-screenshot-oct2026:')
    migrated = result.get('_komertia_final_cost', result.index.to_series().map(lambda _: False)).eq(True)
    mask = eligible & ~migrated
    purchase = result.loc[mask, 'Закупка PLN'].map(number)
    shipping = result.loc[mask, 'Доставка PLN'].map(number)
    final = purchase + shipping + (purchase + shipping) * result.loc[mask, 'Пошлина %'].map(number) / 100
    for column in ('Оформление PLN', 'Доп. расходы PLN', 'Невозмещаемый НДС PLN'):
        final += result.loc[mask, column].map(number)
    result.loc[mask, 'Закупка PLN'] = final
    for column in ('Доставка PLN', 'Пошлина %', 'Оформление PLN', 'Доп. расходы PLN', 'Невозмещаемый НДС PLN'):
        result.loc[mask, column] = 0.0
    if mask.any():
        result.loc[mask, '_komertia_final_cost'] = True
    return result
