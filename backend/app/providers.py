from __future__ import annotations

import os
import json
from datetime import UTC, datetime

import httpx

from .config import CONFIG
from .domain import DataState, League, LeagueRuleSet, Matchup, ProviderStatus


def normalize_espn_cookie(value: str | None, cookie_name: str) -> str:
    """Accept a raw cookie value or a copied name=value fragment without logging it."""
    text = (value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    for fragment in text.split(";"):
        fragment = fragment.strip()
        if "=" in fragment:
            name, candidate = fragment.split("=", 1)
            if name.strip().lower() == cookie_name.lower():
                text = candidate.strip().strip('"').strip("'")
                break
    if cookie_name.lower() == "swid" and text and not (text.startswith("{") and text.endswith("}")):
        text = "{" + text.strip("{}") + "}"
    return text


def _espn_pool_items(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    rows = payload.get("players") or payload.get("playerPoolEntries") or []
    return [item for item in rows if isinstance(item, dict)]


def _espn_pool_player(item: dict) -> dict:
    direct = item.get("player")
    if isinstance(direct, dict) and direct:
        return direct
    entry = item.get("playerPoolEntry")
    if isinstance(entry, dict) and isinstance(entry.get("player"), dict):
        return entry["player"]
    return {}


def _espn_player_values(source: dict, current_period: int, item: dict | None = None) -> dict[str, float | int | None]:
    item = item or {}
    entry = item.get("playerPoolEntry") if isinstance(item.get("playerPoolEntry"), dict) else {}
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
    ownership = source.get("ownership") or entry.get("ownership") or item.get("ownership") or {}
    adp = ownership.get("averageDraftPosition")
    percent_owned = ownership.get("percentOwned")
    rank_types = source.get("draftRanksByRankType") or entry.get("draftRanksByRankType") or item.get("draftRanksByRankType") or {}
    rank_row = rank_types.get("PPR") or rank_types.get("HALF") or rank_types.get("STANDARD") or next(iter(rank_types.values()), {})
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
    supplied_s2 = normalize_espn_cookie(espn_s2, "espn_s2")
    supplied_swid = normalize_espn_cookie(espn_swid, "SWID")
    if bool(supplied_s2) != bool(supplied_swid):
        raise ValueError("INCOMPLETE_ESPN_AUTH")
    if len(supplied_s2) > 4096 or len(supplied_swid) > 256:
        raise ValueError("INVALID_ESPN_AUTH")
    cookies = {}
    if supplied_s2 and supplied_swid:
        cookies = {"espn_s2": supplied_s2, "SWID": supplied_swid}
    elif CONFIG.espn_s2 and CONFIG.espn_swid and not CONFIG.cloud_mode:
        cookies = {"espn_s2": normalize_espn_cookie(CONFIG.espn_s2, "espn_s2"), "SWID": normalize_espn_cookie(CONFIG.espn_swid, "SWID")}
    url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
    params = [("view", v) for v in ("mSettings", "mTeam", "mRoster", "mMatchup", "mDraftDetail")]
    async with httpx.AsyncClient(timeout=15, cookies=cookies, follow_redirects=True) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    try:
        raw = response.json()
    except (TypeError, ValueError) as exc:
        raise ValueError("ESPN_AUTH_RESPONSE_INVALID" if cookies else "ESPN_RESPONSE_INVALID") from exc
    if not isinstance(raw, dict) or (cookies and not raw.get("settings") and not raw.get("teams")):
        raise ValueError("ESPN_AUTH_RESPONSE_INVALID" if cookies else "ESPN_RESPONSE_INVALID")
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
    draft_pool=[]
    scoring_items_for_draft = settings.get("scoringSettings", {}).get("scoringItems", [])
    scoring_type = "PPR" if any(int(item.get("statId", -1)) == 53 and float(item.get("points", 0) or 0) > 0 for item in scoring_items_for_draft) else "STANDARD"
    pool_filters = [
        {"players":{"limit":1500,"sortDraftRanks":{"sortPriority":1,"sortAsc":True,"value":scoring_type}}},
        {"players":{"limit":1000,"sortPercOwned":{"sortPriority":1,"sortAsc":False}}},
        {"players":{"limit":500,"sortDraftRanks":{"sortPriority":1,"sortAsc":True,"value":"STANDARD"}}},
    ]
    pool_items = None
    last_pool_error: Exception | None = None
    pool_diagnostics = {"status": "UNAVAILABLE", "attempts": [], "raw_player_count": 0, "normalized_player_count": 0, "rejected": {}}
    for attempt_number, fantasy_filter in enumerate(pool_filters, 1):
        try:
            async with httpx.AsyncClient(timeout=15,cookies=cookies,follow_redirects=True) as client:
                pool_response=await client.get(url,params={"view":"kona_player_info","scoringPeriodId":0},headers={"X-Fantasy-Filter":json.dumps(fantasy_filter)})
            pool_response.raise_for_status()
            candidate_items = _espn_pool_items(pool_response.json())
            pool_diagnostics["attempts"].append({"attempt": attempt_number, "status_code": pool_response.status_code, "raw_count": len(candidate_items), "result": "accepted" if candidate_items else "empty"})
            if candidate_items:
                pool_items = candidate_items
                break
            last_pool_error = ValueError("ESPN player-pool response contained no players")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise
            pool_diagnostics["attempts"].append({"attempt": attempt_number, "status_code": exc.response.status_code, "raw_count": 0, "result": "http_error"})
            last_pool_error = exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            pool_diagnostics["attempts"].append({"attempt": attempt_number, "status_code": None, "raw_count": 0, "result": type(exc).__name__})
            last_pool_error = exc
    if pool_items is not None:
        pool_diagnostics["raw_player_count"] = len(pool_items)
        rostered={player.id for team in teams for player in team.players}
        for pool_rank, item in enumerate(pool_items, 1):
            try:
                source=_espn_pool_player(item)
                if not source:
                    pool_diagnostics["rejected"]["missing_player_object"] = pool_diagnostics["rejected"].get("missing_player_object", 0) + 1
                    continue
                pid=str(source.get("id") or "")
                position=position_map.get(source.get("defaultPositionId"))
                if not pid:
                    pool_diagnostics["rejected"]["missing_player_id"] = pool_diagnostics["rejected"].get("missing_player_id", 0) + 1
                    continue
                if not position:
                    pool_diagnostics["rejected"]["unsupported_position"] = pool_diagnostics["rejected"].get("unsupported_position", 0) + 1
                    continue
                values = _espn_player_values(source, int(raw.get("scoringPeriodId", 1)), item)
                projected = values["weekly_projection"]
                eligible={position}
                if position in {"RB","WR","TE"}: eligible.add("FLEX")
                if position in {"QB","RB","WR","TE"}: eligible.add("SUPERFLEX")
                draft_player=__import__('app.domain',fromlist=['Player']).Player(id=pid,name=source.get("fullName","Unknown player"),position=position,team=pro_team_map.get(source.get("proTeamId"),"FA"),eligible_slots=eligible,mean=max(0,float(projected or 0)),stdev=max(.1,float(projected or 0)*.38),availability=1,injury_status=str(source.get("injuryStatus","ACTIVE")),rostered=pid in rostered,projection_available=projected is not None,projection_source="ESPN fantasy projection",season_projection=values["season_projection"],average_draft_position=values["average_draft_position"],percent_owned=values["percent_owned"],espn_rank=values["espn_rank"],draft_pool_rank=pool_rank)
                draft_pool.append(draft_player)
                if pid not in rostered:
                    free_agents.append(draft_player.model_copy(update={"rostered": False}))
            except (TypeError, ValueError, KeyError):
                pool_diagnostics["rejected"]["normalization_error"] = pool_diagnostics["rejected"].get("normalization_error", 0) + 1
        pool_diagnostics["normalized_player_count"] = len(draft_pool)
        pool_diagnostics["status"] = "LIVE" if draft_pool else "INVALID"
    elif last_pool_error is not None:
        pool_diagnostics["error_code"] = "ESPN_PLAYER_POOL_UNAVAILABLE"
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
    draft_picks = []
    try:
        draft_size = int(settings.get("size") or len({team.id for team in teams}) or 0)
    except (TypeError, ValueError):
        draft_size = 0
    draft_type = str((settings.get("draftSettings") or {}).get("type") or "SNAKE").upper()
    player_lookup = {player.id: player for team in teams for player in team.players}
    player_lookup.update({player.id: player for player in draft_pool})
    for raw_pick in (raw.get("draftDetail") or {}).get("picks", []):
        player_id = str(raw_pick.get("playerId") or "")
        if not player_id:
            continue
        player = player_lookup.get(player_id)
        pick_number = int(raw_pick.get("overallPickNumber") or len(draft_picks) + 1)
        round_index = (pick_number - 1) // draft_size if draft_size >= 2 else 0
        pick_in_round = ((pick_number - 1) % draft_size) + 1 if draft_size >= 2 else pick_number
        owner_slot = (draft_size - pick_in_round + 1 if "SNAKE" in draft_type and round_index % 2 else pick_in_round) if draft_size >= 2 else 0
        draft_picks.append({
            "number": pick_number,
            "owner_slot": owner_slot,
            "team_id": str(raw_pick.get("teamId") or ""),
            "player_id": player_id,
            "player_name": player.name if player else f"ESPN player {player_id}",
            "position": player.position if player else "UNKNOWN",
            "source": "ESPN live draft",
        })
    normalized_settings = dict(settings)
    normalized_settings["_draft_picks"] = sorted(draft_picks, key=lambda pick: pick["number"])
    raw_order = (raw.get("draftDetail") or {}).get("draftOrder") or {}
    normalized_order = {}
    if isinstance(raw_order, dict):
        for team_key, slot_value in raw_order.items():
            try:
                normalized_order[str(team_key)] = int(slot_value)
            except (TypeError, ValueError):
                continue
    normalized_settings["_draft_order"] = normalized_order
    if draft_picks:
        first_round = [pick for pick in draft_picks if draft_size >= 2 and int(pick["number"]) <= draft_size and pick.get("team_id")]
        normalized_settings["_live_draft_order"] = {str(pick["team_id"]): int(pick["number"]) for pick in first_round}
    normalized_settings["_draft_pool_diagnostics"] = pool_diagnostics
    return League(id=str(raw.get("id", league_id)), name=settings.get("name", "ESPN League"), season=season, week=current_period, user_team_id=str(chosen), roster_slots=roster_slots, teams=teams, free_agents=free_agents, draft_pool=draft_pool, scoring=scoring, playoff_team_count=playoff_team_count, acquisition_budget=settings.get("acquisitionSettings",{}).get("acquisitionBudget"), rules=rules, schedule=schedule, raw_settings=normalized_settings)


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
