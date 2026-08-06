from __future__ import annotations

import os
import json
from datetime import UTC, datetime

import httpx

from .config import CONFIG
from .domain import DataState, League, LeagueRuleSet, Matchup, ProviderStatus


def _espn_player_values(source: dict, current_period: int) -> dict[str, float | int | None]:
    weekly_projection: float | None = None
    season_projection: float | None = None
    for stat in source.get("stats", []):
        if stat.get("statSourceId") != 1:
            continue
        value = float(stat.get("appliedTotal", 0) or 0)
        period = int(stat.get("scoringPeriodId", -1) or -1)
        if period == current_period and value > 0:
            weekly_projection = max(weekly_projection or 0, value)
        if period == 0 and value > 0:
            season_projection = max(season_projection or 0, value)
    ownership = source.get("ownership") or {}
    adp = ownership.get("averageDraftPosition")
    percent_owned = ownership.get("percentOwned")
    rank_types = source.get("draftRanksByRankType") or {}
    rank_row = rank_types.get("PPR") or rank_types.get("STANDARD") or {}
    rank = rank_row.get("rank")
    return {
        "weekly_projection": weekly_projection,
        "season_projection": season_projection,
        "average_draft_position": float(adp) if adp not in (None, 0, 0.0) else None,
        "percent_owned": float(percent_owned) if percent_owned is not None else None,
        "espn_rank": int(rank) if rank not in (None, 0) else None,
    }


