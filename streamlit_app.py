from __future__ import annotations

import asyncio
import csv
import importlib
import io
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import httpx
import streamlit as st


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

OPTIONAL_SECRET_KEYS = ("ODDS_API_KEY", "OPENWEATHER_API_KEY", "DIGEST_WEBHOOK_URL", "ENABLE_MARKET_ADJUSTMENTS")

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

try:
    for _key in OPTIONAL_SECRET_KEYS:
        _value = st.secrets.get(_key)
        if _value and not os.getenv(_key):
            os.environ[_key] = str(_value)
except Exception:
    pass

from app.advanced import (  # noqa: E402
    calibration_summary,
    draft_board,
    evaluate_trade,
    player_research,
    power_rankings,
    report_csv,
    trade_ideas,
    what_if,
)
from app.engine import optimize_lineup, project, user_team, waiver_moves  # noqa: E402
from app.domain import ActiveLeagueState, League, LeagueConnectionStatus, Player, Team  # noqa: E402
from app import draft_intelligence as _draft_intelligence  # noqa: E402

# Streamlit Cloud may hot-reload this entry point while retaining the previous
# backend module in sys.modules. Reload only when a newly deployed symbol is
# absent so an atomic Git deploy cannot fail against that stale module object.
if not hasattr(_draft_intelligence, "DraftConfiguration"):
    _draft_intelligence = importlib.reload(_draft_intelligence)

DEFAULT_DRAFT_SERVICE = _draft_intelligence.DEFAULT_DRAFT_SERVICE
DraftSelection = _draft_intelligence.DraftSelection
DraftSettings = _draft_intelligence.DraftSettings
DraftState = _draft_intelligence.DraftState
build_draft_configuration = _draft_intelligence.build_draft_configuration
league_draft_type = _draft_intelligence.league_draft_type
league_team_count = _draft_intelligence.league_team_count
resolve_manager_count = _draft_intelligence.resolve_manager_count
resolve_draft_slot = _draft_intelligence.resolve_draft_slot
owner_of_pick = _draft_intelligence.owner_of_pick
snake_next_pick = _draft_intelligence.snake_next_pick
from app.projection_service import DEFAULT_PROJECTION_SERVICE, SUPPORTED_MODEL_POSITIONS, TRAINING_POLICY  # noqa: E402
from app.providers import connect_espn, statuses  # noqa: E402
from app.espn_connection import (  # noqa: E402
    EspnSyncContext,
    SessionEspnCredentials,
    SessionLeagueCache,
    build_active_league_state,
    cached_league_connect,
    clear_connection_state,
    connect_with_backoff,
    parse_espn_league_url,
    safe_connection_error,
    select_team,
)
from app.decision_service import build_weekly_brief, roster_outlook, value_based_faab  # noqa: E402
from app.decision_journal import create_decision_entry  # noqa: E402
from app.config import APP_VERSION, CONFIG, config_summary, validate_config  # noqa: E402
from app.identity import build_identity_index, resolve_player_identity  # noqa: E402
from app.market import default_market_provider  # noqa: E402
from app.live_providers import odds as refresh_odds, validate_odds_key, validate_openweather_key  # noqa: E402
from app.operations import DEGRADATION_MATRIX, PERFORMANCE_BUDGETS, health_summary  # noqa: E402
from app.recommendations import generate_recommendation, require_confirmation, validate_recommendation  # noqa: E402
from app.security import allow_streamlit_action, streamlit_client_key  # noqa: E402
from app.simulation import (  # noqa: E402
    ScenarioConstraint,
    league_fingerprint,
    simulate_league,
)
from ui.components import (  # noqa: E402
    action_card,
    badge,
    confidence_badge,
    empty_state,
    freshness_badge,
    metric_card,
    metric_grid,
    page_header,
    player_card,
    section_header,
    stadium_hero,
    warning_state,
)
from ui.formatting import fantasy_points as fmt_points  # noqa: E402
from ui.formatting import h, percentage as fmt_pct, percentage_points  # noqa: E402
from ui.navigation import render_navigation  # noqa: E402
from ui.styles import inject_global_styles  # noqa: E402


LEAGUE_RE = re.compile(r"^[0-9]{1,30}$")
TEAM_RE = re.compile(r"^[0-9]{1,10}$")


def load_safe_config() -> None:
    try:
        for key in OPTIONAL_SECRET_KEYS:
            value = st.secrets.get(key)
            if value and not os.getenv(key):
                os.environ[key] = str(value)
    except Exception:
        pass


def ensure_state() -> None:
    load_safe_config()
    if "league" not in st.session_state:
        st.session_state.league = None
    if "league_connected" not in st.session_state:
        st.session_state.league_connected = False
    if "espn_connection" not in st.session_state:
        st.session_state.espn_connection = None
    if "active_league" not in st.session_state:
        st.session_state.active_league = None
    if "espn_candidate" not in st.session_state:
        st.session_state.espn_candidate = None
    if "espn_candidate_url" not in st.session_state:
        st.session_state.espn_candidate_url = None
    if "espn_cache" not in st.session_state:
        st.session_state.espn_cache = SessionLeagueCache(ttl_seconds=300)
    if "connection_error" not in st.session_state:
        st.session_state.connection_error = None
    if "mode" not in st.session_state:
        st.session_state.mode = "disconnected"
    if "draft_picks" not in st.session_state:
        st.session_state.draft_picks = []
    if "draft_slot" not in st.session_state:
        st.session_state.draft_slot = None
    if "draft_strategy" not in st.session_state:
        st.session_state.draft_strategy = "balanced"
    if "draft_workspace" not in st.session_state:
        st.session_state.draft_workspace = "My Draft Plan"
    if "draft_setup_confirmed" not in st.session_state:
        st.session_state.draft_setup_confirmed = False
    if "draft_manager_confirmed" not in st.session_state:
        st.session_state.draft_manager_confirmed = False
    if "draft_slot_confirmed" not in st.session_state:
        st.session_state.draft_slot_confirmed = False
    if "draft_manual_started" not in st.session_state:
        st.session_state.draft_manual_started = False
    if "draft_ignored" not in st.session_state:
        st.session_state.draft_ignored = []
    if "draft_paused" not in st.session_state:
        st.session_state.draft_paused = False
    if "draft_last_sync" not in st.session_state:
        st.session_state.draft_last_sync = None
    if "draft_configuration" not in st.session_state:
        st.session_state.draft_configuration = None
    if "draft_league_size" not in st.session_state:
        st.session_state.draft_league_size = None
    if "draft_rounds" not in st.session_state:
        st.session_state.draft_rounds = 16
    if "current_pick" not in st.session_state:
        st.session_state.current_pick = 1
    if "playoff_scenarios" not in st.session_state:
        st.session_state.playoff_scenarios = []
    if "playoff_scenario_history" not in st.session_state:
        st.session_state.playoff_scenario_history = []
    if "last_manual_refresh" not in st.session_state:
        st.session_state.last_manual_refresh = None
    if "last_manual_refresh_epoch" not in st.session_state:
        st.session_state.last_manual_refresh_epoch = 0.0
    if "odds_api_key" not in st.session_state:
        st.session_state.odds_api_key = ""
    if "odds_connection" not in st.session_state:
        st.session_state.odds_connection = None
    if "openweather_api_key" not in st.session_state:
        st.session_state.openweather_api_key = ""
    if "openweather_connection" not in st.session_state:
        st.session_state.openweather_connection = None
    if "decision_journal" not in st.session_state:
        st.session_state.decision_journal = []
    if "my_team_view" not in st.session_state:
        st.session_state.my_team_view = "Set My Lineup"
    # Streamlit preserves widget state across deployments. Remove retired values
    # so an old Draft/Team radio choice cannot hide the current recommendation UI.
    if st.session_state.get("draft_workspace") not in {"My Draft Plan", "Live Draft"}:
        st.session_state.draft_workspace = "My Draft Plan"
    if st.session_state.get("my_team_view") not in {"Set My Lineup", "Waiver Adds", "Trades"}:
        st.session_state.my_team_view = "Set My Lineup"
    if st.session_state.get("league_connected") and isinstance(st.session_state.get("league"), League) and not isinstance(st.session_state.get("active_league"), ActiveLeagueState):
        try:
            st.session_state.active_league = build_active_league_state(st.session_state.league, provider="Manual" if st.session_state.get("mode") == "manual" else "ESPN")
        except ValueError:
            st.session_state.league_connected = False
            st.session_state.connection_error = {"status": "unavailable", "message": "Confirm which ESPN team is yours before using this league."}


def client_fingerprint() -> str:
    try:
        headers = dict(st.context.headers)
    except Exception:
        headers = {}
    return streamlit_client_key(headers)


def action_allowed(bucket: str, limit: int, window: int) -> bool:
    allowed, retry = allow_streamlit_action(client_fingerprint(), bucket, limit, window)
    if not allowed:
        st.error(f"Too many attempts. Wait about {retry} seconds and try again.")
    return allowed


def league_label(league) -> str:
    active = st.session_state.get("active_league")
    if isinstance(active, ActiveLeagueState):
        return f"{active.connection_provider} · {active.connection_status.value.title()}"
    return "Live data"


def pct(value: float) -> str:
    return f"{value:.1%}" if 0 < value < 0.01 or 0.99 < value < 1 else f"{value:.0%}"


def delta(value: float, suffix: str = "") -> str:
    return f"{'+' if value > 0 else ''}{value}{suffix}"


def status_badge(state: str) -> str:
    return badge(str(state), str(state))


def player_label(player) -> str:
    status = "" if player.injury_status in {"HEALTHY", "ACTIVE"} else f" - {player.injury_status}"
    return f"{player.name} ({player.position}, {player.team}){status}"


