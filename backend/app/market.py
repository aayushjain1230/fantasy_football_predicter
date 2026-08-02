from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, Protocol


SUPPORTED_MARKETS = {
    "totals": "game_total",
    "spreads": "point_spread",
    "h2h": "moneyline",
    "player_pass_yds": "passing_yards",
    "player_pass_tds": "passing_touchdowns",
    "player_rush_yds": "rushing_yards",
    "player_reception_yds": "receiving_yards",
    "player_receptions": "receptions",
    "player_anytime_td": "anytime_touchdown",
}


@dataclass(frozen=True)
class MarketMetadata:
    source: str = "unavailable"
    retrieved_at: str | None = None
    event_time: str | None = None
    is_stale: bool = False
    books_used: int = 0
    data_quality: str = "unavailable"


@dataclass(frozen=True)
class LineMovement:
    opening_line: float | None = None
    current_line: float | None = None
    movement: float | None = None


@dataclass(frozen=True)
class GameMarket:
    game_id: str
    game_total: float | None = None
    point_spread: float | None = None
    moneyline: float | None = None
    win_probability: float | None = None
    team_implied_total: float | None = None
    movement: LineMovement = field(default_factory=LineMovement)
    metadata: MarketMetadata = field(default_factory=MarketMetadata)
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.metadata.books_used > 0 and self.metadata.data_quality != "unavailable"


@dataclass(frozen=True)
class PlayerMarket:
    player_id: str
    passing_yards: float | None = None
    passing_touchdowns: float | None = None
    rushing_yards: float | None = None
    receiving_yards: float | None = None
    receptions: float | None = None
    anytime_touchdown_probability: float | None = None
    movement: LineMovement = field(default_factory=LineMovement)
    metadata: MarketMetadata = field(default_factory=MarketMetadata)
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.metadata.books_used > 0 and self.metadata.data_quality != "unavailable"


class MarketContextProvider(Protocol):
    def get_game_market(self, game_id: str) -> GameMarket:
        ...

    def get_player_market(self, player_id: str) -> PlayerMarket:
        ...


@dataclass(frozen=True)
class MarketObservation:
    market: str
    selection: str
    line: float | None
    odds: int | float | None = None
    bookmaker: str = ""
    event_id: str = ""
    player_id: str | None = None
    observed_at: str | None = None
    event_time: str | None = None
    is_opening: bool = False


def normalize_market_name(value: str) -> str:
    return SUPPORTED_MARKETS.get((value or "").strip().lower(), (value or "").strip().lower())


