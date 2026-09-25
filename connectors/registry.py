from .base import Connector
from .coingecko import CoinGeckoConnector
from .dynamic import DynamicConnector
from .github import GitHubConnector
from .open_meteo_air import OpenMeteoAirConnector
from .open_meteo_weather import OpenMeteoWeatherConnector
from .usgs import UsgsConnector


class ConnectorRegistry:
    def __init__(self):
        self.connectors: dict[str, Connector] = {}
        self.register(CoinGeckoConnector())
        self.register(OpenMeteoWeatherConnector())
        self.register(OpenMeteoAirConnector())
        self.register(GitHubConnector())
        self.register(UsgsConnector())

    def register(self, connector: Connector):
        self.connectors[connector.name] = connector

    def register_dynamic(self, config: dict) -> DynamicConnector:
        connector = DynamicConnector(config)
        self.register(connector)
        return connector

    def get(self, name: str) -> Connector:
        try:
            return self.connectors[name]
        except KeyError:
            raise ValueError(f"Unknown connector: {name}")

    def search(self, capability: str) -> Connector | None:
        for connector in self.connectors.values():
            if capability in connector.capabilities:
                return connector
        return None

    def all_capabilities(self) -> list[str]:
        return sorted({cap for c in self.connectors.values() for cap in c.capabilities})

    def describe_all(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "description": c.description,
                "capabilities": c.capabilities,
                "parameters": c.parameters,
            }
            for c in self.connectors.values()
        ]
