from __future__ import annotations

from functools import lru_cache

from geopy.geocoders import Nominatim


@lru_cache(maxsize=1000)
def geocode_address(address: str) -> tuple[float, float] | None:
    address = (address or "").strip()
    if not address:
        return None
    geolocator = Nominatim(user_agent="sanzar-crm-web")
    location = geolocator.geocode(address, timeout=10)
    if not location:
        return None
    return float(location.latitude), float(location.longitude)


def parse_coordinates(value: str) -> tuple[float, float] | None:
    from services.locale_numbers import parse_locale_float

    value = (value or "").strip()
    if not value or "," not in value:
        return None
    left, right = value.split(",", 1)
    lat = parse_locale_float(left)
    lon = parse_locale_float(right)
    if lat is None or lon is None:
        return None
    return lat, lon
