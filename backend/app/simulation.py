from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .domain import League, Matchup
from .engine import optimize_lineup
from .projection_service import DEFAULT_PROJECTION_SERVICE, ProjectionService


MATH_STATUS_UNRESOLVED = "Mathematically alive"
MODEL_VERSION = "phase4_schedule_sim_v1"


class ScenarioConstraint(BaseModel):
    matchup_id: str
    winner_team_id: str | Literal["TIE"] | None = None
    home_score: float | None = None
    away_score: float | None = None


class TeamScoreDistribution(BaseModel):
    team_id: str
    team_name: str
    expected_score: float
    median_score: float
    lower_estimate: float
    upper_estimate: float
    score_stdev: float
    starters: list[str]
    bench: list[str]
    missing_projections: list[str] = Field(default_factory=list)
    fallback_projections: list[str] = Field(default_factory=list)
    data_completeness: float
    model_version: str
    warnings: list[str] = Field(default_factory=list)


class TeamSimulationSummary(BaseModel):
    team_id: str
    team_name: str
    current_wins: float
    current_losses: float
    current_ties: float
    points_for: float
    points_against: float
    expected_final_wins: float
    median_final_wins: float
    wins_low: float
    wins_high: float
    expected_final_points: float
    playoff_probability: float
    playoff_se: float
    bye_probability: float
    championship_probability: float
    championship_se: float
    most_likely_seed: int | None
    seed_distribution: dict[int, float]
    mathematical_status: str
    remaining_sos_rank: int | None = None


class ScheduleMetric(BaseModel):
    team_id: str
    team_name: str
    actual_wins: float
    all_play_wins: float
    all_play_losses: float
    all_play_ties: float
    all_play_win_pct: float
    all_play_expected_wins: float
    schedule_luck: float
    points_against_vs_average: float
    completed_sos: float
    remaining_sos: float
    top_half_losses: int
    bottom_half_wins: int


class LeagueSimulationResult(BaseModel):
    model_version: str = MODEL_VERSION
    league_id: str
    season: int
    week: int
    simulations: int
    seed: int
    assumptions: list[str]
    warnings: list[str]
    unsupported_rules: list[str]
    teams: list[TeamSimulationSummary]
    score_distributions: list[TeamScoreDistribution]
    schedule_metrics: list[ScheduleMetric]
    scenario_constraints: list[ScenarioConstraint] = Field(default_factory=list)


@dataclass
class MutableRecord:
    wins: float
    losses: float
    ties: float
    points_for: float
    points_against: float

    def add_result(self, points: float, against: float) -> None:
        self.points_for += points
        self.points_against += against
        if points > against:
            self.wins += 1
        elif points < against:
            self.losses += 1
        else:
            self.ties += 1


