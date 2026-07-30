# app/aqi_service.py
"""
aqi_service.py
----------------
Looks up the current AQI for a "latitude,longitude" string using AQICN's
free API. One external call, no geocoding step.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

WAQI_API_TOKEN = os.getenv("WAQI_API_TOKEN")
AQICN_URL_TEMPLATE = "https://api.waqi.info/feed/geo:{lat};{lon}/"


def get_current_aqi(coordinates: str) -> float:
    """
    coordinates: a string like "28.6139,77.2090" (latitude,longitude).
    Returns the AQI reading from the nearest monitoring station.
    """
    if not WAQI_API_TOKEN:
        raise ValueError("WAQI_API_TOKEN is not set. Check your .env file.")

    try:
        lat_str, lon_str = coordinates.split(",")
        lat, lon = float(lat_str.strip()), float(lon_str.strip())
    except (ValueError, AttributeError):
        raise ValueError(
            f"'{coordinates}' isn't a valid coordinate pair. "
            "Expected format: latitude,longitude (e.g. 28.6139,77.2090)"
        )

    response = requests.get(
        AQICN_URL_TEMPLATE.format(lat=lat, lon=lon),
        params={"token": WAQI_API_TOKEN},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "ok":
        raise ValueError(f"No AQI station found near coordinates '{coordinates}'.")

    return data["data"]["aqi"]


# ==============================================================================
# ROLE OF THIS FILE:
# Wraps AQICN's geo-based feed behind one function -- takes the raw
# "lat,lon" string the user typed in, returns a real AQI number. Same
# shape as price_service.py's get_current_price(): one external call in,
# one clean number out.
# ==============================================================================