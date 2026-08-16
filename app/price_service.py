"""
price_service.py
------------------
Fetches the current price of a crypto asset from CoinGecko's free public
API, and checks whether a trigger's condition is currently true.

This is the first "real" logic in PingMe -- everything before this was
just storing/reading data. This file is what actually goes out and checks
something in the real world.
"""

import requests

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# CoinGecko only understands its own full "id" names (e.g. "bitcoin"), not
# ticker symbols (e.g. "BTC"). Most users will naturally type the ticker,
# so we translate the common ones here before calling the API.
ASSET_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "doge": "dogecoin",
    "usdt": "tether",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
}


def normalize_asset(asset: str) -> str:
    """Turn 'BTC', 'btc', or 'Btc' all into 'bitcoin'. Unknown assets are
    just lowercased and passed through unchanged, since some CoinGecko ids
    (like 'bitcoin' itself) are already the right format."""
    key = asset.strip().lower()
    return ASSET_ALIASES.get(key, key)


def get_current_price(asset: str, vs_currency: str = "usd") -> float:
    """
    Ask CoinGecko for the current price of `asset` (e.g. "bitcoin" or "BTC")
    in `vs_currency` (e.g. "usd"). Returns a plain float.

    Raises a ValueError if CoinGecko doesn't recognize the asset name --
    this happens if someone types a typo, or an asset with no alias mapped.
    """
    asset = normalize_asset(asset)

    response = requests.get(
        COINGECKO_URL,
        params={"ids": asset, "vs_currencies": vs_currency},
        timeout=10,
    )
    response.raise_for_status()  # raises an error if CoinGecko itself is down

    data = response.json()
    if asset not in data:
        raise ValueError(
            f"CoinGecko doesn't recognize '{asset}'. "
            f"Try the full CoinGecko id, e.g. 'bitcoin' or 'ethereum'."
        )

    return data[asset][vs_currency]


def condition_met(current_value: float, condition: str, target_value: float) -> bool:
    if condition == "<":
        return current_value < target_value
    if condition == ">":
        return current_value > target_value
    raise ValueError(f"Unsupported condition: {condition}")

