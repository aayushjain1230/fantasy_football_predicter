from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import asdict
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
from app.demo import demo_league  # noqa: E402
from app.engine import optimize_lineup, project, user_team, waiver_moves  # noqa: E402
from app.draft_intelligence import DEFAULT_DRAFT_SERVICE, DraftSettings, snake_next_pick  # noqa: E402
from app.projection_service import DEFAULT_PROJECTION_SERVICE, SUPPORTED_MODEL_POSITIONS, TRAINING_POLICY  # noqa: E402
from app.providers import connect_espn, statuses  # noqa: E402
from app.decision_service import build_weekly_brief, roster_outlook, value_based_faab  # noqa: E402
from app.decision_journal import create_decision_entry  # noqa: E402
from app.config import APP_VERSION, CONFIG, config_summary, validate_config  # noqa: E402
from app.evaluation import evaluate_prediction_ledger  # noqa: E402
from app.identity import build_identity_index, resolve_player_identity  # noqa: E402
from app.market import default_market_provider  # noqa: E402
from app.operations import DEGRADATION_MATRIX, PERFORMANCE_BUDGETS, health_summary  # noqa: E402
from app.persistence import decision_journal_rows, save_decision_journal_entry  # noqa: E402
from app.recommendations import generate_recommendation, require_confirmation, validate_recommendation  # noqa: E402
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


LEAGUE_RE = re.compile(r"^(demo|[0-9]{1,30})$")
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
        st.session_state.league = demo_league()
    if "league_connected" not in st.session_state:
        st.session_state.league_connected = False
    if "mode" not in st.session_state:
        st.session_state.mode = "demo"
    if "draft_picks" not in st.session_state:
        st.session_state.draft_picks = []
    if "draft_slot" not in st.session_state:
        st.session_state.draft_slot = 6
    if "current_pick" not in st.session_state:
        st.session_state.current_pick = 1
    if "draft_mode" not in st.session_state:
        st.session_state.draft_mode = False
    if "playoff_scenarios" not in st.session_state:
        st.session_state.playoff_scenarios = []
    if "playoff_scenario_history" not in st.session_state:
        st.session_state.playoff_scenario_history = []
    if "last_manual_refresh" not in st.session_state:
        st.session_state.last_manual_refresh = None
    if "last_manual_refresh_epoch" not in st.session_state:
        st.session_state.last_manual_refresh_epoch = 0.0


def league_label(league) -> str:
    return "DEMO PREVIEW" if league.id == "demo" else "LIVE ESPN DATA"


def pct(value: float) -> str:
    return f"{value:.1%}" if 0 < value < 0.01 or 0.99 < value < 1 else f"{value:.0%}"


def delta(value: float, suffix: str = "") -> str:
    return f"{'+' if value > 0 else ''}{value}{suffix}"


def status_badge(state: str) -> str:
    return badge(str(state), str(state))


def player_label(player) -> str:
    status = "" if player.injury_status in {"HEALTHY", "ACTIVE"} else f" - {player.injury_status}"
    return f"{player.name} ({player.position}, {player.team}){status}"


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
    return "The league could not be connected. Check the league ID, season, team ID, and private-league credentials."


