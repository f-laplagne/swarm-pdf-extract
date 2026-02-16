"""Geocoding and OSRM routing utilities for transport visualization.

Uses Nominatim (via geopy) for geocoding with a local JSON file cache,
and the OSRM demo server for driving route calculation (no API key needed).

Location strings from invoices typically follow these patterns:
    "COMPANY, City (dept)"       -> "COMPANY, City, France" then "City, France"
    "Company, PostalCode City"   -> "Company, City, France" then "City, France"
    "City (PostalCode)"          -> "City, France"
    "City"                       -> "City, France"
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "geocode_cache.json")
_OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"


def parse_location(name: str) -> tuple[str | None, str]:
    """Parse a raw location string into (company, city).

    Handles formats found in French transport invoices:
        "EURENCO, Sorgues (84)"           -> ("EURENCO", "Sorgues")
        "TRS Capdeville, 24 Lalinde"      -> ("TRS Capdeville", "Lalinde")
        "Eurenco, 24 Bergerac"            -> ("Eurenco", "Bergerac")
        "ARIANEGROUP, Les Mureaux (78)"   -> ("ARIANEGROUP", "Les Mureaux")
        "Kallo (Beveren-Kallo)"           -> (None, "Kallo")
        "Fos Sur Mer"                     -> (None, "Fos Sur Mer")
        "Sorgues"                         -> (None, "Sorgues")
        "BASE AERIENNE 702, Avord (18)"   -> ("BASE AERIENNE 702", "Avord")
        "Manuco, 24 Bergerac"             -> ("Manuco", "Bergerac")
    """
    # Strip parenthetical content: (84), (F-84706), (Beveren-Kallo), etc.
    cleaned = re.sub(r"\s*\([^)]*\)\s*", "", name).strip()

    if "," in cleaned:
        # Split on first comma: "COMPANY, [postal] City"
        company_part, city_part = cleaned.split(",", 1)
        company = company_part.strip()
        city_part = city_part.strip()
        # Strip leading French postal code (1-5 digits): "24 Bergerac" -> "Bergerac"
        city = re.sub(r"^\d{1,5}\s+", "", city_part).strip()
        return (company, city) if city else (None, company)

    # No comma: plain city name
    return (None, cleaned)


# Keep for backward compatibility with tests
def _clean_location_name(name: str) -> str:
    """Strip postal code parentheticals and extra whitespace (legacy)."""
    cleaned = re.sub(r"\s*\([^)]*\)\s*", "", name)
    return cleaned.strip()


def _load_cache() -> dict[str, list[float] | None]:
    if os.path.exists(_CACHE_PATH):
        with open(_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict[str, list[float] | None]) -> None:
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _nominatim_geocode(query: str) -> tuple[float, float] | None:
    """Single Nominatim geocode attempt. Returns (lat, lon) or None."""
    try:
        geolocator = Nominatim(user_agent="rationalize-dashboard", timeout=10)
        location = geolocator.geocode(query)
        if location:
            return (location.latitude, location.longitude)
    except (GeocoderTimedOut, GeocoderUnavailable, Exception):
        pass
    return None


def geocode_location(name: str) -> tuple[float, float] | None:
    """Geocode a location name to (latitude, longitude).

    Strategy (multi-step with fallback):
        1. Check cache for the raw name
        2. Parse into (company, city)
        3. Try "Company, City, France" (precise site location)
        4. Fallback to "City, France" (city-level)

    Results are cached in a JSON file to avoid repeated Nominatim calls.
    Returns None if all attempts fail.
    """
    cache = _load_cache()

    # Check cache first (keyed on raw name)
    if name in cache:
        val = cache[name]
        return tuple(val) if val is not None else None

    company, city = parse_location(name)

    coords = None

    # Strategy 1: try "Company, City, France" for precise company site
    if company:
        coords = _nominatim_geocode(f"{company}, {city}, France")

    # Strategy 2: fallback to "City, France"
    if coords is None:
        coords = _nominatim_geocode(f"{city}, France")

    # Strategy 3: last resort — just the city name without country
    if coords is None and city:
        coords = _nominatim_geocode(city)

    # Cache the result (even None to avoid retrying)
    cache[name] = list(coords) if coords else None
    _save_cache(cache)
    return coords


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decode a Google-encoded polyline string into list of (lat, lon).

    OSRM returns routes in this format. Algorithm reference:
    https://developers.google.com/maps/documentation/utilities/polylinealgorithm
    """
    points = []
    index = 0
    lat = 0
    lon = 0

    while index < len(encoded):
        # Decode latitude
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += (~(result >> 1) if (result & 1) else (result >> 1))

        # Decode longitude
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lon += (~(result >> 1) if (result & 1) else (result >> 1))

        points.append((lat / 1e5, lon / 1e5))

    return points


def get_osrm_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict[str, Any] | None:
    """Fetch driving route from OSRM demo server.

    Parameters:
        origin: (latitude, longitude) of departure
        destination: (latitude, longitude) of arrival

    Returns dict with keys:
        - distance_km: float
        - duration_min: float
        - geometry: list of (lat, lon) tuples for the polyline
    Or None if the request fails.
    """
    # OSRM expects lon,lat order
    coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    url = f"{_OSRM_BASE}/{coords}?overview=full&geometries=polyline"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rationalize-dashboard"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    if data.get("code") != "Ok" or not data.get("routes"):
        return None

    route = data["routes"][0]
    return {
        "distance_km": round(route["distance"] / 1000, 1),
        "duration_min": round(route["duration"] / 60, 1),
        "geometry": _decode_polyline(route["geometry"]),
    }
