from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx

from .persistence import cache_get, cache_set

STADIUMS = {
    "BAL": {"name": "M&T Bank Stadium", "lat": 39.278, "lon": -76.623, "dome": False},
    "BUF": {"name": "Highmark Stadium", "lat": 42.774, "lon": -78.787, "dome": False},
    "GB": {"name": "Lambeau Field", "lat": 44.501, "lon": -88.062, "dome": False},
    "MIA": {"name": "Hard Rock Stadium", "lat": 25.958, "lon": -80.239, "dome": False},
    "NE": {"name": "Gillette Stadium", "lat": 42.091, "lon": -71.264, "dome": False},
    "NYJ": {"name": "MetLife Stadium", "lat": 40.813, "lon": -74.074, "dome": False},
    "PHI": {"name": "Lincoln Financial Field", "lat": 39.901, "lon": -75.168, "dome": False},
    "PIT": {"name": "Acrisure Stadium", "lat": 40.447, "lon": -80.016, "dome": False},
    "ATL": {"name": "Mercedes-Benz Stadium", "lat": 33.755, "lon": -84.401, "dome": True},
    "ARI": {"name": "State Farm Stadium", "lat": 33.528, "lon": -112.263, "dome": True},
    "DAL": {"name": "AT&T Stadium", "lat": 32.748, "lon": -97.093, "dome": True},
    "DET": {"name": "Ford Field", "lat": 42.34, "lon": -83.046, "dome": True},
    "IND": {"name": "Lucas Oil Stadium", "lat": 39.76, "lon": -86.164, "dome": True},
    "MIN": {"name": "U.S. Bank Stadium", "lat": 44.974, "lon": -93.258, "dome": True},
}


async def odds(force: bool = False) -> dict:
    cached = cache_get("odds:nfl")
    if cached and force:
        fetched=datetime.fromisoformat(cached["fetched_at"])
        if datetime.now(UTC)-fetched < timedelta(minutes=15): return {**cached,"quota_guard":"Refresh suppressed: minimum 15-minute interval"}
    if cached and not force and cached["status"] != "STALE": return cached
    key = os.getenv("ODDS_API_KEY")
    if not key: return cached or {"status": "UNAVAILABLE", "payload": [], "error": "ODDS_API_KEY is not configured"}
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params={"apiKey": key, "regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"})
    response.raise_for_status(); payload = response.json(); now = datetime.now(UTC)
    cache_set("odds:nfl", "The Odds API", payload, now.isoformat(), (now + timedelta(hours=6)).isoformat())
    return {"status": "LIVE", "payload": payload, "remaining_requests": response.headers.get("x-requests-remaining")}


async def weather(team: str, force: bool = False) -> dict:
    stadium = STADIUMS.get(team)
    if not stadium: return {"status": "UNAVAILABLE", "error": "Stadium metadata is not available"}
    if stadium["dome"]: return {"status": "LIVE", "stadium": stadium, "payload": {"dome": True, "impact": "No outdoor weather adjustment"}}
    cache_key = f"weather:{team}"; cached = cache_get(cache_key)
    if cached and not force and cached["status"] != "STALE": return {**cached, "stadium": stadium}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": stadium["lat"], "longitude": stadium["lon"], "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m", "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "forecast_days": 7, "timezone": "America/New_York"})
    response.raise_for_status(); payload=response.json(); now=datetime.now(UTC)
    cache_set(cache_key,"Open-Meteo",payload,now.isoformat(),(now+timedelta(hours=3)).isoformat())
    return {"status":"LIVE","stadium":stadium,"payload":payload}


async def nflverse_rosters(season: int, force: bool = False) -> dict:
    key=f"nflverse:rosters:{season}"; cached=cache_get(key)
    if cached and not force and cached["status"] != "STALE": return cached
    url=f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.csv"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client: response=await client.get(url)
    response.raise_for_status(); text=response.text; now=datetime.now(UTC)
    cache_set(key,"nflverse",{"csv":text},now.isoformat(),(now+timedelta(days=1)).isoformat())
    return {"status":"LIVE","payload":{"csv":text}}