def page_home(league) -> None:
    if not st.session_state.get("league_connected"):
        stadium_hero()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Connect ESPN League", type="primary", use_container_width=True):
                st.session_state.pending_page = "Settings"
                st.rerun()
        with c2:
            if st.button("Preview Demo (Optional)", use_container_width=True):
                st.session_state.league = demo_league()
                st.session_state.mode = "demo"
                st.session_state.league_connected = True
                st.rerun()
        warning_state(
            "Private leagues are supported",
            "Use the private-league section in Settings. Credentials are used only for the current connection and are not saved by Fourth Down.",
        )
        return

    page_header(
        "Weekly Command Center",
        "Home",
        f"{league.name} | Week {league.week} | {league_label(league)}",
        [status_badge(league_label(league))],
    )
    brief = build_weekly_brief(league)
    metric_grid(
        [
            metric_card("Projected Points", fmt_points(brief.expected_score), "Current optimal lineup", "green"),
            metric_card("Win Estimate", fmt_pct(brief.win_probability), brief.matchup_summary, "blue"),
            metric_card("Playoff Odds", fmt_pct(brief.playoff_probability), "Schedule-aware estimate", "purple"),
            metric_card("Best Position", brief.best_position or "Unknown", "Roster strength", "gold"),
        ]
    )
    section_header("What To Do First", "Ranked by urgency, expected impact, confidence, and deadline.")
    for action in brief.top_actions[:4]:
        action_card(action)
        with st.expander(f"Why: {action.title}"):
            for item in action.reasons:
                st.write(f"- {item}")
            if action.risks:
                st.write(f"Main risk: {action.risks[0]}")
            if action.missing_inputs:
                st.write("Missing inputs:", ", ".join(action.missing_inputs))
    empty_state("Roster summary", f"{brief.roster_summary} Session state can reset when Streamlit reconnects.")


def page_connect() -> None:
    st.header("Connect League")
    st.write("Use `demo` or a numeric ESPN league ID. Private leagues require both ESPN browser-cookie values.")
    with st.form("connect", clear_on_submit=True):
        league_id = st.text_input("League ID", value="")
        season = st.number_input("Season", min_value=2020, max_value=2030, value=2026, step=1)
        team_id = st.text_input("Team ID (optional)", value="")
        with st.expander("Private league authentication"):
            st.caption(
                "Only enter credentials on a deployment you trust. Fourth Down sends them to ESPN for this request "
                "and does not save them to its database, environment, logs, URL, or connected league object."
            )
            espn_s2 = st.text_input(
                "espn_s2 cookie",
                value="",
                type="password",
                help="Copy the complete espn_s2 value from the cookies for espn.com in your signed-in browser.",
            )
            espn_swid = st.text_input(
                "SWID cookie",
                value="",
                type="password",
                help="Copy the SWID value, including braces if ESPN shows them.",
            )
        submitted = st.form_submit_button("Connect league")
    if submitted:
        league_id = league_id.strip()
        team_id = team_id.strip()
        if not LEAGUE_RE.match(league_id):
            st.error("League ID must be `demo` or 1 to 30 digits.")
            return
        if team_id and not TEAM_RE.match(team_id):
            st.error("Team ID must be 1 to 10 digits.")
            return
        try:
            with st.spinner("Requesting league data from ESPN..."):
                league = asyncio.run(
                    connect_espn(
                        league_id,
                        int(season),
                        team_id or None,
                        espn_s2=espn_s2,
                        espn_swid=espn_swid,
                    )
                )
            st.session_state.league = league
            st.session_state.mode = "demo" if league.id == "demo" else "live"
            st.session_state.league_connected = True
            st.session_state.draft_picks = []
            st.session_state.playoff_scenarios = []
            st.session_state.playoff_scenario_history = []
            st.session_state.simulation_cache = {}
            st.success(f"Connected to {league.name}.")
        except Exception as exc:
            st.error(connect_error(exc))
    if st.button("Disconnect league"):
        st.session_state.league = demo_league()
        st.session_state.mode = "demo"
        st.session_state.league_connected = False
        st.session_state.draft_picks = []
        st.session_state.playoff_scenarios = []
        st.session_state.playoff_scenario_history = []
        st.session_state.simulation_cache = {}
        st.rerun()
    st.info(
        "League data is browser-session scoped and may reset when Streamlit reconnects. "
        "Private ESPN credentials are not retained after the connection form is submitted."
    )


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
            save_decision_journal_entry(entry.to_row())
            st.success("Recommendation recorded locally. No ESPN transaction was submitted.")
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
    league_size = max(2, len(league.teams) or 12)
    current_pick = max(1, int(st.session_state.current_pick))
    draft_slot = min(max(1, int(st.session_state.draft_slot)), league_size)
    st.session_state.current_pick = current_pick
    st.session_state.draft_slot = draft_slot
    next_pick = snake_next_pick(current_pick, draft_slot, league_size)
    return DraftSettings(league_size=league_size, current_pick=current_pick, next_pick=next_pick)


