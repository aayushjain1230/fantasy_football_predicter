from app.demo import demo_league
from app.engine import optimize_lineup, project, waiver_moves


def test_projection_factors_are_bounded():
    player = demo_league().teams[0].players[0]
    assert project(player, market_factor=99, context_factor=99).mean == round(player.mean * 1.18 * 1.10, 2)


def test_lineup_is_legal_and_unique():
    league = demo_league()
    result = optimize_lineup(league.teams[0].players, league.roster_slots)
    ids = [e.player.id for e in result.starters]
    assert len(ids) == len(set(ids)) == len(league.roster_slots)
    assert all(e.slot in e.player.eligible_slots for e in result.starters)


def test_simulation_is_deterministic():
    league = demo_league()
    a = optimize_lineup(league.teams[0].players, league.roster_slots)
    b = optimize_lineup(league.teams[0].players, league.roster_slots)
    assert a.win_probability == b.win_probability


def test_waiver_moves_compare_real_drop():
    moves = waiver_moves(demo_league())
    assert moves and all(move.weekly_gain > 0 for move in moves)
    assert all(move.add.id != move.drop.id for move in moves)
