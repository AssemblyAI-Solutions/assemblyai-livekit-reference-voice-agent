"""Current weather from Open-Meteo (https://open-meteo.com), which needs no API key.

The agent's `lookup_weather` tool calls this. Swap it for your own API to give the agent
tools that matter to your use case.
"""

from __future__ import annotations

import aiohttp

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes, see https://open-meteo.com/en/docs
_CONDITIONS = {
    0: "clear skies",
    1: "mostly clear skies",
    2: "partly cloudy skies",
    3: "overcast skies",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "thunderstorms with hail",
}


class LocationNotFoundError(LookupError):
    pass


async def current_weather(location: str) -> str:
    """Describe the current weather in `location`, a place name such as "Paris"."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
        async with http.get(GEOCODING_URL, params={"name": location, "count": 1}) as resp:
            resp.raise_for_status()
            places = (await resp.json()).get("results")
        if not places:
            raise LocationNotFoundError(location)
        place = places[0]

        params = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        }
        async with http.get(FORECAST_URL, params=params) as resp:
            resp.raise_for_status()
            current = (await resp.json())["current"]

    name = ", ".join(p for p in (place["name"], place.get("admin1"), place.get("country")) if p)
    conditions = _CONDITIONS.get(current["weather_code"], "unknown conditions")
    return (
        f"{name}: {round(current['temperature_2m'])}°F with {conditions}, "
        f"wind {round(current['wind_speed_10m'])} mph"
    )
