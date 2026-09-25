from typing import Any

from .base import Connector


class UsgsConnector(Connector):
    name = "usgs"
    description = "Magnitude of the most recent earthquake worldwide"
    capabilities = ["earthquake", "earthquake_magnitude"]

    # No required parameters — always checks the single most recent quake
    # globally. The user's condition (e.g. magnitude >= 6) does the
    # filtering at evaluation time, so there's nothing to fill or ask for.
    parameters: dict[str, dict[str, Any]] = {}

    value_field = "magnitude"
    min_interval_seconds = 60
    default_interval_seconds = 120  # earthquakes are time-sensitive

    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "method": "GET",
            "url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
            "params": {
                "format": "geojson",
                "orderby": "time",
                "limit": 1,
            },
        }

    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        features = response_json.get("features", [])
        if not features:
            return 0.0
        return float(features[0]["properties"].get("mag") or 0.0)
