"""Compatibility exports follow the current canonical metadata module."""
import komertia_details as _details

__all__ = [
    'PHOTO', 'FULL_NAME', 'NAME_PL', 'DETAILS', 'ALIASES',
    'value', 'complete_name', 'photo_source', 'polish_name', 'enrich_details',
    'import_details', 'uploaded_photo', 'full_table', 'excel_details',
]


def __getattr__(name):
    if name in __all__:
        return getattr(_details, name)
    raise AttributeError(name)