def page_draft_intelligence(league) -> None:
    section_header("Draft Board", "Contextual draft recommendations and ADP-relative value.")
    settings = draft_settings_from_state(league)
    drafted = {pick["player_id"] for pick in st.session_state.draft_picks}
    board = DEFAULT_DRAFT_SERVICE.current_board(league, settings, drafted)
    st.caption("Fixture ADP and fixture draft model artifacts validate the architecture. Production ADP is unavailable until a legal source is configured.")
    if not board:
        st.info("No remaining QB/RB/WR/TE players are available for draft intelligence.")
        return
    st.dataframe(
        [
            {
                "Tier": row.get("tier"),
                "Player": row["player_name"],
                "Pos": row["position"],
                "Team": row["team"],
                "ADP": row["consensus_adp"],
                "Expected VOR": row["expected_vor"],
                "ADP Value": row.get("adp_relative_value", "fallback"),
                "Outperform": pct(row.get("outperform_probability", 0)),
                "Underperform": pct(row.get("underperform_probability", 0)),
                "Avail Next": pct(row.get("available_next_pick_probability", 0)),
                "Confidence": row.get("confidence", "fallback"),
            }
            for row in board
        ],
        hide_index=True,
        use_container_width=True,
    )
    selected = st.selectbox("Player detail", board, format_func=lambda row: f"{row['player_name']} ({row['position']})")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected VOR", selected["expected_vor"])
    c2.metric("ADP Expectation", selected.get("expected_value_at_adp", "n/a"))
    c3.metric("ADP Value", selected.get("adp_relative_value", "n/a"))
    c4.metric("Available Next Pick", pct(selected.get("available_next_pick_probability", 0)))
    st.write(f"Availability method: {selected.get('availability_method', 'fallback')}")
    st.write(f"Performance risk: {selected.get('performance_risk', 'n/a')}")
    st.write(f"Availability risk: {selected.get('availability_risk', 'n/a')}")
    st.write("Explanation")
    st.write("- Expected VOR compares modeled season value with league replacement level.")
    st.write("- ADP-relative value compares expected VOR with historical fixture expectation at the player's draft cost.")
    st.write("- Outperform/meet/underperform probabilities are fixture-calibrated summaries, not production probabilities.")


