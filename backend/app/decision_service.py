from __future__ import annotations

from collections import defaultdict

from .advanced import evaluate_trade, trade_ideas
from .domain import DecisionRecommendation, League, RosterPositionOutlook, Team, WeeklyBrief
from .engine import optimize_lineup, user_team, waiver_moves
from .simulation import simulate_league


PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Monitor": 4}


def _priority(points: float | None, win_delta: float | None, *, critical: bool = False, monitor: bool = False) -> str:
    if critical:
        return "Critical"
    if monitor:
        return "Monitor"
    points = abs(points or 0)
    win_delta = abs(win_delta or 0)
    if points >= 4 or win_delta >= 0.06:
        return "High"
    if points >= 1.5 or win_delta >= 0.025:
        return "Medium"
    return "Low"


def _confidence(points: float, missing_count: int, injury_sensitive: bool = False) -> str:
    if injury_sensitive or missing_count >= 4:
        return "Low"
    if points >= 3 and missing_count <= 2:
        return "High"
    return "Medium"


def _robustness(points: float, risk_count: int, injury_sensitive: bool = False) -> str:
    if injury_sensitive or points < 1:
        return "Assumption-sensitive"
    if points >= 4 and risk_count <= 1:
        return "Robust"
    if points >= 1.5:
        return "Moderately robust"
    return "Speculative"


def _current_opponent(league: League, team: Team) -> Team | None:
    for matchup in league.schedule:
        if not matchup.is_complete and matchup.period == league.week and team.id in {matchup.home_team_id, matchup.away_team_id}:
            opponent_id = matchup.away_team_id if matchup.home_team_id == team.id else matchup.home_team_id
            return next((candidate for candidate in league.teams if candidate.id == opponent_id), None)
    return next((candidate for candidate in league.teams if candidate.id != team.id), None)


def _lineup_decisions(league: League, team: Team) -> list[DecisionRecommendation]:
    balanced = optimize_lineup(team.players, league.roster_slots, style="balanced", league=league)
    safe = optimize_lineup(team.players, league.roster_slots, style="safe", league=league)
    upside = optimize_lineup(team.players, league.roster_slots, style="upside", league=league)
    decisions: list[DecisionRecommendation] = []
    if not balanced.is_complete:
        decisions.append(
            DecisionRecommendation(
                decision_id="lineup-incomplete",
                category="Lineup",
                priority="Critical",
                title="Fix incomplete lineup",
                recommended_action=f"Fill missing slots: {', '.join(balanced.missing_slots)}",
                baseline_action="Current roster cannot form a complete legal lineup",
                confidence="High",
                robustness="Robust",
                deadline=f"Before Week {league.week} lineup lock",
                reasons=["The exact optimizer could not assign enough eligible active players to required starter slots."],
                risks=["ESPN roster or injury data may change before lock."],
                details={"open_feature": "Lineup", "lineup": balanced.model_dump(mode="json")},
            )
        )
    inactive = [entry for entry in balanced.starters if entry.player.availability <= 0 or entry.player.injury_status in {"OUT", "INJURY RESERVE"}]
    for entry in inactive:
        decisions.append(
            DecisionRecommendation(
                decision_id=f"inactive-{entry.player.id}",
                category="Lineup",
                priority="Critical",
                title=f"Replace inactive starter: {entry.player.name}",
                recommended_action=f"Do not leave {entry.player.name} in {entry.slot}. Re-run the lineup tab after ESPN updates status.",
                baseline_action=f"Starting {entry.player.name}",
                expected_points_change=entry.projection.mean,
                confidence="High",
                robustness="Robust",
                deadline=f"Before {entry.player.team} kickoff",
                reasons=["Inactive or unavailable players are excluded from legal optimized lineups."],
                risks=["If ESPN status is stale, confirm directly before lock."],
                details={"open_feature": "Lineup", "player_id": entry.player.id},
            )
        )
    if safe.expected_score and upside.expected_score and abs(safe.expected_score - upside.expected_score) >= 1.5:
        recommended = safe if balanced.win_probability >= 0.55 else upside
        alternative = upside if recommended.style == "safe" else safe
        change = recommended.expected_score - alternative.expected_score
        decisions.append(
            DecisionRecommendation(
                decision_id="lineup-strategy",
                category="Lineup",
                priority=_priority(change, recommended.win_probability - alternative.win_probability),
                title=f"Use the {recommended.style.title()} lineup profile",
                recommended_action=f"Prefer {recommended.style.title()} this week",
                baseline_action=f"{alternative.style.title()} lineup",
                expected_points_change=round(change, 1),
                win_probability_change=round(recommended.win_probability - alternative.win_probability, 3),
                lower_impact=round(recommended.floor - alternative.floor, 1),
                upper_impact=round(recommended.ceiling - alternative.ceiling, 1),
                confidence=_confidence(abs(change), 1),
                robustness=_robustness(abs(change), 1),
                deadline=f"Before Week {league.week} lineup lock",
                reasons=[f"{recommended.style.title()} is selected from the exact legal lineup optimizer.", "Strategy recommendation compares expected score, lower outcome, upper outcome, and win probability."],
                risks=["Opponent-aware choice depends on current opponent projection and may change with injuries."],
                details={"open_feature": "Lineup", "recommended_style": recommended.style},
            )
        )
    return decisions


