from __future__ import annotations

import random

from .domain import League, LineupEntry, LineupResult, Player, Projection, WaiverMove
from .projection_service import DEFAULT_PROJECTION_SERVICE, ProjectionService
from .ros_service import project_ros


def _live_factors(player: Player) -> tuple[float, float, list[str], list[str]]:
    try:
        from .persistence import cache_get
        nfl_names={"BAL":"Baltimore Ravens","BUF":"Buffalo Bills","GB":"Green Bay Packers","MIA":"Miami Dolphins","NE":"New England Patriots","NYJ":"New York Jets","PHI":"Philadelphia Eagles","PIT":"Pittsburgh Steelers","ATL":"Atlanta Falcons","ARI":"Arizona Cardinals","DAL":"Dallas Cowboys","DET":"Detroit Lions","IND":"Indianapolis Colts","MIN":"Minnesota Vikings","CAR":"Carolina Panthers","TEN":"Tennessee Titans","SF":"San Francisco 49ers","SEA":"Seattle Seahawks","TB":"Tampa Bay Buccaneers","WAS":"Washington Commanders","JAX":"Jacksonville Jaguars","KC":"Kansas City Chiefs","LV":"Las Vegas Raiders","LAC":"Los Angeles Chargers","LAR":"Los Angeles Rams","CHI":"Chicago Bears","CIN":"Cincinnati Bengals","CLE":"Cleveland Browns","DEN":"Denver Broncos","HOU":"Houston Texans","NO":"New Orleans Saints","NYG":"New York Giants"}
        odds_cache=cache_get("odds:nfl"); weather_cache=cache_get(f"weather:{player.team}")
        market=1.0; context=1.0; reasons=[]; missing=[]
        if odds_cache:
            team_name=nfl_names.get(player.team,player.team); totals=[]
            for game in odds_cache["payload"]:
                if team_name not in {game.get("home_team"),game.get("away_team")}: continue
                for book in game.get("bookmakers",[]):
                    for market_data in book.get("markets",[]):
                        if market_data.get("key")=="totals": totals += [float(x["point"]) for x in market_data.get("outcomes",[]) if x.get("name")=="Over" and x.get("point")]
            if totals:
                consensus=sum(totals)/len(totals); market=max(.88,min(1.12,1+(consensus-44)*.012)); reasons.append(f"Consensus game total {consensus:.1f} adjusts the market prior")
            else: missing.append("team game market")
        else: missing.append("Vegas game lines")
        if weather_cache:
            hourly=weather_cache["payload"].get("hourly",{}); winds=hourly.get("wind_speed_10m",[])[:48]; precip=hourly.get("precipitation_probability",[])[:48]
            severe=(max(winds or [0])>=25 or max(precip or [0])>=70)
            if severe and player.position in {"QB","WR","K"}: context=.94; reasons.append("Severe outdoor forecast modestly lowers passing/kicking efficiency")
        else: missing.append("stadium weather")
        return market,context,reasons,missing
    except Exception:
        return 1.0,1.0,[],["live context"]


def project(player: Player, market_factor: float | None = None, context_factor: float | None = None, missing: list[str] | None = None) -> Projection:
    # Factors are intentionally bounded: Vegas is the prior, context is a modest adjustment.
    live_market,live_context,live_reasons,live_missing=_live_factors(player)
    market = min(1.18, max(.82, live_market if market_factor is None else market_factor))
    context = min(1.10, max(.90, live_context if context_factor is None else context_factor))
    mean = max(0, player.mean * market * context * player.availability)
    sd = player.stdev * (1.2 if player.injury_status != "HEALTHY" else 1)
    absent = missing if missing is not None else ["player props",*live_missing]
    adjustments=[
        {"name":"market_context","factor":round(market,3),"source":"cached game total when available"},
        {"name":"weather_context","factor":round(context,3),"source":"cached stadium forecast when available"},
        {"name":"availability","factor":round(player.availability,3),"source":"ESPN injury/availability field or demo fixture"},
    ]
    reasons = ["Baseline projection is adjusted only by bounded context", "Availability is applied directly to expected output",*live_reasons]
    if player.injury_status != "HEALTHY": reasons.append(f"{player.injury_status.title()} status lowers availability and raises uncertainty")
    return Projection(player_id=player.id, baseline_source="ESPN weekly projection or demo fixture baseline", baseline_value=round(player.mean,2), mean=round(mean, 2), median=round(mean, 2), floor=round(max(0, mean - 1.28 * sd), 2), ceiling=round(mean + 1.28 * sd, 2), confidence=round(max(.35, .82 - .08 * len(absent)), 2), adjustments=adjustments, reasons=reasons, missing=absent, limitations=["This is an explainable projection-adjustment engine, not a trained machine-learning projection model.", "Uncertainty ranges are heuristic and not empirically calibrated in Phase 1."])


