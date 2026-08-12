import asyncio
import json

import httpx
import pytest

from app.domain import DataState
from app import providers
from app import live_providers


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://example.test")
        self.response = httpx.Response(status_code, request=self.request)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=self.request, response=self.response)


class FakeClient:
    calls = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "cookies": self.kwargs.get("cookies")})
        if headers:
            return FakeResponse({"players": [free_agent_fixture(), {"player": player_fixture()}]})
        return FakeResponse(league_fixture())


def player_fixture(pid="100", name="Test QB", pos=1, pro=1, projected=18):
    return {
        "id": pid,
        "fullName": name,
        "defaultPositionId": pos,
        "proTeamId": pro,
        "injuryStatus": "ACTIVE",
        "stats": [{"scoringPeriodId": 1, "statSourceId": 1, "appliedTotal": projected}],
    }


def free_agent_fixture():
    return {"player": player_fixture("200", "Free WR", 3, 8, 11)}


def league_fixture():
    return {
        "id": 123,
        "scoringPeriodId": 1,
        "settings": {
            "name": "Public League",
            "size": 10,
            "draftSettings": {"type": "SNAKE"},
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "2": 1, "23": 1}},
            "scoringSettings": {"scoringItems": [{"statId": 1, "points": 1}]},
            "scheduleSettings": {"playoffTeamCount": 4, "matchupPeriodCount": 14},
        },
        "draftDetail": {"draftOrder": {"1": 6}, "picks": [{"overallPickNumber": 1, "teamId": 1, "playerId": 100}]},
        "schedule": [
            {"id": 1, "matchupPeriodId": 1, "home": {"teamId": 1, "totalPoints": 99.5}, "away": {"teamId": 2, "totalPoints": 88.0}, "winner": "HOME"},
            {"id": 2, "matchupPeriodId": 2, "home": {"teamId": 1}, "away": {"teamId": 2}},
        ],
        "teams": [
            {
                "id": 1,
                "location": "Alpha",
                "nickname": "One",
                "record": {"overall": {"wins": 1, "losses": 0}},
                "roster": {"entries": [{"playerPoolEntry": {"player": player_fixture()}}]},
            }
        ],
    }