def page_draft_room(league) -> None:
    section_header("Live Draft State", "Session-local pick tracking and next-pick context.")
    league_size = max(2, len(league.teams) or 12)
    st.session_state.draft_slot = st.number_input("Your draft slot", min_value=1, max_value=league_size, value=int(st.session_state.draft_slot), step=1)
    st.session_state.current_pick = st.number_input("Current overall pick", min_value=1, max_value=300, value=int(st.session_state.current_pick), step=1)
    settings = draft_settings_from_state(league)
    st.metric("Next user pick", settings.next_pick)
    board = DEFAULT_DRAFT_SERVICE.current_board(league, settings, {pick["player_id"] for pick in st.session_state.draft_picks})
    if board:
        pick = st.selectbox("Mark drafted", board, format_func=lambda row: f"{row['player_name']} ({row['position']})")
        if st.button("Record pick"):
            if pick["player_id"] not in {p["player_id"] for p in st.session_state.draft_picks}:
                st.session_state.draft_picks.append({"number": len(st.session_state.draft_picks) + 1, "player_id": pick["player_id"], "player_name": pick["player_name"], "position": pick["position"]})
                st.session_state.current_pick = int(st.session_state.current_pick) + 1
                st.rerun()
    c1, c2, c3 = st.columns(3)
    if c1.button("Undo last pick", disabled=not st.session_state.draft_picks):
        st.session_state.draft_picks.pop()
        st.rerun()
    if c2.button("Reset draft"):
        st.session_state.draft_picks = []
        st.session_state.current_pick = 1
        st.rerun()
    c3.download_button("Export draft CSV", data="\n".join([",".join(map(str, pick.values())) for pick in st.session_state.draft_picks]), file_name="fourth-down-draft.csv", mime="text/csv")
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
    result = get_league_simulation(league, simulations=1000, seed=41)
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
    page_header("My Team", "Roster Decisions", "Lineup, waivers, trades, roster outlook, and contingency planning in one workspace.", [status_badge(league_label(league))])
    brief = build_weekly_brief(league)
    st.caption("Roster decisions, not separate labs. Technical detail is available inside each feature.")
    section_header("Priority Actions", "Recommendation first, calculations behind expanders.")
    if brief.top_actions:
        st.dataframe(
            [
                {
                    "Priority": action.priority,
                    "Category": action.category,
                    "Action": action.recommended_action,
                    "Impact": action.expected_points_change,
                    "Confidence": action.confidence,
                    "Robustness": action.robustness,
                    "Deadline": action.deadline or "Monitor",
                }
                for action in brief.top_actions
            ],
            hide_index=True,
            use_container_width=True,
        )
    tabs = st.tabs(["Lineup", "Waivers", "Trades", "Roster Outlook", "Contingencies"])
    with tabs[0]:
        page_lineup(league)
    with tabs[1]:
        page_waivers(league)
    with tabs[2]:
        page_trades(league)
    with tabs[3]:
        outlook = roster_outlook(league)
        st.dataframe([row.model_dump() for row in outlook], hide_index=True, use_container_width=True)
        st.info(f"Biggest weakness: {brief.biggest_weakness or 'Unavailable'}. Best position: {brief.best_position or 'Unavailable'}.")
    with tabs[4]:
        team = user_team(league)
        questionable = [p for p in team.players if p.injury_status not in {"HEALTHY", "ACTIVE"}]
        if not questionable:
            st.success("No injury contingency is currently supported by roster data.")
        for player in questionable:
            replacements = sorted([p for p in team.players if p.id != player.id and p.availability > 0 and (p.position == player.position or p.eligible_slots & player.eligible_slots)], key=lambda p: p.mean, reverse=True)[:3]
            with st.container(border=True):
                st.markdown(f"**If {player.name} is inactive**")
                st.write(f"Keep {player.name} in the most flexible eligible slot when possible, then use the best available late replacement.")
                st.write("Replacement options:", ", ".join(p.name for p in replacements) if replacements else "No legal replacement currently modeled.")
                st.caption("Kickoff-time and locked-player support requires reliable game-start data; absent that, this is a roster-eligibility contingency.")


