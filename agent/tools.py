import httpx


async def geocode_location(location: str) -> dict:
    """
    Convert a human-readable location into latitude and longitude.
    Returns up to 5 candidates when the name is ambiguous (e.g. "Paris"
    matches Paris, France and Paris, Texas) — the caller decides whether
    to auto-pick a confident single match or ask the user which one.

    Use this when an API requires geographic coordinates but the
    user has provided a place name, city, landmark, or address.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": location, "count": 5, "language": "en", "format": "json"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        # Return as a normal tool result rather than raising — a raised
        # exception here would crash the whole agent loop instead of
        # letting the model fall back to asking the user for coordinates.
        return {"found": False, "location": location, "error": f"Geocoding lookup failed: {exc}"}

    results = data.get("results", [])
    if not results:
        return {"found": False, "location": location}

    candidates = [
        {
            "label": ", ".join(filter(None, [r.get("name"), r.get("admin1"), r.get("country")])),
            "name": r.get("name"),
            "country": r.get("country"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
        }
        for r in results
    ]

    return {"found": True, "location": location, "candidates": candidates}
