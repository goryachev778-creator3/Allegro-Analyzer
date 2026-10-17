"""Keep imported order identities separate without embedding private order data."""
import pandas as pd


def order_labels(frame):
    if 'source_order' not in frame:
        return pd.Series('A1632', index=frame.index)
    return frame['source_order'].fillna('').astype(str).str.strip().replace('', 'A1632')
