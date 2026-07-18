from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .demo import demo_league
from .engine import optimize_lineup, user_team, waiver_moves
from .providers import connect_espn, statuses
from .persistence import delete_all_user_data, load_state, record_prediction, save_state
from .live_providers import nflverse_rosters, odds, weather
from .security import SecurityMiddleware, allowed_origins, clean_question, validate_discord_webhook
from .errors import AppError, error_payload
from .prompting import wrap_untrusted_user_input
import httpx
from .advanced import calibration_summary, draft_board, evaluate_trade, player_research, power_rankings, report_csv, trade_ideas, what_if

app = FastAPI(title="Fourth Down API", version="0.3.0")
app.add_middleware(SecurityMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=sorted(allowed_origins()), allow_methods=["GET","POST","DELETE","OPTIONS"], allow_headers=["Content-Type"], allow_credentials=False)
_saved = load_state("current_league")
CURRENT = __import__('app.domain',fromlist=['League']).League.model_validate(_saved) if _saved else demo_league()


class ConnectRequest(BaseModel):
    league_id: str = Field(min_length=1, max_length=30, pattern=r"^(demo|[0-9]{1,30})$")
    season: int = Field(ge=2020, le=2030)
    team_id: str | None = Field(default=None, pattern=r"^[0-9]{1,10}$")


class TradeRequest(BaseModel):
    send_ids: list[str] = Field(min_length=1, max_length=4)
    receive_ids: list[str] = Field(min_length=1, max_length=4)
    opponent_team_id: str | None = None


class WhatIfRequest(BaseModel):
    remove_id: str
    add_id: str


class DraftPickRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    team_id: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    @field_validator("question")
    @classmethod
    def normalize_question(cls,value:str)->str:return clean_question(value)

class DeleteDataRequest(BaseModel):
    confirmation: str = Field(pattern=r"^DELETE MY DATA$")

@app.exception_handler(RequestValidationError)
async def validation_error(_:Request,exc:RequestValidationError):
    fields=[".".join(str(x) for x in err["loc"] if x!="body") for err in exc.errors()]
    return JSONResponse(status_code=422,content={**error_payload("INVALID_INPUT","Some information is missing or formatted incorrectly.","Review the highlighted fields and try again."),"fields":fields})

@app.exception_handler(AppError)
async def app_error(_:Request,exc:AppError):return JSONResponse(status_code=exc.status_code,content=exc.payload())

@app.exception_handler(HTTPException)
async def http_error(_:Request,exc:HTTPException):
    if isinstance(exc.detail,dict):return JSONResponse(status_code=exc.status_code,content={"detail":exc.detail})
    defaults={404:("NOT_FOUND","That item could not be found.","Check the address or selection and try again."),409:("CONFLICT","That action conflicts with the current state.","Refresh the page and try again."),422:("INVALID_INPUT",str(exc.detail),"Review your selection and try again."),502:("PROVIDER_ERROR",str(exc.detail),"Wait a moment and retry; cached data remains available.")}
    code,message,hint=defaults.get(exc.status_code,("REQUEST_FAILED",str(exc.detail),"Try again. If this continues, restart Fourth Down."))
    return JSONResponse(status_code=exc.status_code,content=error_payload(code,message,hint,exc.status_code>=500))


@app.get("/api/health")
def health(): return {"status": "ok", "mode": "demo" if CURRENT.id == "demo" else "live"}