def american_odds_to_implied_probability(odds: int | float | None) -> float | None:
    if odds is None:
        return None
    try:
        value = float(odds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value == 0:
        return None
    if value > 0:
        return round(100 / (value + 100), 6)
    return round(abs(value) / (abs(value) + 100), 6)


def remove_vig(two_sided_probabilities: dict[str, float | None]) -> dict[str, float]:
    clean = {key: value for key, value in two_sided_probabilities.items() if value is not None and value > 0}
    total = sum(clean.values())
    if len(clean) < 2 or total <= 0:
        return {}
    return {key: round(value / total, 6) for key, value in clean.items()}


def consensus_line(observations: list[MarketObservation], *, max_age_hours: int = 24, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    clean: list[MarketObservation] = []
    seen: set[tuple[str, str, str, float | None, int | float | None]] = set()
    for obs in observations:
        if obs.line is None:
            continue
        try:
            line = float(obs.line)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(line):
            continue
        observed_at = _parse_time(obs.observed_at)
        if observed_at and now - observed_at > timedelta(hours=max_age_hours):
            continue
        key = (obs.bookmaker.lower(), normalize_market_name(obs.market), obs.selection.lower(), line, obs.odds)
        if key in seen:
            continue
        seen.add(key)
        clean.append(obs)
    if not clean:
        return {"available": False, "line": None, "books_used": 0, "data_quality": "unavailable"}
    current = [float(obs.line) for obs in clean if not obs.is_opening]
    opening = [float(obs.line) for obs in clean if obs.is_opening]
    current_line = median(current or [float(obs.line) for obs in clean])
    opening_line = median(opening) if opening else None
    books = {obs.bookmaker.lower() for obs in clean if obs.bookmaker}
    return {
        "available": True,
        "line": round(current_line, 3),
        "books_used": len(books) or len(clean),
        "data_quality": "fresh" if len(books) >= 2 else "partial",
        "opening_line": round(opening_line, 3) if opening_line is not None else None,
        "line_movement": round(current_line - opening_line, 3) if opening_line is not None else None,
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class UnavailableMarketContextProvider:
    def __init__(self, reason: str | None = None):
        self.reason = reason or "ODDS_API_KEY is not configured"

    def get_game_market(self, game_id: str) -> GameMarket:
        return GameMarket(game_id=game_id, unavailable_reason=self.reason)

    def get_player_market(self, player_id: str) -> PlayerMarket:
        return PlayerMarket(player_id=player_id, unavailable_reason=self.reason)


class FixtureMarketContextProvider:
    def __init__(self, game_observations: dict[str, list[MarketObservation]] | None = None, player_observations: dict[str, list[MarketObservation]] | None = None):
        self.game_observations = game_observations or {}
        self.player_observations = player_observations or {}

    def get_game_market(self, game_id: str) -> GameMarket:
        observations = self.game_observations.get(game_id, [])
        total = consensus_line([obs for obs in observations if normalize_market_name(obs.market) == "game_total"])
        spread = consensus_line([obs for obs in observations if normalize_market_name(obs.market) == "point_spread"])
        now = datetime.now(UTC).isoformat()
        books = max(total.get("books_used", 0), spread.get("books_used", 0))
        return GameMarket(
            game_id=game_id,
            game_total=total.get("line"),
            point_spread=spread.get("line"),
            movement=LineMovement(total.get("opening_line"), total.get("line"), total.get("line_movement")),
            metadata=MarketMetadata(source="fixture", retrieved_at=now, books_used=books, data_quality=total.get("data_quality", "unavailable")),
            unavailable_reason=None if books else "No available market data",
        )

    def get_player_market(self, player_id: str) -> PlayerMarket:
        observations = self.player_observations.get(player_id, [])
        by_market = {market: consensus_line([obs for obs in observations if normalize_market_name(obs.market) == market]) for market in set(SUPPORTED_MARKETS.values())}
        td_obs = [obs for obs in observations if normalize_market_name(obs.market) == "anytime_touchdown"]
        raw_probs = [american_odds_to_implied_probability(obs.odds) for obs in td_obs]
        probs = [value for value in raw_probs if value is not None]
        now = datetime.now(UTC).isoformat()
        books = max([row.get("books_used", 0) for row in by_market.values()] + [0])
        return PlayerMarket(
            player_id=player_id,
            passing_yards=by_market.get("passing_yards", {}).get("line"),
            passing_touchdowns=by_market.get("passing_touchdowns", {}).get("line"),
            rushing_yards=by_market.get("rushing_yards", {}).get("line"),
            receiving_yards=by_market.get("receiving_yards", {}).get("line"),
            receptions=by_market.get("receptions", {}).get("line"),
            anytime_touchdown_probability=round(median(probs), 6) if probs else None,
            metadata=MarketMetadata(source="fixture", retrieved_at=now, books_used=books or len({obs.bookmaker for obs in td_obs if obs.bookmaker}), data_quality="fresh" if books >= 2 else "partial" if observations else "unavailable"),
            unavailable_reason=None if observations else "No available market data",
        )


def default_market_provider() -> MarketContextProvider:
    if not os.getenv("ODDS_API_KEY"):
        return UnavailableMarketContextProvider()
    return UnavailableMarketContextProvider("Live Odds API adapter is not enabled in Streamlit; use manual refresh/cache path.")
