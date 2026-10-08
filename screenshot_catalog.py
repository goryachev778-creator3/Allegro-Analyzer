"""Verified transcription of the user's Komertia screenshots."""
import json
from pathlib import Path
import pandas as pd
from analyzer import INPUTS
from komertia import apply_costs


def load_catalog():
    payload = json.loads((Path(__file__).parent / 'assets' / 'komertia-screenshots.json').read_text())
    raw = pd.DataFrame(payload['rows'])
    frame = pd.DataFrame(0.0, index=raw.index, columns=INPUTS)
    frame['Товар'] = raw['Produkt']
    frame['SKU'] = ''
    frame['Цена Allegro PLN'] = raw['Цена Allegro PLN']
    frame['Комиссия %'] = raw['Комиссия %']
    frame = apply_costs(frame, raw)
    for col in ('Produkt', 'Wariant', 'Ilość', 'source_row'):
        frame[col] = raw[col]
    frame['_position_id'] = raw['position_id']
    return frame
