from app.advanced import calibration_summary, evaluate_trade, player_research, power_rankings, trade_ideas
from app.demo import demo_league
from app.domain import League, Player, Team
from app.engine import optimize_lineup, project, waiver_moves
from app.projection_service import ProjectionService


def p(pid: str, pos: str, mean: float, sd: float = 3, availability: float = 1) -> Player:
    eligible = {pos}
    if pos in {"RB", "WR", "TE"}:
        eligible.add("FLEX")
    if pos in {"QB", "RB", "WR", "TE"}:
        eligible.add("SUPERFLEX")
    return Player(id=pid, name=pid, position=pos, team="TST", eligible_slots=eligible, mean=mean, stdev=sd, availability=availability, injury_status="OUT" if availability == 0 else "HEALTHY")


def league_with(players: list[Player], free_agents: list[Player] | None = None, slots: list[str] | None = None) -> League:
    return League(id="unit", name="Unit League", season=2026, week=1, user_team_id="1", roster_slots=slots or ["QB"], teams=[Team(id="1", name="You", players=players), Team(id="2", name="Them", players=[p("opp-qb", "QB", 12)])], free_agents=free_agents or [])


def test_projection_factors_are_bounded_and_labeled():
    player = demo_league().teams[0].players[0]
    result = project(player, market_factor=99, context_factor=99)
    assert result.mean == round(player.mean * 1.18 * 1.10, 2)
    assert result.baseline_value == player.mean
    assert result.baseline_source
    assert result.adjustments
    assert "estimates" in result.limitations[0]
    assert "player props" in result.missing


def test_optimal_lineup_beats_greedy_flex_trap():
    players = [
        Player(id="elite-k-flex", name="elite-k-flex", position="K", team="TST", eligible_slots={"K", "FLEX"}, mean=20, stdev=3),
        Player(id="k2", name="k2", position="K", team="TST", eligible_slots={"K"}, mean=19, stdev=3),
        p("rb", "RB", 10),
    ]
    result = optimize_lineup(players, ["K", "FLEX"])
    assigned = {(entry.slot, entry.player.id) for entry in result.starters}
    assert result.is_complete
    assert ("FLEX", "elite-k-flex") in assigned
    assert ("K", "k2") in assigned
    assert result.expected_score == 39


def test_flex_conflict_and_duplicate_prevention(tmp_path):
    players = [p("rb1", "RB", 12), p("rb2", "RB", 10), p("wr1", "WR", 11)]
    result = optimize_lineup(players, ["RB", "FLEX"], projection_service=ProjectionService(tmp_path))
    ids = [entry.player.id for entry in result.starters]
    assert len(ids) == len(set(ids)) == 2
    assert result.expected_score == 23


def test_unavailable_player_is_not_started():
    players = [p("out-qb", "QB", 40, availability=0), p("active-qb", "QB", 12)]
    result = optimize_lineup(players, ["QB"])
    assert result.starters[0].player.id == "active-qb"


def test_incomplete_legal_lineup_reports_missing_slots():
    result = optimize_lineup([p("only-qb", "QB", 12)], ["QB", "RB"])
    assert not result.is_complete
    assert "RB" in result.missing_slots
    assert "complete legal lineup" in result.explanation


def test_simulation_is_deterministic():
    league = demo_league()
    a = optimize_lineup(league.teams[0].players, league.roster_slots)
    b = optimize_lineup(league.teams[0].players, league.roster_slots)
    assert a.win_probability == b.win_probability


def test_power_rankings_are_deterministic_and_display_bounded():
    league = demo_league()
    a = power_rankings(league, simulations=50, seed=99)
    b = power_rankings(league, simulations=50, seed=99)
    assert [x.model_dump() for x in a] == [x.model_dump() for x in b]
    assert all(0 <= row.playoff_probability <= 1 for row in a)


def test_waiver_moves_compare_legal_lineups_and_use_week_specific_ros():
    league = demo_league()
    moves = waiver_moves(league)
    assert moves and all(move.weekly_gain > 0 for move in moves)
    assert all(move.add.id != move.drop.id for move in moves)
    assert "espn weekly projections" in " ".join(moves[0].reasons).lower()
    assert moves[0].drop_safety in {"Safe drop", "Reasonable drop", "Situational drop", "High-risk drop", "Do not drop"}
    assert moves[0].faab_guidance["label"] == "Value-based FAAB guidance"


def test_recommendations_survive_missing_current_week_with_real_season_baselines():
    league = demo_league()
    league.teams = [
        team.model_copy(update={"players": [player.model_copy(update={"mean": float(player.season_projection or player.mean * 17) / 17, "projection_available": True, "projection_source": "ESPN season projection (weekly average)", "season_projection": float(player.season_projection or player.mean * 17)}) for player in team.players]})
        for team in league.teams
    ]
    league.free_agents = [player.model_copy(update={"mean": float(player.season_projection or player.mean * 17) / 17, "projection_available": True, "projection_source": "ESPN season projection (weekly average)", "season_projection": float(player.season_projection or player.mean * 17)}) for player in league.free_agents]
    lineup = optimize_lineup(league.teams[0].players, league.roster_slots, league=league)
    moves = waiver_moves(league)
    ideas = trade_ideas(league)
    assert lineup.starters
    assert lineup.expected_score > 0
    assert moves
    assert ideas
    assert "season-average" in " ".join(moves[0].reasons).lower()
    assert moves[0].confidence < 0.64


def test_uneven_trade_reports_required_drop_and_heuristic_risk():
    league = demo_league()
    team = league.teams[0]
    opponent = league.teams[1]
    result = evaluate_trade(league, [team.players[0].id], [opponent.players[0].id, opponent.players[1].id], opponent.id)
    assert result.required_drop is not None
    assert "heuristic" in " ".join(result.risks).lower()


def test_player_research_does_not_generate_synthetic_history():
    league = demo_league()
    data = player_research(league, league.teams[0].players[0].id)
    assert data["weekly_trend"] is None
    assert "unavailable" in data["historical_note"].lower()


def test_calibration_unavailable_without_real_outcomes():
    summary = calibration_summary(rows=[], minimum_sample=2)
    assert summary.status == "UNAVAILABLE"
    assert summary.sample_size == 0
    assert not summary.buckets


def test_real_calibration_metrics_from_known_rows():
    rows = [
        {"predicted_points": 10, "actual_points": 8, "predicted_probability": .75, "actual_outcome": 1},
        {"predicted_points": 20, "actual_points": 23, "predicted_probability": .25, "actual_outcome": 0},
    ]
    summary = calibration_summary(rows=rows, minimum_sample=2)
    assert summary.status == "AVAILABLE"
    assert summary.sample_size == 2
    assert summary.points_mae == 2.5
    assert summary.mean_bias == -0.5
    assert summary.brier_score == 0.062


def test_demo_calibration_is_labeled_as_demo_only():
    summary = calibration_summary(demo_example=True)
    assert summary.status == "DEMO"
    assert summary.is_demo
    assert "not model performance" in summary.verdict.lower()
