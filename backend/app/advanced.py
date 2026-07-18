from __future__ import annotations

import csv
import io
import itertools
import math
import random
from collections import defaultdict

from .domain import (
    CalibrationSummary,
    DraftRecommendation,
    ImpactRange,
    League,
    Player,
    TeamStrength,
    TradeResult,
)
from .engine import optimize_lineup, project, user_team


def roster_distribution(players: list[Player], slots: list[str], seed: int = 19) -> ImpactRange:
    lineup = optimize_lineup(players, slots, seed=seed)
    return ImpactRange(floor=lineup.floor, median=lineup.expected_score, ceiling=lineup.ceiling)


def replacement_levels(league: League) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for team in league.teams:
        for player in team.players:
            grouped[player.position].append(player.mean)
    for player in league.free_agents:
        grouped[player.position].append(player.mean)
    return {position: sorted(values, reverse=True)[min(len(values) - 1, max(0, len(league.teams)))] for position, values in grouped.items() if values}


def draft_board(league: League, mode: str = "balanced") -> list[DraftRecommendation]:
    team = user_team(league)
    levels = replacement_levels(league)
    counts = defaultdict(int)
    for player in team.players:
        counts[player.position] += 1
    pool = sorted(league.free_agents + [p for t in league.teams if t.id != team.id for p in t.players], key=lambda p: p.mean, reverse=True)
    results = []
    risk_weight = {"safe": -.25, "balanced": 0, "ceiling": .25}.get(mode, 0)
    for player in pool:
        replacement = levels.get(player.position, 0)
        vor = player.mean - replacement
        scarcity = max(0, vor) / max(1, player.mean)
        need = max(0, 2 - counts[player.position])
        score = vor + need * 1.5 + risk_weight * player.stdev
        survival = 1 / (1 + math.exp((score - 5) / 2.5))
        results.append((score, DraftRecommendation(player=player, rank=0, vor=round(vor, 1), scarcity=round(scarcity, 2), survival_probability=round(survival, 2), roster_fit="Priority need" if need else "Depth and upside", risk="HIGH" if player.stdev > 5.5 else "MEDIUM" if player.stdev > 4 else "LOW", explanation=f"{player.name} adds {vor:.1f} points over the current {player.position} replacement baseline and has a {survival:.0%} modeled chance to reach the next selection.")))
    ranked = []
    for rank, (_, rec) in enumerate(sorted(results, key=lambda x: x[0], reverse=True)[:12], 1):
        ranked.append(rec.model_copy(update={"rank": rank}))
    return ranked


def evaluate_trade(league: League, send_ids: list[str], receive_ids: list[str], opponent_team_id: str | None = None) -> TradeResult:
    team = user_team(league)
    opponents = [t for t in league.teams if t.id != team.id]
    opponent = next((t for t in opponents if t.id == opponent_team_id), opponents[0])
    send = [p for p in team.players if p.id in send_ids]
    receive = [p for p in opponent.players if p.id in receive_ids]
    if not send or not receive:
        raise ValueError("Select at least one player from each team")
    after_players = [p for p in team.players if p.id not in send_ids] + receive
    required_drop = None
    if len(after_players) > len(team.players):
        candidates = [p for p in after_players if p.id not in receive_ids]
        required_drop = min(candidates, key=lambda p: p.mean)
        after_players.remove(required_drop)
    before = roster_distribution(team.players, league.roster_slots)
    after = roster_distribution(after_players, league.roster_slots)
    delta = after.median - before.median
    playoff_delta = max(-.18, min(.18, delta / 80))
    championship_delta = max(-.12, min(.12, delta / 120))
    sent_value, received_value = sum(p.mean for p in send), sum(p.mean for p in receive)
    acceptance = 1 / (1 + math.exp((received_value - sent_value) / 4))
    verdict = "EXCELLENT" if delta >= 4 else "GOOD" if delta >= 1.5 else "NEUTRAL" if delta > -1.5 else "RISKY" if delta > -4 else "BAD"
    return TradeResult(send=send, receive=receive, required_drop=required_drop, before=before, after=after, weekly_delta=round(delta, 1), playoff_delta=round(playoff_delta, 3), championship_delta=round(championship_delta, 3), acceptance_likelihood=round(acceptance, 2), verdict=verdict, reasons=["Evaluates the complete legal starting roster before and after the deal", f"Median weekly output changes by {delta:+.1f} points"], risks=["Acceptance is a value-balance estimate, not a prediction of another manager's behavior"])


def trade_ideas(league: League) -> list[TradeResult]:
    team = user_team(league)
    ideas = []
    for opponent in [t for t in league.teams if t.id != team.id]:
        sends = sorted(team.players, key=lambda p: p.mean)[-5:]
        receives = sorted(opponent.players, key=lambda p: p.mean, reverse=True)[:5]
        for send, receive in itertools.product(sends, receives):
            if send.position != receive.position and "FLEX" not in send.eligible_slots.intersection(receive.eligible_slots):
                continue
            result = evaluate_trade(league, [send.id], [receive.id], opponent.id)
            if result.weekly_delta >= -1:
                ideas.append(result)
    return sorted(ideas, key=lambda x: (x.weekly_delta, x.acceptance_likelihood), reverse=True)[:5]


