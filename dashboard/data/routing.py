"""Geocoding and OSRM routing utilities for transport visualization.

Uses Nominatim (via geopy) for geocoding with a local JSON file cache,
and the OSRM demo server for driving route calculation (no API key needed).
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


def _clean_location_name(name: str) -> str:
    """Strip postal code parentheticals and extra whitespace.

    Examples:
        "Sorgues (F-84706)" -> "Sorgues"
        "Dunkerque (59140)" -> "Dunkerque"
        "Lyon (FR)" -> "Lyon"
        "Saint-Etienne" -> "Saint-Etienne"
    """
    # Remove parenthetical content like (F-84706), (59140), (FR)
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


def geocode_location(name: str) -> tuple[float, float] | None:
    """Geocode a location name to (latitude, longitude).

    Results are cached in a JSON file to avoid repeated Nominatim calls.
    Returns None if geocoding fails.
    """
    cleaned = _clean_location_name(name)
    cache = _load_cache()

    if cleaned in cache:
        val = cache[cleaned]
        return tuple(val) if val is not None else None

    try:
        geolocator = Nominatim(user_agent="rationalize-dashboard", timeout=10)
        location = geolocator.geocode(cleaned)
        if location:
            coords = [location.latitude, location.longitude]
            cache[cleaned] = coords
            _save_cache(cache)
            return (coords[0], coords[1])
        else:
            cache[cleaned] = None
            _save_cache(cache)
            return None
    except (GeocoderTimedOut, GeocoderUnavailable, Exception):
        return None


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
