from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .domain import League, LineupEntry, LineupResult, Player, Projection, WaiverMove


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
    reasons = ["Game expectation establishes the scoring baseline", "Role and availability are applied as bounded context",*live_reasons]
    if player.injury_status != "HEALTHY": reasons.append(f"{player.injury_status.title()} status lowers availability and raises uncertainty")
    return Projection(player_id=player.id, mean=round(mean, 2), median=round(mean, 2), floor=round(max(0, mean - 1.28 * sd), 2), ceiling=round(mean + 1.28 * sd, 2), confidence=round(max(.35, .82 - .08 * len(absent)), 2), reasons=reasons, missing=absent)


def _eligible(player: Player, slot: str) -> bool:
    return slot in player.eligible_slots


def optimize_lineup(players: list[Player], slots: list[str], *, style: str = "balanced", opponent_mean: float = 112, seed: int = 7) -> LineupResult:
    multiplier = {"safe": -0.28, "balanced": 0, "upside": .28}[style]
    remaining = players[:]
    entries: list[LineupEntry] = []
    for slot in sorted(slots, key=lambda s: (s == "FLEX", s)):
        eligible = [p for p in remaining if _eligible(p, slot)]
        if not eligible: continue
        chosen = max(eligible, key=lambda p: p.mean + multiplier * p.stdev)
        remaining.remove(chosen)
        entries.append(LineupEntry(slot=slot, player=chosen, projection=project(chosen)))
    means = [e.projection.mean for e in entries]
    floor = sum(e.projection.floor for e in entries)
    ceiling = sum(e.projection.ceiling for e in entries)
    rng = random.Random(seed)
    wins = 0
    for _ in range(2500):
        score = sum(max(0, rng.gauss(e.projection.mean, e.player.stdev)) for e in entries)
        wins += score > max(0, rng.gauss(opponent_mean, 15))
    return LineupResult(style=style, starters=entries, bench=remaining, expected_score=round(sum(means), 1), floor=round(floor, 1), ceiling=round(ceiling, 1), win_probability=round(wins / 2500, 3), changes=[f"Start {e.player.name} in {e.slot}" for e in entries if e.player.injury_status != "HEALTHY"])


def waiver_moves(league: League) -> list[WaiverMove]:
    team = next(t for t in league.teams if t.id == league.user_team_id)
    bench_value = {p.id: p.mean for p in team.players}
    results: list[WaiverMove] = []
    for add in league.free_agents:
        candidates = [p for p in team.players if p.position == add.position or "FLEX" in p.eligible_slots]
        if not candidates: continue
        drop = min(candidates, key=lambda p: bench_value[p.id])
        gain = add.mean - drop.mean
        if gain <= 0: continue
        category = "MUST ADD" if gain >= 4 else "STRONG ADD" if gain >= 2 else "TEAM-NEEDS FIT"
        results.append(WaiverMove(add=add, drop=drop, weekly_gain=round(gain, 1), ros_gain=round(gain * 6.2, 1), category=category, confidence=.68, faab_percent=min(25, max(3, round(gain * 3))), reasons=[f"Raises the {add.position} replacement baseline", "Improves usable weekly depth without assuming a prop feed"], risks=["Role and free-agent availability can change before waivers clear"]))
    return sorted(results, key=lambda m: m.weekly_gain, reverse=True)


def user_team(league: League):
    return next(team for team in league.teams if team.id == league.user_team_id)
