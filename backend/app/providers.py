from __future__ import annotations

import os
import json
from datetime import UTC, datetime

import httpx

from .demo import demo_league
from .domain import DataState, League, ProviderStatus


async def connect_espn(league_id: str, season: int, team_id: str | None = None) -> League:
    if league_id == "demo": return demo_league()
    cookies = {}
    if os.getenv("ESPN_S2") and os.getenv("ESPN_SWID"):
        cookies = {"espn_s2": os.environ["ESPN_S2"], "SWID": os.environ["ESPN_SWID"]}
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
            weekly_projection = 0.0
            weekly_actual = 0.0
            for stat in source.get("stats", []):
                if int(stat.get("scoringPeriodId", -1)) != int(raw.get("scoringPeriodId", 1)): continue
                if stat.get("statSourceId") == 1: weekly_projection = max(weekly_projection, float(stat.get("appliedTotal", 0) or 0))
                if stat.get("statSourceId") == 0: weekly_actual = max(weekly_actual, float(stat.get("appliedTotal", 0) or 0))
            mean = weekly_projection or weekly_actual or 6.0
            eligible = {position}
            if position in {"RB","WR","TE"}: eligible.add("FLEX")
            if position in {"QB","RB","WR","TE"}: eligible.add("SUPERFLEX")
            injury = str(source.get("injuryStatus", "ACTIVE")).replace("_", " ")
            players.append(__import__('app.domain',fromlist=['Player']).Player(id=str(source.get("id")),name=source.get("fullName","Unknown player"),position=position,team=pro_team_map.get(source.get("proTeamId"),"FA"),eligible_slots=eligible,mean=max(0,mean),stdev=max(2.5,mean*.32),availability=.7 if injury in {"QUESTIONABLE","DOUBTFUL"} else 0 if injury in {"OUT","INJURY RESERVE"} else 1,injury_status=injury,rostered=True))
        teams.append(Team(id=str(t["id"]), name=(t.get("location", "") + " " + t.get("nickname", "Team")).strip(), record=f"{t.get('record', {}).get('overall', {}).get('wins', 0)}-{t.get('record', {}).get('overall', {}).get('losses', 0)}", players=players))
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
            projected=0.0
            for stat in source.get("stats",[]):
                if int(stat.get("scoringPeriodId",-1))==int(raw.get("scoringPeriodId",1)) and stat.get("statSourceId")==1:
                    projected=max(projected,float(stat.get("appliedTotal",0) or 0))
            eligible={position}
            if position in {"RB","WR","TE"}: eligible.add("FLEX")
            if position in {"QB","RB","WR","TE"}: eligible.add("SUPERFLEX")
            free_agents.append(__import__('app.domain',fromlist=['Player']).Player(id=pid,name=source.get("fullName","Unknown player"),position=position,team=pro_team_map.get(source.get("proTeamId"),"FA"),eligible_slots=eligible,mean=max(0,projected or 4.0),stdev=max(2.5,(projected or 4.0)*.38),availability=1,injury_status=str(source.get("injuryStatus","ACTIVE")),rostered=False))
    except httpx.HTTPError:
        free_agents=[]
    scoring_items=settings.get("scoringSettings",{}).get("scoringItems",[])
    scoring={str(item.get("statId")):float(item.get("points",0) or 0) for item in scoring_items if item.get("statId") is not None}
    return League(id=str(raw.get("id", league_id)), name=settings.get("name", "ESPN League"), season=season, week=int(raw.get("scoringPeriodId", 1)), user_team_id=str(chosen), roster_slots=roster_slots, teams=teams, free_agents=free_agents, scoring=scoring, playoff_team_count=int(settings.get("scheduleSettings",{}).get("playoffTeamCount",4)), acquisition_budget=settings.get("acquisitionSettings",{}).get("acquisitionBudget"))


def statuses(demo: bool = True) -> list[ProviderStatus]:
    now = datetime.now(UTC).isoformat()
    return [
        ProviderStatus(provider="ESPN", category="League data", state=DataState.MOCK if demo else DataState.LIVE, updated=now, impact="Demo league" if demo else "Roster and scoring are current"),
        ProviderStatus(provider="The Odds API", category="Vegas game lines", state=DataState.UNAVAILABLE if not os.getenv("ODDS_API_KEY") else DataState.CACHED, key_configured=bool(os.getenv("ODDS_API_KEY")), impact="Neutral baseline; configure the optional free key" if not os.getenv("ODDS_API_KEY") else "Markets included in projections"),
        ProviderStatus(provider="Open-Meteo", category="Weather", state=DataState.CACHED, updated=now, impact="No severe weather adjustment in demo"),
        ProviderStatus(provider="nflverse", category="Usage and injuries", state=DataState.MOCK if demo else DataState.CACHED, updated=now, impact="Role signals are labeled demo" if demo else "Usage context included"),
        ProviderStatus(provider="Player props", category="Player markets", state=DataState.UNAVAILABLE, impact="Optional; projections use game-level markets"),
    ]