def _eligible(player: Player, slot: str) -> bool:
    if player.availability <= 0:
        return False
    if slot == "FLEX" and player.position in {"RB", "WR", "TE"}:
        return True
    if slot == "SUPERFLEX" and player.position in {"QB", "RB", "WR", "TE"}:
        return True
    return slot in player.eligible_slots


def optimize_lineup(players: list[Player], slots: list[str], *, style: str = "balanced", opponent_mean: float = 112, seed: int = 7, league: League | None = None, projection_service: ProjectionService | None = None) -> LineupResult:
    if style not in {"safe", "balanced", "upside"}:
        raise ValueError("style must be safe, balanced, or upside")
    service = projection_service or DEFAULT_PROJECTION_SERVICE
    projections = {player.id: service.project_player(player=player, league=league, week=league.week if league else None) for player in players}
    def objective(player: Player) -> float:
        projection = projections[player.id]
        if style == "safe":
            return projection.mean - 0.28 * player.stdev
        if style == "upside":
            return projection.mean + 0.28 * player.stdev
        return projection.mean

    ordered_slots = sorted(enumerate(slots), key=lambda item: (sum(1 for p in players if _eligible(p, item[1])), item[1], item[0]))
    suffix_capacity: list[set[str]] = [set() for _ in range(len(ordered_slots)+1)]
    for idx in range(len(ordered_slots)-1, -1, -1):
        suffix_capacity[idx] = suffix_capacity[idx+1] | {p.id for p in players if _eligible(p, ordered_slots[idx][1])}

    best_score: float | None = None
    best_assignment: list[tuple[int, str, Player]] = []

    def search(slot_index: int, used: set[str], score: float, assignment: list[tuple[int, str, Player]]) -> None:
        nonlocal best_score, best_assignment
        if slot_index == len(ordered_slots):
            if best_score is None or score > best_score:
                best_score = score
                best_assignment = assignment[:]
            return
        original_index, slot = ordered_slots[slot_index]
        if len((suffix_capacity[slot_index] - used)) < len(ordered_slots) - slot_index:
            return
        eligible = [p for p in players if p.id not in used and _eligible(p, slot)]
        for player in sorted(eligible, key=objective, reverse=True):
            used.add(player.id)
            assignment.append((original_index, slot, player))
            search(slot_index + 1, used, score + objective(player), assignment)
            assignment.pop()
            used.remove(player.id)

    search(0, set(), 0, [])
    entries: list[LineupEntry] = []
    if best_assignment:
        entries = [LineupEntry(slot=slot, player=player, projection=projections[player.id]) for _, slot, player in sorted(best_assignment, key=lambda x: x[0])]
    used_ids={entry.player.id for entry in entries}
    remaining = [player for player in players if player.id not in used_ids]
    filled_indexes={index for index, _, _ in best_assignment}
    missing_slots = [] if len(entries)==len(slots) else [slot for index, slot in enumerate(slots) if index not in filled_indexes]
    means = [e.projection.mean for e in entries]
    floor = sum(e.projection.floor for e in entries)
    ceiling = sum(e.projection.ceiling for e in entries)
    rng = random.Random(seed)
    wins = 0
    for _ in range(2500):
        score = sum(max(0, rng.gauss(e.projection.mean, e.player.stdev)) for e in entries)
        wins += score > max(0, rng.gauss(opponent_mean, 15))
    complete=len(entries)==len(slots)
    explanation={"safe":"Maximizes adjusted projection minus a variance penalty.","balanced":"Maximizes adjusted expected projection.","upside":"Maximizes adjusted projection plus a variance reward."}[style]
    if not complete:
        explanation += " A complete legal lineup could not be formed from available eligible players."
    return LineupResult(style=style, starters=entries, bench=remaining, expected_score=round(sum(means), 1), floor=round(floor, 1), ceiling=round(ceiling, 1), win_probability=round(wins / 2500, 3) if entries else 0, changes=[f"Start {e.player.name} in {e.slot}" for e in entries if e.player.injury_status != "HEALTHY"], is_complete=complete, missing_slots=missing_slots, explanation=explanation)


