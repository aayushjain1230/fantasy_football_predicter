from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable, Iterable, MutableMapping
from urllib.parse import parse_qs, urlparse

import httpx

from .domain import ActiveLeagueState, League, LeagueConnectionStatus
from .draft_intelligence import build_draft_configuration, league_draft_type, resolve_draft_slot, resolve_manager_count


ESPN_HOSTS = {"fantasy.espn.com", "games.espn.com", "lm-api-reads.fantasy.espn.com"}
SECRET_QUERY_KEYS = {"espn_s2", "swid", "cookie", "token", "authorization"}
LEAGUE_PATH_RE = re.compile(r"/leagues/(?P<league_id>\d{1,30})(?:/|$)")
SEASON_PATH_RE = re.compile(r"/seasons/(?P<season>20\d{2})(?:/|$)")
CONNECTION_SESSION_KEYS = {
    "league", "active_league", "espn_connection", "espn_candidate", "espn_candidate_url",
    "espn_candidate_credentials", "league_connected", "mode", "draft_picks", "draft_configuration",
    "draft_setup_confirmed", "draft_manager_confirmed", "draft_slot_confirmed", "draft_slot",
    "draft_league_size", "draft_manual_started", "draft_ignored", "simulation_cache", "connection_error",
}


@dataclass(frozen=True)
class ParsedEspnLeagueUrl:
    league_id: str
    season: int
    canonical_url: str


@dataclass(frozen=True)
class SessionEspnCredentials:
    """Session-only ESPN material. Repr is redacted by design."""

    espn_s2: str = ""
    swid: str = ""

    def __repr__(self) -> str:
        return "SessionEspnCredentials(espn_s2='***', swid='***')"

    @property
    def authenticated(self) -> bool:
        return bool(self.espn_s2 and self.swid)


@dataclass(frozen=True)
class EspnSyncContext:
    league_id: str
    season: int
    team_id: str
    canonical_url: str
    credentials: SessionEspnCredentials = SessionEspnCredentials()

    def __repr__(self) -> str:
        return f"EspnSyncContext(league_id={self.league_id!r}, season={self.season}, team_id={self.team_id!r}, credentials=***)"


def parse_espn_league_url(value: str, *, default_season: int | None = None) -> ParsedEspnLeagueUrl:
    text = (value or "").strip()
    if not text:
        raise ValueError("ESPN_URL_REQUIRED")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ESPN_HOSTS or parsed.username or parsed.password:
        raise ValueError("INVALID_ESPN_URL")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if SECRET_QUERY_KEYS.intersection(key.lower() for key in query):
        raise ValueError("SECRET_IN_URL")
    league_id = (query.get("leagueId") or query.get("leagueID") or [None])[0]
    if not league_id:
        match = LEAGUE_PATH_RE.search(parsed.path)
        league_id = match.group("league_id") if match else None
    if not league_id or not re.fullmatch(r"\d{1,30}", str(league_id)):
        raise ValueError("INVALID_ESPN_URL")
    season_match = SEASON_PATH_RE.search(parsed.path)
    path_season = int(season_match.group("season")) if season_match else None
    raw_season = (query.get("seasonId") or query.get("season") or [path_season or default_season or datetime.now(UTC).year])[0]
    try:
        season = int(raw_season)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_ESPN_URL") from exc
    if not 2020 <= season <= datetime.now(UTC).year + 1:
        raise ValueError("INVALID_ESPN_URL")
    canonical = f"https://fantasy.espn.com/football/league?leagueId={league_id}&seasonId={season}"
    return ParsedEspnLeagueUrl(str(league_id), season, canonical)


def scoring_format(league: League) -> str:
    return build_draft_configuration(league).scoring_format


def draft_rounds(league: League) -> int:
    config = build_draft_configuration(league)
    return int(config.total_rounds)


def build_active_league_state(
    league: League,
    *,
    provider: str = "ESPN",
    status: LeagueConnectionStatus | None = None,
    league_size: int | None = None,
    league_size_confirmed: bool = False,
    draft_position: int | None = None,
    draft_position_source: str | None = None,
    synced_at: datetime | None = None,
) -> ActiveLeagueState:
    if league.raw_settings.get("_team_selection_required"):
        raise ValueError("TEAM_CONFIRMATION_REQUIRED")
    team = next((row for row in league.teams if row.id == league.user_team_id), None)
    if team is None:
        raise ValueError("TEAM_NOT_FOUND")
    manager = resolve_manager_count(league, league_size, manual_confirmed=league_size_confirmed)
    seat = resolve_draft_slot(league, draft_position, manual_confirmed=draft_position_source == "manual")
    diagnostics = league.raw_settings.get("_draft_pool_diagnostics", {}) if isinstance(league.raw_settings, dict) else {}
    resolved_status = status or (LeagueConnectionStatus.PARTIAL if diagnostics.get("status") not in {None, "LIVE"} else LeagueConnectionStatus.CONNECTED)
    return ActiveLeagueState(
        connection_provider=provider,
        connection_status=resolved_status,
        league_id=league.id,
        league_name=league.name,
        season=league.season,
        team_id=team.id,
        team_name=team.name,
        league_size=manager.value,
        league_size_source=manager.source,
        league_size_confirmed=manager.confirmed,
        scoring_format=scoring_format(league),
        roster_slots=list(league.roster_slots),
        draft_type=league_draft_type(league),
        draft_rounds=draft_rounds(league),
        draft_position=seat.value,
        draft_position_source=draft_position_source or seat.source,
        draft_order_published=seat.source in {"espn_draft_order", "espn_live_draft"},
        last_synced_at=synced_at or datetime.now(UTC),
        sync_message="League imported with limited player-pool data" if resolved_status == LeagueConnectionStatus.PARTIAL else "League synchronized",
    )


