"""Tests for dashboard.data.routing — geocoding and OSRM utilities."""

import json
from unittest.mock import patch, MagicMock

import pytest

from dashboard.data.routing import (
    _clean_location_name,
    _decode_polyline,
    geocode_location,
    get_osrm_route,
)


# --- _clean_location_name ---


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
@patch("dashboard.data.routing.Nominatim")
def test_geocode_location_success(mock_nominatim_cls, mock_load, mock_save):
    mock_location = MagicMock()
    mock_location.latitude = 43.95
    mock_location.longitude = 4.87
    mock_geolocator = MagicMock()
    mock_geolocator.geocode.return_value = mock_location
    mock_nominatim_cls.return_value = mock_geolocator

    result = geocode_location("Sorgues (F-84706)")
    assert result == (43.95, 4.87)
    # Should have been called with cleaned name
    mock_geolocator.geocode.assert_called_once_with("Sorgues")
    mock_save.assert_called_once()


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={"Lyon": [45.76, 4.83]})
def test_geocode_location_cached(mock_load, mock_save):
    result = geocode_location("Lyon (FR)")
    assert result == (45.76, 4.83)
    # Should NOT save again for cached result
    mock_save.assert_not_called()


@patch("dashboard.data.routing._save_cache")
@patch("dashboard.data.routing._load_cache", return_value={})
@patch("dashboard.data.routing.Nominatim")
def test_geocode_location_not_found(mock_nominatim_cls, mock_load, mock_save):
    mock_geolocator = MagicMock()
    mock_geolocator.geocode.return_value = None
    mock_nominatim_cls.return_value = mock_geolocator

    result = geocode_location("UnknownPlace12345")
    assert result is None
    mock_save.assert_called_once()


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
