"""Allocate native editable grid widths to the actual available main-column width."""
from pathlib import Path
import streamlit.components.v1 as components

LABELS = {'Закупка PLN':'Закупка', 'Цена Allegro PLN':'Allegro', 'Комиссия %':'Ком. %', 'Комиссия PLN':'Ком. zł', 'Прибыль PLN':'Прибыль', 'Маржа %':'Маржа %'}


def available_width():
    component = components.declare_component('allegro_table_width', path=str(Path(__file__).parent / 'table_width'))
    return component(key='main_table_width', default=850)


def widths(available):
    numeric = {'Закупка PLN':90, 'Цена Allegro PLN':85, 'Комиссия %':80, 'Комиссия PLN':80, 'Прибыль PLN':70, 'Маржа %':75}
    result = {'№':35, 'Фото Komertia':50, **numeric}
    remainder = max(60, int(available) - sum(result.values()) - 55)
    result['Produkt'] = int(remainder * .6)
    result['Wariant'] = remainder - result['Produkt']
    return result