def _waiver_decisions(league: League) -> list[DecisionRecommendation]:
    moves = waiver_moves(league)
    decisions: list[DecisionRecommendation] = []
    for index, move in enumerate(moves[:3], 1):
        injury_sensitive = move.add.injury_status not in {"HEALTHY", "ACTIVE"} or move.drop.injury_status not in {"HEALTHY", "ACTIVE"}
        decisions.append(
            DecisionRecommendation(
                decision_id=f"waiver-{move.add.id}-{move.drop.id}",
                category="Waivers",
                priority=_priority(move.weekly_gain, None, monitor=move.weekly_gain < 1),
                title=f"Add {move.add.name}",
                recommended_action=f"Add {move.add.name}; drop {move.drop.name}",
                baseline_action="Hold current roster",
                expected_points_change=move.weekly_gain,
                lower_impact=round(max(0, move.weekly_gain - move.add.stdev * 0.35), 1),
                upper_impact=round(move.weekly_gain + move.add.stdev * 0.35, 1),
                confidence=_confidence(move.weekly_gain, 2, injury_sensitive),
                robustness=_robustness(move.weekly_gain, len(move.risks), injury_sensitive),
                deadline="Before waivers clear",
                reasons=move.reasons[:2],
                risks=move.risks[:2],
                missing_inputs=["Market bid history", "True rest-of-season role"] if league.id == "demo" else ["Market bid history"],
                details={
                    "open_feature": "Waivers",
                    "add_id": move.add.id,
                    "drop_id": move.drop.id,
                    "faab_guidance": move.faab_guidance or value_based_faab(league, move.weekly_gain, move.add.position, move.confidence),
                    "drop_safety": move.drop_safety,
                    "rank": index,
                },
            )
        )
    return decisions


def _trade_decisions(league: League) -> list[DecisionRecommendation]:
    decisions = []
    for index, idea in enumerate(trade_ideas(league)[:2], 1):
        if idea.weekly_delta < 1:
            continue
        decisions.append(
            DecisionRecommendation(
                decision_id=f"trade-{index}",
                category="Trades",
                priority=_priority(idea.weekly_delta, idea.playoff_delta),
                title=f"Explore trade for {', '.join(p.name for p in idea.receive)}",
                recommended_action=f"Offer {', '.join(p.name for p in idea.send)} for {', '.join(p.name for p in idea.receive)}",
                baseline_action="No trade",
                expected_points_change=idea.weekly_delta,
                playoff_probability_change=idea.playoff_delta,
                confidence=_confidence(idea.weekly_delta, 3),
                robustness=_robustness(idea.weekly_delta, len(idea.risks)),
                deadline="Before trade deadline",
                reasons=idea.reasons,
                risks=["Trade impact depends on both teams' future lineup needs and injury changes.", "Playoff and title deltas are estimates, not guaranteed outcomes."],
                missing_inputs=["Opponent manager preferences", "Historical trade market outcomes"],
                details={"open_feature": "Trades", "value_balance": idea.acceptance_likelihood, "classification": classify_trade(idea.weekly_delta, idea.acceptance_likelihood)},
            )
        )
    return decisions


def classify_trade(user_delta: float, value_balance: float) -> str:
    if user_delta >= 2 and 0.35 <= value_balance <= 0.65:
        return "Mutually beneficial"
    if user_delta >= 2 and value_balance > 0.65:
        return "User-favored"
    if abs(user_delta) < 1:
        return "Balanced but strategically different"
    if user_delta < -1:
        return "Harmful to user"
    return "Too uncertain"


