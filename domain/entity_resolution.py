"""Domain entity resolution — pure functions, zero external dependencies.

Only stdlib imports allowed.
"""

import math


def resolve_value(value, mappings, prefix_mappings=None):
    """Resolve a raw value to canonical form using exact then prefix matching."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return value
    val = str(value)
    if val in mappings:
        return mappings[val]
    if prefix_mappings:
        for prefix in sorted(prefix_mappings, key=len, reverse=True):
            if val.startswith(prefix):
                return prefix_mappings[prefix]
    return val


def expand_canonical(canonical, reverse_mappings):
    """Return all raw values + canonical, sorted."""
    values = set(reverse_mappings.get(canonical, []))
    values.add(canonical)
    return sorted(values)
