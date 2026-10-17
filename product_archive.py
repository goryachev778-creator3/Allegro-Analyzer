"""Archive the four requested zero-price records without deleting database rows."""
import pandas as pd
from analyzer import number
from komertia_details import is_order_total

TARGETS = (12, 13, 15, 17)
FLAG = '_archived_no_allegro_price'
MODE = '_landed_purchase_analysis'


def enabled(frame):
    return MODE in frame and frame[MODE].eq(True).any()


def prepare(frame):
    result = frame.copy()
    if enabled(result):
        return result, ''
    positions = [i for i, row in result.iterrows() if not is_order_total(row)]
    if len(positions) != 25:
        return result, 'Для переноса указанных строк ожидаются 25 товаров; данные не изменены.'
    selected = [positions[n-1] for n in TARGETS]
    if any(number(result.loc[i, 'Цена Allegro PLN']) != 0 for i in selected):
        return result, 'У одной из строк №12, 13, 15, 17 уже есть цена Allegro. Автоматический перенос отменён.'
    result[FLAG] = False
    result.loc[selected, FLAG] = True
    result[MODE] = True
    return result, ''


def active_mask(frame):
    products = ~frame.apply(is_order_total, axis=1)
    if not enabled(frame):
        return products
    archived = frame[FLAG].eq(True) if FLAG in frame else pd.Series(False, index=frame.index)
    from order_scope import order_labels
    new_order = order_labels(frame).ne('A1632')
    return products & ~archived & (frame['Цена Allegro PLN'].map(number).gt(0) | new_order)


def totals(result):
    result = result.loc[result['Цена Allegro PLN'].map(number).gt(0)]
    return pd.DataFrame([{'Produkt': 'ИТОГО — по 1 шт. каждого активного товара',
        'Товаров': len(result), 'Прибыль PLN': result['Прибыль PLN'].sum(),
        'Маржа %': result['Маржа %'].mean()}])
