from app.decision_service import build_weekly_brief, classify_trade, value_based_faab
from app.demo import demo_league
from app.domain import League, LeagueRuleSet, Matchup, Player, Team


def p(pid: str, pos: str, mean: float, availability: float = 1) -> Player:
    eligible = {pos}
    if pos in {"RB", "WR", "TE"}:
        eligible.add("FLEX")
    if pos in {"QB", "RB", "WR", "TE"}:
        eligible.add("SUPERFLEX")
    return Player(id=pid, name=pid, position=pos, team="TST", eligible_slots=eligible, mean=mean, stdev=2, availability=availability, injury_status="OUT" if availability == 0 else "HEALTHY")


def test_weekly_brief_returns_ranked_user_facing_decisions():
    brief = build_weekly_brief(demo_league())
    assert brief.top_actions
    priorities = [action.priority for action in brief.top_actions]
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Monitor": 4}
    assert priorities == sorted(priorities, key=order.get)
    first = brief.top_actions[0]
    assert first.recommended_action
    assert first.confidence in {"High", "Medium", "Low"}
    assert first.robustness in {"Robust", "Moderately robust", "Assumption-sensitive", "Speculative"}


def test_brief_can_recommend_holding_when_no_move_has_value():
    team = Team(id="1", name="You", wins=1, losses=0, players=[p("qb", "QB", 20)])
    opp = Team(id="2", name="Them", wins=0, losses=1, players=[p("opp", "QB", 18)])
    league = League(
        id="hold",
        name="Hold League",
        season=2026,
        week=1,
        user_team_id="1",
        roster_slots=["QB"],
        teams=[team, opp],
        free_agents=[p("fa", "QB", 1, availability=1)],
        rules=LeagueRuleSet(regular_season_end=1),
        schedule=[Matchup(id="1", period=1, home_team_id="1", away_team_id="2")],
    )
    brief = build_weekly_brief(league)
    assert any(action.decision_id == "hold-roster" for action in brief.top_actions)


def test_faab_guidance_is_value_based_not_market_prediction():
    league = demo_league()
    guidance = value_based_faab(league, weekly_gain=3.2, position="RB", confidence=0.64)
    assert guidance["label"] == "Value-based FAAB guidance"
    assert guidance["suggested_low"] <= guidance["suggested_high"] <= guidance["aggressive_max"]
    assert "not a prediction" in guidance["note"]


def test_trade_classification_does_not_claim_acceptance_probability():
    assert classify_trade(3.0, 0.5) == "Mutually beneficial"
    brief = build_weekly_brief(demo_league())
    trade_actions = [action for action in brief.top_actions if action.category == "Trades"]
    for action in trade_actions:
        text = " ".join([action.title, action.recommended_action, *action.reasons, *action.risks]).lower()
        assert "accept" not in text
