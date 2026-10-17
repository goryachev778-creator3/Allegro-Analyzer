"""Colour read-only cells without replacing Streamlit's editable numeric grid."""
from analyzer import COLORS


def profitability_style(frame):
    def style_row(row):
        background = COLORS.get(row.get('Статус'), 'E2E8F0')
        foreground = {'Выгодный': '14532D', 'Слабая прибыль': '713F12',
                      'Убыточный': '7F1D1D', 'Без цены': '334155'}.get(row.get('Статус'), '334155')
        return [f'background-color: #{background}; color: #{foreground}; font-weight: bold'
                if column in ('Прибыль PLN', 'Маржа %') else ''
                for column in row.index]
    return frame.style.apply(style_row, axis=1)