def page_players(league) -> None:
    page_header("Players", "Research", "Search, compare, and inspect player projections without leaving the player workspace.", [status_badge(league_label(league))])
    players = [p for t in league.teams for p in t.players] + league.free_agents
    query = st.text_input("Search player or NFL team", value="")
    filtered = [p for p in players if not query or query.lower() in p.name.lower() or query.lower() in p.team.lower()]
    selected = st.selectbox("Player", filtered or players, format_func=player_label)
    data = player_research(league, selected.id)
    projection = data["projection"]
    identity_index = build_identity_index(players, season=league.season)
    identity = resolve_player_identity(selected.name, candidates=identity_index, position=selected.position, nfl_team_id=selected.team)
    market = default_market_provider().get_player_market(selected.id)
    st.markdown(player_card(selected, projection), unsafe_allow_html=True)
    metric_grid(
        [
            metric_card("Baseline Projection", fmt_points(projection.baseline_projection or projection.baseline_value), projection.baseline_source, "blue"),
            metric_card("Final Projection", fmt_points(projection.final_projection or projection.mean), "Baseline plus validated adjustments", "green"),
            metric_card("Range", f"{fmt_points(projection.floor)}-{fmt_points(projection.ceiling)}", "Lower to upper estimate", "gold"),
            metric_card("Market Context", "Available" if market.available else "Unavailable", market.metadata.data_quality, "purple"),
        ]
    )
    tabs = st.tabs(["Decision View", "Projection", "Market/Draft", "History", "Model Details"])
    with tabs[0]:
        add_relevance = "Free agent" if not selected.rostered else "Rostered"
        st.write(f"{selected.name} is currently marked as **{add_relevance}**.")
        st.write(f"Role: {data['role']}")
        st.write("Start/add/trade relevance is derived from lineup, waiver, and trade features inside My Team.")
    with tabs[1]:
        st.write(f"Baseline source: {projection.baseline_source}")
        st.write(f"Baseline projection: {projection.baseline_projection or projection.baseline_value}")
        st.write(f"Market adjustment: {projection.market_adjustment}")
        st.write(f"Final projection: {projection.final_projection or projection.mean}")
        st.write(f"Market data available: {projection.market_data_available}")
        st.write(f"Market data quality: {projection.market_data_quality}")
        st.dataframe(projection.adjustments, hide_index=True, use_container_width=True)
        st.write("Missing inputs:", ", ".join(projection.missing) if projection.missing else "None")
    with tabs[2]:
        st.write("Canonical identity")
        st.json(
            {
                "canonical_player_id": identity.canonical_player_id,
                "normalized_name": identity.normalized_name,
                "nfl_team_id": identity.nfl_team_id,
                "resolved": identity.resolved,
                "ambiguous": identity.ambiguous,
                "reason": identity.reason,
            }
        )
        st.write("Market context")
        if market.available:
            st.json(asdict(market))
        else:
            st.info(market.unavailable_reason or "No available market data. No betting line is fabricated.")
        if selected.position in SUPPORTED_MODEL_POSITIONS:
            settings = draft_settings_from_state(league)
            board = DEFAULT_DRAFT_SERVICE.current_board(league, settings, set())
            draft_row = next((row for row in board if row["player_id"] == selected.id), None)
            if draft_row:
                st.json({key: draft_row[key] for key in ("consensus_adp", "expected_vor", "adp_relative_value", "outperform_probability", "underperform_probability", "availability_method") if key in draft_row})
            else:
                st.info("No draft-market row is available for this player.")
        else:
            st.info("Draft-market intelligence currently supports QB/RB/WR/TE fixture artifacts.")
    with tabs[3]:
        st.info(data["historical_note"])
        page_historical_draft_explorer()
    with tabs[4]:
        st.write(f"Model: `{projection.model_name}` `{projection.model_version}`")
        st.write(f"Training cutoff: {projection.training_cutoff or 'Unavailable'}")
        for item in projection.reasons + projection.limitations:
            st.write(f"- {item}")


def page_league(league) -> None:
    page_header("League", "Outlook", "Standings, playoff context, scenarios, power, and schedule luck.", [status_badge(league_label(league))])
    st.caption("Standings, playoff outlook, scenarios, power, and schedule context in one league workspace.")
    tabs = st.tabs(["Outlook", "Standings", "Scenarios", "Power", "Schedule Luck", "Team Detail"])
    with tabs[0]:
        page_league_outlook(league)
    with tabs[1]:
        page_standings(league)
    with tabs[2]:
        page_playoff_machine(league)
    with tabs[3]:
        page_rankings(league)
    with tabs[4]:
        page_schedule_analysis(league)
    with tabs[5]:
        page_team_detail(league)


