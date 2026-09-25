from typing import Any

from .base import Connector


class OpenMeteoAirConnector(Connector):
    name = "open_meteo_air"
    description = "Current air quality (European AQI) at a location"
    capabilities = ["aqi", "air_quality"]

    parameters = {
        "latitude": {"type": "float", "required": True, "description": "Location latitude"},
        "longitude": {"type": "float", "required": True, "description": "Location longitude"},
    }

    value_field = "aqi"
    min_interval_seconds = 300
    default_interval_seconds = 1800  # AQI changes slowly

    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "method": "GET",
            "url": "https://air-quality-api.open-meteo.com/v1/air-quality",
            "params": {
                "latitude": parameters["latitude"],
                "longitude": parameters["longitude"],
                "current": "european_aqi",
            },
        }

    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        try:
            return float(response_json["current"]["european_aqi"])
        except KeyError as exc:
            raise ValueError("Open-Meteo Air Quality response missing current.european_aqi") from exc