async def connect_espn(
    league_id: str,
    season: int,
    team_id: str | None = None,
    *,
    espn_s2: str | None = None,
    espn_swid: str | None = None,
) -> League:
    supplied_s2 = (espn_s2 or "").strip()
    supplied_swid = (espn_swid or "").strip()
    if bool(supplied_s2) != bool(supplied_swid):
        raise ValueError("INCOMPLETE_ESPN_AUTH")
    if len(supplied_s2) > 4096 or len(supplied_swid) > 256:
        raise ValueError("INVALID_ESPN_AUTH")
    cookies = {}
    if supplied_s2 and supplied_swid:
        cookies = {"espn_s2": supplied_s2, "SWID": supplied_swid}
    elif CONFIG.espn_s2 and CONFIG.espn_swid and not CONFIG.cloud_mode:
        cookies = {"espn_s2": CONFIG.espn_s2, "SWID": CONFIG.espn_swid}
    url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
    params = [("view", v) for v in ("mSettings", "mTeam", "mRoster", "mMatchup")]
    async with httpx.AsyncClient(timeout=15, cookies=cookies) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    raw = response.json()
    # ESPN's player pool needs a separate paged call; connection returns a safe normalized core.
    position_map = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
    pro_team_map = {1:"ATL",2:"BUF",3:"CHI",4:"CIN",5:"CLE",6:"DAL",7:"DEN",8:"DET",9:"GB",10:"TEN",11:"IND",12:"KC",13:"LV",14:"LAR",15:"MIA",16:"MIN",17:"NE",18:"NO",19:"NYG",20:"NYJ",21:"PHI",22:"ARI",23:"PIT",24:"LAC",25:"SF",26:"SEA",27:"TB",28:"WAS",29:"CAR",30:"JAX",33:"BAL",34:"HOU"}
    slot_map = {0:"QB",2:"RB",4:"WR",6:"TE",16:"DST",17:"K",20:"BENCH",21:"IR",23:"FLEX",7:"SUPERFLEX"}
    settings = raw.get("settings", {})
    roster_counts = settings.get("rosterSettings", {}).get("lineupSlotCounts", {})
    roster_slots: list[str] = []
    for raw_slot, count in roster_counts.items():
        slot = slot_map.get(int(raw_slot))
        if slot and slot not in {"BENCH", "IR"}: roster_slots.extend([slot] * int(count))
    if not roster_slots: roster_slots=["QB","RB","RB","WR","WR","TE","FLEX","K","DST"]
    teams = []
    from .domain import Team
    for t in raw.get("teams", []):
        players = []
        for entry in t.get("roster", {}).get("entries", []):
            source = entry.get("playerPoolEntry", {}).get("player", {})
            position = position_map.get(source.get("defaultPositionId"))
            if not position: continue
            values = _espn_player_values(source, int(raw.get("scoringPeriodId", 1)))
            weekly_projection = values["weekly_projection"]
            mean = float(weekly_projection or 0)
            eligible = {position}
            if position in {"RB","WR","TE"}: eligible.add("FLEX")
            if position in {"QB","RB","WR","TE"}: eligible.add("SUPERFLEX")
            injury = str(source.get("injuryStatus", "ACTIVE")).replace("_", " ")
            players.append(__import__('app.domain',fromlist=['Player']).Player(id=str(source.get("id")),name=source.get("fullName","Unknown player"),position=position,team=pro_team_map.get(source.get("proTeamId"),"FA"),eligible_slots=eligible,mean=max(0,mean),stdev=max(.1,mean*.32),availability=.7 if injury in {"QUESTIONABLE","DOUBTFUL"} else 0 if injury in {"OUT","INJURY RESERVE"} else 1,injury_status=injury,rostered=True,projection_available=weekly_projection is not None,projection_source="ESPN fantasy projection",season_projection=values["season_projection"],average_draft_position=values["average_draft_position"],percent_owned=values["percent_owned"],espn_rank=values["espn_rank"]))
        overall = t.get("record", {}).get("overall", {})
        wins = float(overall.get("wins", 0) or 0)
        losses = float(overall.get("losses", 0) or 0)
        ties = float(overall.get("ties", 0) or 0)
        teams.append(Team(id=str(t["id"]), name=(t.get("location", "") + " " + t.get("nickname", "Team")).strip(), record=f"{int(wins)}-{int(losses)}" + (f"-{int(ties)}" if ties else ""), players=players, division_id=str(t.get("divisionId")) if t.get("divisionId") is not None else None, wins=wins, losses=losses, ties=ties, points_for=float(overall.get("pointsFor", overall.get("points", 0)) or 0), points_against=float(overall.get("pointsAgainst", 0) or 0)))
    chosen = team_id or (teams[0].id if teams else "1")
    if teams and not any(team.id==str(chosen) for team in teams):
        raise ValueError("TEAM_NOT_FOUND")
    free_agents=[]
    try:
        fantasy_filter={"players":{"filterStatus":{"value":["FREEAGENT","WAIVERS"]},"limit":200,"sortPercOwned":{"sortPriority":1,"sortAsc":False}}}
        async with httpx.AsyncClient(timeout=15,cookies=cookies) as client:
            pool_response=await client.get(url,params={"view":"kona_player_info"},headers={"X-Fantasy-Filter":json.dumps(fantasy_filter)})
        pool_response.raise_for_status()
        rostered={player.id for team in teams for player in team.players}
        for item in pool_response.json().get("players",[]):
            source=item.get("player",{})
            pid=str(source.get("id")); position=position_map.get(source.get("defaultPositionId"))
            if not position or pid in rostered: continue
            values = _espn_player_values(source, int(raw.get("scoringPeriodId", 1)))
            projected = values["weekly_projection"]
            eligible={position}
            if position in {"RB","WR","TE"}: eligible.add("FLEX")
            if position in {"QB","RB","WR","TE"}: eligible.add("SUPERFLEX")
            free_agents.append(__import__('app.domain',fromlist=['Player']).Player(id=pid,name=source.get("fullName","Unknown player"),position=position,team=pro_team_map.get(source.get("proTeamId"),"FA"),eligible_slots=eligible,mean=max(0,float(projected or 0)),stdev=max(.1,float(projected or 0)*.38),availability=1,injury_status=str(source.get("injuryStatus","ACTIVE")),rostered=False,projection_available=projected is not None,projection_source="ESPN fantasy projection",season_projection=values["season_projection"],average_draft_position=values["average_draft_position"],percent_owned=values["percent_owned"],espn_rank=values["espn_rank"]))
    except httpx.HTTPError:
        free_agents=[]
    scoring_items=settings.get("scoringSettings",{}).get("scoringItems",[])
    scoring={str(item.get("statId")):float(item.get("points",0) or 0) for item in scoring_items if item.get("statId") is not None}
    schedule_settings = settings.get("scheduleSettings", {})
    current_period = int(raw.get("scoringPeriodId", 1))
    schedule: list[Matchup] = []
    for item in raw.get("schedule", []):
        home = item.get("home") or {}
        away = item.get("away") or {}
        home_id = home.get("teamId")
        away_id = away.get("teamId")
        if home_id is None or away_id is None:
            continue
        period = int(item.get("matchupPeriodId", item.get("scoringPeriodId", current_period)) or current_period)
        home_score = home.get("totalPoints")
        away_score = away.get("totalPoints")
        is_complete = bool(item.get("winner")) or period < current_period
        is_current = period == current_period and not is_complete
        schedule.append(Matchup(id=str(item.get("id") or f"{period}-{home_id}-{away_id}"), period=period, home_team_id=str(home_id), away_team_id=str(away_id), home_score=float(home_score) if home_score is not None else None, away_score=float(away_score) if away_score is not None else None, is_complete=is_complete, is_current=is_current, is_playoff=period >= int(schedule_settings.get("playoffMatchupPeriodLength", 1) or 1) + int(schedule_settings.get("matchupPeriodCount", 14) or 14), raw=item))
    regular_season_end = int(schedule_settings.get("matchupPeriodCount", 14) or 14)
    playoff_team_count = int(schedule_settings.get("playoffTeamCount", 4) or 4)
    first_byes = 2 if playoff_team_count in {6, 10} else 0
    unsupported = []
    assumptions = ["Seeding uses overall record, then points for, unless ESPN exposes a supported tiebreaker."]
    if not schedule:
        unsupported.append("ESPN schedule unavailable in response; schedule-aware simulation is disabled until a schedule is available.")
    if schedule_settings.get("matchupPeriodLength") not in (None, 1):
        unsupported.append("Nonstandard regular-season matchup period length is preserved but not fully supported.")
    if schedule_settings.get("playoffMatchupPeriodLength") not in (None, 1):
        assumptions.append("Multi-week playoff length is preserved for display; the simulator treats supported playoffs as one scoring period per round unless ESPN's raw settings clearly specify otherwise.")
    rules = LeagueRuleSet(regular_season_start=1, regular_season_end=regular_season_end, playoff_start=regular_season_end + 1, playoff_end=int(schedule_settings.get("playoffMatchupPeriodCount", regular_season_end + 3) or regular_season_end + 3), playoff_matchup_period_length=int(schedule_settings.get("playoffMatchupPeriodLength", 1) or 1), first_round_byes=first_byes, tiebreaker="record_then_points_for", reseeding="fixed", unsupported=unsupported, assumptions=assumptions, raw=schedule_settings)
    return League(id=str(raw.get("id", league_id)), name=settings.get("name", "ESPN League"), season=season, week=current_period, user_team_id=str(chosen), roster_slots=roster_slots, teams=teams, free_agents=free_agents, scoring=scoring, playoff_team_count=playoff_team_count, acquisition_budget=settings.get("acquisitionSettings",{}).get("acquisitionBudget"), rules=rules, schedule=schedule, raw_settings=settings)