def value_based_faab(league: League, weekly_gain: float, position: str, confidence: float) -> dict[str, object]:
    original_budget = league.acquisition_budget or 100
    scarcity = 1.25 if position in {"RB", "TE", "DST"} else 1.0
    season_urgency = max(0.7, min(1.3, league.week / max(1, league.rules.regular_season_end)))
    value = weekly_gain * scarcity * season_urgency * max(0.5, confidence)
    low = max(1, round(value * 0.9))
    high = max(low, round(value * 1.4))
    aggressive = max(high, round(value * 1.9))
    return {
        "label": "Value-based FAAB guidance",
        "suggested_low": low,
        "suggested_high": high,
        "aggressive_max": aggressive,
        "original_budget": original_budget,
        "percent_range": f"{low / original_budget:.0%}-{high / original_budget:.0%}",
        "confidence": "Medium" if confidence >= 0.55 else "Low",
        "note": "No market bidding data is available, so this is value-based guidance, not a prediction of opponent bids.",
    }


def roster_outlook(league: League, team: Team | None = None) -> list[RosterPositionOutlook]:
    team = team or user_team(league)
    by_position: dict[str, list] = defaultdict(list)
    for player in team.players:
        by_position[player.position].append(player)
    outlook = []
    for position, players in sorted(by_position.items()):
        ranked = sorted(players, key=lambda p: p.mean * p.availability, reverse=True)
        starter_strength = sum(p.mean * p.availability for p in ranked[:2 if position in {"RB", "WR"} else 1])
        reliable = sum(1 for p in players if p.availability >= 0.75 and p.mean >= 8)
        volatility = sum(p.stdev for p in players) / len(players)
        injured = sum(1 for p in players if p.injury_status not in {"HEALTHY", "ACTIVE"})
        outlook.append(
            RosterPositionOutlook(
                position=position,
                starter_strength=round(starter_strength, 1),
                bench_depth=max(0, len(players) - (2 if position in {"RB", "WR"} else 1)),
                reliable_options=reliable,
                injury_exposure="High" if injured >= 2 else "Medium" if injured else "Low",
                weekly_volatility="High" if volatility >= 5.5 else "Medium" if volatility >= 4 else "Low",
                drop_flexibility="Low" if reliable <= 1 else "Medium" if reliable == 2 else "High",
                summary=f"{position}: {reliable} reliable option{'s' if reliable != 1 else ''}, {injured} injury flag{'s' if injured != 1 else ''}.",
            )
        )
    return outlook


def build_weekly_brief(league: League, team: Team | None = None, week: int | None = None, strategy: str = "balanced") -> WeeklyBrief:
    team = team or user_team(league)
    lineup = optimize_lineup(team.players, league.roster_slots, style=strategy, league=league)
    opponent = _current_opponent(league, team)
    sim = simulate_league(league, simulations=750, seed=101)
    sim_team = next((row for row in sim.teams if row.team_id == team.id), None)
    outlook = roster_outlook(league, team)
    weakness = min(outlook, key=lambda row: (row.reliable_options, row.starter_strength), default=None)
    strength = max(outlook, key=lambda row: (row.reliable_options, row.starter_strength), default=None)
    actions = _lineup_decisions(league, team) + _waiver_decisions(league) + _trade_decisions(league)
    actions.sort(key=lambda item: (PRIORITY_ORDER.get(item.priority, 9), -(item.expected_points_change or 0), item.category))
    if not actions:
        actions = [
            DecisionRecommendation(
                decision_id="hold-roster",
                category="Roster",
                priority="Monitor",
                title="No urgent move supported",
                recommended_action="Hold the current roster",
                baseline_action="Force a low-value move",
                confidence="Medium",
                robustness="Moderately robust",
                deadline=f"Before Week {week or league.week} games",
                reasons=["No modeled lineup, waiver, or trade move cleared a meaningful impact threshold."],
                risks=["Late injury news or free-agent changes can create new value."],
                details={"open_feature": "Roster Outlook"},
            )
        ]
    matchup = f"vs {opponent.name}" if opponent else "No current opponent found"
    return WeeklyBrief(
        league_name=league.name,
        team_name=team.name,
        week=week or league.week,
        matchup_summary=matchup,
        expected_score=lineup.expected_score,
        win_probability=lineup.win_probability,
        playoff_probability=sim_team.playoff_probability if sim_team else None,
        championship_probability=sim_team.championship_probability if sim_team else None,
        biggest_weakness=weakness.position if weakness else None,
        best_position=strength.position if strength else None,
        roster_summary=f"{team.name} projects for {lineup.expected_score:.1f} points. Biggest modeled weakness: {weakness.position if weakness else 'unavailable'}.",
        top_actions=actions[:6],
        position_outlook=outlook,
        assumptions=sim.assumptions,
        limitations=sim.warnings,
    )