def select_team(league: League, team_id: str) -> League:
    if not any(team.id == str(team_id) for team in league.teams):
        raise ValueError("TEAM_NOT_FOUND")
    settings = dict(league.raw_settings)
    settings["_team_selection_required"] = False
    settings["_selected_team_source"] = "user_confirmed"
    return league.model_copy(update={"user_team_id": str(team_id), "raw_settings": settings})


def deduplicate_leagues(leagues: Iterable[League]) -> list[League]:
    unique: dict[tuple[str, int], League] = {}
    for league in leagues:
        unique[(league.id, league.season)] = league
    return list(unique.values())


async def connect_with_backoff(
    operation: Callable[[], Awaitable[League]],
    *,
    attempts: int = 3,
    base_delay: float = 0.15,
) -> League:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await operation()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(min(1.0, base_delay * (2**attempt)))
    assert last_error is not None
    raise last_error


class SessionLeagueCache:
    """Per-Streamlit-session cache; never use as a process-global private cache."""

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = timedelta(seconds=max(1, ttl_seconds))
        self._values: dict[tuple[str, int, str], tuple[datetime, League]] = {}

    def get(self, league_id: str, season: int, auth_scope: str) -> League | None:
        row = self._values.get((league_id, season, auth_scope))
        if not row:
            return None
        created, league = row
        if datetime.now(UTC) - created > self.ttl:
            self.invalidate(league_id, season)
            return None
        return league

    def put(self, league: League, auth_scope: str) -> None:
        self._values[(league.id, league.season, auth_scope)] = (datetime.now(UTC), league)

    def invalidate(self, league_id: str | None = None, season: int | None = None) -> None:
        for key in list(self._values):
            if (league_id is None or key[0] == league_id) and (season is None or key[1] == season):
                self._values.pop(key, None)


async def cached_league_connect(
    cache: SessionLeagueCache,
    league_id: str,
    season: int,
    auth_scope: str,
    operation: Callable[[], Awaitable[League]],
    *,
    force: bool = False,
) -> League:
    cached = None if force else cache.get(league_id, season, auth_scope)
    if cached is not None:
        return cached
    league = await connect_with_backoff(operation)
    cache.put(league, auth_scope)
    return league


def safe_connection_error(exc: Exception) -> tuple[LeagueConnectionStatus, str]:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 403}:
        return LeagueConnectionStatus.EXPIRED, "Your ESPN session has expired. Reconnect ESPN to refresh your league."
    if str(exc) in {"ESPN_AUTH_RESPONSE_INVALID", "INVALID_ESPN_AUTH"}:
        return LeagueConnectionStatus.EXPIRED, "Your ESPN session has expired or is not valid for this league. Reconnect ESPN and try again."
    if str(exc) == "INCOMPLETE_ESPN_AUTH":
        return LeagueConnectionStatus.UNAVAILABLE, "Private ESPN connection needs both sensitive session values. Enter both, or leave both blank for a public league."
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return LeagueConnectionStatus.UNAVAILABLE, "We could not find that football league for this season. Open the league in ESPN and copy its current URL."
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return LeagueConnectionStatus.UNAVAILABLE, "ESPN is temporarily unavailable. Your existing league remains active; try Sync now again shortly."
    if str(exc) == "SECRET_IN_URL":
        return LeagueConnectionStatus.UNAVAILABLE, "Remove authentication values from the URL. Fourth Down never accepts ESPN session tokens in links."
    return LeagueConnectionStatus.UNAVAILABLE, "Fourth Down could not import that ESPN league. Check the league URL and season, then try again."


def clear_connection_state(state: MutableMapping[str, object]) -> None:
    cache = state.get("espn_cache")
    if isinstance(cache, SessionLeagueCache):
        cache.invalidate()
    for key in CONNECTION_SESSION_KEYS:
        state.pop(key, None)
