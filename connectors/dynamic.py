from typing import Any

import jmespath

from .base import Connector


class DynamicConnector(Connector):
    """
    Config-driven connector for APIs that don't warrant (or don't have
    time for) a hand-written Python class. Built at runtime from a dict —
    normally produced by the discovery agent reading a public API's
    OpenAPI spec — instead of requiring a new .py file and a deploy for
    every new source. This is what makes "thousands of public APIs"
    tractable: the code is written once, here; everything else is data.

    Scope, honestly: this only covers an unauthenticated or simple
    query/header-key-authenticated GET endpoint returning JSON, where the
    value of interest sits at a fixed JMESPath in the response. OAuth,
    POST bodies, pagination, and multi-step calls still need a real
    Connector subclass — this generalizes the common case, not all of it.

    Example config:
    {
        "name": "open_meteo_weather_dynamic",
        "description": "...",
        "capabilities": ["temperature"],
        "value_field": "temperature",
        "base_url": "https://api.open-meteo.com/v1/forecast",
        "static_params": {"current": "temperature_2m"},
        "param_query_keys": {"latitude": "latitude", "longitude": "longitude"},
        "response_path": "current.temperature_2m",
        "parameters": {
            "latitude": {"type": "float", "required": True, "description": "..."},
            "longitude": {"type": "float", "required": True, "description": "..."}
        },
        "auth": null   # or {"type": "query"|"header", "key_name": ..., "key_value": ...}
    }
    """

    def __init__(self, config: dict[str, Any]):
        self.name = config["name"]
        self.description = config["description"]
        self.capabilities = config["capabilities"]
        self.parameters = config.get("parameters", {})
        self.value_field = config["value_field"]
        self.min_interval_seconds = config.get("min_interval_seconds", 60)
        self.default_interval_seconds = config.get("default_interval_seconds", 300)

        self._base_url = config["base_url"]
        self._method = config.get("method", "GET")
        self._static_params = config.get("static_params", {})
        # Maps our internal parameter name -> the API's actual query key name,
        # since they don't always match (e.g. our "coin_id" -> their "ids").
        self._param_query_keys = config.get("param_query_keys", {})
        self._response_path = config["response_path"]
        self._auth = config.get("auth")

    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        params = dict(self._static_params)
        for our_name, api_key in self._param_query_keys.items():
            if our_name in parameters:
                params[api_key] = parameters[our_name]

        headers: dict[str, str] = {}
        if self._auth:
            if self._auth["type"] == "query":
                params[self._auth["key_name"]] = self._auth["key_value"]
            elif self._auth["type"] == "header":
                headers[self._auth["key_name"]] = self._auth["key_value"]

        return {"method": self._method, "url": self._base_url, "params": params, "headers": headers}

    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        value = jmespath.search(self._response_path, response_json)
        if value is None:
            raise ValueError(
                f"JMESPath '{self._response_path}' found nothing in the response "
                f"from {self.name} — the spec-derived path may be wrong."
            )
        return float(value)

    def to_config(self) -> dict[str, Any]:
        """Serialize back to the dict form, for persisting to the DB."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "parameters": self.parameters,
            "value_field": self.value_field,
            "min_interval_seconds": self.min_interval_seconds,
            "default_interval_seconds": self.default_interval_seconds,
            "base_url": self._base_url,
            "method": self._method,
            "static_params": self._static_params,
            "param_query_keys": self._param_query_keys,
            "response_path": self._response_path,
            "auth": self._auth,
        }
