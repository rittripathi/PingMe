from typing import Any

from .base import Connector


class OpenMeteoWeatherConnector(Connector):
    name = "open_meteo_weather"
    description = "Current temperature at a location"
    capabilities = ["temperature", "weather"]

    parameters = {
        "latitude": {"type": "float", "required": True, "description": "Location latitude"},
        "longitude": {"type": "float", "required": True, "description": "Location longitude"},
    }

    value_field = "temperature"
    min_interval_seconds = 300
    default_interval_seconds = 900  # forecast data updates roughly every 15 min

    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "method": "GET",
            "url": "https://api.open-meteo.com/v1/forecast",
            "params": {
                "latitude": parameters["latitude"],
                "longitude": parameters["longitude"],
                "current": "temperature_2m",
            },
        }

    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        try:
            return float(response_json["current"]["temperature_2m"])
        except KeyError as exc:
            raise ValueError("Open-Meteo response missing current.temperature_2m") from exc