def what_if(league: League, remove_id: str, add_id: str) -> dict:
    team = user_team(league)
    all_players = [p for t in league.teams for p in t.players] + league.free_agents
    remove = next((p for p in team.players if p.id == remove_id), None)
    add = next((p for p in all_players if p.id == add_id), None)
    if not remove or not add:
        raise ValueError("Both players must exist and the removed player must be on your roster")
    before_lineup = optimize_lineup(team.players, league.roster_slots)
    after_players = [p for p in team.players if p.id != remove_id] + [add]
    after_lineup = optimize_lineup(after_players, league.roster_slots)
    return {"remove": remove, "add": add, "before": before_lineup, "after": after_lineup, "score_delta": round(after_lineup.expected_score - before_lineup.expected_score, 1), "win_probability_delta": round(after_lineup.win_probability - before_lineup.win_probability, 3)}


def power_rankings(league: League, simulations: int = 4000, seed: int = 31) -> list[TeamStrength]:
    rng = random.Random(seed)
    base = []
    for team in league.teams:
        if team.players:
            lineup = optimize_lineup(team.players, league.roster_slots, opponent_mean=110, seed=seed)
            mean, spread = lineup.expected_score, max(8, (lineup.ceiling - lineup.floor) / 2.56)
        else:
            mean, spread = 82, 15
        base.append((team, mean, spread))
    playoff_counts = defaultdict(int); title_counts = defaultdict(int); win_samples = defaultdict(list)
    remaining_weeks = max(1, 14 - league.week)
    for _ in range(simulations):
        season_scores = []
        for team, mean, spread in base:
            wins = sum(rng.random() < 1 / (1 + math.exp(-(rng.gauss(mean, spread) - 108) / 14)) for _ in range(remaining_weeks))
            current_wins = int(team.record.split("-")[0]) if "-" in team.record else 0
            total = current_wins + wins
            win_samples[team.id].append(total)
            season_scores.append((total + rng.random() * .01, team.id))
        season_scores.sort(reverse=True)
        playoff_ids = [tid for _, tid in season_scores[:max(1, min(4, len(season_scores)))]]
        for tid in playoff_ids: playoff_counts[tid] += 1
        champion = max(playoff_ids, key=lambda tid: next(mean for team, mean, _ in base if team.id == tid) + rng.gauss(0, 18))
        title_counts[champion] += 1
    results = []
    for team, mean, _ in sorted(base, key=lambda x: x[1], reverse=True):
        samples = sorted(win_samples[team.id]); n = len(samples)
        results.append(TeamStrength(team_id=team.id, team_name=team.name, rank=len(results)+1, expected_score=round(mean, 1), playoff_probability=round(playoff_counts[team.id]/simulations, 3), championship_probability=round(title_counts[team.id]/simulations, 3), projected_wins=round(sum(samples)/n, 1), wins_low=float(samples[int(.1*n)]), wins_high=float(samples[min(n-1, int(.9*n))])))
    return results


def calibration_summary() -> CalibrationSummary:
    # Seed observations represent stored demo predictions; production persistence can append real outcomes.
    observations = [(112.4, 108.1, .63, 1), (121.2, 115.8, .71, 1), (104.7, 111.0, .46, 0), (118.0, 105.4, .68, 1), (109.3, 117.2, .55, 0), (126.1, 120.5, .74, 1), (98.5, 103.2, .41, 0), (115.6, 113.0, .58, 1)]
    mae = sum(abs(pred-actual) for pred,actual,_,_ in observations)/len(observations)
    brier = sum((prob-outcome)**2 for _,_,prob,outcome in observations)/len(observations)
    bias = sum(prob-outcome for _,_,prob,outcome in observations)/len(observations)
    buckets=[]
    for low in (0, .5, .6, .7, .8):
        high = .5 if low == 0 else low + .1
        group=[o for o in observations if low <= o[2] < high]
        if group: buckets.append({"predicted":round(sum(o[2] for o in group)/len(group),2),"observed":round(sum(o[3] for o in group)/len(group),2),"count":float(len(group))})
    verdict = "Slightly over-confident" if bias > .05 else "Slightly under-confident" if bias < -.05 else "Well balanced in this sample"
    return CalibrationSummary(sample_size=len(observations), points_mae=round(mae,2), brier_score=round(brier,3), confidence_bias=round(bias,3), verdict=verdict, buckets=buckets)


def player_research(league: League, player_id: str) -> dict:
    all_players = [p for t in league.teams for p in t.players] + league.free_agents
    player = next((p for p in all_players if p.id == player_id), None)
    if not player: raise ValueError("Player not found")
    projection = project(player)
    trend = [round(max(0, player.mean + math.sin(i * 1.7) * player.stdev * .6), 1) for i in range(6)]
    return {"player": player, "projection": projection, "weekly_trend": trend, "role": "Starter" if player.mean >= 12 else "Rotational / matchup dependent", "market": {"game_total": None, "spread": None, "state": "UNAVAILABLE"}, "explanation": projection.reasons}


def report_csv(league: League) -> str:
    stream = io.StringIO(); writer = csv.writer(stream)
    writer.writerow(["Fourth Down weekly report", league.name, f"Week {league.week}"])
    writer.writerow(["Team", "Expected points", "Win probability", "Floor", "Ceiling"])
    for team in league.teams:
        if not team.players: continue
        result=optimize_lineup(team.players,league.roster_slots)
        writer.writerow([team.name,result.expected_score,result.win_probability,result.floor,result.ceiling])
    return stream.getvalue()
