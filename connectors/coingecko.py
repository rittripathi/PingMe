from typing import Any

from .base import Connector


class CoinGeckoConnector(Connector):
    name = "coingecko"
    description = "Current cryptocurrency spot price"

    # NOTE: earlier drafts also listed crypto_market_cap / crypto_price_change
    # as capabilities, but build_request only ever calls the simple/price
    # endpoint — those capabilities were never actually fulfillable. Listing
    # them let the classifier pick a capability the connector couldn't
    # deliver, which verify_request would then fail on. Trimmed to what's real.
    capabilities = ["crypto_price"]

    parameters = {
        "coin_id": {
            "type": "string",
            "required": True,
            "description": "CoinGecko coin id, e.g. bitcoin",
        },
        "currency": {
            "type": "string",
            "required": True,
            "default": "usd",
            "description": "Fiat currency, e.g. usd",
        },
    }

    value_field = "price"
    min_interval_seconds = 60
    default_interval_seconds = 120  # fast-moving data

    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "method": "GET",
            "url": "https://api.coingecko.com/api/v3/simple/price",
            "params": {
                "ids": parameters["coin_id"],
                "vs_currencies": parameters["currency"],
            },
        }

    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        coin_id = parameters["coin_id"]
        currency = parameters["currency"]
        try:
            return float(response_json[coin_id][currency])
        except KeyError as exc:
            raise ValueError(
                f"CoinGecko response missing '{coin_id}.{currency}' — "
                f"check coin_id is a valid CoinGecko id."
            ) from exc
