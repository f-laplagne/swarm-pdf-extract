"""Domain normalization — pure functions, zero external dependencies.

Only stdlib imports allowed.
"""

import re

_LEGAL_SUFFIXES = re.compile(
    r"\b(SA|SARL|SAS|SASU|EURL|SNC|GmbH|AG|BV|NV|Ltd|LLC|Inc|PLC)\b\.?",
    re.IGNORECASE,
)
_LEADING_QTY = re.compile(r"^\d+[\s,.]?\d*\s*(kg|t|m|l)\s+", re.IGNORECASE)


def normalize_supplier(name):
    """Normalize a supplier name: strip legal suffixes, collapse whitespace, uppercase."""
    result = _LEGAL_SUFFIXES.sub("", name)
    return " ".join(result.split()).strip().upper()


def normalize_material(name):
    """Normalize a material name: strip leading quantities, strip after dash, uppercase."""
    result = _LEADING_QTY.sub("", name)
    if " - " in result:
        result = result.split(" - ")[0]
    return " ".join(result.split()).strip().upper()