@app.post("/api/connect")
async def connect(req: ConnectRequest):
    global CURRENT
    try:
        CURRENT = await connect_espn(req.league_id, req.season, req.team_id)
        if not CURRENT.teams:
            raise AppError(404,"LEAGUE_NOT_FOUND","ESPN did not return any teams for that league.","Check the league ID and season. For a private league, also verify your ESPN cookies.")
        save_state("current_league", CURRENT.model_dump(mode="json"))
        warnings=[]
        if CURRENT.id!="demo" and not any(team.players for team in CURRENT.teams): warnings.append("League connected, but ESPN returned no rostered players. This can happen before rosters are populated or when private-league cookies have expired.")
        if CURRENT.id!="demo" and not CURRENT.free_agents: warnings.append("League connected, but ESPN did not return a free-agent pool. Waiver recommendations will remain unavailable until the next refresh.")
        return {"league": CURRENT, "mode": "demo" if CURRENT.id == "demo" else "live", "warnings":warnings}
    except AppError:
        raise
    except ValueError as exc:
        if str(exc)=="TEAM_NOT_FOUND": raise AppError(404,"TEAM_NOT_FOUND","That team ID is not in this league.","Leave Team ID blank to select the first team, or copy the correct team ID from ESPN.") from exc
        raise AppError(422,"LEAGUE_DATA_INVALID","ESPN returned league data Fourth Down could not understand.","Confirm the season and league settings, then try again.") from exc
    except httpx.TimeoutException as exc:
        raise AppError(504,"ESPN_TIMEOUT","ESPN took too long to respond.","Your information is probably correct. Wait a minute and try connecting again.",True) from exc
    except httpx.HTTPStatusError as exc:
        status=exc.response.status_code
        if status==404: raise AppError(404,"LEAGUE_NOT_FOUND","No ESPN league was found with that ID for this season.","Check for a mistyped league ID and confirm the season year, then try again.") from exc
        if status in {401,403}: raise AppError(401,"ESPN_AUTH_REQUIRED","ESPN would not allow access to this league.","If the league is private, refresh ESPN_S2 and ESPN_SWID from your logged-in browser, restart Fourth Down, and try again.") from exc
        if status==429: raise AppError(429,"ESPN_RATE_LIMITED","ESPN is temporarily limiting connection requests.","Wait a few minutes before trying again.",True) from exc
        raise AppError(502,"ESPN_ERROR",f"ESPN returned an unexpected response ({status}).","Wait briefly and retry. If it continues, confirm the league still opens in ESPN.",True) from exc
    except httpx.ConnectError as exc:
        raise AppError(503,"ESPN_UNREACHABLE","Fourth Down could not reach ESPN.","Check your internet connection and try again. Your credentials were not changed.",True) from exc
    except Exception as exc:
        raise AppError(500,"CONNECTION_FAILED","The league connection could not be completed.","Restart Fourth Down and try again. If it continues, share this error code—not your ESPN cookies.",True) from exc


@app.get("/api/overview")
def overview():
    team = user_team(CURRENT)
    lineup = optimize_lineup(team.players, CURRENT.roster_slots) if team.players else None
    if lineup: record_prediction(CURRENT.id,CURRENT.season,CURRENT.week,"weekly_lineup",lineup.expected_score,lineup.win_probability)
    return {"league": CURRENT, "team": team, "lineup": lineup, "actions": waiver_moves(CURRENT)[:2], "data_status": statuses(CURRENT.id == "demo"), "mode": "demo" if CURRENT.id == "demo" else "live"}


@app.get("/api/lineup")
def lineup():
    players = user_team(CURRENT).players
    return {style: optimize_lineup(players, CURRENT.roster_slots, style=style) for style in ("safe", "balanced", "upside")}


@app.get("/api/waivers")
def waivers(): return {"moves": waiver_moves(CURRENT), "mode": "demo" if CURRENT.id == "demo" else "live"}


@app.get("/api/data-sources")
def data_sources(): return statuses(CURRENT.id == "demo")


@app.get("/api/draft")
def draft(mode: str = "balanced"):
    if mode not in {"safe", "balanced", "ceiling"}: raise HTTPException(422, "Mode must be safe, balanced, or ceiling")
    state=load_state(f"draft:{CURRENT.id}") or {"picks":[]}
    drafted={pick["player_id"] for pick in state["picks"]}
    recommendations=[rec for rec in draft_board(CURRENT,mode) if rec.player.id not in drafted]
    return {"mode": mode, "recommendations": recommendations, "method": "VOR + roster need + positional scarcity", "picks":state["picks"]}


