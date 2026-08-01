import pytest

from app.demo import demo_league
from app.domain import League, LeagueRuleSet, Matchup, Player, Team
from app.simulation import ScenarioConstraint, league_fingerprint, schedule_analysis, simulate_league, team_score_distributions, validate_scenarios


def p(pid: str, pos: str, mean: float, sd: float = 2.0) -> Player:
    eligible = {pos}
    if pos in {"RB", "WR", "TE"}:
        eligible.add("FLEX")
    if pos in {"QB", "RB", "WR", "TE"}:
        eligible.add("SUPERFLEX")
    return Player(id=pid, name=pid, position=pos, team="TST", eligible_slots=eligible, mean=mean, stdev=sd)


def team(tid: str, wins: int, losses: int, mean: float) -> Team:
    return Team(id=tid, name=f"Team {tid}", record=f"{wins}-{losses}", wins=wins, losses=losses, points_for=wins * 100, points_against=losses * 100, players=[p(f"{tid}-qb", "QB", mean)])


def tiny_league() -> League:
    return League(
        id="tiny",
        name="Tiny",
        season=2026,
        week=2,
        user_team_id="1",
        roster_slots=["QB"],
        playoff_team_count=2,
        teams=[team("1", 1, 0, 30), team("2", 1, 0, 20), team("3", 0, 1, 10), team("4", 0, 1, 8)],
        rules=LeagueRuleSet(regular_season_end=3, playoff_start=4, playoff_end=5, tiebreaker="record_then_points_for"),
        schedule=[
            Matchup(id="1-1-3", period=1, home_team_id="1", away_team_id="3", home_score=120, away_score=100, is_complete=True),
            Matchup(id="1-2-4", period=1, home_team_id="2", away_team_id="4", home_score=110, away_score=90, is_complete=True),
            Matchup(id="2-1-2", period=2, home_team_id="1", away_team_id="2", is_current=True),
            Matchup(id="2-3-4", period=2, home_team_id="3", away_team_id="4", is_current=True),
            Matchup(id="3-1-4", period=3, home_team_id="1", away_team_id="4"),
            Matchup(id="3-2-3", period=3, home_team_id="2", away_team_id="3"),
        ],
    )


def test_simulation_is_deterministic_and_does_not_mutate_source_league():
    league = tiny_league()
    before = league.model_dump()
    a = simulate_league(league, simulations=200, seed=7)
    b = simulate_league(league, simulations=200, seed=7)
    assert a.model_dump() == b.model_dump()
    assert league.model_dump() == before
    assert a.teams[0].playoff_se >= 0
    assert a.teams[0].most_likely_seed is not None


def test_actual_remaining_matchups_drive_playoff_probability():
    league = tiny_league()
    baseline = simulate_league(league, simulations=500, seed=9)
    constrained = simulate_league(league, scenarios=[ScenarioConstraint(matchup_id="2-1-2", winner_team_id="2")], simulations=500, seed=9)
    team1_base = next(row for row in baseline.teams if row.team_id == "1")
    team1_loss = next(row for row in constrained.teams if row.team_id == "1")
    assert team1_loss.expected_final_wins < team1_base.expected_final_wins
    assert any(s.matchup_id == "2-1-2" for s in constrained.scenario_constraints)


def test_scenario_validation_rejects_contradictions_and_completed_overrides():
    league = tiny_league()
    with pytest.raises(ValueError, match="Completed"):
        validate_scenarios(league, [ScenarioConstraint(matchup_id="1-1-3", winner_team_id="1")])
    with pytest.raises(ValueError, match="selected more than once"):
        validate_scenarios(league, [ScenarioConstraint(matchup_id="2-1-2", winner_team_id="1"), ScenarioConstraint(matchup_id="2-1-2", winner_team_id="2")])
    with pytest.raises(ValueError, match="scores do not match"):
        validate_scenarios(league, [ScenarioConstraint(matchup_id="2-1-2", winner_team_id="1", home_score=80, away_score=90)])


def test_mathematical_status_is_not_inferred_from_monte_carlo_zero():
    league = tiny_league()
    result = simulate_league(league, simulations=50, seed=5)
    statuses = {team.team_id: team.mathematical_status for team in result.teams}
    assert statuses["1"] in {"Clinched playoff berth", "Mathematically alive"}
    assert all(status != "Mathematically eliminated" for status in statuses.values() if status.startswith("Clinched"))


def test_team_distribution_uses_variance_aggregation_not_summed_floors():
    league = demo_league()
    dist = team_score_distributions(league)[0]
    assert dist.upper_estimate > dist.expected_score > dist.lower_estimate
    assert dist.score_stdev > 0
    assert dist.model_version == "phase4_schedule_sim_v1"


def test_schedule_luck_and_all_play_metrics_use_completed_weeks_only():
    league = tiny_league()
    metrics = schedule_analysis(league, team_score_distributions(league))
    row = next(metric for metric in metrics if metric.team_id == "1")
    assert row.all_play_wins == 3
    assert row.all_play_expected_wins == 1
    assert row.schedule_luck == 0


def test_league_fingerprint_changes_when_schedule_changes():
    league = tiny_league()
    first = league_fingerprint(league)
    league.schedule.append(Matchup(id="4-1-3", period=4, home_team_id="1", away_team_id="3"))
    assert league_fingerprint(league) != first
