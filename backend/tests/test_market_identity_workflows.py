import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from app.cache_policy import private_league_hash, stable_cache_key
from app.decision_journal import create_decision_entry, evaluate_decision
from app.demo import demo_league
from app.domain import Player, ProviderReliabilityState
from app.engine import optimize_lineup
from app.identity import build_identity_index, normalize_player_name, resolve_player_identity
from app.market import (
    FixtureMarketContextProvider,
    MarketObservation,
    UnavailableMarketContextProvider,
    american_odds_to_implied_probability,
    consensus_line,
    remove_vig,
)
from app.projection_service import ProjectionService
from app.provider_reliability import with_provider_retries
from app.recommendations import RecommendationStatus, execute_if_supported, generate_recommendation, require_confirmation, validate_recommendation


def p(pid: str, name: str, pos: str, mean: float, sd: float = 3, team: str = "BAL") -> Player:
    eligible = {pos}
    if pos in {"RB", "WR", "TE"}:
        eligible.add("FLEX")
    if pos in {"QB", "RB", "WR", "TE"}:
        eligible.add("SUPERFLEX")
    return Player(id=pid, name=name, position=pos, team=team, eligible_slots=eligible, mean=mean, stdev=sd)


def test_american_odds_and_vig_removal():
    assert american_odds_to_implied_probability(-150) == 0.6
    assert american_odds_to_implied_probability(200) == 0.333333
    assert american_odds_to_implied_probability("bad") is None
    fair = remove_vig({"home": 0.6, "away": 0.5})
    assert fair == {"home": 0.545455, "away": 0.454545}


def test_consensus_market_calculation_filters_bad_stale_and_duplicate_records():
    now = datetime.now(UTC)
    observations = [
        MarketObservation("totals", "Over", 47.5, -110, "A", observed_at=now.isoformat()),
        MarketObservation("totals", "Over", 47.5, -110, "A", observed_at=now.isoformat()),
        MarketObservation("totals", "Over", 48.5, -105, "B", observed_at=now.isoformat()),
        MarketObservation("totals", "Over", None, -105, "C", observed_at=now.isoformat()),
        MarketObservation("totals", "Over", 99.0, -105, "D", observed_at=(now - timedelta(days=3)).isoformat()),
        MarketObservation("totals", "Over", 45.5, -110, "A", observed_at=now.isoformat(), is_opening=True),
    ]
    result = consensus_line(observations, now=now)
    assert result["line"] == 48.0
    assert result["books_used"] == 2
    assert result["opening_line"] == 45.5
    assert result["line_movement"] == 2.5


def test_missing_market_provider_never_fabricates_lines():
    provider = UnavailableMarketContextProvider()
    game = provider.get_game_market("game-1")
    player = provider.get_player_market("player-1")
    assert not game.available
    assert game.game_total is None
    assert not player.available
    assert player.rushing_yards is None


def test_fixture_market_provider_exposes_books_and_quality():
    provider = FixtureMarketContextProvider(
        player_observations={
            "p1": [
                MarketObservation("player_receptions", "Over", 5.5, -110, "A"),
                MarketObservation("player_receptions", "Over", 6.5, -115, "B"),
            ]
        }
    )
    market = provider.get_player_market("p1")
    assert market.available
    assert market.receptions == 6.0
    assert market.metadata.books_used == 2
    assert market.metadata.data_quality == "fresh"


def test_player_identity_resolution_handles_suffixes_apostrophes_and_ambiguity():
    players = [
        p("1", "Brian Robinson Jr.", "RB", 10, team="WAS"),
        p("2", "Brian Robinson", "WR", 9, team="LAR"),
        p("3", "D'Andre Swift", "RB", 12, team="CHI"),
        p("4", "D Andre Swift", "RB", 8, team="DET"),
    ]
    index = build_identity_index(players, season=2026)
    assert normalize_player_name("Brian Robinson III") == "brian robinson"
    resolved = resolve_player_identity("D'Andre Swift", candidates=index, position="RB", nfl_team_id="CHI")
    assert resolved.resolved
    ambiguous = resolve_player_identity("D Andre Swift", candidates=index, position="RB")
    assert not ambiguous.resolved
    assert ambiguous.ambiguous