@app.post("/api/draft/pick")
def draft_pick(req: DraftPickRequest):
    key=f"draft:{CURRENT.id}"; state=load_state(key) or {"picks":[]}
    if any(p["player_id"]==req.player_id for p in state["picks"]): raise HTTPException(409,"Player has already been drafted")
    state["picks"].append({"number":len(state["picks"])+1,"player_id":req.player_id,"team_id":req.team_id})
    save_state(key,state); return state


@app.delete("/api/draft")
def draft_reset(): save_state(f"draft:{CURRENT.id}",{"picks":[]}); return {"picks":[]}


@app.get("/api/trades")
def trades():
    team = user_team(CURRENT)
    opponents = [t for t in CURRENT.teams if t.id != team.id]
    return {"your_players": team.players, "opponents": opponents, "ideas": trade_ideas(CURRENT)}


@app.post("/api/trades/evaluate")
def trade_evaluate(req: TradeRequest):
    try: return evaluate_trade(CURRENT, req.send_ids, req.receive_ids, req.opponent_team_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.get("/api/players")
def players(q: str = ""):
    values = [p for t in CURRENT.teams for p in t.players] + CURRENT.free_agents
    if q: values = [p for p in values if q.lower() in p.name.lower() or q.lower() in p.team.lower()]
    return {"players": values[:50]}


@app.get("/api/players/{player_id}")
def player(player_id: str):
    try: return player_research(CURRENT, player_id)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc


@app.get("/api/what-if/options")
def what_if_options():
    team = user_team(CURRENT)
    alternatives = [p for t in CURRENT.teams if t.id != team.id for p in t.players] + CURRENT.free_agents
    return {"roster": team.players, "alternatives": alternatives}


@app.post("/api/what-if")
def what_if_run(req: WhatIfRequest):
    try: return what_if(CURRENT, req.remove_id, req.add_id)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@app.get("/api/power-rankings")
def rankings(): return {"teams": power_rankings(CURRENT), "simulations": 4000}


@app.get("/api/standings-projection")
def standings(): return {"teams": sorted(power_rankings(CURRENT), key=lambda t: t.projected_wins, reverse=True), "through_week": CURRENT.week}


@app.get("/api/trust")
def trust(): return calibration_summary()


@app.get("/api/reports/weekly.csv", response_class=PlainTextResponse)
def weekly_report(): return PlainTextResponse(report_csv(CURRENT), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=fourth-down-weekly.csv"})


@app.get("/api/reports/weekly.pdf")
def weekly_pdf():
    team=user_team(CURRENT); lineup=optimize_lineup(team.players,CURRENT.roster_slots) if team.players else None
    lines=["Fourth Down Weekly Decision Report",CURRENT.name,f"Season {CURRENT.season} - Week {CURRENT.week}",f"Team: {team.name} ({team.record})"]
    if lineup: lines += [f"Expected score: {lineup.expected_score}",f"Range: {lineup.floor} to {lineup.ceiling}",f"Win probability: {lineup.win_probability:.0%}"]
    content="BT /F1 16 Tf 60 750 Td "+" ".join(f"({line.replace('(','[').replace(')',']')}) Tj 0 -25 Td" for line in lines)+" ET"
    objects=[b"<< /Type /Catalog /Pages 2 0 R >>",b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode(),b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    pdf=bytearray(b"%PDF-1.4\n"); offsets=[0]
    for i,obj in enumerate(objects,1): offsets.append(len(pdf)); pdf.extend(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=len(pdf); pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()); pdf.extend(b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets[1:])); pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return Response(bytes(pdf),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=fourth-down-weekly.pdf"})


@app.post("/api/ask")
def ask_engine(req: AskRequest):
    q=req.question.lower(); untrusted=wrap_untrusted_user_input(req.question); team=user_team(CURRENT)
    if "waiver" in q or "add" in q:
        moves=waiver_moves(CURRENT); answer=f"Your top add is {moves[0].add.name}, dropping {moves[0].drop.name}, for an estimated {moves[0].weekly_gain:+.1f} weekly points." if moves else "No positive add/drop move is currently modeled."
    elif "lineup" in q or "start" in q or "bench" in q:
        result=optimize_lineup(team.players,CURRENT.roster_slots); answer=f"The balanced lineup projects for {result.expected_score} points with a {result.win_probability:.0%} simulated win probability."
    elif "trade" in q:
        ideas=trade_ideas(CURRENT); answer=f"The strongest generated offer sends {ideas[0].send[0].name} for {ideas[0].receive[0].name}; modeled weekly change {ideas[0].weekly_delta:+.1f}." if ideas else "No realistic non-negative trade idea was found."
    else:
        answer="I can answer template-based questions about your lineup, waiver adds, or generated trade ideas using current engine output."
    return {"answer":answer,"method":"Template matched locally; no LLM or prompt was used","mode":"derived","input_boundary":"UNTRUSTED_USER_INPUT","input_length":len(req.question)}


@app.post("/api/digest/send")
async def send_digest():
    import os, httpx
    url=os.getenv("DIGEST_WEBHOOK_URL")
    if not url: raise HTTPException(422,"DIGEST_WEBHOOK_URL is not configured")
    try: validate_discord_webhook(url)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    team=user_team(CURRENT); lineup=optimize_lineup(team.players,CURRENT.roster_slots); moves=waiver_moves(CURRENT)
    message=f"Fourth Down — {CURRENT.name}, Week {CURRENT.week}\n{team.name}: {lineup.expected_score} projected, {lineup.win_probability:.0%} win chance."
    if moves: message += f"\nTop move: add {moves[0].add.name}, drop {moves[0].drop.name}."
    async with httpx.AsyncClient(timeout=15) as client: response=await client.post(url,json={"content":message})
    response.raise_for_status(); return {"sent":True}

@app.get("/api/privacy")
def privacy_summary():
    return {"storage":"Local SQLite only","tracking":False,"advertising":False,"secrets_returned_to_browser":False,"external_providers":["ESPN when connected","The Odds API when refreshed","Open-Meteo when requested","nflverse when refreshed","Discord only when digest is manually sent"],"deletion":"DELETE /api/privacy/data with explicit confirmation"}

@app.delete("/api/privacy/data")
def delete_data(req:DeleteDataRequest):
    global CURRENT
    delete_all_user_data(); CURRENT=demo_league()
    return {"deleted":True,"mode":"demo"}


@app.get("/api/settings")
def settings(): return {"league": CURRENT, "privacy": {"espn_s2_configured": bool(__import__('os').getenv('ESPN_S2')), "espn_swid_configured": bool(__import__('os').getenv('ESPN_SWID')), "odds_key_configured": bool(__import__('os').getenv('ODDS_API_KEY'))}}


@app.post("/api/providers/odds/refresh")
async def refresh_odds():
    try: return await odds(force=True)
    except Exception as exc: raise HTTPException(502,"Odds refresh failed; cached data remains available") from exc


@app.get("/api/providers/weather/{team}")
async def provider_weather(team: str):
    try: return await weather(team.upper())
    except Exception as exc: raise HTTPException(502,"Weather provider is temporarily unavailable") from exc


@app.post("/api/providers/nflverse/refresh")
async def refresh_nflverse():
    try:
        result=await nflverse_rosters(CURRENT.season,force=True)
        return {"status":result["status"],"bytes":len(result["payload"]["csv"])}
    except Exception as exc: raise HTTPException(502,"nflverse refresh failed; cached data remains available") from exc