def waiver_moves(league: League) -> list[WaiverMove]:
    team = next(t for t in league.teams if t.id == league.user_team_id)
    before = optimize_lineup(team.players, league.roster_slots, league=league)
    results: list[WaiverMove] = []
    for add in league.free_agents:
        best = None
        for drop in team.players:
            after_players = [p for p in team.players if p.id != drop.id] + [add]
            after = optimize_lineup(after_players, league.roster_slots, league=league)
            if not after.is_complete:
                continue
            gain = after.expected_score - before.expected_score
            if best is None or gain > best[0]:
                best = (gain, drop, after)
        if not best or best[0] <= 0: continue
        gain, drop, _ = best
        add_ros = project_ros(add, league)
        drop_ros = project_ros(drop, league)
        ros_gain = add_ros.expected_vor - drop_ros.expected_vor
        drop_safety = _drop_safety(drop, team.players, league)
        faab_guidance = _faab_guidance(league, gain, ros_gain, add.position)
        category = "MUST ADD" if gain >= 4 else "STRONG ADD" if gain >= 2 else "TEAM-NEEDS FIT"
        results.append(WaiverMove(add=add, drop=drop, weekly_gain=round(gain, 1), ros_gain=round(ros_gain, 1), category=category, confidence=.64, faab_percent=int(faab_guidance["suggested_high_percent"]), reasons=["Compares the best legal lineup before and after the add/drop.", "Rest-of-season impact sums week-specific projection-service outputs and replacement value rather than multiplying one week by a constant."], risks=["Role, injuries, and free-agent availability can change before waivers clear.", "Future opponent context and verified bye weeks are labeled missing until integrated."], drop_safety=drop_safety, faab_guidance=faab_guidance))
    return sorted(results, key=lambda m: m.weekly_gain, reverse=True)


def user_team(league: League):
    return next(team for team in league.teams if team.id == league.user_team_id)


def _drop_safety(drop: Player, roster: list[Player], league: League) -> str:
    healthy_same_position = [p for p in roster if p.id != drop.id and p.position == drop.position and p.availability > 0.75]
    ros = project_ros(drop, league)
    if drop.mean >= 12 or ros.starter_level_weeks >= 3:
        return "Do not drop"
    if len(healthy_same_position) <= 1:
        return "High-risk drop"
    if ros.expected_vor > 8:
        return "Situational drop"
    if drop.mean >= 8:
        return "Reasonable drop"
    return "Safe drop"


def _faab_guidance(league: League, weekly_gain: float, ros_gain: float, position: str) -> dict[str, object]:
    original = league.acquisition_budget or 100
    scarcity = 1.25 if position in {"RB", "TE", "DST"} else 1.0
    leverage = 1.15 if league.week >= max(1, league.rules.regular_season_end - 3) else 1.0
    raw_percent = max(1, min(35, round((weekly_gain * 1.7 + max(0, ros_gain) * 0.15) * scarcity * leverage)))
    low = max(1, round(raw_percent * 0.75))
    high = max(low, round(raw_percent * 1.15))
    aggressive = max(high, round(raw_percent * 1.6))
    return {
        "label": "Value-based FAAB guidance",
        "suggested_low_percent": low,
        "suggested_high_percent": high,
        "aggressive_max_percent": aggressive,
        "suggested_low": round(original * low / 100),
        "suggested_high": round(original * high / 100),
        "aggressive_max": round(original * aggressive / 100),
        "note": "No market bidding data is available, so this is not a prediction of other managers' bids.",
    }