def test_public_espn_response_normalization(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    monkeypatch.delenv("ESPN_S2", raising=False)
    monkeypatch.delenv("ESPN_SWID", raising=False)
    league = asyncio.run(providers.connect_espn("123", 2026))
    assert league.name == "Public League"
    assert league.roster_slots == ["QB", "RB", "FLEX"]
    assert league.teams[0].players[0].name == "Test QB"
    assert league.free_agents[0].name == "Free WR"
    assert {player.name for player in league.draft_pool} == {"Free WR", "Test QB"}
    assert next(player for player in league.draft_pool if player.name == "Test QB").rostered
    assert league.rules.regular_season_end == 14
    assert league.schedule[0].is_complete
    assert league.schedule[1].home_team_id == "1"
    assert league.raw_settings["size"] == 10
    assert league.raw_settings["_draft_picks"][0]["player_name"] == "Test QB"
    assert league.raw_settings["_draft_picks"][0]["owner_slot"] == 1
    assert league.raw_settings["_draft_order"] == {"1": 6}
    assert league.raw_settings["_live_draft_order"] == {"1": 1}
    assert all(call["cookies"] == {} for call in FakeClient.calls)
    assert any(("view", "mDraftDetail") in (call["params"] or []) for call in FakeClient.calls if not call["headers"])
    pool_call = next(call for call in FakeClient.calls if call["headers"])
    draft_filter = json.loads(pool_call["headers"]["X-Fantasy-Filter"])["players"]
    assert draft_filter["limit"] == 1500
    assert "filterStatus" not in draft_filter
    assert "sortDraftRanks" in draft_filter
    assert pool_call["params"]["scoringPeriodId"] == 0


def test_espn_draft_rank_is_parsed_when_adp_and_projection_are_missing():
    values = providers._espn_player_values(
        {"draftRanksByRankType": {"PPR": {"rank": 17}}, "stats": []},
        current_period=1,
    )
    assert values["espn_rank"] == 17
    assert values["average_draft_position"] is None
    assert values["season_projection"] is None


def test_espn_wrapper_ownership_and_rank_are_parsed():
    values = providers._espn_player_values(
        {"stats": []},
        current_period=1,
        item={
            "playerPoolEntry": {
                "ownership": {"averageDraftPosition": 23.5, "percentOwned": 91.2},
                "draftRanksByRankType": {"PPR": {"rank": 19}},
            }
        },
    )
    assert values["average_draft_position"] == 23.5
    assert values["percent_owned"] == 91.2
    assert values["espn_rank"] == 19


def test_private_auth_error_is_not_decorated_with_secrets(monkeypatch):
    class AuthClient(FakeClient):
        async def get(self, *args, **kwargs):
            return FakeResponse({}, 403)

    monkeypatch.setattr(providers.httpx, "AsyncClient", AuthClient)
    monkeypatch.setenv("ESPN_S2", "secret-cookie-value")
    monkeypatch.setenv("ESPN_SWID", "{secret-swid}")
    try:
        asyncio.run(providers.connect_espn("123", 2026))
    except httpx.HTTPStatusError as exc:
        text = str(exc)
        assert "secret-cookie-value" not in text
        assert "secret-swid" not in text
    else:
        raise AssertionError("expected auth error")


def test_private_credentials_are_sent_only_as_espn_cookies(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    league = asyncio.run(
        providers.connect_espn(
            "123",
            2026,
            espn_s2="private-s2",
            espn_swid="{private-swid}",
        )
    )
    assert league.name == "Public League"
    assert FakeClient.calls
    assert all(
        call["cookies"] == {"espn_s2": "private-s2", "SWID": "{private-swid}"}
        for call in FakeClient.calls
    )


def test_copied_cookie_fragments_are_normalized(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    asyncio.run(
        providers.connect_espn(
            "123",
            2026,
            espn_s2="espn_s2=private-s2; Path=/",
            espn_swid="SWID=private-swid; Domain=.espn.com",
        )
    )
    assert all(call["cookies"] == {"espn_s2": "private-s2", "SWID": "{private-swid}"} for call in FakeClient.calls)


def test_player_pool_retries_with_bounded_fallback(monkeypatch):
    class FallbackClient(FakeClient):
        pool_calls = 0

        async def get(self, url, params=None, headers=None):
            if headers:
                self.__class__.pool_calls += 1
                if self.__class__.pool_calls == 1:
                    return FakeResponse({}, 500)
                return FakeResponse({"players": [free_agent_fixture()]})
            return FakeResponse(league_fixture())

    FallbackClient.pool_calls = 0
    monkeypatch.setattr(providers.httpx, "AsyncClient", FallbackClient)
    league = asyncio.run(providers.connect_espn("123", 2026))
    assert FallbackClient.pool_calls == 2
    assert league.draft_pool


def test_player_pool_failure_preserves_league_and_exposes_diagnostics(monkeypatch):
    class FailedPoolClient(FakeClient):
        async def get(self, url, params=None, headers=None):
            return FakeResponse({}, 500) if headers else FakeResponse(league_fixture())

    monkeypatch.setattr(providers.httpx, "AsyncClient", FailedPoolClient)
    league = asyncio.run(providers.connect_espn("123", 2026))
    assert league.name == "Public League"
    assert league.draft_pool == []
    diagnostics = league.raw_settings["_draft_pool_diagnostics"]
    assert diagnostics["status"] == "UNAVAILABLE"
    assert diagnostics["raw_player_count"] == 0
    assert diagnostics["normalized_player_count"] == 0
    assert len(diagnostics["attempts"]) == 3


def test_nested_player_pool_entry_shape_is_normalized(monkeypatch):
    class NestedPoolClient(FakeClient):
        async def get(self, url, params=None, headers=None):
            if headers:
                return FakeResponse({"players": [{"playerPoolEntry": {"player": player_fixture("300", "Nested RB", 2, 2, 12)}}]})
            return FakeResponse(league_fixture())

    monkeypatch.setattr(providers.httpx, "AsyncClient", NestedPoolClient)
    league = asyncio.run(providers.connect_espn("123", 2026))
    assert [player.name for player in league.draft_pool] == ["Nested RB"]
    diagnostics = league.raw_settings["_draft_pool_diagnostics"]
    assert diagnostics["raw_player_count"] == 1
    assert diagnostics["normalized_player_count"] == 1
    assert diagnostics["status"] == "LIVE"
    assert league.draft_pool[0].draft_pool_rank == 1


def test_private_login_page_becomes_safe_auth_error(monkeypatch):
    class HtmlResponse(FakeResponse):
        def json(self):
            raise ValueError("not json private-s2")

    class HtmlClient(FakeClient):
        async def get(self, *args, **kwargs):
            return HtmlResponse("<html>login</html>")

    monkeypatch.setattr(providers.httpx, "AsyncClient", HtmlClient)
    with pytest.raises(ValueError, match="ESPN_AUTH_RESPONSE_INVALID") as captured:
        asyncio.run(providers.connect_espn("123", 2026, espn_s2="private-s2", espn_swid="private-swid"))
    assert "private-s2" not in str(captured.value)


def test_private_credentials_require_both_values():
    try:
        asyncio.run(providers.connect_espn("123", 2026, espn_s2="private-s2"))
    except ValueError as exc:
        assert str(exc) == "INCOMPLETE_ESPN_AUTH"
        assert "private-s2" not in str(exc)
    else:
        raise AssertionError("expected incomplete private authentication error")


def test_provider_statuses_are_honest_without_cache(monkeypatch):
    monkeypatch.setattr("app.persistence.cache_get", lambda key: None)
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    states = {status.provider: status for status in providers.statuses(demo=True)}
    assert states["ESPN"].state == DataState.LIVE
    assert states["The Odds API"].state == DataState.UNAVAILABLE
    assert states["nflverse"].used_by == []
    assert "not yet parsed" in states["nflverse"].impact


def test_provider_status_uses_cached_odds_only_after_cache(monkeypatch):
    monkeypatch.setattr("app.persistence.cache_get", lambda key: {"status": "CACHED", "fetched_at": "2026-01-01T00:00:00Z"} if key == "odds:nfl" else None)
    rows = providers.statuses(demo=False)
    odds = next(row for row in rows if row.provider == "The Odds API")
    assert odds.state == DataState.CACHED
    assert odds.updated == "2026-01-01T00:00:00Z"


def test_session_odds_key_validates_without_persistence(monkeypatch):
    calls = []

    class OddsResponse(FakeResponse):
        headers = {"x-requests-remaining": "499", "x-requests-used": "1"}

    class OddsClient(FakeClient):
        async def get(self, url, params=None, headers=None):
            calls.append({"url": url, "params": params})
            return OddsResponse([{"key": "americanfootball_nfl"}])

    monkeypatch.setattr(live_providers.httpx, "AsyncClient", OddsClient)
    result = asyncio.run(live_providers.validate_odds_key("session-secret"))
    assert result["valid"] is True
    assert calls[0]["url"].endswith("/v4/sports")
    assert calls[0]["params"] == {"apiKey": "session-secret"}
    assert "session-secret" not in str(result)


def test_session_odds_refresh_reports_quota_and_caches_payload_only(monkeypatch):
    cached = []

    class OddsResponse(FakeResponse):
        headers = {"x-requests-remaining": "497", "x-requests-used": "3", "x-requests-last": "3"}

    class OddsClient(FakeClient):
        async def get(self, url, params=None, headers=None):
            assert params["apiKey"] == "session-secret"
            return OddsResponse([{"id": "game-1", "bookmakers": []}])

    monkeypatch.setattr(live_providers.httpx, "AsyncClient", OddsClient)
    monkeypatch.setattr(live_providers, "cache_get", lambda key: None)
    monkeypatch.setattr(live_providers, "cache_set", lambda *args: cached.append(args))
    result = asyncio.run(live_providers.odds(force=True, api_key="session-secret"))
    assert result["status"] == "LIVE"
    assert result["request_cost"] == "3"
    assert result["remaining_requests"] == "497"
    assert cached and "session-secret" not in str(cached)


def test_openweather_key_validation_does_not_return_secret(monkeypatch):
    class WeatherResponse(FakeResponse):
        headers = {}

    class WeatherClient(FakeClient):
        async def get(self, url, params=None, headers=None):
            assert url == "https://api.openweathermap.org/data/2.5/weather"
            assert params["appid"] == "weather-secret"
            return WeatherResponse({"name": "Baltimore"})

    monkeypatch.setattr(live_providers.httpx, "AsyncClient", WeatherClient)
    result = asyncio.run(live_providers.validate_openweather_key("weather-secret"))
    assert result == {"valid": True, "provider": "OpenWeather", "sample_station": "Baltimore"}
    assert "weather-secret" not in str(result)
