"""Tests for dashboard.data.routing — geocoding and OSRM utilities."""

import json
from unittest.mock import patch, MagicMock, call

import pytest

from dashboard.data.routing import (
    _clean_location_name,
    _decode_polyline,
    geocode_location,
    get_osrm_route,
    parse_location,
)


# --- parse_location ---


@pytest.mark.parametrize("raw,expected_company,expected_city", [
    ("EURENCO, Sorgues (84)", "EURENCO", "Sorgues"),
    ("EURENCO, Saint-Martin-de-Crau (13)", "EURENCO", "Saint-Martin-de-Crau"),
    ("TRS Capdeville, 24 Lalinde", "TRS Capdeville", "Lalinde"),
    ("Eurenco, 24 Bergerac", "Eurenco", "Bergerac"),
    ("Manuco, 24 Bergerac", "Manuco", "Bergerac"),
    ("ARIANEGROUP, Les Mureaux (78)", "ARIANEGROUP", "Les Mureaux"),
    ("ARIANEGROUP CRB, Vert-le-Petit (91)", "ARIANEGROUP CRB", "Vert-le-Petit"),
    ("BASE AERIENNE 702, Avord (18)", "BASE AERIENNE 702", "Avord"),
    ("THALES, La Ferté-Saint-Aubin (45)", "THALES", "La Ferté-Saint-Aubin"),
    ("MBDA FRANCE, Selles-Saint-Denis (41)", "MBDA FRANCE", "Selles-Saint-Denis"),
    ("CEA, Gramat (46)", "CEA", "Gramat"),
    ("ISL, Baldersheim (68)", "ISL", "Baldersheim"),
    ("SIMU, Guipavas (29)", "SIMU", "Guipavas"),
    ("NEXTER MUNITIONS, Bourges (18)", "NEXTER MUNITIONS", "Bourges"),
])
def test_parse_location_with_company(raw, expected_company, expected_city):
    company, city = parse_location(raw)
    assert company == expected_company
    assert city == expected_city


@pytest.mark.parametrize("raw,expected_city", [
    ("Sorgues", "Sorgues"),
    ("Fos Sur Mer", "Fos Sur Mer"),
    ("Kallo", "Kallo"),
    ("Kallo (Beveren-Kallo)", "Kallo"),
])
def test_parse_location_city_only(raw, expected_city):
    company, city = parse_location(raw)
    assert company is None
    assert city == expected_city


# --- _clean_location_name (legacy) ---


@pytest.mark.parametrize("raw,expected", [
    ("Sorgues (F-84706)", "Sorgues"),
    ("Dunkerque (59140)", "Dunkerque"),
    ("Lyon (FR)", "Lyon"),
    ("Saint-Etienne", "Saint-Etienne"),
    ("Marseille  (13000) ", "Marseille"),
    ("Port de Fos (F-13270)", "Port de Fos"),
    ("Genova", "Genova"),
])
def test_clean_location_name(raw, expected):
    assert _clean_location_name(raw) == expected


# --- _decode_polyline ---


def test_decode_polyline():
    # Encoded polyline for roughly: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    points = _decode_polyline(encoded)
    assert len(points) == 3
    assert abs(points[0][0] - 38.5) < 0.01
    assert abs(points[0][1] - (-120.2)) < 0.01


# --- geocode_location ---


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={})
@patch("dashboard.data.routing._nominatim_geocode")
def test_geocode_company_site_found(mock_geocode, mock_load, mock_save):
    """When company+city query succeeds, use that result."""
    mock_geocode.return_value = (43.95, 4.87)

    result = geocode_location("EURENCO, Sorgues (84)")
    assert result == (43.95, 4.87)
    # Should try "EURENCO, Sorgues, France" first
    mock_geocode.assert_called_once_with("EURENCO, Sorgues, France")
    mock_save.assert_called_once()


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={})
@patch("dashboard.data.routing._nominatim_geocode")
def test_geocode_fallback_to_city(mock_geocode, mock_load, mock_save):
    """When company+city fails, fall back to city+France."""
    mock_geocode.side_effect = [None, (44.85, 0.48)]

    result = geocode_location("Eurenco, 24 Bergerac")
    assert result == (44.85, 0.48)
    assert mock_geocode.call_count == 2
    mock_geocode.assert_any_call("Eurenco, Bergerac, France")
    mock_geocode.assert_any_call("Bergerac, France")


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={})
@patch("dashboard.data.routing._nominatim_geocode")
def test_geocode_city_only(mock_geocode, mock_load, mock_save):
    """Plain city name: no company step, goes straight to city+France."""
    mock_geocode.return_value = (43.24, 5.05)

    result = geocode_location("Fos Sur Mer")
    assert result == (43.24, 5.05)
    mock_geocode.assert_called_once_with("Fos Sur Mer, France")


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={})
@patch("dashboard.data.routing._nominatim_geocode")
def test_geocode_last_resort_no_country(mock_geocode, mock_load, mock_save):
    """When city+France fails, try just the city name."""
    # No company → 2 calls only: "Kallo, France" then "Kallo"
    mock_geocode.side_effect = [None, (51.22, 4.27)]

    result = geocode_location("Kallo")
    assert result == (51.22, 4.27)
    assert mock_geocode.call_count == 2
    mock_geocode.assert_any_call("Kallo, France")
    mock_geocode.assert_any_call("Kallo")


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={})
@patch("dashboard.data.routing._nominatim_geocode")
def test_geocode_all_attempts_fail(mock_geocode, mock_load, mock_save):
    """When all strategies fail, return None and cache it."""
    mock_geocode.return_value = None

    result = geocode_location("UnknownPlace12345")
    assert result is None
    mock_save.assert_called_once()
    # Verify None is cached for the raw name
    cached = mock_save.call_args[0][0]
    assert cached["UnknownPlace12345"] is None


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache",
       return_value={"EURENCO, Sorgues (84)": [43.95, 4.87]})
def test_geocode_location_cached(mock_load, mock_save):
    """Cached results are returned without any Nominatim calls."""
    result = geocode_location("EURENCO, Sorgues (84)")
    assert result == (43.95, 4.87)
    mock_save.assert_not_called()


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache",
       return_value={"Kallo": None})
def test_geocode_location_cached_none(mock_load, mock_save):
    """Cached None results are returned without retrying."""
    result = geocode_location("Kallo")
    assert result is None
    mock_save.assert_not_called()


# --- get_osrm_route ---


@patch("dashboard.data.routing.urllib.request.urlopen")
def test_get_osrm_route_success(mock_urlopen):
    response_data = {
        "code": "Ok",
        "routes": [{
            "distance": 150000,
            "duration": 7200,
            "geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
        }],
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_resp

    result = get_osrm_route((43.95, 4.87), (51.03, 2.38))
    assert result is not None
    assert result["distance_km"] == 150.0
    assert result["duration_min"] == 120.0
    assert len(result["geometry"]) == 3


@patch("dashboard.data.routing.urllib.request.urlopen")
def test_get_osrm_route_no_route(mock_urlopen):
    response_data = {"code": "Ok", "routes": []}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_resp

    result = get_osrm_route((43.95, 4.87), (0.0, 0.0))
    assert result is None


@patch("dashboard.data.routing.urllib.request.urlopen", side_effect=Exception("timeout"))
def test_get_osrm_route_network_error(mock_urlopen):
    result = get_osrm_route((43.95, 4.87), (51.03, 2.38))
    assert result is None