def safe_draft_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    fields = list(rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@")) else value for key, value in row.items()})
    return output.getvalue()


def canonical_draft_state(league) -> DraftState:
    config = st.session_state.get("draft_configuration") or build_draft_configuration(
        league, league_size=league_team_count(league), draft_slot=int(st.session_state.draft_slot),
        current_overall_pick=int(st.session_state.current_pick), total_rounds=int(st.session_state.draft_rounds),
        manager_count_confirmed=True, draft_slot_confirmed=True,
    )
    config = config.model_copy(update={"current_overall_pick": int(st.session_state.current_pick)})
    selections = []
    for index, pick in enumerate(sorted(st.session_state.draft_picks, key=lambda row: int(row.get("number", 0))), 1):
        number = int(pick.get("number") or index)
        selections.append(DraftSelection(
            overall_pick=number,
            round_number=(number - 1) // config.league_size + 1,
            pick_in_round=(number - 1) % config.league_size + 1,
            owner_slot=int(pick.get("owner_slot") or owner_of_pick(number, config.league_size, config.draft_type)),
            player_id=str(pick["player_id"]),
            player_name=str(pick.get("player_name") or pick["player_id"]),
            position=str(pick.get("position") or "UNKNOWN"),
            source=str(pick.get("source") or "manual"),
        ))
    return DraftState(configuration=config, selections=selections, current_overall_pick=int(st.session_state.current_pick))


def draft_state_rows(state: DraftState) -> list[dict]:
    return [
        {
            "number": item.overall_pick,
            "round": item.round_number,
            "pick_in_round": item.pick_in_round,
            "owner_slot": item.owner_slot,
            "player_id": item.player_id,
            "player_name": item.player_name,
            "position": item.position,
            "recorded_at": item.recorded_at.isoformat(),
            "source": item.source,
        }
        for item in state.selections
    ]


def synced_picks_for_configuration(picks: list[dict], config) -> list[dict]:
    normalized = []
    for pick in sorted(picks, key=lambda row: int(row.get("number", 0))):
        number = int(pick.get("number") or 0)
        if number < 1:
            continue
        owner_slot = owner_of_pick(number, config.league_size, config.draft_type) if config.draft_type != "auction" else 0
        normalized.append({**pick, "number": number, "round": (number - 1) // config.league_size + 1, "pick_in_round": (number - 1) % config.league_size + 1, "owner_slot": owner_slot})
    return normalized


def render_draft_pool_diagnostics(league) -> None:
    diagnostics = league.raw_settings.get("_draft_pool_diagnostics", {})
    if not diagnostics:
        st.error("This session predates draft-pool diagnostics. Disconnect and reconnect the league with season 2026.")
        return
    status = diagnostics.get("status", "UNAVAILABLE")
    raw_count = int(diagnostics.get("raw_player_count", 0) or 0)
    normalized_count = int(diagnostics.get("normalized_player_count", 0) or 0)
    if status == "UNAVAILABLE":
        st.error("The league connected, but all ESPN draft-player requests failed. Your league data was preserved; recommendations are unavailable until ESPN returns the player pool.")
    elif status == "INVALID":
        st.error(f"ESPN returned {raw_count} raw player records, but none could be normalized into supported fantasy players.")
    else:
        st.warning(f"ESPN pool status: {status}. Raw players: {raw_count}; normalized players: {normalized_count}.")
    with st.expander("ESPN draft-pool diagnostics"):
        st.json({"status": status, "raw_player_count": raw_count, "normalized_player_count": normalized_count, "rejected": diagnostics.get("rejected", {}), "attempts": diagnostics.get("attempts", [])})


def render_shell_style() -> None:
    inject_global_styles()


def table_players(players: Iterable) -> list[dict]:
    return [
        {
            "Player": p.name,
            "Pos": p.position,
            "Team": p.team,
            "Baseline": p.mean,
            "Uncertainty": f"+/- {p.stdev:.1f}",
            "Availability": f"{p.availability:.0%}",
            "Status": p.injury_status,
        }
        for p in players
    ]


def table_lineup(result) -> list[dict]:
    return [
        {
            "Slot": e.slot,
            "Player": e.player.name,
            "Pos": e.player.position,
            "Baseline": e.projection.baseline_value,
            "Final": e.projection.mean,
            "Floor": e.projection.floor,
            "Ceiling": e.projection.ceiling,
            "Confidence": pct(e.projection.confidence),
        }
        for e in result.starters
    ]


def lineup_diff_rows(current, recommended) -> list[dict]:
    current_by_slot = {entry.slot: entry for entry in current.starters}
    rows = []
    for entry in recommended.starters:
        old = current_by_slot.get(entry.slot)
        rows.append(
            {
                "Slot": entry.slot,
                "Current Starter": old.player.name if old else "Empty",
                "Recommended Starter": entry.player.name,
                "Expected Diff": round(entry.projection.mean - (old.projection.mean if old else 0), 1),
                "Floor Diff": round(entry.projection.floor - (old.projection.floor if old else 0), 1),
                "Ceiling Diff": round(entry.projection.ceiling - (old.projection.ceiling if old else 0), 1),
            }
        )
    return rows


def get_league_simulation(league, simulations: int = 1000, seed: int = 41, scenarios: list[dict] | None = None):
    key = json.dumps(
        {
            "fingerprint": league_fingerprint(league),
            "simulations": simulations,
            "seed": seed,
            "scenarios": scenarios or [],
        },
        sort_keys=True,
    )
    cache = st.session_state.setdefault("simulation_cache", {})
    if key not in cache:
        constraints = [ScenarioConstraint(**item) for item in (scenarios or [])]
        cache[key] = simulate_league(league, scenarios=constraints, simulations=simulations, seed=seed).model_dump()
    return cache[key]


def sim_rows(result: dict) -> list[dict]:
    return [
        {
            "Team": row["team_name"],
            "Current": f'{row["current_wins"]:.0f}-{row["current_losses"]:.0f}' + (f'-{row["current_ties"]:.0f}' if row["current_ties"] else ""),
            "Exp Wins": row["expected_final_wins"],
            "Median": row["median_final_wins"],
            "Win Range": f'{row["wins_low"]:.1f}-{row["wins_high"]:.1f}',
            "Exp Points": row["expected_final_points"],
            "Likely Seed": row["most_likely_seed"],
            "Playoff": pct(row["playoff_probability"]),
            "MC SE": pct(row["playoff_se"]),
            "Bye": pct(row["bye_probability"]),
            "Title": pct(row["championship_probability"]),
            "Status": row["mathematical_status"],
            "Rem SOS Rank": row["remaining_sos_rank"],
        }
        for row in result["teams"]
    ]


def connect_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 404:
            return "ESPN did not find that league for the selected season. Check the league ID and season."
        if code in {401, 403}:
            return "ESPN denied access. For a private league, refresh both espn_s2 and SWID from the same signed-in ESPN browser session."
        if code == 429:
            return "ESPN is rate-limiting requests. Wait a few minutes and try again."
        return f"ESPN returned HTTP {code}. Try again later."
    if isinstance(exc, httpx.TimeoutException):
        return "ESPN took too long to respond. Try again later."
    if isinstance(exc, httpx.ConnectError):
        return "Fourth Down could not reach ESPN from this runtime."
    if str(exc) == "TEAM_NOT_FOUND":
        return "That team ID was not found in the league."
    if str(exc) == "INCOMPLETE_ESPN_AUTH":
        return "Private league authentication requires both espn_s2 and SWID. Enter both values or leave both blank."
    if str(exc) == "INVALID_ESPN_AUTH":
        return "The ESPN credential value is not valid. Copy fresh espn_s2 and SWID cookie values and try again."
    if str(exc) == "ESPN_AUTH_RESPONSE_INVALID":
        return "ESPN returned a sign-in or non-league response. The cookies are expired, copied from different ESPN sessions, or do not have access to this league. Sign out and back into ESPN, then copy fresh espn_s2 and SWID values from the same browser session."
    if str(exc) == "ESPN_RESPONSE_INVALID":
        return "ESPN returned an unexpected response instead of league data. Confirm the league season and try again."
    if str(exc) == "ESPN_PLAYER_POOL_UNAVAILABLE":
        return "Your league connected, but ESPN's separate draft-player request failed after three safe fallback attempts. Confirm the season is 2026, reconnect, and try again. This is an ESPN player-pool failure—not missing recommendation data."
    if str(exc) == "ESPN_PLAYER_POOL_INVALID":
        return "ESPN returned a malformed draft-player response. Reconnect and try again; Fourth Down did not substitute an empty or invented player pool."
    return "The league could not be connected. Check the league ID, season, team ID, and private-league credentials."


def clear_espn_session() -> None:
    clear_connection_state(st.session_state)
    ensure_state()


def activate_league(
    league: League,
    provider: str,
    sync_context: EspnSyncContext | None = None,
    *,
    league_size: int | None = None,
    league_size_confirmed: bool = False,
    draft_position: int | None = None,
    draft_position_source: str | None = None,
) -> None:
    active = build_active_league_state(
        league,
        provider=provider,
        league_size=league_size,
        league_size_confirmed=league_size_confirmed,
        draft_position=draft_position,
        draft_position_source=draft_position_source,
    )
    st.session_state.league = league
    st.session_state.active_league = active
    st.session_state.espn_connection = sync_context
    st.session_state.league_connected = True
    st.session_state.mode = "live" if provider == "ESPN" else "manual"
    st.session_state.draft_picks = []
    st.session_state.draft_configuration = None
    st.session_state.draft_setup_confirmed = False
    st.session_state.draft_league_size = active.league_size
    st.session_state.draft_manager_confirmed = active.league_size_confirmed
    st.session_state.draft_slot = active.draft_position
    st.session_state.draft_slot_confirmed = active.draft_position_source in {"espn_draft_order", "espn_live_draft"}
    st.session_state.draft_rounds = active.draft_rounds
    st.session_state.current_pick = 1
    st.session_state.simulation_cache = {}
    st.session_state.connection_error = None


async def import_espn_candidate(parsed, credentials: SessionEspnCredentials, *, force: bool = False) -> League:
    cache: SessionLeagueCache = st.session_state.espn_cache
    auth_scope = "private" if credentials.authenticated else "public"
    return await cached_league_connect(
        cache,
        parsed.league_id,
        parsed.season,
        auth_scope,
        lambda: connect_espn(
            parsed.league_id,
            parsed.season,
            espn_s2=credentials.espn_s2,
            espn_swid=credentials.swid,
        ),
        force=force,
    )


async def sync_espn_context(context: EspnSyncContext) -> League:
    cache: SessionLeagueCache = st.session_state.espn_cache
    cache.invalidate(context.league_id, context.season)
    return await connect_with_backoff(
        lambda: connect_espn(
            context.league_id,
            context.season,
            context.team_id,
            espn_s2=context.credentials.espn_s2,
            espn_swid=context.credentials.swid,
        )
    )


def preserve_synced_league(refreshed: League) -> None:
    current = st.session_state.get("active_league")
    st.session_state.league = refreshed
    if isinstance(current, ActiveLeagueState):
        st.session_state.active_league = build_active_league_state(
            refreshed,
            provider=current.connection_provider,
            league_size=current.league_size,
            league_size_confirmed=current.league_size_confirmed,
            draft_position=current.draft_position,
            draft_position_source=current.draft_position_source,
        )


def page_home(league) -> None:
    if not st.session_state.get("league_connected"):
        stadium_hero()
        if st.button("Connect ESPN League", type="primary", use_container_width=True):
            st.session_state.pending_page = "Settings"
            st.rerun()
        warning_state(
            "Private leagues are supported",
            "Paste your ESPN league URL in Settings. A collapsed session-only fallback is available for private leagues; Fourth Down never asks for your ESPN password.",
        )
        return

    page_header(
        "Your Week at a Glance",
        "Home",
        f"{league.name} · Week {league.week}",
        [status_badge(league_label(league))],
    )
    active = st.session_state.get("active_league")
    if isinstance(active, ActiveLeagueState) and active.connection_status == LeagueConnectionStatus.PARTIAL:
        st.warning("We imported your league, but the player pool is temporarily unavailable. Your league connection is still active.")
        if st.button("Retry Player Pool", use_container_width=True, disabled=not isinstance(st.session_state.get("espn_connection"), EspnSyncContext)):
            try:
                with st.spinner("Retrying ESPN player pool…"):
                    preserve_synced_league(asyncio.run(sync_espn_context(st.session_state.espn_connection)))
                st.rerun()
            except Exception as exc:
                _, message = safe_connection_error(exc)
                st.error(message)
    brief = build_weekly_brief(league)
    metric_grid(
        [
            metric_card("Projected Points", fmt_points(brief.expected_score), "Current optimal lineup", "green"),
            metric_card("Win Estimate", fmt_pct(brief.win_probability), brief.matchup_summary, "blue"),
            metric_card("Playoff Odds", fmt_pct(brief.playoff_probability), "Schedule-aware estimate", "purple"),
            metric_card("Best Position", brief.best_position or "Unknown", "Roster strength", "gold"),
        ]
    )
    section_header("Do This Next", "The most useful moves for your team right now.")
    for action in brief.top_actions[:3]:
        action_card(action)
        with st.expander("Why this move"):
            for item in action.reasons:
                st.write(f"- {item}")
            if action.risks:
                st.write(f"Main risk: {action.risks[0]}")
            if action.missing_inputs:
                st.write("Missing inputs:", ", ".join(action.missing_inputs))
    quick_a, quick_b, quick_c, quick_d = st.columns(4)
    for column, label, view in ((quick_a, "Set My Lineup", "Set My Lineup"), (quick_b, "Find a Waiver", "Waiver Adds"), (quick_c, "Make a Trade", "Trades")):
        if column.button(label, type="primary" if label == "Set My Lineup" else "secondary", use_container_width=True):
            st.session_state.my_team_view = view
            st.session_state.pending_page = "My Team"
            st.rerun()
    if quick_d.button("Open Draft", use_container_width=True):
        st.session_state.pending_page = "Draft"
        st.rerun()
    with st.expander("Team summary"):
        st.write(brief.roster_summary)
        st.write(f"Best position: {brief.best_position or 'Unavailable'}")
        st.write(f"Biggest need: {brief.biggest_weakness or 'Unavailable'}")


def page_connect() -> None:
    page_header("Connect Your Fantasy League", "League Setup", "Import your league to personalize draft, lineup, waiver, and trade recommendations.")
    espn_tab, sleeper_tab, manual_tab = st.tabs(["ESPN", "Sleeper", "Manual Setup"])
    with espn_tab:
        section_header("ESPN", "Import league settings, teams, rosters, scoring, and available draft information.")
        st.markdown("**Fourth Down never sees or stores your ESPN password.**")
        st.caption("Fourth Down uses league data in read-only mode and never makes roster changes on your behalf.")
        with st.form("espn-url-connect", clear_on_submit=False):
            league_url = st.text_input("Paste ESPN league URL", placeholder="Open your ESPN league and paste the URL here")
            with st.expander("Private league · advanced session connection"):
                st.warning("Sensitive session values act like passwords. Use this only on a Fourth Down deployment you trust. They remain in this Streamlit session so Sync now can work, and Disconnect ESPN removes them.")
                st.caption("Sign into ESPN normally in this browser first. Fourth Down never asks for your ESPN email or password.")
                espn_s2 = st.text_input("ESPN session value", type="password", key="private-espn-s2")
                swid = st.text_input("ESPN account session value", type="password", key="private-swid")
            connect_clicked = st.form_submit_button("Connect ESPN", type="primary", use_container_width=True)
        if connect_clicked and action_allowed("espn-connect", 6, 300):
            try:
                parsed = parse_espn_league_url(league_url, default_season=datetime.now(UTC).year)
                credentials = SessionEspnCredentials(espn_s2.strip(), swid.strip())
                with st.spinner("Importing league from ESPN…"):
                    candidate = asyncio.run(import_espn_candidate(parsed, credentials))
                st.session_state.espn_candidate = candidate
                st.session_state.espn_candidate_url = parsed
                st.session_state.espn_candidate_credentials = credentials
            except Exception as exc:
                status, message = safe_connection_error(exc)
                st.session_state.connection_error = {"status": status.value, "message": message}
        error = st.session_state.get("connection_error")
        if error:
            st.error(error["message"])
        candidate = st.session_state.get("espn_candidate")
        parsed = st.session_state.get("espn_candidate_url")
        if isinstance(candidate, League) and parsed:
            section_header("Choose Your Team", "ESPN returned this league. Confirm which team is yours before activating it.")
            manager = resolve_manager_count(candidate)
            seat = resolve_draft_slot(candidate)
            selected_team = st.selectbox("Your team", candidate.teams, format_func=lambda team: team.name, key="candidate-team")
            card_league = select_team(candidate, selected_team.id)
            st.markdown(
                f'<div class="fd-league-card"><div class="fd-league-name">{h(card_league.name)}</div>'
                f'<div class="fd-league-meta">{card_league.season} · {manager.value or "Confirm size"} Teams · {h(build_draft_configuration(card_league).scoring_format)} · {h(league_draft_type(card_league).title())} Draft</div>'
                f'<div class="fd-league-team">Your Team: {h(selected_team.name)}</div>'
                f'<div class="fd-league-status">Draft Position: {seat.value if seat.source in {"espn_draft_order", "espn_live_draft"} else "Not Published"}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Use This League", type="primary", use_container_width=True):
                credentials = st.session_state.get("espn_candidate_credentials") or SessionEspnCredentials()
                context = EspnSyncContext(parsed.league_id, parsed.season, selected_team.id, parsed.canonical_url, credentials)
                activate_league(card_league, "ESPN", context)
                st.session_state.pending_page = "Home"
                st.rerun()
        with st.expander("One-click browser connection"):
            st.info("Coming after a dedicated encrypted HTTPS handshake service is deployed and tested. The extension is not active in this Streamlit deployment.")
    with sleeper_tab:
        st.info("Sleeper import is not connected yet. Fourth Down will not pretend a league was imported. Use ESPN or Manual Setup.")
    with manual_tab:
        section_header("Manual Setup", "Use real settings you enter. Manual leagues are always labeled Manual.")
        with st.form("manual-league-setup"):
            name = st.text_input("League name", "My League")
            team_name = st.text_input("Your team name", "My Team")
            a, b, c = st.columns(3)
            size = a.number_input("Managers", 4, 20, 10, 1)
            scoring = b.selectbox("Scoring", ["full PPR", "half PPR", "standard"])
            draft_type = c.selectbox("Draft type", ["snake", "linear", "auction"])
            seat = st.selectbox("Expected draft position", list(range(1, int(size) + 1)), disabled=draft_type == "auction")
            slots_text = st.text_input("Starting roster slots", "QB,RB,RB,WR,WR,TE,FLEX,DST,K")
            bench = st.number_input("Bench players", 0, 20, 7, 1)
            ranking_file = st.file_uploader("Optional rankings CSV", type=["csv"], key="manual-rankings")
            manual_clicked = st.form_submit_button("Use Manual League", type="primary", use_container_width=True)
        if manual_clicked:
            slots = [slot.strip().upper() for slot in slots_text.split(",") if slot.strip().upper() in {"QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "DST", "K"}]
            if not slots:
                st.error("Add at least one valid starting roster slot.")
            else:
                players = []
                try:
                    rows = list(csv.DictReader(io.StringIO(ranking_file.getvalue().decode("utf-8-sig")))) if ranking_file else []
                    for index, row in enumerate(rows[:1500], 1):
                        player_name = str(row.get("player") or row.get("name") or "").strip()[:80]
                        position = str(row.get("position") or "").strip().upper()
                        if not player_name or position not in {"QB", "RB", "WR", "TE", "K", "DST"}: continue
                        projection = float(row["projection"]) if row.get("projection") else None
                        adp = float(row.get("adp") or row.get("rank") or index)
                        players.append(Player(id=f"upload-{index}", name=player_name, position=position, team=str(row.get("team") or "FA")[:5], eligible_slots={position, *({"FLEX"} if position in {"RB", "WR", "TE"} else set())}, mean=max(0, (projection or 0) / 17), stdev=max(.1, (projection or 0) * .02), rostered=False, projection_available=projection is not None, projection_source="User-uploaded rankings", season_projection=projection, average_draft_position=adp, draft_pool_rank=index))
                except (UnicodeDecodeError, ValueError, TypeError):
                    st.error("The rankings CSV could not be read. Numeric ADP and projection fields must contain numbers.")
                    return
                teams = [Team(id=str(index), name=team_name if index == 1 else f"Team {index}", players=[]) for index in range(1, int(size) + 1)]
                reception = 1 if scoring == "full PPR" else .5 if scoring == "half PPR" else 0
                league = League(id="manual-session", name=name[:80], season=datetime.now(UTC).year, week=1, user_team_id="1", roster_slots=slots, teams=teams, free_agents=players, draft_pool=players, raw_settings={"size": int(size), "draftSettings": {"type": draft_type.upper()}, "rosterSettings": {"lineupSlotCounts": {"20": int(bench)}}, "scoringSettings": {"scoringItems": [{"statId": 53, "points": reception}]}, "_manual_setup": True})
                activate_league(league, "Manual", league_size=int(size), league_size_confirmed=True, draft_position=int(seat) if draft_type != "auction" else None, draft_position_source="manual" if draft_type != "auction" else "unavailable")
                st.session_state.pending_page = "Draft"
                st.rerun()


def page_dashboard(league) -> None:
    st.header("Dashboard")
    team = user_team(league)
    lineup = optimize_lineup(team.players, league.roster_slots)
    moves = waiver_moves(league)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Roster", team.name)
    c2.metric("Expected", f"{lineup.expected_score:.1f}")
    c3.metric("Range", f"{lineup.floor:.0f}-{lineup.ceiling:.0f}")
    c4.metric("Top Waiver Gain", delta(moves[0].weekly_gain, " pts") if moves else "None")
    if not lineup.is_complete:
        st.warning(f"Incomplete lineup: missing {', '.join(lineup.missing_slots)}.")
    st.subheader("Current Optimal Lineup")
    st.dataframe(table_lineup(lineup), hide_index=True, use_container_width=True)


def page_lineup(league) -> None:
    section_header("Set My Lineup", "The starters Fourth Down recommends this week.")
    team = user_team(league)
    result = optimize_lineup(team.players, league.roster_slots, style="Balanced", league=league)
    st.success(f"Recommended lineup · {result.expected_score:.1f} projected points")
    st.dataframe(
        [{"Slot": entry.slot, "Start": entry.player.name, "Team": entry.player.team, "Projection": round(entry.projection.mean, 1)} for entry in result.starters],
        hide_index=True, use_container_width=True,
    )
    if result.missing_slots:
        st.warning(f"You still need: {', '.join(result.missing_slots)}")
    with st.expander("Bench and lineup details"):
        if result.bench:
            st.write("Bench: " + " · ".join(player.name for player in result.bench))
        st.write(result.explanation)
        st.caption("Fourth Down does not submit lineup changes to ESPN.")
    return
    section_header("Lineup", "Compare meaningful Conservative, Balanced, and Aggressive starter sets.")
    st.write("Conservative prioritizes floor, Balanced maximizes expected fantasy points, and Aggressive weights ceiling against the current matchup.")
    team = user_team(league)
    baseline = optimize_lineup(team.players, league.roster_slots, style="Balanced", league=league)
    selected_style = st.radio("Risk mode", ["Conservative", "Balanced", "Aggressive"], index=1, horizontal=True)
    result = optimize_lineup(team.players, league.roster_slots, style=selected_style, league=league)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected", f"{result.expected_score:.1f}", delta(result.expected_score - baseline.expected_score, " pts"))
    c2.metric("Floor", f"{result.floor:.1f}", delta(result.floor - baseline.floor, " pts"))
    c3.metric("Ceiling", f"{result.ceiling:.1f}", delta(result.ceiling - baseline.ceiling, " pts"))
    c4.metric("Win Estimate", pct(result.win_probability), percentage_points(result.win_probability - baseline.win_probability))
    st.caption(result.explanation)
    st.dataframe(table_lineup(result), hide_index=True, use_container_width=True)
    if result.missing_slots:
        st.warning(f"Missing slots: {', '.join(result.missing_slots)}")
    with st.expander("Preview recommended changes"):
        st.dataframe(lineup_diff_rows(baseline, result), hide_index=True, use_container_width=True)
        preview = validate_recommendation(
            generate_recommendation(
                "Lineup optimization",
                {"style": "Balanced", "expected_points": baseline.expected_score, "floor": baseline.floor, "ceiling": baseline.ceiling},
                {"style": selected_style, "expected_points": result.expected_score, "floor": result.floor, "ceiling": result.ceiling},
                expected_points_difference=round(result.expected_score - baseline.expected_score, 1),
                floor_difference=round(result.floor - baseline.floor, 1),
                ceiling_difference=round(result.ceiling - baseline.ceiling, 1),
                win_probability_difference=round(result.win_probability - baseline.win_probability, 3),
                reasons=[result.explanation],
                confidence="Medium",
                data_freshness=[league_label(league)],
            )
        )
        preview = require_confirmation(preview, supported_execution=False)
        st.info(f"Preview status: {preview.status}. Streamlit does not submit lineup changes.")
        if st.button("Record this recommendation", use_container_width=True):
            entry = create_decision_entry(
                season=league.season,
                week=league.week,
                league_id=league.id,
                decision_type="Lineup optimization",
                model_version=result.starters[0].projection.model_version if result.starters else "unavailable",
                data_snapshot_id=league_fingerprint(league),
                recommendation={"style": selected_style, "expected_points": result.expected_score},
                alternatives=[{"style": "Balanced", "expected_points": baseline.expected_score}],
                expected_points=result.expected_score,
                floor=result.floor,
                ceiling=result.ceiling,
                confidence=preview.confidence,
                explanation=preview.reasons,
                execution_status=str(preview.status),
            )
            st.session_state.decision_journal.insert(0, entry.to_row())
            st.success("Recommendation recorded in this browser session. No ESPN transaction was submitted.")
    st.subheader("All Risk Modes")
    for style in ("Conservative", "Balanced", "Aggressive"):
        result = optimize_lineup(team.players, league.roster_slots, style=style, league=league)
        with st.expander(style, expanded=style == selected_style):
            c1, c2, c3 = st.columns(3)
            c1.metric("Expected", f"{result.expected_score:.1f}")
            c2.metric("Win Estimate", pct(result.win_probability))
            c3.metric("Complete", "Yes" if result.is_complete else "No")
            st.caption(result.explanation)
            st.dataframe(table_lineup(result), hide_index=True, use_container_width=True)
            if result.missing_slots:
                st.warning(f"Missing slots: {', '.join(result.missing_slots)}")


def page_waivers(league) -> None:
    section_header("Best Waiver Adds", "Who to add, who to drop, and a practical bid.")
    moves = waiver_moves(league)
    if not moves:
        st.info("No waiver move currently improves your roster.")
        return
    best = moves[0]
    st.success(f"ADD {best.add.name} · DROP {best.drop.name}")
    summary_a, summary_b, summary_c = st.columns(3)
    summary_a.metric("Weekly improvement", f"+{best.weekly_gain:.1f} pts")
    summary_b.metric("Suggested FAAB", f"${best.faab_guidance.get('suggested_low', 0)}–${best.faab_guidance.get('suggested_high', 0)}")
    summary_c.metric("Drop safety", str(best.drop_safety).title())
    st.write("**Why**")
    for reason in best.reasons[:3]:
        st.write(f"- {reason}")
    if len(moves) > 1:
        with st.expander("Other waiver options"):
            st.dataframe([{"Add": move.add.name, "Drop": move.drop.name, "Weekly gain": round(move.weekly_gain, 1), "FAAB": f"${move.faab_guidance.get('suggested_low', 0)}–${move.faab_guidance.get('suggested_high', 0)}"} for move in moves[1:8]], hide_index=True, use_container_width=True)
    with st.expander("Risks and details"):
        for risk in best.risks:
            st.write(f"- {risk}")
        st.caption("Recommendations use the connected ESPN free-agent pool and do not submit claims.")
    return
    section_header("Waivers", "Add/drop recommendations with roster impact, drop safety, and value-based FAAB.")
    moves = waiver_moves(league)
    if not moves:
        st.info("No positive legal add/drop move is currently modeled.")
        return
    st.dataframe(
        [
            {
                "Add": m.add.name,
                "Drop": m.drop.name,
                "Weekly Change": m.weekly_gain,
                "ROS VOR Change": m.ros_gain,
                "FAAB Guidance": f'${m.faab_guidance.get("suggested_low", 0)}-${m.faab_guidance.get("suggested_high", 0)}',
                "Drop Safety": m.drop_safety,
                "Confidence": pct(m.confidence),
                "Category": m.category,
            }
            for m in moves
        ],
        hide_index=True,
        use_container_width=True,
    )
    selected = st.selectbox("Inspect recommendation", moves, format_func=lambda m: f"{m.add.name} for {m.drop.name}")
    st.write("Reasons")
    for item in selected.reasons:
        st.write(f"- {item}")
    st.write("Risks and missing information")
    for item in selected.risks:
        st.write(f"- {item}")
    if selected.faab_guidance:
        st.write("FAAB")
        st.json(selected.faab_guidance)


def page_trades(league) -> None:
    section_header("Trades", "Find a deal or rate one you are considering.")
    team = user_team(league)
    opponents = [item for item in league.teams if item.id != team.id]
    if not opponents:
        st.info("No trade partners are available in this league snapshot.")
        return
    mode = st.radio("Trade tool", ["Trades to Consider", "Rate a Trade"], horizontal=True, label_visibility="collapsed")
    if mode == "Trades to Consider":
        ideas = trade_ideas(league)
        if not ideas:
            st.info("No trade currently creates a clear improvement without an unreasonable value gap.")
            return
        for index, idea in enumerate(ideas[:5], 1):
            with st.container(border=True):
                st.write(f"**Trade {index}: Send {', '.join(player.name for player in idea.send)}**")
                st.write(f"Get {', '.join(player.name for player in idea.receive)}")
                st.write(f"Projected weekly change: {idea.weekly_delta:+.1f} points · Verdict: **{idea.verdict}**")
    else:
        partner = st.selectbox("Trade partner", opponents, format_func=lambda item: item.name)
        send = st.multiselect("You send", team.players, format_func=player_label, max_selections=4)
        receive = st.multiselect("You receive", partner.players, format_func=player_label, max_selections=4)
        if st.button("Rate This Trade", type="primary", disabled=not send or not receive, use_container_width=True):
            try:
                result = evaluate_trade(league, [player.id for player in send], [player.id for player in receive], partner.id)
                st.success(result.verdict)
                result_a, result_b = st.columns(2)
                result_a.metric("Weekly change", f"{result.weekly_delta:+.1f} pts")
                result_b.metric("Value balance", "Fair" if result.acceptance_likelihood >= .45 else "Uneven")
                if result.required_drop:
                    st.warning(f"You would also need to drop {result.required_drop.name}.")
                for reason in (result.reasons + result.risks)[:4]:
                    st.write(f"- {reason}")
                with st.expander("How this was rated"):
                    st.write("Fourth Down compares your legal lineup before and after the trade, rest-of-season player value, roster fit, and any required drop. Value balance is not a prediction that the other manager will accept.")
            except ValueError:
                st.error("That trade could not be evaluated. Check the selected players and try again.")
    return
    section_header("Trades", "Evaluate full-roster trade impact, value balance, and required drops.")
    team = user_team(league)
    opponents = [t for t in league.teams if t.id != team.id]
    if not opponents:
        st.info("No trade partners are available in this league snapshot.")
        return
    opponent = st.selectbox("Partner", opponents, format_func=lambda t: f"{t.name} ({t.record})")
    send = st.multiselect("Send", team.players, format_func=player_label, max_selections=4)
    receive = st.multiselect("Receive", opponent.players, format_func=player_label, max_selections=4)
    if st.button("Evaluate", disabled=not send or not receive):
        try:
            result = evaluate_trade(league, [p.id for p in send], [p.id for p in receive], opponent.id)
            c1, c2, c3 = st.columns(3)
            c1.metric("Verdict", result.verdict)
            c2.metric("Weekly Change", delta(result.weekly_delta, " pts"))
            c3.metric("Value Balance", pct(result.acceptance_likelihood))
            st.caption("Value Balance is a heuristic roster-value balance score, not a behavioral acceptance prediction.")
            if result.required_drop:
                st.warning(f"Uneven trade requires dropping {result.required_drop.name}.")
            st.write("Before:", result.before.model_dump())
            st.write("After:", result.after.model_dump())
            for item in result.reasons + result.risks:
                st.write(f"- {item}")
        except ValueError as exc:
            st.error(str(exc))
    ideas = trade_ideas(league)
    if ideas:
        st.subheader("Generated Value-Balance Ideas")
        st.dataframe(
            [
                {
                    "Send": ", ".join(p.name for p in i.send),
                    "Receive": ", ".join(p.name for p in i.receive),
                    "Weekly Change": i.weekly_delta,
                    "Verdict": i.verdict,
                    "Value Balance": pct(i.acceptance_likelihood),
                }
                for i in ideas
            ],
            hide_index=True,
            use_container_width=True,
        )


def page_draft(league) -> None:
    st.header("Draft Assistant")
    mode = st.radio("Mode", ["balanced", "safe", "ceiling"], horizontal=True)
    board = draft_board(league, mode)
    drafted = {p["player_id"] for p in st.session_state.draft_picks}
    board = [rec for rec in board if rec.player.id not in drafted]
    st.caption("Availability at next pick is a heuristic score, not trained from ADP distributions.")
    st.dataframe(
        [
            {
                "Rank": r.rank,
                "Player": r.player.name,
                "Pos": r.player.position,
                "VOR": r.vor,
                "Scarcity": r.scarcity,
                "Heuristic Availability": pct(r.survival_probability),
                "Fit": r.roster_fit,
                "Risk": r.risk,
            }
            for r in board
        ],
        hide_index=True,
        use_container_width=True,
    )
    if board:
        pick = st.selectbox("Mark drafted in this session", board, format_func=lambda r: player_label(r.player))
        if st.button("Add draft pick"):
            st.session_state.draft_picks.append({"player_id": pick.player.id, "team_id": league.user_team_id})
            st.rerun()


def draft_settings_from_state(league) -> DraftSettings:
    config = st.session_state.get("draft_configuration")
    league_size = config.league_size if config else league_team_count(league)
    current_pick = max(1, int(st.session_state.current_pick))
    draft_slot = min(max(1, int(st.session_state.draft_slot or 1)), league_size)
    st.session_state.current_pick = current_pick
    st.session_state.draft_slot = draft_slot
    draft_type = config.draft_type if config else league_draft_type(league)
    if draft_type == "snake":
        next_pick = snake_next_pick(current_pick, draft_slot, league_size)
    else:
        current_slot = ((current_pick - 1) % league_size) + 1
        distance = (draft_slot - current_slot) % league_size
        next_pick = current_pick + (distance or league_size)
    return DraftSettings(league_size=league_size, current_pick=current_pick, next_pick=next_pick, draft_type=draft_type)


def page_draft_intelligence(league) -> None:
    section_header("2. My Draft Plan", "Realistic targets at every pick you own. Future availability is estimated, never promised.")
    settings = draft_settings_from_state(league)
    drafted = {pick["player_id"] for pick in st.session_state.draft_picks}
    board = DEFAULT_DRAFT_SERVICE.current_board(league, settings, drafted)
    draft_type = league_draft_type(league)
    if draft_type == "auction":
        st.info("Auction drafts do not have round-owned picks. Live Draft will rank nominations after you start it.")
        return
    plan = DEFAULT_DRAFT_SERVICE.overall_pick_plan(league, int(st.session_state.draft_slot), rounds=min(30, int(st.session_state.draft_rounds)), strategy=st.session_state.draft_strategy, draft_type=draft_type, league_size=settings.league_size)
    if not board:
        pool = league.draft_pool or league.free_agents
        if not pool:
            st.warning("ESPN has not returned a usable player pool yet. Reconnect or try again shortly.")
        else:
            st.warning("A real player pool was returned, but there is not enough legitimate ranking information to build a plan.")
        return
    st.caption("Targets are recalculated after each planned selection. They are possibilities, not guarantees.")
    index = 0
    while index < len(plan):
        row = plan[index]
        next_row = plan[index + 1] if index + 1 < len(plan) else None
        consecutive = next_row and next_row["overall_pick"] == row["overall_pick"] + 1
        if consecutive:
            pair_settings = DraftSettings(league_size=settings.league_size, current_pick=row["overall_pick"], next_pick=next_row["overall_pick"], draft_type="snake")
            pairs = DEFAULT_DRAFT_SERVICE.turn_pair_plan(league, pair_settings, int(st.session_state.draft_slot), set(), [], st.session_state.draft_strategy)
            st.subheader(f"ROUNDS {row['round']}–{next_row['round']} · PICKS {row['overall_pick']} AND {next_row['overall_pick']}")
            if pairs:
                best_pair = pairs[0]
                st.write(f"**Best combination:** {best_pair['first']['player_name']} ({best_pair['first']['position']}) + {best_pair['second']['player_name']} ({best_pair['second']['position']})")
                for alternative in pairs[1:3]:
                    st.write(f"Alternative: {alternative['first']['player_name']} + {alternative['second']['player_name']}")
            index += 2
            continue
        st.subheader(f"ROUND {row['round']} · PICK {row['overall_pick']}")
        st.write("**Primary targets**")
        for target_index, target in enumerate(row.get("primary_targets", []), 1):
            st.write(f"{target_index}. **{target['player_name']}** · {target['position']} · {target['team']} · Fourth Down #{target['fourth_down_rank']} · ADP {target['consensus_adp']} · Tier {target['tier']} · {target['availability_label']}")
            st.caption(target["recommendation_reason"])
        backups = row.get("backup_targets", [])
        if backups:
            st.write("**Backups:** " + " · ".join(f"{target['player_name']} ({target['position']})" for target in backups))
        st.write("**Plan:** " + row.get("instruction", "Take the strongest remaining tier that fits your roster."))
        index += 1
    with st.expander("Advanced methodology and data status"):
        st.write("Fourth Down combines league scoring, roster fit, market cost, projection value, tier scarcity, injury risk, and risk of waiting. ESPN ADP is a market input—not the recommendation by itself.")
        diagnostics = league.raw_settings.get("_draft_pool_diagnostics", {})
        st.write(f"Player pool: {diagnostics.get('normalized_player_count', len(league.draft_pool))} players · Status: {diagnostics.get('status', 'available')}")


def page_draft_room(league) -> None:
    section_header("3. Live Draft", "The recommendation updates after every recorded or ESPN-synced selection.")
    config = st.session_state.get("draft_configuration")
    espn_picks = list(league.raw_settings.get("_draft_picks", []))
    live_started = bool(espn_picks or st.session_state.get("draft_picks") or st.session_state.get("draft_manual_started"))
    if not live_started:
        st.info("Waiting for your ESPN draft to begin.")
        st.write(f"Your setup is ready: **{config.league_size} teams · {config.draft_type.title()} · Seat {config.draft_slot or 'N/A'}**")
        check, manual = st.columns(2)
        if check.button("Check Draft Status", type="primary", use_container_width=True):
            connection = st.session_state.get("espn_connection")
            if not connection:
                st.warning("Reconnect the league once to enable ESPN draft checks. Manual mode is still available.")
            elif action_allowed("espn-draft-sync", 20, 300):
                try:
                    refreshed = asyncio.run(sync_espn_context(connection))
                    picks = synced_picks_for_configuration(list(refreshed.raw_settings.get("_draft_picks", [])), config)
                    preserve_synced_league(refreshed)
                    st.session_state.draft_last_sync = datetime.now(UTC).isoformat()
                    if picks:
                        st.session_state.draft_picks = picks
                        st.session_state.current_pick = max(int(pick["number"]) for pick in picks) + 1
                        st.session_state.draft_ignored = []
                        st.rerun()
                    st.info("ESPN has not published a completed pick yet.")
                except Exception:
                    st.warning("ESPN draft status could not be refreshed. Your setup and any manual picks are unchanged.")
        if manual.button("Start Manual Live Draft", use_container_width=True):
            st.session_state.draft_manual_started = True
            st.session_state.current_pick = 1
            st.rerun()
        with st.expander("How ESPN synchronization works"):
            st.write("Fourth Down refreshes only when you press the button. ESPN’s unofficial fantasy endpoints do not provide a guaranteed real-time event stream, so the app does not claim second-by-second sync.")
        return

    if st.session_state.get("draft_paused"):
        st.warning("Draft paused. Recommendations and pick entry are frozen.")
        if st.button("Resume Draft", type="primary"):
            st.session_state.draft_paused = False
            st.rerun()
        return
    refresh_a, refresh_b = st.columns([1, 2])
    if refresh_a.button("Refresh ESPN Picks", use_container_width=True):
        connection = st.session_state.get("espn_connection")
        if not connection:
            refresh_b.warning("This manual draft has no ESPN refresh connection.")
        elif action_allowed("espn-draft-sync", 20, 300):
            try:
                refreshed = asyncio.run(sync_espn_context(connection))
                picks = synced_picks_for_configuration(list(refreshed.raw_settings.get("_draft_picks", [])), config)
                preserve_synced_league(refreshed)
                st.session_state.draft_last_sync = datetime.now(UTC).isoformat()
                if picks:
                    st.session_state.draft_picks = picks
                    st.session_state.current_pick = max(int(pick["number"]) for pick in picks) + 1
                    st.session_state.draft_ignored = []
                    st.rerun()
                refresh_b.info("ESPN returned no completed selections. Existing manual picks were preserved.")
            except Exception:
                refresh_b.warning("ESPN refresh failed. Existing picks and recommendations were preserved.")
    current_pick = max(1, int(st.session_state.current_pick))
    league_size = config.league_size
    draft_type = config.draft_type
    round_number = (current_pick - 1) // league_size + 1
    pick_in_round = (current_pick - 1) % league_size + 1
    owner_slot = owner_of_pick(current_pick, league_size, draft_type) if draft_type != "auction" else 0
    next_user_pick = config.user_owned_picks[0] if config.user_owned_picks else None
    if draft_type != "auction":
        next_user_pick = next((pick for pick in config.user_owned_picks if pick >= current_pick), None)
    drafted_ids = {str(pick["player_id"]) for pick in st.session_state.draft_picks}
    ignored_ids = set(st.session_state.get("draft_ignored", []))
    user_positions = [str(pick.get("position", "UNKNOWN")) for pick in st.session_state.draft_picks if int(pick.get("owner_slot") or 0) == int(config.draft_slot or 0)]
    next_after = next((pick for pick in config.user_owned_picks if pick > current_pick), current_pick + league_size)
    settings = DraftSettings(league_size=league_size, current_pick=current_pick, next_pick=next_after, draft_type=draft_type)
    recommendations = DEFAULT_DRAFT_SERVICE.pick_plan(league, settings, drafted_ids | ignored_ids, user_positions, backup_count=3, strategy=st.session_state.draft_strategy, recent_drafted_positions=[pick.get("position", "UNKNOWN") for pick in st.session_state.draft_picks])
    on_clock = draft_type == "auction" or owner_slot == config.draft_slot
    if on_clock:
        st.success(f"YOU’RE ON THE CLOCK · Round {round_number} · Pick {current_pick}")
    else:
        away = max(0, int(next_user_pick or current_pick) - current_pick)
        st.subheader(f"PICK {current_pick} · TEAM {owner_slot} ON THE CLOCK")
        st.write(f"**Your next pick:** Pick {next_user_pick} · {away} selection{'s' if away != 1 else ''} away")
    if recommendations:
        best, backups = recommendations[0], recommendations[1:4]
        heading = "DRAFT" if on_clock else "CURRENT PLAN"
        st.subheader(f"{heading} {best['player_name']}")
        st.write(f"**{best['position']} · {best['team']} · Tier {best['tier']}**")
        st.write("**Why**")
        reasons = [part.strip().capitalize() for part in best["recommendation_reason"].rstrip(".").split(";")][:3]
        for reason in reasons:
            st.write(f"- {reason}")
        if backups:
            st.write("**Backups**")
            for index, player in enumerate(backups, 1):
                st.write(f"{index}. {player['player_name']} · {player['position']} · {player['availability_label']}")
        if on_clock:
            action_a, action_b, action_c = st.columns(3)
            if action_a.button("Drafted", type="primary", use_container_width=True):
                state = canonical_draft_state(league).record(DraftSelection(overall_pick=current_pick, round_number=round_number, pick_in_round=pick_in_round, owner_slot=owner_slot, player_id=best["player_id"], player_name=best["player_name"], position=best["position"], source="manual"))
                st.session_state.draft_picks = draft_state_rows(state)
                st.session_state.current_pick = state.current_overall_pick
                st.session_state.draft_ignored = []
                st.rerun()
            if action_b.button("Ignore for this pick", use_container_width=True):
                st.session_state.draft_ignored = [*ignored_ids, best["player_id"]]
                st.rerun()
            with action_c.expander("View alternatives"):
                for player in backups:
                    st.write(f"{player['player_name']} · {player['position']} · Tier {player['tier']}")
    else:
        st.warning("No legitimate recommendation is available from the remaining player data.")

    board = DEFAULT_DRAFT_SERVICE.current_board(league, settings, drafted_ids)
    if board:
        selected = st.selectbox("Player drafted", board, format_func=lambda row: f"{row['player_name']} · {row['position']} · {row['team']}")
        if st.button("Record Pick", use_container_width=True):
            state = canonical_draft_state(league).record(DraftSelection(overall_pick=current_pick, round_number=round_number, pick_in_round=pick_in_round, owner_slot=owner_slot, player_id=selected["player_id"], player_name=selected["player_name"], position=selected["position"], source="manual"))
            st.session_state.draft_picks = draft_state_rows(state)
            st.session_state.current_pick = state.current_overall_pick
            st.session_state.draft_ignored = []
            st.rerun()
    controls = st.columns(4)
    if controls[0].button("Undo last pick", disabled=not st.session_state.draft_picks):
        state = canonical_draft_state(league).undo()
        st.session_state.draft_picks = draft_state_rows(state)
        st.session_state.current_pick = state.current_overall_pick
        st.session_state.draft_ignored = []
        st.rerun()
    if controls[1].button("Pause draft"):
        st.session_state.draft_paused = True
        st.rerun()
    with controls[2].popover("Correct pick"):
        if st.session_state.draft_picks and board:
            correction_pick = st.selectbox("Recorded pick", st.session_state.draft_picks, format_func=lambda pick: f"Pick {pick['number']}: {pick.get('player_name')}")
            correction_player = st.selectbox("Correct player", board, format_func=lambda row: f"{row['player_name']} · {row['position']}")
            if st.button("Save correction"):
                number = int(correction_pick["number"])
                replacement = DraftSelection(overall_pick=number, round_number=(number - 1) // league_size + 1, pick_in_round=(number - 1) % league_size + 1, owner_slot=int(correction_pick["owner_slot"]), player_id=correction_player["player_id"], player_name=correction_player["player_name"], position=correction_player["position"], source="manual-correction")
                state = canonical_draft_state(league).correct(number, replacement)
                st.session_state.draft_picks = draft_state_rows(state)
                st.rerun()
    with controls[3].popover("Reset draft"):
        reset_confirmed = st.checkbox("I understand this removes every recorded pick")
        if st.button("Reset now", disabled=not reset_confirmed):
            state = canonical_draft_state(league).reset(confirmed=True)
            st.session_state.draft_picks = draft_state_rows(state)
            st.session_state.current_pick = 1
            st.session_state.draft_manual_started = False
            st.session_state.draft_ignored = []
            st.rerun()
    if st.session_state.get("draft_last_sync"):
        st.caption(f"Last successful ESPN refresh: {st.session_state.draft_last_sync}. Manual refresh only.")
    with st.expander("Why this recommendation? Advanced details"):
        if recommendations:
            best = recommendations[0]
            st.write(f"Fourth Down rank: {best['fourth_down_rank']} · ADP: {best['consensus_adp']} · Value over replacement: {best.get('expected_vor', 'Unavailable')} · Risk of waiting: {best.get('cost_of_waiting', 0):.1f}")
        st.write("The engine weighs league-adjusted value, roster fit, tier scarcity, market cost, injury risk, and likely alternatives at your next pick.")
    return

    section_header("Who Should I Draft?", "A live pick-by-pick answer using your draft slot, roster construction, ESPN projections, ADP, and value over replacement.")
    league_size = league_team_count(league)
    sync_a, sync_b = st.columns([1, 2])
    if sync_a.button("Sync ESPN draft now", type="primary", use_container_width=True):
        connection = st.session_state.get("espn_connection")
        if not connection:
            sync_b.error("Reconnect the league once so this session can securely refresh ESPN draft picks.")
        elif action_allowed("espn-draft-sync", 20, 300):
            try:
                with st.spinner("Loading the latest ESPN selections..."):
                    refreshed = asyncio.run(sync_espn_context(connection))
                espn_picks = list(refreshed.raw_settings.get("_draft_picks", []))
                preserve_synced_league(refreshed)
                if espn_picks:
                    st.session_state.draft_picks = espn_picks
                    st.session_state.current_pick = max(pick["number"] for pick in espn_picks) + 1
                    st.session_state.draft_sync_message = f"Synced {len(espn_picks)} ESPN picks. Recommendations recalculated for overall pick {st.session_state.current_pick}."
                else:
                    st.session_state.draft_sync_message = "ESPN has not published any completed draft picks yet. Your manually recorded picks were kept."
                st.rerun()
            except Exception as exc:
                sync_b.error(connect_error(exc))
    if st.session_state.get("draft_sync_message"):
        sync_b.success(st.session_state.pop("draft_sync_message"))
    st.session_state.current_pick = st.number_input("Current overall pick", min_value=1, max_value=300, value=int(st.session_state.current_pick), step=1)
    user_team = next((team for team in league.teams if team.id == league.user_team_id), None)
    existing_roster = [player.position for player in user_team.players] if user_team else []
    count_existing = st.toggle(
        "Count my current ESPN roster as keepers",
        value=False,
        help="Turn this on only if those players will remain on your roster for this draft. Leave it off for a normal redraft league.",
    )
    settings = draft_settings_from_state(league)
    current_pick = int(st.session_state.current_pick)
    round_index = (current_pick - 1) // league_size
    pick_in_round = ((current_pick - 1) % league_size) + 1
    draft_type = league_draft_type(league)
    owner_slot = owner_of_pick(current_pick, league_size, draft_type) if draft_type != "auction" else 0
    if draft_type == "auction":
        st.warning("ESPN reports an auction/salary-cap draft. Pick ownership and snake turns do not apply; recommendations are ranked nominations and values, not an overall-pick sequence.")
    drafted_ids = {pick["player_id"] for pick in st.session_state.draft_picks}
    user_positions = [pick["position"] for pick in st.session_state.draft_picks if pick.get("owner_slot") == int(st.session_state.draft_slot)]
    if count_existing:
        user_positions = existing_roster + user_positions
        if user_team:
            drafted_ids.update(player.id for player in user_team.players)
    recent_positions = [pick.get("position", "UNKNOWN") for pick in st.session_state.draft_picks]
    insights = DEFAULT_DRAFT_SERVICE.draft_insights(league, settings, drafted_ids, user_positions, strategy=st.session_state.draft_strategy, recent_drafted_positions=recent_positions)
    plan = insights["best"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Round", round_index + 1, f"Pick {pick_in_round}")
    c2.metric("Overall pick", current_pick, "Auction nomination" if draft_type == "auction" else "You are on the clock" if owner_slot == int(st.session_state.draft_slot) else f"Seat {owner_slot} on clock")
    c3.metric("Your draft seat", f"{int(st.session_state.draft_slot)} of {league_size}")
    next_user_pick = current_pick if owner_slot == int(st.session_state.draft_slot) else settings.next_pick
    if draft_type == "auction":
        c4.metric("Next owned pick", "N/A", "Auctions have nominations, not owned picks")
    else:
        c4.metric("Next owned pick", next_user_pick, f"{max(0, next_user_pick - current_pick)} selections away")
    if draft_type == "snake" and owner_slot == int(st.session_state.draft_slot):
        following_pick = snake_next_pick(current_pick, int(st.session_state.draft_slot), league_size)
        st.caption(f"After this selection, you pick again at overall {following_pick}." + (" You are on the snake turn and will pick twice in a row." if following_pick == current_pick + 1 else ""))
        if following_pick == current_pick + 1:
            pairs = DEFAULT_DRAFT_SERVICE.turn_pair_plan(league, settings, int(st.session_state.draft_slot), drafted_ids, user_positions, strategy=st.session_state.draft_strategy)
            if pairs:
                st.subheader(f"Optimize picks {current_pick} + {following_pick} together")
                st.dataframe(
                    [{"Plan": index + 1, "First pick": row["first"]["player_name"], "Second pick": row["second"]["player_name"], "Positions": f'{row["first"]["position"]} + {row["second"]["position"]}', "Why": f'{row["first"]["availability_label"]} / {row["second"]["availability_label"]} next-pick availability'} for index, row in enumerate(pairs)],
                    hide_index=True,
                    use_container_width=True,
                )
    if plan:
        best = plan[0]
        if owner_slot == int(st.session_state.draft_slot):
            st.success(f"DRAFT {best['player_name']} — {best['position']}, {best['team']}")
        else:
            st.info(f"Current top target for your next pick: {best['player_name']} ({best['position']}, {best['team']})")
        st.caption(best["recommendation_reason"] + " This is a decision estimate from live ESPN inputs, not a guarantee.")
        best_value = max(plan, key=lambda row: row.get("adp_relative_value") or 0)
        tier_priority = max(plan, key=lambda row: row.get("cost_of_waiting") or 0)
        safer = min(plan, key=lambda row: (row.get("injury_status") not in {"ACTIVE", "HEALTHY"}, row.get("season_projection") is None, row.get("consensus_adp", 9999)))
        upside = max(plan, key=lambda row: (row.get("expected_vor") or 0, row.get("adp_relative_value") or 0))
        wait_candidate = max(plan, key=lambda row: row.get("availability_probability") or 0)
        alt_a, alt_b, alt_c, alt_d = st.columns(4)
        alt_a.metric("Best value", best_value["player_name"], f"ADP value {best_value['adp_relative_value']:+.0f}")
        alt_b.metric("Tier priority", tier_priority["player_name"], f"Wait cost {tier_priority['cost_of_waiting']:.1f}")
        alt_c.metric("Safer choice", safer["player_name"], safer.get("injury_status", "ACTIVE"))
        alt_d.metric("Upside choice", upside["player_name"], f"VOR {upside.get('expected_vor') or 0:.1f}")
        st.caption(f"Likely safer to wait on: {wait_candidate['player_name']} · {wait_candidate['availability_label']} heuristic availability at pick {settings.next_pick}.")
        st.subheader("What your roster needs next")
        st.dataframe(
            [{"Position": row["position"], "Have": row["filled"], "Starter target": row["target"], "Need": row["gap"], "Status": row["priority"]} for row in insights["needs"]],
            hide_index=True,
            use_container_width=True,
        )
        pick_tab, sleeper_tab, strong_tab = st.tabs(["Best picks & backups", "Sleepers", "Strong players"])
        with pick_tab:
            st.dataframe(
                [{"Order": index + 1, "Player": row["player_name"], "Pos": row["position"], "Team": row["team"], "ESPN ADP/rank": row["consensus_adp"], "Projection": row["season_projection"], "VOR": row["expected_vor"], "Tier": row["tier"], "Tier left": row["players_remaining_in_tier"], "Next-pick availability": row["availability_label"], "Wait cost": row["cost_of_waiting"], "Why": row["recommendation_reason"]} for index, row in enumerate(plan)],
                hide_index=True,
                use_container_width=True,
            )
        with sleeper_tab:
            if insights["sleepers"]:
                st.caption("Sleeper = available later than this pick, positive VOR, and materially better projection value than ESPN ADP implies. It is not a guarantee of a breakout.")
                st.dataframe(
                    [{"Player": row["player_name"], "Pos": row["position"], "Team": row["team"], "ESPN ADP": row["consensus_adp"], "Projection": row["season_projection"], "VOR": row["expected_vor"], "ADP value": row["adp_relative_value"]} for row in insights["sleepers"]],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No remaining player meets the live sleeper threshold right now. Fourth Down will not invent one.")
        with strong_tab:
            st.caption("Strong players are the remaining players with the highest projected value over the league-specific replacement level, regardless of your immediate roster need.")
            st.dataframe(
                [{"Player": row["player_name"], "Pos": row["position"], "Team": row["team"], "Projection": row["season_projection"], "VOR": row["expected_vor"], "ESPN ADP": row["consensus_adp"], "Tier": row["tier"]} for row in insights["strong"]],
                hide_index=True,
                use_container_width=True,
            )
    else:
        pool = league.draft_pool or league.free_agents
        if not pool:
            render_draft_pool_diagnostics(league)
        else:
            st.info(f"No recommendation is available from the {len(pool)} normalized ESPN draft-pool players because the remaining players lack ADP, draft rank, season projection, and ownership signals.")
    board = DEFAULT_DRAFT_SERVICE.current_board(league, settings, drafted_ids)
    if board:
        pick = st.selectbox("Player selected at this overall pick", board, format_func=lambda row: f"{row['player_name']} ({row['position']}, {row['team']})")
        if st.button("Record selected player", type="primary", use_container_width=True):
            state = canonical_draft_state(league)
            try:
                state = state.record(DraftSelection(
                    overall_pick=current_pick,
                    round_number=round_index + 1,
                    pick_in_round=pick_in_round,
                    owner_slot=owner_slot,
                    player_id=pick["player_id"],
                    player_name=pick["player_name"],
                    position=pick["position"],
                    source="manual",
                ))
                st.session_state.draft_picks = draft_state_rows(state)
                st.session_state.current_pick = state.current_overall_pick
                st.rerun()
            except ValueError as exc:
                st.error("That player was already selected." if str(exc) == "PLAYER_ALREADY_DRAFTED" else "The selection was out of sequence. Sync or reset the draft state and try again.")
    c1, c2, c3 = st.columns(3)
    if c1.button("Undo last pick", disabled=not st.session_state.draft_picks):
        state = canonical_draft_state(league).undo()
        st.session_state.draft_picks = draft_state_rows(state)
        st.session_state.current_pick = state.current_overall_pick
        st.rerun()
    confirm_reset = c2.checkbox("Confirm reset", value=False)
    if c2.button("Reset draft", disabled=not confirm_reset):
        st.session_state.draft_picks = []
        st.session_state.current_pick = 1
        st.rerun()
    c3.download_button("Export draft CSV", data=safe_draft_csv(st.session_state.draft_picks), file_name="fourth-down-draft.csv", mime="text/csv")
    st.dataframe(st.session_state.draft_picks, hide_index=True, use_container_width=True)


def page_historical_draft_explorer() -> None:
    st.header("Historical Draft Explorer")
    path = ROOT / "data" / "processed" / "draft_dataset.csv"
    if not path.exists():
        st.warning("Draft dataset has not been built. Run `python scripts/build_draft_dataset.py`.")
        return
    import csv
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    positions = ["ALL"] + sorted({row["position"] for row in rows})
    position = st.selectbox("Position", positions)
    filtered = [row for row in rows if position == "ALL" or row["position"] == position]
    st.dataframe(filtered, hide_index=True, use_container_width=True)
    st.download_button("Download filtered CSV", data="\n".join([",".join(row.values()) for row in filtered]), file_name="draft-history.csv", mime="text/csv")


def page_draft_model_performance() -> None:
    section_header("Draft Evaluation", "Fixture evaluation only; not production accuracy.")
    path = ROOT / "models" / "draft" / "latest" / "evaluation.json"
    card = ROOT / "docs" / "DRAFT_MODEL_CARD.md"
    if path.exists():
        st.json(json.loads(path.read_text(encoding="utf-8")))
        st.caption("Fixture evaluation only; not production accuracy.")
    else:
        st.warning("No draft evaluation artifact found.")
    if card.exists():
        st.markdown(card.read_text(encoding="utf-8"))


def page_market_movement() -> None:
    st.header("Market Movement")
    st.warning("Production current ADP snapshots are not configured. Fixture ADP has no genuine movement history, so risers/fallers are disabled.")
    path = ROOT / "data" / "raw" / "current_adp_refresh_report.json"
    if path.exists():
        st.json(json.loads(path.read_text(encoding="utf-8")))


def page_player_research(league) -> None:
    section_header("Player Detail", "Projection provenance, missing inputs, and player-specific context.")
    players = [p for t in league.teams for p in t.players] + league.free_agents
    selected = st.selectbox("Player", players, format_func=player_label)
    data = player_research(league, selected.id)
    projection = data["projection"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Baseline", projection.baseline_value)
    c2.metric("Final", projection.mean)
    c3.metric("Range", f"{projection.floor}-{projection.ceiling}")
    c4.metric("Confidence", pct(projection.confidence))
    st.subheader("Projection Provenance")
    st.write(f"Baseline source: {projection.baseline_source}")
    st.dataframe(projection.adjustments, hide_index=True, use_container_width=True)
    st.write("Missing inputs:", ", ".join(projection.missing) if projection.missing else "None")
    st.info(data["historical_note"])
    for item in projection.reasons + projection.limitations:
        st.write(f"- {item}")


def page_projection_lab(league) -> None:
    st.header("Projection Details")
    st.caption("Phase 2 model artifacts are loaded from trusted repository JSON files. Streamlit never trains models during reruns.")
    players = [p for t in league.teams for p in t.players if p.position in SUPPORTED_MODEL_POSITIONS] + [p for p in league.free_agents if p.position in SUPPORTED_MODEL_POSITIONS]
    if not players:
        st.info("No QB/RB/WR/TE players are available in this league snapshot.")
        return
    selected = st.selectbox("Player", players, format_func=player_label, key="projection_lab_player")
    projection = DEFAULT_PROJECTION_SERVICE.project_player(selected, league=league, week=league.week)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected", projection.mean)
    c2.metric("Median", projection.median)
    c3.metric("Interval", f"{projection.floor} to {projection.ceiling}")
    c4.metric("Fallback", "Yes" if projection.fallback_used else "No")
    st.write(f"Model: `{projection.model_name}` `{projection.model_version}`")
    st.write(f"Training cutoff: {projection.training_cutoff or 'Unavailable'}")
    st.write(f"Interval label: {projection.uncertainty_label}")
    st.write(f"Baseline: {projection.baseline_source} ({projection.baseline_value})")
    if projection.important_features:
        st.subheader("Important Inputs")
        st.dataframe(projection.important_features, hide_index=True, use_container_width=True)
    st.write("Missing inputs:", ", ".join(projection.missing) if projection.missing else "None")
    for item in projection.limitations:
        st.write(f"- {item}")

    st.subheader("Model Policy")
    st.json(TRAINING_POLICY)
    evaluation_path = ROOT / "models" / "projections" / "latest" / "evaluation.json"
    if evaluation_path.exists():
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        st.subheader("Fixture Evaluation")
        st.caption("Generated from the committed deterministic fixture dataset; this validates architecture and is not a production accuracy claim.")
        st.dataframe([{"Position": pos, **values} for pos, values in sorted(evaluation.items())], hide_index=True, use_container_width=True)
    else:
        st.warning("No evaluation artifact was found. The app will continue using labeled fallback projections.")


def page_rankings(league) -> None:
    st.header("Power Rankings")
    st.caption("Team strength is separated from resume and future outlook. Playoff odds use the normalized remaining schedule when available.")
    result = get_league_simulation(league, simulations=1000, seed=43)
    distributions = {row["team_id"]: row for row in result["score_distributions"]}
    metrics = {row["team_id"]: row for row in result["schedule_metrics"]}
    rows = []
    for row in result["teams"]:
        dist = distributions[row["team_id"]]
        metric = metrics.get(row["team_id"], {})
        strength = dist["expected_score"]
        resume = metric.get("all_play_win_pct", 0) * 100
        outlook = row["playoff_probability"] * 100
        composite = 0.5 * strength + 0.25 * resume + 0.25 * outlook
        rows.append({"Team": row["team_name"], "Strength": round(strength, 1), "Resume": round(resume, 1), "Future Outlook": round(outlook, 1), "Composite": round(composite, 1), "Tier": "A" if composite >= 95 else "B" if composite >= 82 else "C", "Method": "50% projected lineup strength, 25% all-play resume, 25% playoff outlook"})
    rows.sort(key=lambda item: item["Composite"], reverse=True)
    st.dataframe([{**row, "Rank": idx + 1} for idx, row in enumerate(rows)], hide_index=True, use_container_width=True)
    st.caption("Small score differences should not be treated as meaningful. Correlation modeling remains limited and is disclosed in Simulation Methodology.")


def page_league_outlook(league) -> None:
    st.header("League Outlook")
    simulations = st.slider("Simulations", 250, 5000, 1000, step=250)
    seed = st.number_input("Random seed", min_value=1, max_value=9999, value=41, step=1)
    result = get_league_simulation(league, simulations=int(simulations), seed=int(seed))
    c1, c2, c3 = st.columns(3)
    c1.metric("Simulations", f'{result["simulations"]:,}')
    c2.metric("Model", result["model_version"])
    c3.metric("Schedule Matchups", len(league.schedule))
    st.dataframe(
        sim_rows(result),
        hide_index=True,
        use_container_width=True,
    )
    if result["warnings"]:
        st.warning(" ".join(result["warnings"]))
    st.subheader("Score Distributions")
    st.dataframe(
        [
            {
                "Team": row["team_name"],
                "Expected": row["expected_score"],
                "Median": row["median_score"],
                "Lower": row["lower_estimate"],
                "Upper": row["upper_estimate"],
                "Stdev": row["score_stdev"],
                "Completeness": pct(row["data_completeness"]),
                "Fallback Starters": ", ".join(row["fallback_projections"]) if row["fallback_projections"] else "None",
            }
            for row in result["score_distributions"]
        ],
        hide_index=True,
        use_container_width=True,
    )


def page_standings(league) -> None:
    st.header("Standings Outlook")
    st.caption("Projected final standings use the normalized actual remaining schedule where available and supported record/points-for tiebreaking.")
    result = get_league_simulation(league, simulations=250, seed=41)
    st.dataframe(sim_rows(result), hide_index=True, use_container_width=True)


def page_playoff_machine(league) -> None:
    section_header("Playoff Scenarios", "Lock remaining matchup outcomes and compare conditional playoff outlooks.")
    st.caption("Lock deterministic outcomes for unresolved matchups. Scenario state is stored only in this Streamlit session.")
    future = [m for m in league.schedule if not m.is_complete and m.period <= league.rules.regular_season_end]
    team_names = {team.id: team.name for team in league.teams}
    if not future:
        st.info("No unresolved regular-season matchups are available in this league snapshot.")
        return
    matchup = st.selectbox("Matchup", future, format_func=lambda m: f"Week {m.period}: {team_names.get(m.home_team_id, m.home_team_id)} vs {team_names.get(m.away_team_id, m.away_team_id)}")
    choices = {
        "Leave unresolved": None,
        f"{team_names.get(matchup.home_team_id, matchup.home_team_id)} wins": matchup.home_team_id,
        f"{team_names.get(matchup.away_team_id, matchup.away_team_id)} wins": matchup.away_team_id,
        "Tie": "TIE",
    }
    selected = st.radio("Outcome", list(choices), horizontal=True)
    use_scores = st.checkbox("Set hypothetical scores")
    home_score = away_score = None
    if use_scores:
        home_score = st.number_input("Home score", min_value=0.0, max_value=300.0, value=110.0, step=0.5)
        away_score = st.number_input("Away score", min_value=0.0, max_value=300.0, value=105.0, step=0.5)
    if st.button("Apply scenario"):
        current = list(st.session_state.playoff_scenarios)
        st.session_state.playoff_scenario_history.append(current)
        current = [item for item in current if item["matchup_id"] != matchup.id]
        if choices[selected]:
            current.append({"matchup_id": matchup.id, "winner_team_id": choices[selected], "home_score": home_score, "away_score": away_score})
        st.session_state.playoff_scenarios = current
        st.session_state.simulation_cache = {}
        st.rerun()
    c1, c2, c3 = st.columns(3)
    if c1.button("Undo last change", disabled=not st.session_state.playoff_scenario_history):
        st.session_state.playoff_scenarios = st.session_state.playoff_scenario_history.pop()
        st.session_state.simulation_cache = {}
        st.rerun()
    if c2.button("Reset scenario"):
        st.session_state.playoff_scenarios = []
        st.session_state.playoff_scenario_history = []
        st.session_state.simulation_cache = {}
        st.rerun()
    scenario_rows = []
    for item in st.session_state.playoff_scenarios:
        m = next(match for match in future if match.id == item["matchup_id"])
        winner = item["winner_team_id"]
        scenario_rows.append({"Week": m.period, "Matchup": f"{team_names.get(m.home_team_id)} vs {team_names.get(m.away_team_id)}", "Locked Outcome": "Tie" if winner == "TIE" else f"{team_names.get(winner)} wins", "Scores": f'{item.get("home_score")} - {item.get("away_score")}' if item.get("home_score") is not None else "Not set"})
    st.dataframe(scenario_rows, hide_index=True, use_container_width=True)
    baseline = get_league_simulation(league, simulations=1000, seed=51)
    try:
        scenario = get_league_simulation(league, simulations=1000, seed=51, scenarios=st.session_state.playoff_scenarios)
    except ValueError as exc:
        st.error(str(exc))
        return
    comparison = []
    base_by_team = {row["team_id"]: row for row in baseline["teams"]}
    for row in scenario["teams"]:
        base = base_by_team[row["team_id"]]
        comparison.append({"Team": row["team_name"], "Baseline Playoff": pct(base["playoff_probability"]), "Scenario Playoff": pct(row["playoff_probability"]), "Change": f'{(row["playoff_probability"] - base["playoff_probability"]) * 100:+.1f} pts', "Baseline Title": pct(base["championship_probability"]), "Scenario Title": pct(row["championship_probability"])})
    st.subheader("Scenario Comparison")
    st.dataframe(comparison, hide_index=True, use_container_width=True)
    c3.download_button("Export scenario JSON", data=json.dumps(scenario, indent=2), file_name="fourth-down-scenario.json", mime="application/json")


def page_schedule_analysis(league) -> None:
    section_header("Schedule Context", "All-play record, expected wins, schedule luck, and opponent strength.")
    result = get_league_simulation(league, simulations=1000, seed=61)
    st.caption("Schedule luck is defined as actual wins minus all-play expected wins. This is descriptive, not proof of manager skill or causation.")
    st.dataframe(
        [
            {
                "Team": row["team_name"],
                "Actual Wins": row["actual_wins"],
                "All-Play": f'{row["all_play_wins"]:.0f}-{row["all_play_losses"]:.0f}-{row["all_play_ties"]:.0f}',
                "All-Play Win %": pct(row["all_play_win_pct"]),
                "All-Play Exp Wins": row["all_play_expected_wins"],
                "Schedule Luck": row["schedule_luck"],
                "PA vs Avg": row["points_against_vs_average"],
                "Completed SOS": row["completed_sos"],
                "Remaining SOS": row["remaining_sos"],
                "Top-Half Losses": row["top_half_losses"],
                "Bottom-Half Wins": row["bottom_half_wins"],
            }
            for row in result["schedule_metrics"]
        ],
        hide_index=True,
        use_container_width=True,
    )


def page_team_detail(league) -> None:
    st.header("Team Detail")
    result = get_league_simulation(league, simulations=1000, seed=71)
    teams_by_id = {team.id: team for team in league.teams}
    selected = st.selectbox("Team", result["teams"], format_func=lambda row: row["team_name"])
    dist = next(row for row in result["score_distributions"] if row["team_id"] == selected["team_id"])
    metric = next(row for row in result["schedule_metrics"] if row["team_id"] == selected["team_id"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Playoff", pct(selected["playoff_probability"]))
    c2.metric("Title", pct(selected["championship_probability"]))
    c3.metric("Expected Wins", selected["expected_final_wins"])
    c4.metric("Schedule Luck", metric["schedule_luck"])
    st.write(f"Mathematical status: {selected['mathematical_status']}")
    st.subheader("Starting Lineup Distribution")
    st.write(f"Expected {dist['expected_score']} with heuristic interval {dist['lower_estimate']} to {dist['upper_estimate']}.")
    st.write("Starters:", ", ".join(dist["starters"]))
    st.subheader("Remaining Opponents")
    rows = []
    for matchup in league.schedule:
        if matchup.is_complete or selected["team_id"] not in {matchup.home_team_id, matchup.away_team_id}:
            continue
        opponent_id = matchup.away_team_id if matchup.home_team_id == selected["team_id"] else matchup.home_team_id
        rows.append({"Week": matchup.period, "Opponent": teams_by_id.get(opponent_id).name if opponent_id in teams_by_id else opponent_id, "Current": "Yes" if matchup.is_current else "No"})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.subheader("Seed Distribution")
    st.dataframe([{"Seed": seed, "Probability": pct(prob)} for seed, prob in selected["seed_distribution"].items()], hide_index=True, use_container_width=True)


def page_simulation_methodology(league) -> None:
    st.header("Simulation Methodology")
    result = get_league_simulation(league, simulations=250, seed=81)
    st.write("- Completed matchup outcomes and current standings are treated as known facts.")
    st.write("- Unresolved regular-season matchups are simulated against the actual normalized ESPN/demo schedule.")
    st.write("- Current live partial scoring is not mixed with full projections; current week is treated as pregame-only unless final.")
    st.write("- Team score distributions are built from legal optimized lineups and aggregated variance, not by summing player floors and ceilings.")
    st.write("- Player correlations are not claimed as empirical in Phase 4. A heuristic team-level variance term is disclosed instead.")
    st.write("- Standings and playoff seeding use supported record plus points-for tiebreaking. Unsupported or ambiguous rules are shown as limitations.")
    st.write("- Monte Carlo standard error shown beside probabilities describes simulation sampling uncertainty only, not projection or structural model error.")
    st.write("- Clinch and elimination status uses small exact enumeration when possible; finite Monte Carlo 0% or 100% is never treated as proof.")
    st.write("Assumptions")
    for item in result["assumptions"] + result["warnings"]:
        st.write(f"- {item}")
    if league.rules.raw:
        st.subheader("Raw ESPN Schedule Settings")
        st.json(league.rules.raw)


def page_my_team(league) -> None:
    page_header("My Team", "Decisions", "Set your lineup, improve through waivers, or evaluate a trade.", [status_badge(league_label(league))])
    choice = st.radio("Choose a decision", ["Set My Lineup", "Waiver Adds", "Trades"], key="my_team_view", horizontal=True, label_visibility="collapsed")
    if choice == "Set My Lineup":
        page_lineup(league)
    elif choice == "Waiver Adds":
        page_waivers(league)
    else:
        page_trades(league)


def page_players(league) -> None:
    page_header("Players", "Player Lookup", "Search a player and get the useful answer first.", [status_badge(league_label(league))])
    players = [p for t in league.teams for p in t.players] + league.free_agents
    query = st.text_input("Search player or NFL team", value="", placeholder="Search by name or team")
    filtered = [p for p in players if not query or query.lower() in p.name.lower() or query.lower() in p.team.lower()]
    selected = st.selectbox("Player", filtered or players, format_func=player_label)
    data = player_research(league, selected.id)
    projection = data["projection"]
    st.markdown(player_card(selected, projection), unsafe_allow_html=True)
    team = user_team(league)
    lineup = optimize_lineup(team.players, league.roster_slots, league=league)
    starter_ids = {entry.player.id for entry in lineup.starters}
    waiver = next((move for move in waiver_moves(league) if move.add.id == selected.id), None)
    if selected.id in starter_ids:
        decision = "START"
        explanation = "Fourth Down currently places this player in your best legal lineup."
    elif waiver:
        decision = "ADD"
        explanation = f"Add {selected.name} and drop {waiver.drop.name}; projected weekly improvement {waiver.weekly_gain:+.1f} points."
    elif selected.rostered:
        decision = "BENCH / HOLD"
        explanation = "This player is on your roster but does not make the recommended starting lineup right now."
    else:
        decision = "WATCH"
        explanation = "This player is available, but no positive add/drop move currently ranks high enough."
    st.subheader(decision)
    st.write(explanation)
    metric_grid([
        metric_card("Week projection", fmt_points(projection.final_projection or projection.mean), "Current estimate", "green"),
        metric_card("Expected range", f"{fmt_points(projection.floor)}–{fmt_points(projection.ceiling)}", "Floor to ceiling", "blue"),
        metric_card("Status", selected.injury_status.title(), selected.team, "gold"),
    ])
    with st.expander("Projection and data details"):
        st.write(f"Projection source: {projection.baseline_source}")
        st.write(f"Role: {data['role']}")
        if projection.reasons:
            for reason in projection.reasons[:4]:
                st.write(f"- {reason}")
        if projection.missing:
            st.caption("Unavailable inputs: " + ", ".join(projection.missing))


def page_league(league) -> None:
    page_header("League", "Standings", "See where you stand and what remains.", [status_badge(league_label(league))])
    result = get_league_simulation(league, simulations=1000, seed=41)
    mine = next((row for row in result["teams"] if row["team_id"] == league.user_team_id), None)
    team = user_team(league)
    if mine:
        metric_grid([
            metric_card("Record", team.record, "Current ESPN record", "blue"),
            metric_card("Playoff outlook", pct(mine["playoff_probability"]), "Schedule-aware estimate", "green"),
            metric_card("Likely seed", mine["most_likely_seed"], "Most common simulated finish", "gold"),
            metric_card("Remaining schedule", f"#{mine['remaining_sos_rank']}", "Difficulty rank", "orange"),
        ])
    section_header("League Standings", "Current record and a concise rest-of-season outlook.")
    st.dataframe([
        {"Team": row["team_name"], "Record": f"{row['current_wins']:.0f}-{row['current_losses']:.0f}", "Projected wins": row["expected_final_wins"], "Playoff outlook": pct(row["playoff_probability"]), "Likely seed": row["most_likely_seed"]}
        for row in result["teams"]
    ], hide_index=True, use_container_width=True)
    with st.expander("Explore playoff scenarios"):
        page_playoff_machine(league)
    with st.expander("How the outlook is calculated"):
        st.write("The outlook uses your current standings, connected schedule, and projected legal lineups. It is directional—not a guarantee.")
        if result.get("warnings"):
            for warning in result["warnings"]:
                st.write(f"- {warning}")


def page_draft_context(league) -> None:
    page_header("Draft", "Draft Assistant", "Plan each round before the draft, then get one clear answer while you are on the clock.", [status_badge(league_label(league))])
    active = st.session_state.get("active_league")
    manager_value = active.league_size if isinstance(active, ActiveLeagueState) else st.session_state.get("draft_league_size")
    manager_confirmed = active.league_size_confirmed if isinstance(active, ActiveLeagueState) else bool(st.session_state.get("draft_manager_confirmed"))
    seat_value = active.draft_position if isinstance(active, ActiveLeagueState) else st.session_state.get("draft_slot")
    seat_manual = isinstance(active, ActiveLeagueState) and active.draft_position_source == "manual"
    manager_resolution = resolve_manager_count(league, manager_value, manual_confirmed=manager_confirmed)
    seat_resolution = resolve_draft_slot(league, seat_value, manual_confirmed=seat_manual)
    if not st.session_state.get("draft_setup_confirmed"):
        section_header("1. Draft Setup", "Confirm the facts that control every pick and recommendation.")
        if manager_resolution.conflict_values:
            st.warning(manager_resolution.message + " Confirm the correct draft size below.")
        elif manager_resolution.message:
            st.info(manager_resolution.message)
        if seat_resolution.source == "unavailable":
            st.info("ESPN has not published your draft order yet. Select your expected draft seat for planning. You can change this later.")
        team = next((item for item in league.teams if item.id == league.user_team_id), None)
        default_size = int(st.session_state.get("draft_league_size") or manager_resolution.value or max(4, len(league.teams)))
        default_slot = min(default_size, max(1, int(st.session_state.get("draft_slot") or seat_resolution.value or 1)))
        settings = league.raw_settings if isinstance(league.raw_settings, dict) else {}
        counts = (settings.get("rosterSettings") or {}).get("lineupSlotCounts") or {}
        defaults = {slot: league.roster_slots.count(slot) for slot in ("QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "DST", "K")}
        default_bench = int(counts.get("20", counts.get(20, 7)) or 7)
        with st.form("draft-setup"):
            a, b, c = st.columns(3)
            if manager_resolution.conflict_values:
                manager_choice = a.radio("Confirm the correct draft size", [*[str(value) for value in manager_resolution.conflict_values], "Custom"])
                managers = a.number_input("Custom manager count", 4, 20, default_size, 1, disabled=manager_choice != "Custom") if manager_choice == "Custom" else int(manager_choice)
            else:
                managers = a.number_input("Number of managers", 4, 20, default_size, 1)
            espn_type = league_draft_type(league)
            draft_type = b.selectbox("Draft type", ["snake", "linear", "auction"], index=["snake", "linear", "auction"].index(espn_type))
            seat = c.selectbox("Your draft seat", list(range(1, int(managers) + 1)), index=min(default_slot, int(managers)) - 1, disabled=draft_type == "auction")
            d, e, f = st.columns(3)
            detected_scoring = build_draft_configuration(league, league_size=int(managers)).scoring_format
            scoring = d.selectbox("Scoring format", ["full PPR", "half PPR", "standard"], index=["full PPR", "half PPR", "standard"].index(detected_scoring))
            bench = e.number_input("Bench players", 0, 20, default_bench, 1)
            rounds = f.number_input("Draft rounds", 1, 30, max(1, len(league.roster_slots) + default_bench), 1)
            st.caption("Starters")
            slot_columns = st.columns(4)
            slot_counts = {}
            for index, slot_name in enumerate(("QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "DST", "K")):
                slot_counts[slot_name] = slot_columns[index % 4].number_input(slot_name, 0, 5, int(defaults.get(slot_name, 0)), 1, key=f"setup-{slot_name}")
            pool = league.draft_pool or league.free_agents
            keepers = st.multiselect("Keepers (optional)", pool, format_func=lambda player: f"{player.name} · {player.position}")
            st.caption(f"Your team: {(team.name if team else 'Selected ESPN team')} · Your draft seat: {seat if draft_type != 'auction' else 'Not applicable'} of {managers}")
            confirmed = st.form_submit_button("Confirm Draft Setup", type="primary", use_container_width=True)
        if confirmed:
            starting_slots = [slot for slot, count in slot_counts.items() for _ in range(int(count))]
            config = build_draft_configuration(
                league, league_size=int(managers), draft_slot=int(seat) if draft_type != "auction" else None,
                total_rounds=int(rounds), keeper_player_ids={player.id for player in keepers}, manager_count_confirmed=True,
                draft_slot_confirmed=True, draft_type=draft_type, scoring_format=scoring, starting_slots=starting_slots, bench_slots=int(bench),
            )
            st.session_state.draft_configuration = config
            st.session_state.draft_league_size = int(managers)
            st.session_state.draft_slot = int(seat) if draft_type != "auction" else None
            st.session_state.draft_rounds = int(rounds)
            st.session_state.draft_manager_confirmed = True
            st.session_state.draft_slot_confirmed = True
            if isinstance(active, ActiveLeagueState):
                st.session_state.active_league = active.model_copy(update={
                    "league_size": int(managers), "league_size_source": "manual", "league_size_confirmed": True,
                    "draft_position": int(seat) if draft_type != "auction" else None,
                    "draft_position_source": active.draft_position_source if active.draft_order_published and int(seat) == active.draft_position else "manual" if draft_type != "auction" else "unavailable",
                    "draft_order_published": active.draft_order_published,
                    "scoring_format": scoring, "roster_slots": starting_slots, "draft_type": draft_type, "draft_rounds": int(rounds),
                })
            st.session_state.draft_setup_confirmed = True
            st.session_state.draft_workspace = "My Draft Plan"
            st.session_state.draft_picks = []
            st.session_state.current_pick = 1
            st.session_state.draft_ignored = []
            st.rerun()
        return

    config = st.session_state.draft_configuration
    team = next((item for item in league.teams if item.id == league.user_team_id), None)
    st.success(f"YOUR DRAFT · {config.league_size}-team {config.draft_type} · Seat {config.draft_slot or 'N/A'} · {config.scoring_format}")
    slot_summary = " · ".join(f"{config.starting_slots.count(slot)} {slot}" for slot in dict.fromkeys(config.starting_slots)) or "None"
    st.caption(f"Your team: {team.name if team else 'Selected ESPN team'} · Starters: {slot_summary} · Bench: {config.bench_slots} · Keepers: {len(config.keeper_player_ids)}")
    if st.button("Edit Draft Setup"):
        st.session_state.draft_setup_confirmed = False
        st.session_state.draft_picks = []
        st.session_state.current_pick = 1
        st.session_state.draft_ignored = []
        st.rerun()
    configured_settings = dict(league.raw_settings)
    configured_settings["size"] = config.league_size
    league = league.model_copy(update={"raw_settings": configured_settings, "roster_slots": config.starting_slots})
    workspace = st.radio("Draft", ["My Draft Plan", "Live Draft"], key="draft_workspace", horizontal=True, label_visibility="collapsed")
    if workspace == "My Draft Plan":
        page_draft_intelligence(league)
    else:
        page_draft_room(league)


def page_settings(league) -> None:
    if not st.session_state.get("league_connected"):
        page_header(
            "Connect ESPN",
            "Live Setup",
            "Connect a public or private ESPN league before opening the decision workspace.",
            [status_badge("NOT CONNECTED")],
        )
        page_connect()
        return
    page_header("Settings", "Account & Data", "Manage your league connection, optional data keys, and session privacy.", [status_badge(league_label(league))])
    connection_tab, data_tab, privacy_tab = st.tabs(["League Connection", "Optional Data", "Privacy"])
    with connection_tab:
        team = user_team(league)
        st.success(f"Connected to {league.name}")
        st.write(f"Team: **{team.name}** · Season {league.season} · Week {league.week}")
        active = st.session_state.get("active_league")
        if isinstance(active, ActiveLeagueState):
            st.caption(f"Last synchronized {active.last_synced_at.astimezone().strftime('%b %d, %Y · %I:%M %p')}")
            if active.connection_status == LeagueConnectionStatus.EXPIRED:
                st.error(active.sync_message)
                if st.button("Reconnect ESPN", use_container_width=True):
                    clear_espn_session()
                    st.rerun()
        sync_col, disconnect_col = st.columns(2)
        if sync_col.button("Sync now", type="primary", use_container_width=True, disabled=not isinstance(st.session_state.get("espn_connection"), EspnSyncContext)):
            if action_allowed("espn-sync", 12, 300):
                try:
                    with st.spinner("Synchronizing with ESPN…"):
                        refreshed = asyncio.run(sync_espn_context(st.session_state.espn_connection))
                    preserve_synced_league(refreshed)
                    st.success("League synchronized.")
                    st.rerun()
                except Exception as exc:
                    status, message = safe_connection_error(exc)
                    if isinstance(active, ActiveLeagueState):
                        st.session_state.active_league = active.model_copy(update={"connection_status": status, "sync_message": message})
                    st.error(message)
        if disconnect_col.button("Disconnect ESPN" if st.session_state.get("mode") == "live" else "Disconnect League", use_container_width=True):
            clear_espn_session()
            st.rerun()
        with st.expander("Connect a different league"):
            page_connect()
        with st.expander("League details"):
            st.write(f"Roster: {', '.join(league.roster_slots)}")
            st.write(f"Playoff teams: {league.playoff_team_count}")
    with data_tab:
        st.write("Optional keys stay in this browser session and are removed when you disconnect or reset.")
        with st.form("simple-odds-key", clear_on_submit=True):
            odds_key = st.text_input("The Odds API key", type="password", help="Optional NFL market context.")
            use_odds = st.form_submit_button("Validate Odds Key")
        if use_odds:
            if action_allowed("odds-key-validation", 5, 300):
                try:
                    result = asyncio.run(validate_odds_key(odds_key))
                    if result.get("valid"):
                        st.session_state.odds_api_key = odds_key.strip()
                        st.session_state.odds_connection = result
                        st.success("Odds key connected for this session.")
                    else:
                        st.error("The Odds API rejected that key. Check it and try again.")
                except httpx.HTTPError:
                    st.error("The Odds API could not be reached. The key was not saved.")
        with st.form("simple-weather-key", clear_on_submit=True):
            weather_key = st.text_input("OpenWeather key", type="password", help="Optional weather-provider validation.")
            use_weather = st.form_submit_button("Validate Weather Key")
        if use_weather:
            if action_allowed("openweather-key-validation", 5, 600):
                try:
                    result = asyncio.run(validate_openweather_key(weather_key))
                    if result.get("valid"):
                        st.session_state.openweather_api_key = weather_key.strip()
                        st.session_state.openweather_connection = result
                        st.success("Weather key connected for this session.")
                    else:
                        st.error("OpenWeather rejected that key. Check it and try again.")
                except httpx.HTTPError:
                    st.error("OpenWeather could not be reached. The key was not saved.")
        if st.session_state.get("odds_api_key") or st.session_state.get("openweather_api_key"):
            if st.button("Remove Optional Keys"):
                st.session_state.odds_api_key = ""
                st.session_state.odds_connection = None
                st.session_state.openweather_api_key = ""
                st.session_state.openweather_connection = None
                st.rerun()
        with st.expander("Data status"):
            page_data_sources(league)
    with privacy_tab:
        st.subheader("Your private data stays session-only")
        st.write("- Fourth Down never asks for your ESPN password.")
        st.write("- Private-league cookies and optional API keys are not saved to the repository or database.")
        st.write("- The public app does not persist your league, draft, or decisions between Streamlit sessions.")
        st.write("- Fourth Down never submits lineups, waivers, trades, or draft picks to ESPN.")
        with st.expander("Technical security details"):
            page_privacy()
        confirm_reset = st.checkbox("I understand this clears my current Fourth Down session")
        if st.button("Reset Session", disabled=not confirm_reset):
            for key in list(st.session_state.keys()):
                st.session_state.pop(key, None)
            st.rerun()
    return
    page_header("Settings", "Operations", "Connection, data freshness, privacy, evaluation, and launch-readiness controls.", [status_badge(league_label(league))])
    st.caption("Connection, data freshness, privacy, strategy, and technical limits.")
    summary = health_summary(league)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("App Version", summary["app_version"])
    c2.metric("Mode", summary["mode"])
    c3.metric("Season / Week", f'{summary["season"]} / {summary["week"]}')
    c4.metric("Projection Model", summary["projection_model_version"])
    tabs = st.tabs(["Connection", "League Settings", "Health", "Data Freshness", "Methodology", "Privacy", "Evaluation", "Feedback"])
    with tabs[0]:
        page_connect()
    with tabs[1]:
        st.write(f"Selected league: **{league.name}**")
        st.write(f"Selected team: **{user_team(league).name}**")
        st.write(f"Roster slots: {', '.join(league.roster_slots)}")
        st.write(f"Playoff teams: {league.playoff_team_count}")
        st.write(f"Tiebreaker assumption: {league.rules.tiebreaker}")
        if league.rules.unsupported:
            st.warning(" ".join(league.rules.unsupported))
    with tabs[2]:
        st.subheader("Operational Summary")
        st.write(f"Training cutoff: {summary['training_cutoff'] or 'Unavailable'}")
        st.write(f"Checked at: {summary['checked_at']}")
        st.write("Degraded features")
        for item in summary["degraded_features"]:
            st.write(f"- {item}")
        with st.expander("Configuration classification"):
            st.dataframe(summary["config"], hide_index=True, use_container_width=True)
        with st.expander("Graceful degradation matrix"):
            st.dataframe(DEGRADATION_MATRIX, hide_index=True, use_container_width=True)
        with st.expander("Performance budgets"):
            st.dataframe(PERFORMANCE_BUDGETS, hide_index=True, use_container_width=True)
        warnings = validate_config(CONFIG)
        if warnings:
            st.warning(" ".join(warnings))
    with tabs[3]:
        page_data_sources(league)
        st.subheader("The Odds API")
        st.write("Add your own key for this browser session. It is password-masked, never written to `.env`, SQLite, logs, exports, or the connected league.")
        with st.form("odds_api_connection", clear_on_submit=True):
            odds_key = st.text_input("Odds API key", type="password", value="")
            validate_key = st.form_submit_button("Validate and use key")
        if validate_key:
            if not action_allowed("odds-key-validation", 5, 300):
                return
            try:
                result = asyncio.run(validate_odds_key(odds_key))
                if result.get("valid"):
                    st.session_state.odds_api_key = odds_key.strip()
                    st.session_state.odds_connection = result
                    st.success("Odds API key validated for this session.")
                else:
                    st.error(result.get("error", "The key could not be validated."))
            except httpx.HTTPError:
                st.error("The Odds API could not be reached. The key was not saved; try again later.")
        if st.session_state.odds_api_key:
            status = st.session_state.odds_connection or {}
            st.success(f"Session key connected. Remaining credits reported: {status.get('remaining_requests') or 'unknown'}.")
            c_odds1, c_odds2 = st.columns(2)
            if c_odds1.button("Refresh live NFL odds", use_container_width=True):
                if not action_allowed("odds-refresh", 4, 900):
                    return
                try:
                    with st.spinner("Loading live NFL totals, spreads, and moneylines..."):
                        odds_result = asyncio.run(refresh_odds(force=True, api_key=st.session_state.odds_api_key))
                    st.session_state.odds_connection = odds_result
                    st.success(f"Live NFL odds loaded. Request cost: {odds_result.get('request_cost') or 'unknown'}; remaining: {odds_result.get('remaining_requests') or 'unknown'}.")
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {401, 403}:
                        st.error("The Odds API rejected the key. Remove it and paste a current key.")
                    elif exc.response.status_code == 429:
                        st.error("The Odds API quota or rate limit has been reached. Wait for the provider reset.")
                    else:
                        st.error("The Odds API returned an error. No invented market data was used.")
                except httpx.HTTPError:
                    st.error("The Odds API could not be reached. Existing cached odds, if any, were left unchanged.")
            if c_odds2.button("Remove session key", use_container_width=True):
                st.session_state.odds_api_key = ""
                st.session_state.odds_connection = None
                st.rerun()
            odds_snapshot = st.session_state.get("odds_connection") or {}
            games = odds_snapshot.get("payload") if odds_snapshot.get("status") == "LIVE" else []
            if games:
                st.subheader("Current NFL market snapshot")
                st.dataframe(
                    [
                        {
                            "Matchup": f"{game.get('away_team', 'Unknown')} at {game.get('home_team', 'Unknown')}",
                            "Kickoff": game.get("commence_time", "Unknown"),
                            "Books": len(game.get("bookmakers", [])),
                            "Markets": ", ".join(sorted({market.get("key", "") for book in game.get("bookmakers", []) for market in book.get("markets", []) if market.get("key")})),
                        }
                        for game in games
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
        st.caption("Key validation uses the provider's sports endpoint. Refreshing NFL totals, spreads, and moneylines consumes provider credits; a 15-minute refresh guard prevents accidental repeated calls.")
        st.subheader("OpenWeather")
        st.write("Optional session-only key for weather-provider validation. Fourth Down will not apply weather to a projection until the game location and kickoff forecast are matched.")
        with st.form("openweather_api_connection", clear_on_submit=True):
            weather_key = st.text_input("OpenWeather API key", type="password", value="")
            validate_weather = st.form_submit_button("Validate OpenWeather key")
        if validate_weather:
            if not action_allowed("openweather-key-validation", 5, 600):
                return
            try:
                weather_result = asyncio.run(validate_openweather_key(weather_key))
                if weather_result.get("valid"):
                    st.session_state.openweather_api_key = weather_key.strip()
                    st.session_state.openweather_connection = weather_result
                    st.success("OpenWeather key validated for this session.")
                else:
                    st.error(weather_result.get("error", "The key could not be validated."))
            except httpx.HTTPError:
                st.error("OpenWeather could not be reached. The key was not saved; try again later.")
        if st.session_state.openweather_api_key:
            weather_status = st.session_state.openweather_connection or {}
            st.success(f"OpenWeather connected for this session. Validation location: {weather_status.get('sample_station', 'available')}.")
            if st.button("Remove OpenWeather session key", use_container_width=True):
                st.session_state.openweather_api_key = ""
                st.session_state.openweather_connection = None
                st.rerun()
        st.subheader("Manual Refresh")
        st.write("Streamlit Community Cloud is not treated as a durable background worker. Refreshes are manual, cooldown-protected, and session-local.")
        if st.session_state.last_manual_refresh:
            st.caption(f"Last manual refresh: {st.session_state.last_manual_refresh}")
        if st.button("Refresh provider status", use_container_width=True):
            import time
            from datetime import UTC, datetime

            now = time.time()
            if now - float(st.session_state.last_manual_refresh_epoch or 0) < 60:
                st.warning("Refresh cooldown is active. Wait at least 60 seconds before trying again.")
            else:
                st.session_state.last_manual_refresh_epoch = now
                st.session_state.last_manual_refresh = datetime.now(UTC).isoformat()
                st.success("Provider status refreshed for this session. No duplicate background job was started.")
    with tabs[4]:
        page_methodology()
        with st.expander("Simulation details"):
            page_simulation_methodology(league)
    with tabs[5]:
        page_privacy()
        st.subheader("Security posture")
        security_rows = [
            {"Control": "ESPN credentials", "Status": "Session only", "Details": "Password-masked; sent only to ESPN; never stored in SQLite, URL, logs, or exports."},
            {"Control": "Provider API keys", "Status": "Session only", "Details": "Password-masked; outbound provider use only; removed on disconnect/reset."},
            {"Control": "RLS", "Status": "Not applicable", "Details": "The public Streamlit app does not persist per-user records in a shared database. SQLite is blocked in multi-user mode."},
            {"Control": "Rate limits", "Status": "Enabled", "Details": "Process-wide pseudonymous limits protect ESPN connection and provider validation/refresh actions."},
            {"Control": "XSRF / CORS", "Status": "Enabled", "Details": "Streamlit XSRF and CORS protections are enabled in deployment configuration."},
            {"Control": "AI endpoints", "Status": "Protected / unused", "Details": "FastAPI AI route is limited to 10 requests/minute; the Streamlit product uses no LLM endpoint."},
            {"Control": "Demo data", "Status": "Disabled", "Details": "Live ESPN connection required; missing provider inputs stay unavailable."},
        ]
        st.dataframe(security_rows, hide_index=True, use_container_width=True)
        st.subheader("Session Reset")
        st.write("Reset clears Streamlit session state for league, draft, scenarios, selections, and private derived results. It does not remove data from ESPN or other providers.")
        if st.button("Reset this Streamlit session"):
            for key in ["league", "espn_connection", "mode", "draft_picks", "draft_strategy", "draft_league_size", "draft_rounds", "playoff_scenarios", "playoff_scenario_history", "simulation_cache", "draft_slot", "current_pick", "odds_api_key", "odds_connection", "openweather_api_key", "openweather_connection", "decision_journal"]:
                st.session_state.pop(key, None)
            st.rerun()
    with tabs[6]:
        page_trust()
        st.subheader("Prediction Ledger Evaluation")
        st.info("Real accuracy reporting remains unavailable until this browser session contains enough pre-game predictions and final outcomes. Shared SQLite evaluation is disabled on the public app.")
        st.subheader("Decision Journal")
        rows = list(st.session_state.get("decision_journal", []))
        if rows:
            st.dataframe(
                [
                    {
                        "Created": row["created_at"],
                        "Type": row["decision_type"],
                        "Status": row["execution_status"],
                        "Expected": row.get("expected_points"),
                        "Confidence": row["confidence"],
                        "Evaluated": row.get("evaluated_at") or "No",
                    }
                    for row in rows[:25]
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No recommendations have been recorded in this local decision journal yet.")
    with tabs[7]:
        st.subheader("Safe Feedback")
        st.write("Open a GitHub issue with the feature involved, expected behavior, actual behavior, safe error code, and app version.")
        st.warning("Do not include ESPN cookies, API keys, private league screenshots, personal information, or full provider responses.")
        st.link_button("Open GitHub Issues", "https://github.com/aayushjain1230/fantasy_football_predicter/issues")


def page_data_sources(league) -> None:
    section_header("Provider Freshness", "Provider state, use, impact, and unavailable behavior.")
    rows = []
    for s in statuses(False):
        session_odds_key = s.provider == "The Odds API" and bool(st.session_state.get("odds_api_key"))
        session_weather_key = s.provider == "OpenWeather" and bool(st.session_state.get("openweather_api_key"))
        rows.append(
            {
                "Provider": s.provider,
                "Category": s.category,
                "State": s.state,
                "Last Update": s.updated or "Unknown",
                "Key Configured": s.key_configured or session_odds_key or session_weather_key,
                "Used By": ", ".join(s.used_by) if s.used_by else "Not integrated",
                "Impact": s.impact,
                "Unavailable Behavior": s.unavailable_behavior,
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)


def page_trust() -> None:
    st.header("Model Trust")
    summary = calibration_summary(rows=[])
    if summary.status == "UNAVAILABLE":
        st.warning(summary.verdict)
        st.write(f"Current real sample size: {summary.sample_size}. Minimum before reporting metrics: {summary.minimum_sample}.")
        st.info("Accuracy metrics appear only after enough real predictions and real outcomes are recorded. No example data is substituted.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sample", summary.sample_size)
    c2.metric("MAE", summary.points_mae)
    c3.metric("RMSE", summary.points_rmse)
    c4.metric("Brier", summary.brier_score)
    st.caption(summary.verdict)
    st.dataframe(summary.buckets, hide_index=True, use_container_width=True)


def page_methodology() -> None:
    st.header("Methodology")
    st.write(
        "Fourth Down starts from an available baseline projection, usually ESPN's weekly projection for connected leagues, "
        "then applies bounded contextual adjustments when data is actually available."
    )
    st.write("- Lineups are solved with exact search over legal slot assignments and unique-player constraints.")
    st.write("- Conservative, Balanced, and Aggressive lineups differ by floor, expected points, and matchup-aware ceiling objectives.")
    st.write("- Market context is optional; unavailable markets are labeled unavailable and never replace the baseline projection.")
    st.write("- Recommendation previews and decision-journal records are local recommendation workflow artifacts, not ESPN transactions.")
    st.write("- Waivers and trades compare full legal lineups before and after the move.")
    st.write("- League outlook and playoff probabilities use normalized scheduled matchups when a schedule is available.")
    st.write("- Schedule-aware outputs are Monte Carlo estimates with separate mathematical status where exact enumeration is small enough.")
    st.write("- Fourth Down does not add an LLM, automatic ESPN transactions, dynasty tools, or social features.")


def page_privacy() -> None:
    st.header("Privacy and Limitations")
    st.write("- Public Streamlit deployment stores league state only in Streamlit session state.")
    st.write("- Session state is not authentication, tenant isolation, or permanent storage.")
    st.write("- Private ESPN cookies should not be placed in shared Streamlit app secrets.")
    st.write("- Local `.env` cookies are for local single-user use only.")
    st.write("- The public Streamlit app does not persist private per-user league records to SQLite.")
    st.write("- Public odds/weather cache entries contain provider data only; they never contain API keys or ESPN credentials.")
    st.write("- RLS is not claimed because there is no shared per-user database. Multi-user SQLite mode fails closed.")
    st.write("- Fourth Down does not submit ESPN transactions or provide betting advice.")


PAGES = {
    "Home": page_home,
    "My Team": page_my_team,
    "Players": page_players,
    "Draft": page_draft_context,
    "League": page_league,
    "Settings": page_settings,
}


def visible_pages() -> dict[str, object]:
    if not st.session_state.get("league_connected"):
        return {
            "Home": page_home,
            "Settings": page_settings,
        }
    return dict(PAGES)


def main() -> None:
    st.set_page_config(page_title="Fourth Down", layout="wide", initial_sidebar_state="expanded")
    render_shell_style()
    ensure_state()
    league = st.session_state.league
    with st.sidebar:
        pages = visible_pages()
        connected = bool(st.session_state.get("league_connected"))
        if connected:
            team = user_team(league)
            team_name = team.name
            league_name = league.name
            week: int | str = league.week
            mode_label = league_label(league)
        else:
            team_name = "Connect your team"
            league_name = "No league connected"
            week = "—"
            mode_label = "ESPN CONNECTION REQUIRED"
        page_name = render_navigation(
            team_name,
            league_name,
            week,
            mode_label,
            connected,
            list(pages),
        )
        pending = st.session_state.pop("pending_page", None)
        if pending in pages:
            page_name = pending
    pages[page_name](league)


if __name__ == "__main__":
    main()