def league_fingerprint(league: League) -> str:
    payload = {
        "id": league.id,
        "season": league.season,
        "week": league.week,
        "slots": league.roster_slots,
        "teams": [
            {
                "id": team.id,
                "record": team.record,
                "wins": team.wins,
                "losses": team.losses,
                "ties": team.ties,
                "pf": team.points_for,
                "pa": team.points_against,
                "players": [(p.id, p.mean, p.stdev, p.availability, p.injury_status) for p in team.players],
            }
            for team in league.teams
        ],
        "schedule": [m.model_dump(exclude={"raw"}) for m in league.schedule],
        "rules": league.rules.model_dump(exclude={"raw"}),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _team_record(team) -> MutableRecord:
    if team.wins or team.losses or team.ties:
        return MutableRecord(team.wins, team.losses, team.ties, team.points_for, team.points_against)
    parts = [float(x) for x in team.record.split("-") if x.replace(".", "", 1).isdigit()]
    wins = parts[0] if parts else 0
    losses = parts[1] if len(parts) > 1 else 0
    ties = parts[2] if len(parts) > 2 else 0
    return MutableRecord(wins, losses, ties, team.points_for, team.points_against)


def _standings_order(records: dict[str, MutableRecord]) -> list[str]:
    return sorted(records, key=lambda tid: (records[tid].wins + 0.5 * records[tid].ties, records[tid].points_for, -records[tid].points_against, tid), reverse=True)


def _prob_se(probability: float, simulations: int) -> float:
    if simulations <= 0:
        return 0
    return math.sqrt(probability * (1 - probability) / simulations)


def _future_matchups(league: League) -> list[Matchup]:
    return [m for m in league.schedule if not m.is_complete and m.period <= league.rules.regular_season_end]


def validate_scenarios(league: League, scenarios: list[ScenarioConstraint] | None) -> list[ScenarioConstraint]:
    if not scenarios:
        return []
    by_id = {m.id: m for m in league.schedule}
    validated: list[ScenarioConstraint] = []
    seen: set[str] = set()
    week_team: set[tuple[int, str]] = set()
    for scenario in scenarios:
        if scenario.matchup_id not in by_id:
            raise ValueError(f"Invalid matchup ID: {scenario.matchup_id}")
        if scenario.matchup_id in seen:
            raise ValueError(f"Contradictory scenario: matchup {scenario.matchup_id} was selected more than once")
        matchup = by_id[scenario.matchup_id]
        if matchup.is_complete:
            raise ValueError("Completed matchups cannot be overridden")
        if scenario.winner_team_id not in {None, "TIE", matchup.home_team_id, matchup.away_team_id}:
            raise ValueError("Scenario winner must be one of the matchup teams or TIE")
        if scenario.home_score is not None and scenario.away_score is not None and scenario.winner_team_id:
            if scenario.winner_team_id == "TIE" and scenario.home_score != scenario.away_score:
                raise ValueError("Tie scenario requires equal hypothetical scores")
            if scenario.winner_team_id == matchup.home_team_id and scenario.home_score <= scenario.away_score:
                raise ValueError("Hypothetical scores do not match the selected winner")
            if scenario.winner_team_id == matchup.away_team_id and scenario.away_score <= scenario.home_score:
                raise ValueError("Hypothetical scores do not match the selected winner")
        for team_id in (matchup.home_team_id, matchup.away_team_id):
            key = (matchup.period, team_id)
            if key in week_team:
                raise ValueError("A team cannot be assigned to two scenario opponents in the same week")
            week_team.add(key)
        seen.add(scenario.matchup_id)
        validated.append(scenario)
    return validated


def team_score_distributions(league: League, projection_service: ProjectionService | None = None) -> list[TeamScoreDistribution]:
    service = projection_service or DEFAULT_PROJECTION_SERVICE
    rows: list[TeamScoreDistribution] = []
    for team in league.teams:
        lineup = optimize_lineup(team.players, league.roster_slots, league=league, projection_service=service)
        means = [entry.projection.mean for entry in lineup.starters]
        variances = [max(1, entry.player.stdev) ** 2 for entry in lineup.starters]
        stdev = math.sqrt(sum(variances) + (4.0 if lineup.is_complete else 9.0) ** 2)
        completeness = sum(entry.projection.data_completeness for entry in lineup.starters) / len(lineup.starters) if lineup.starters else 0
        fallbacks = [entry.player.name for entry in lineup.starters if entry.projection.fallback_used]
        missing = sorted({item for entry in lineup.starters for item in entry.projection.missing})
        warnings = []
        if not lineup.is_complete:
            warnings.append(f"Incomplete legal lineup; missing {', '.join(lineup.missing_slots)}")
        rows.append(TeamScoreDistribution(team_id=team.id, team_name=team.name, expected_score=round(sum(means), 2), median_score=round(sum(means), 2), lower_estimate=round(max(0, sum(means) - 1.28 * stdev), 2), upper_estimate=round(sum(means) + 1.28 * stdev, 2), score_stdev=round(stdev, 2), starters=[entry.player.name for entry in lineup.starters], bench=[p.name for p in lineup.bench], missing_projections=missing, fallback_projections=fallbacks, data_completeness=round(completeness, 2), model_version=MODEL_VERSION, warnings=warnings))
    return rows


def _score_sample(rng: random.Random, dist: TeamScoreDistribution) -> float:
    return max(0.0, rng.gauss(dist.expected_score, dist.score_stdev))


def _apply_matchup(records: dict[str, MutableRecord], home_id: str, away_id: str, home_score: float, away_score: float) -> None:
    records[home_id].add_result(home_score, away_score)
    records[away_id].add_result(away_score, home_score)


def _simulate_playoffs(rng: random.Random, seed_order: list[str], dists: dict[str, TeamScoreDistribution], playoff_count: int, byes: int) -> tuple[str | None, set[str], set[str]]:
    playoff_ids = seed_order[: max(1, min(playoff_count, len(seed_order)))]
    bye_ids = set(playoff_ids[: max(0, min(byes, len(playoff_ids)))])
    alive = playoff_ids[:]
    if len(alive) == 1:
        return alive[0], set(playoff_ids), bye_ids
    if bye_ids:
        first_round = alive[byes:]
        winners = alive[:byes]
        pairs = list(zip(first_round[: len(first_round) // 2], reversed(first_round[len(first_round) // 2 :])))
    else:
        winners = []
        pairs = list(zip(alive[: len(alive) // 2], reversed(alive[len(alive) // 2 :])))
    while pairs:
        next_round = winners[:]
        for higher, lower in pairs:
            h_score = _score_sample(rng, dists[higher])
            l_score = _score_sample(rng, dists[lower])
            next_round.append(higher if h_score >= l_score else lower)
        winners = []
        if len(next_round) == 1:
            return next_round[0], set(playoff_ids), bye_ids
        pairs = list(zip(next_round[: len(next_round) // 2], reversed(next_round[len(next_round) // 2 :])))
    return None, set(playoff_ids), bye_ids


def _mathematical_statuses(league: League, scenarios: list[ScenarioConstraint]) -> dict[str, str]:
    future = _future_matchups(league)
    constrained = {s.matchup_id: s for s in scenarios if s.winner_team_id}
    unresolved = [m for m in future if m.id not in constrained]
    if len(unresolved) > 12:
        return {team.id: "Status unresolved because remaining scenarios are too large" for team in league.teams}
    playoff_hits = defaultdict(int)
    total = 0

    def branch(index: int, records: dict[str, MutableRecord]) -> None:
        nonlocal total
        if index == len(future):
            total += 1
            for tid in _standings_order(records)[: max(1, min(league.playoff_team_count, len(records)))]:
                playoff_hits[tid] += 1
            return
        matchup = future[index]
        scenario = constrained.get(matchup.id)
        outcomes: list[str]
        if scenario:
            outcomes = [str(scenario.winner_team_id)]
        else:
            outcomes = [matchup.home_team_id, matchup.away_team_id]
        for outcome in outcomes:
            next_records = deepcopy(records)
            if outcome == matchup.home_team_id:
                _apply_matchup(next_records, matchup.home_team_id, matchup.away_team_id, 1, 0)
            elif outcome == matchup.away_team_id:
                _apply_matchup(next_records, matchup.home_team_id, matchup.away_team_id, 0, 1)
            else:
                _apply_matchup(next_records, matchup.home_team_id, matchup.away_team_id, 0, 0)
            branch(index + 1, next_records)

    branch(0, {team.id: _team_record(team) for team in league.teams})
    if total == 0:
        return {team.id: MATH_STATUS_UNRESOLVED for team in league.teams}
    statuses = {}
    for team in league.teams:
        hits = playoff_hits[team.id]
        if hits == total:
            statuses[team.id] = "Clinched playoff berth"
        elif hits == 0:
            statuses[team.id] = "Mathematically eliminated"
        else:
            statuses[team.id] = MATH_STATUS_UNRESOLVED
    if league.rules.unsupported:
        statuses = {team.id: "Status unresolved because unsupported tiebreaker" for team in league.teams}
    return statuses


def schedule_analysis(league: League, dists: list[TeamScoreDistribution]) -> list[ScheduleMetric]:
    team_ids = [team.id for team in league.teams]
    team_names = {team.id: team.name for team in league.teams}
    powers = {row.team_id: row.expected_score for row in dists}
    completed = [m for m in league.schedule if m.is_complete and m.home_score is not None and m.away_score is not None]
    weekly_scores: dict[int, dict[str, float]] = defaultdict(dict)
    opponents: dict[str, list[str]] = defaultdict(list)
    for matchup in completed:
        weekly_scores[matchup.period][matchup.home_team_id] = float(matchup.home_score)
        weekly_scores[matchup.period][matchup.away_team_id] = float(matchup.away_score)
        opponents[matchup.home_team_id].append(matchup.away_team_id)
        opponents[matchup.away_team_id].append(matchup.home_team_id)
    league_avg_pa = 0.0
    records = {team.id: _team_record(team) for team in league.teams}
    if records:
        league_avg_pa = sum(r.points_against for r in records.values()) / len(records)
    rows = []
    for team in league.teams:
        all_wins = all_losses = all_ties = 0.0
        top_half_losses = bottom_half_wins = 0
        for period, scores in weekly_scores.items():
            if team.id not in scores:
                continue
            own = scores[team.id]
            values = sorted(scores.values(), reverse=True)
            rank = 1 + sum(1 for score in values if score > own)
            top_half = rank <= max(1, len(values) // 2)
            for other_id, other_score in scores.items():
                if other_id == team.id:
                    continue
                if own > other_score:
                    all_wins += 1
                elif own < other_score:
                    all_losses += 1
                else:
                    all_ties += 1
            actual_matchups = [m for m in completed if m.period == period and team.id in {m.home_team_id, m.away_team_id}]
            for matchup in actual_matchups:
                if matchup.period not in weekly_scores or team.id not in {matchup.home_team_id, matchup.away_team_id}:
                    continue
                if matchup.home_team_id == team.id:
                    opp_score = matchup.away_score or 0
                    won = own > opp_score
                else:
                    opp_score = matchup.home_score or 0
                    won = own > opp_score
                if top_half and not won:
                    top_half_losses += 1
                if not top_half and won:
                    bottom_half_wins += 1
        comparisons = all_wins + all_losses + all_ties
        all_pct = (all_wins + 0.5 * all_ties) / comparisons if comparisons else 0
        completed_games = sum(1 for m in completed if team.id in {m.home_team_id, m.away_team_id})
        expected_wins = all_pct * completed_games
        future_opponents = [m.away_team_id if m.home_team_id == team.id else m.home_team_id for m in _future_matchups(league) if team.id in {m.home_team_id, m.away_team_id}]
        completed_sos = sum(powers.get(opp, 0) for opp in opponents[team.id]) / len(opponents[team.id]) if opponents[team.id] else 0
        remaining_sos = sum(powers.get(opp, 0) for opp in future_opponents) / len(future_opponents) if future_opponents else 0
        rec = records[team.id]
        rows.append(ScheduleMetric(team_id=team.id, team_name=team.name, actual_wins=rec.wins, all_play_wins=all_wins, all_play_losses=all_losses, all_play_ties=all_ties, all_play_win_pct=round(all_pct, 3), all_play_expected_wins=round(expected_wins, 2), schedule_luck=round(rec.wins - expected_wins, 2), points_against_vs_average=round(rec.points_against - league_avg_pa, 2), completed_sos=round(completed_sos, 2), remaining_sos=round(remaining_sos, 2), top_half_losses=top_half_losses, bottom_half_wins=bottom_half_wins))
    sos_order = {team_id: index + 1 for index, team_id in enumerate(sorted(team_ids, key=lambda tid: next((r.remaining_sos for r in rows if r.team_id == tid), 0), reverse=True))}
    for row in rows:
        row.remaining_sos = round(row.remaining_sos, 2)
    return sorted(rows, key=lambda row: sos_order[row.team_id])


def simulate_league(league: League, projections: ProjectionService | None = None, scenarios: list[ScenarioConstraint] | None = None, simulations: int = 1000, seed: int = 41) -> LeagueSimulationResult:
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    if simulations > 20000:
        raise ValueError("simulations must be 20,000 or fewer for Streamlit Community Cloud")
    source_league = league.model_copy(deep=True)
    scenario_constraints = validate_scenarios(source_league, scenarios)
    scenario_by_id = {s.matchup_id: s for s in scenario_constraints}
    dists = {row.team_id: row for row in team_score_distributions(source_league, projections)}
    rng = random.Random(seed)
    playoff_counts = defaultdict(int)
    bye_counts = defaultdict(int)
    title_counts = defaultdict(int)
    final_wins = defaultdict(list)
    final_points = defaultdict(list)
    seed_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    future = _future_matchups(source_league)
    warnings = []
    if not future:
        warnings.append("No remaining regular-season schedule is available; projections use current standings only.")
    if any(m.is_current for m in future):
        warnings.append("Current matchup live partial scoring is not modeled; current-week simulations are pregame-only unless the matchup is final.")
    warnings.extend(source_league.rules.assumptions)
    warnings.extend(source_league.rules.unsupported)

    for _ in range(simulations):
        records = {team.id: _team_record(team) for team in source_league.teams}
        for matchup in future:
            scenario = scenario_by_id.get(matchup.id)
            if scenario and scenario.home_score is not None and scenario.away_score is not None:
                home_score, away_score = scenario.home_score, scenario.away_score
            else:
                home_score = _score_sample(rng, dists[matchup.home_team_id])
                away_score = _score_sample(rng, dists[matchup.away_team_id])
                if scenario and scenario.winner_team_id:
                    if scenario.winner_team_id == matchup.home_team_id and home_score <= away_score:
                        home_score = away_score + 0.1
                    elif scenario.winner_team_id == matchup.away_team_id and away_score <= home_score:
                        away_score = home_score + 0.1
                    elif scenario.winner_team_id == "TIE":
                        away_score = home_score
            _apply_matchup(records, matchup.home_team_id, matchup.away_team_id, home_score, away_score)
        order = _standings_order(records)
        for idx, team_id in enumerate(order, 1):
            seed_counts[team_id][idx] += 1
            final_wins[team_id].append(records[team_id].wins + 0.5 * records[team_id].ties)
            final_points[team_id].append(records[team_id].points_for)
        champion, playoff_ids, bye_ids = _simulate_playoffs(rng, order, dists, source_league.playoff_team_count, source_league.rules.first_round_byes)
        for team_id in playoff_ids:
            playoff_counts[team_id] += 1
        for team_id in bye_ids:
            bye_counts[team_id] += 1
        if champion:
            title_counts[champion] += 1

    math_status = _mathematical_statuses(source_league, scenario_constraints)
    metrics = schedule_analysis(source_league, list(dists.values()))
    sos_rank = {row.team_id: rank + 1 for rank, row in enumerate(sorted(metrics, key=lambda row: row.remaining_sos, reverse=True))}
    team_rows: list[TeamSimulationSummary] = []
    for team in source_league.teams:
        wins = sorted(final_wins[team.id])
        points = sorted(final_points[team.id])
        n = len(wins)
        seed_distribution = {seed_no: round(count / simulations, 4) for seed_no, count in sorted(seed_counts[team.id].items())}
        most_likely_seed = max(seed_distribution, key=seed_distribution.get) if seed_distribution else None
        playoff_probability = playoff_counts[team.id] / simulations
        championship_probability = title_counts[team.id] / simulations
        rec = _team_record(team)
        team_rows.append(TeamSimulationSummary(team_id=team.id, team_name=team.name, current_wins=rec.wins, current_losses=rec.losses, current_ties=rec.ties, points_for=round(rec.points_for, 2), points_against=round(rec.points_against, 2), expected_final_wins=round(sum(wins) / n, 2), median_final_wins=round(wins[n // 2], 2), wins_low=round(wins[int(0.1 * n)], 2), wins_high=round(wins[min(n - 1, int(0.9 * n))], 2), expected_final_points=round(sum(points) / n, 2), playoff_probability=round(playoff_probability, 4), playoff_se=round(_prob_se(playoff_probability, simulations), 4), bye_probability=round(bye_counts[team.id] / simulations, 4), championship_probability=round(championship_probability, 4), championship_se=round(_prob_se(championship_probability, simulations), 4), most_likely_seed=most_likely_seed, seed_distribution=seed_distribution, mathematical_status=math_status.get(team.id, MATH_STATUS_UNRESOLVED), remaining_sos_rank=sos_rank.get(team.id)))
    team_rows.sort(key=lambda row: (row.expected_final_wins, row.expected_final_points), reverse=True)
    return LeagueSimulationResult(league_id=source_league.id, season=source_league.season, week=source_league.week, simulations=simulations, seed=seed, assumptions=["Future regular-season games use the actual normalized schedule when available.", "Legal optimized lineups feed team score distributions.", "Team scores use independent normal team distributions with heuristic team-level variance; correlations are not claimed as empirical.", "Seeding uses supported record plus points-for tiebreaking."], warnings=warnings, unsupported_rules=source_league.rules.unsupported, teams=team_rows, score_distributions=list(dists.values()), schedule_metrics=metrics, scenario_constraints=scenario_constraints)