def statuses(demo: bool = False) -> list[ProviderStatus]:
    from .persistence import cache_get
    now = datetime.now(UTC).isoformat()
    odds_cache = cache_get("odds:nfl")
    return [
        ProviderStatus(provider="ESPN", category="League data", state=DataState.LIVE, updated=now, used_by=["rosters","opponent rosters","lineup slots","weekly projections","season projections","ADP","free agents"], impact="Roster, scoring, lineup slots, projections, draft context, and free agents were loaded for this session", unavailable_behavior="The affected recommendation is unavailable; private leagues require session-only espn_s2 and SWID credentials."),
        ProviderStatus(provider="The Odds API", category="NFL market context", state=DataState(odds_cache["status"]) if odds_cache else DataState.UNAVAILABLE, updated=odds_cache["fetched_at"] if odds_cache else None, key_configured=bool(CONFIG.odds_api_key), used_by=["live NFL totals, spreads, and moneyline snapshot"], impact="Displayed as market context only; not applied to ESPN projections" if odds_cache else "No market context is displayed and no projection adjustment is applied", unavailable_behavior="Projection uses the ESPN baseline and marks game markets as missing."),
        ProviderStatus(provider="Open-Meteo", category="Weather", state=DataState.UNAVAILABLE, key_configured=False, used_by=["bounded projection adjustment when explicitly refreshed"], impact="Not refreshed for this session", unavailable_behavior="No weather adjustment is applied and stadium weather is marked missing."),
        ProviderStatus(provider="OpenWeather", category="Weather", state=DataState.UNAVAILABLE, key_configured=bool(CONFIG.openweather_api_key), used_by=["provider validation; future kickoff-matched weather context"], impact="No projection adjustment is applied until a game location and kickoff forecast are matched", unavailable_behavior="Weather remains unavailable; no neutral or invented value is substituted."),
        ProviderStatus(provider="nflverse", category="Open NFL roster data", state=DataState.UNAVAILABLE, key_configured=False, used_by=[], impact="Downloaded data is not yet parsed into projections in Phase 1", unavailable_behavior="No usage or injury adjustment is made from nflverse."),
        ProviderStatus(provider="Player props", category="Player markets", state=DataState.UNAVAILABLE, key_configured=False, used_by=[], impact="Not integrated in Phase 1", unavailable_behavior="Player prop inputs are listed as missing and confidence is reduced."),
    ]
