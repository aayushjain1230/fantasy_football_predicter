import asyncio
import json
import time
from datetime import UTC, datetime

import pytest

from app.connection_handshake import OneTimeConnectionStore
from app.demo import demo_league
from app.domain import LeagueConnectionStatus
from app.espn_connection import (
    SessionEspnCredentials,
    SessionLeagueCache,
    build_active_league_state,
    cached_league_connect,
    clear_connection_state,
    connect_with_backoff,
    deduplicate_leagues,
    parse_espn_league_url,
    select_team,
)


@pytest.mark.parametrize(
    "url,league_id,season",
    [
        ("https://fantasy.espn.com/football/league?leagueId=12345&seasonId=2026", "12345", 2026),
        ("https://games.espn.com/ffl/leagueoffice?leagueId=55&seasonId=2025", "55", 2025),
        ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/88", "88", 2026),
    ],
)
def test_parse_espn_league_urls(url, league_id, season):
    parsed = parse_espn_league_url(url, default_season=season)
    assert parsed.league_id == league_id
    assert parsed.season == season
    assert "espn_s2" not in parsed.canonical_url.lower()


def test_authentication_secrets_are_rejected_in_urls_and_redacted_in_repr():
    with pytest.raises(ValueError, match="SECRET_IN_URL"):
        parse_espn_league_url("https://fantasy.espn.com/football/league?leagueId=1&seasonId=2026&SWID=secret")
    credentials = SessionEspnCredentials("secret-s2", "secret-swid")
    assert "secret-s2" not in repr(credentials)
    assert "secret-swid" not in repr(credentials)


def test_multiple_leagues_are_deduplicated_by_id_and_season():
    league = demo_league()
    newer = league.model_copy(update={"name": "Updated"})
    other = league.model_copy(update={"season": league.season - 1})
    result = deduplicate_leagues([league, newer, other])
    assert len(result) == 2
    assert next(row for row in result if row.season == league.season).name == "Updated"


def test_active_league_selection_uses_confirmed_team_and_valid_draft_source():
    league = demo_league()
    selected = select_team(league, league.teams[1].id)
    selected.raw_settings["_draft_order"] = {selected.user_team_id: 4}
    active = build_active_league_state(selected)
    assert active.team_id == league.teams[1].id
    assert active.team_name == league.teams[1].name
    assert active.draft_position == 4
    assert active.draft_position_source == "espn_draft_order"
    assert active.draft_order_published


def test_missing_draft_order_is_never_inferred_from_team_id():
    league = demo_league()
    league.user_team_id = "2"
    league.raw_settings["_draft_order"] = {}
    league.raw_settings["_live_draft_order"] = {}
    active = build_active_league_state(league)
    assert active.draft_position is None
    assert active.draft_position_source == "unavailable"


def test_player_pool_failure_keeps_active_league_partial():
    league = demo_league()
    league.raw_settings["_draft_pool_diagnostics"] = {"status": "UNAVAILABLE"}
    active = build_active_league_state(league)
    assert active.connection_status == LeagueConnectionStatus.PARTIAL
    assert active.league_id == league.id


def test_session_cache_prevents_repeat_call_and_can_be_invalidated():
    league = demo_league()
    cache = SessionLeagueCache(ttl_seconds=60)
    cache.put(league, "private")
    assert cache.get(league.id, league.season, "private") is league
    cache.invalidate(league.id, league.season)
    assert cache.get(league.id, league.season, "private") is None


def test_disconnect_clears_credentials_active_league_and_cache():
    league = demo_league()
    cache = SessionLeagueCache()
    cache.put(league, "private")
    state = {
        "league": league,
        "active_league": build_active_league_state(league),
        "espn_connection": SessionEspnCredentials("secret", "secret"),
        "espn_candidate_credentials": SessionEspnCredentials("secret", "secret"),
        "espn_cache": cache,
        "unrelated_preference": "keep",
    }
    clear_connection_state(state)
    assert "league" not in state
    assert "espn_connection" not in state
    assert "espn_candidate_credentials" not in state
    assert cache.get(league.id, league.season, "private") is None
    assert state["unrelated_preference"] == "keep"


def test_connect_backoff_returns_success_without_duplicate_success_call():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls < 2:
            import httpx
            raise httpx.ConnectError("temporary")
        return demo_league()

    assert asyncio.run(connect_with_backoff(operation, base_delay=0)).id == "demo"
    assert calls == 2


def test_streamlit_style_reruns_use_session_cache_without_repeated_espn_calls():
    calls = 0
    league = demo_league()
    cache = SessionLeagueCache()

    async def operation():
        nonlocal calls
        calls += 1
        return league

    async def reruns():
        first = await cached_league_connect(cache, league.id, league.season, "private", operation)
        second = await cached_league_connect(cache, league.id, league.season, "private", operation)
        return first, second

    first, second = asyncio.run(reruns())
    assert first is second
    assert calls == 1


def test_one_time_code_expires_is_single_use_and_checks_state():
    store = OneTimeConnectionStore(ttl_seconds=1)
    issued = store.issue("client")
    assert not store.redeem(issued.code, "wrong-state")
    issued = store.issue("client")
    assert store.redeem(issued.code, issued.state)
    assert not store.redeem(issued.code, issued.state)
    expired = store.issue("other")
    time.sleep(1.05)
    assert not store.redeem(expired.code, expired.state)


def test_one_time_code_issue_is_rate_limited():
    store = OneTimeConnectionStore(issue_limit=1, window_seconds=60)
    store.issue("client")
    with pytest.raises(ValueError, match="RATE_LIMITED"):
        store.issue("client")


def test_disabled_extension_requests_no_sensitive_permissions():
    from pathlib import Path

    manifest = json.loads((Path(__file__).resolve().parents[2] / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["permissions"] == []
    assert manifest["host_permissions"] == []
    script_text = " ".join((Path(__file__).resolve().parents[2] / "browser_extension" / name).read_text(encoding="utf-8") for name in ("background.js", "content.js", "popup.js"))
    assert "cookies.get" not in script_text
    assert "espn_s2" not in script_text
    assert "SWID" not in script_text