def page_draft_context(league) -> None:
    st.header("Draft")
    st.caption("Contextual draft workspace. Disable draft mode in Settings after the draft.")
    tabs = st.tabs(["Board", "Room", "Market", "Performance"])
    with tabs[0]:
        page_draft_intelligence(league)
    with tabs[1]:
        page_draft_room(league)
    with tabs[2]:
        page_market_movement()
    with tabs[3]:
        page_draft_model_performance()


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
    page_header("Settings", "Operations", "Connection, data freshness, privacy, evaluation, and launch-readiness controls.", [status_badge(league_label(league))])
    st.caption("Connection, data freshness, privacy, strategy, and technical limits.")
    st.session_state.draft_mode = st.toggle("Show contextual Draft destination", value=bool(st.session_state.draft_mode))
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
        st.subheader("Session Reset")
        st.write("Reset clears Streamlit session state for league, draft, scenarios, selections, and private derived results. It does not remove data from ESPN or other providers.")
        if st.button("Reset this Streamlit session"):
            for key in ["league", "mode", "draft_picks", "playoff_scenarios", "playoff_scenario_history", "simulation_cache", "draft_slot", "current_pick"]:
                st.session_state.pop(key, None)
            st.rerun()
    with tabs[6]:
        page_trust()
        st.subheader("Prediction Ledger Evaluation")
        ledger = evaluate_prediction_ledger()
        if ledger["status"] == "UNAVAILABLE":
            st.info(f"{ledger['message']} Current eligible sample: {ledger['sample_size']} / {ledger['minimum_sample']}.")
        else:
            st.json(ledger["metrics"])
        st.subheader("Decision Journal")
        rows = decision_journal_rows()
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
        st.write("Open a GitHub issue with the feature involved, expected behavior, actual behavior, safe error code, app version, and whether demo or live mode was used.")
        st.warning("Do not include ESPN cookies, API keys, private league screenshots, personal information, or full provider responses.")
        st.link_button("Open GitHub Issues", "https://github.com/aayushjain1230/fantasy_football_predicter/issues")


def page_data_sources(league) -> None:
    section_header("Provider Freshness", "Provider state, use, impact, and unavailable behavior.")
    rows = []
    for s in statuses(league.id == "demo"):
        rows.append(
            {
                "Provider": s.provider,
                "Category": s.category,
                "State": s.state,
                "Last Update": s.updated or "Unknown",
                "Key Configured": s.key_configured,
                "Used By": ", ".join(s.used_by) if s.used_by else "Not integrated",
                "Impact": s.impact,
                "Unavailable Behavior": s.unavailable_behavior,
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)


def page_trust() -> None:
    st.header("Model Trust")
    summary = calibration_summary()
    if summary.status == "UNAVAILABLE":
        st.warning(summary.verdict)
        st.write(f"Current real sample size: {summary.sample_size}. Minimum before reporting metrics: {summary.minimum_sample}.")
        demo = calibration_summary(demo_example=True)
        st.subheader("Demo Example Only")
        st.caption("These values demonstrate the interface and are not evidence of model accuracy.")
        st.dataframe(demo.buckets, hide_index=True, use_container_width=True)
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
    st.write("- Phase 4 still does not add an LLM, automatic ESPN transactions, dynasty tools, or social features.")


def page_privacy() -> None:
    st.header("Privacy and Limitations")
    st.write("- Public Streamlit deployment stores league state only in Streamlit session state.")
    st.write("- Session state is not authentication, tenant isolation, or permanent storage.")
    st.write("- Private ESPN cookies should not be placed in shared Streamlit app secrets.")
    st.write("- Local `.env` cookies are for local single-user use only.")
    st.write("- SQLite persistence is local/ephemeral and is not a multi-user cloud database.")
    st.write("- Fourth Down does not submit ESPN transactions or provide betting advice.")


PAGES = {
    "Home": page_home,
    "My Team": page_my_team,
    "Players": page_players,
    "League": page_league,
    "Settings": page_settings,
}


def visible_pages() -> dict[str, object]:
    if not st.session_state.get("league_connected"):
        return {
            "Home": page_home,
            "Settings": page_settings,
        }
    pages = dict(PAGES)
    if st.session_state.get("draft_mode"):
        pages["Draft"] = page_draft_context
    return pages


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
            connected and st.session_state.get("draft_mode", False),
            list(pages),
        )
        pending = st.session_state.pop("pending_page", None)
        if pending in pages:
            page_name = pending
    pages[page_name](league)


if __name__ == "__main__":
    main()
