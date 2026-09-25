from abc import ABC, abstractmethod
from typing import Any

import httpx


class Connector(ABC):
    """
    Single source of truth for a data source. Previously this was split
    across two parallel hierarchies (apis/*.py for the planner, connectors/
    *.py for the scheduler) with duplicated CoinGecko/weather logic and
    slightly different shapes. One class now serves both:

    - the planner uses `capabilities`, `parameters`, and `value_field` to
      match intent, fill and validate params, and know what to call the
      resulting number
    - the scheduler uses `fetch()` to get a live value on each poll

    Only `build_request` and `extract_value` are connector-specific.
    `fetch()` is provided once, here, for everyone.
    """

    name: str
    description: str
    capabilities: list[str]

    # Planning-time parameter schema: {"param_name": {"type": ..., "required": ..., "description": ...}}
    parameters: dict[str, dict[str, Any]]

    # Canonical field name this connector's value is stored/compared under.
    value_field: str

    # Scheduling bounds. min = hard floor (protects the upstream API from
    # abuse / rate limiting). default = used when the user doesn't specify
    # a frequency and the interval resolver falls back to this connector's
    # own judgment about how fast its data changes.
    min_interval_seconds: int
    default_interval_seconds: int

    @abstractmethod
    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Convert validated parameters into an HTTP request spec."""
        raise NotImplementedError

    @abstractmethod
    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        """Pull the `value_field` number out of a raw API response."""
        raise NotImplementedError

    async def fetch(self, parameters: dict[str, Any]) -> float:
        """
        Build the request, call it, extract the value. Used identically
        by the planner's verification step and the scheduler's worker —
        the only two callers of a connector, and now they share one path.
        """
        request = self.build_request(parameters)
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                request["method"],
                request["url"],
                params=request.get("params", {}),
                headers=request.get("headers") or {},
            )
            response.raise_for_status()
            payload = response.json()
        return self.extract_value(payload, parameters)