def test_cache_keys_isolate_private_leagues_and_dimensions():
    a = stable_cache_key("ESPN", "roster", league=private_league_hash("123"), week=1, scoring="ppr")
    b = stable_cache_key("ESPN", "roster", league=private_league_hash("456"), week=1, scoring="ppr")
    c = stable_cache_key("ESPN", "roster", league=private_league_hash("123"), week=2, scoring="ppr")
    assert len({a, b, c}) == 3


def test_conservative_balanced_aggressive_have_distinct_objectives():
    league = demo_league()
    team = league.teams[0]
    conservative = optimize_lineup(team.players, league.roster_slots, style="Conservative", league=league)
    balanced = optimize_lineup(team.players, league.roster_slots, style="Balanced", league=league)
    aggressive = optimize_lineup(team.players, league.roster_slots, style="Aggressive", league=league, opponent_mean=160)
    assert "floor" in conservative.explanation.lower()
    assert "expected" in balanced.explanation.lower()
    assert "ceiling" in aggressive.explanation.lower()
    assert conservative.is_complete and balanced.is_complete and aggressive.is_complete


def test_locked_players_and_duplicate_prevention():
    players = [p("qb1", "QB One", "QB", 20), p("qb2", "QB Two", "QB", 18), p("rb", "RB One", "RB", 15)]
    result = optimize_lineup(players, ["QB", "FLEX"], style="Balanced", locked_player_ids={"qb2"})
    ids = [entry.player.id for entry in result.starters]
    assert "qb2" in ids
    assert len(ids) == len(set(ids))


def test_market_adjusted_projection_keeps_baseline_distinct(tmp_path):
    provider = FixtureMarketContextProvider(player_observations={"p1": [MarketObservation("player_receptions", "Over", 8.5, -110, "A"), MarketObservation("player_receptions", "Over", 8.0, -110, "B")]})
    service = ProjectionService(market_provider=provider, enable_market_adjustments=True)
    player = p("p1", "Slot WR", "WR", 10)
    projection = service.project_player(player)
    assert projection.baseline_projection != projection.final_projection
    assert projection.final_projection == projection.mean
    assert projection.market_data_available
    assert projection.market_adjustment != 0


def test_recommendation_status_transitions_are_explicit():
    preview = validate_recommendation(generate_recommendation("Lineup", {"QB": "A"}, {"QB": "B"}))
    assert preview.status == RecommendationStatus.PREVIEW
    preview = require_confirmation(preview, supported_execution=False)
    assert preview.status == RecommendationStatus.UNSUPPORTED
    preview = execute_if_supported(preview, confirmed=True, supported_execution=False)
    assert preview.status == RecommendationStatus.UNSUPPORTED


def test_decision_journal_creation_and_no_lookahead_regret():
    entry = create_decision_entry(
        season=2026,
        week=1,
        league_id="private-123",
        decision_type="Start/sit",
        model_version="test",
        data_snapshot_id="snapshot",
        recommendation={"player_id": "a"},
        alternatives=[{"player_id": "b"}, {"player_id": "late-waiver-not-valid"}],
        expected_points=12,
        floor=8,
        ceiling=18,
        confidence="Medium",
        explanation=["Fixture test"],
    )
    evaluated = evaluate_decision(entry, {"a": 10, "b": 14, "late-waiver-not-valid": 30}, ["b"])
    assert evaluated.league_id_hash != "private-123"
    assert evaluated.actual_outcome["absolute_error"] == 2
    assert evaluated.actual_outcome["regret"] == 4


def test_provider_timeout_and_rate_limit_states():
    async def timeout_call():
        raise httpx.TimeoutException("slow")

    _, timeout_status = asyncio.run(with_provider_retries("Odds", timeout_call, retries=0))
    assert timeout_status.status == ProviderReliabilityState.UNAVAILABLE

    async def rate_limited():
        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("too many", request=request, response=response)

    _, rate_status = asyncio.run(with_provider_retries("Odds", rate_limited, retries=1))
    assert rate_status.status == ProviderReliabilityState.RATE_LIMITED
