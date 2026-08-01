from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .artifacts import projection_artifact_summary
from .config import APP_VERSION, CONFIG, config_summary, validate_config
from .domain import League
from .providers import statuses
from .simulation import MODEL_VERSION as SIMULATION_MODEL_VERSION


DEGRADATION_MATRIX = [
    {"Failure": "ESPN unavailable", "Expected behavior": "Keep current session state when present; otherwise offer demo mode.", "Feature": "Connection"},
    {"Failure": "Public league not found", "Expected behavior": "Show league-ID/season error; do not switch to unlabeled demo data.", "Feature": "Connection"},
    {"Failure": "Private league detected", "Expected behavior": "Explain private leagues are local-only for Phase 6 public deployment.", "Feature": "Connection"},
    {"Failure": "Projection artifact missing", "Expected behavior": "Use labeled fallback projection-adjustment engine.", "Feature": "Projections"},
    {"Failure": "Current ADP unavailable", "Expected behavior": "Hide market movement and label ADP unavailable.", "Feature": "Players/Draft"},
    {"Failure": "Odds API unavailable", "Expected behavior": "Use neutral market context and list game markets as missing.", "Feature": "Projection context"},
    {"Failure": "Weather unavailable", "Expected behavior": "Omit weather adjustment and list stadium weather as missing.", "Feature": "Projection context"},
    {"Failure": "Schedule incomplete", "Expected behavior": "Show schedule limitation and avoid exact playoff-status claims.", "Feature": "League"},
    {"Failure": "Free-agent pool unavailable", "Expected behavior": "Disable waiver recommendations with a concise empty state.", "Feature": "My Team"},
    {"Failure": "Simulation failure", "Expected behavior": "Preserve point projections and show probabilities unavailable.", "Feature": "League/Home"},
    {"Failure": "Historical dataset unavailable", "Expected behavior": "Keep inference working from committed JSON artifacts.", "Feature": "Modeling"},
]


PERFORMANCE_BUDGETS = [
    {"Operation": "Initial demo render", "Budget": "under 5 seconds"},
    {"Operation": "Player search", "Budget": "under 1 second for 50 displayed rows"},
    {"Operation": "Lineup optimization", "Budget": "under 1 second for normal rosters"},
    {"Operation": "Waiver ranking", "Budget": "under 5 seconds for demo-sized pools"},
    {"Operation": "Standard playoff simulation", "Budget": "under 8 seconds at default count"},
    {"Operation": "Interactive use", "Budget": "no model training or dataset downloads on rerun"},
]


def health_summary(league: League) -> dict[str, Any]:
    artifact = projection_artifact_summary()
    provider_rows = statuses(league.id == "demo")
    degraded = []
    if artifact["valid_artifacts"] < artifact["total_artifacts"]:
        degraded.append("Some projection artifacts are invalid or missing; fallback projections may be used.")
    if not league.schedule:
        degraded.append("League schedule is unavailable; schedule-aware outputs are limited.")
    if not league.free_agents:
        degraded.append("Free-agent pool unavailable; waiver recommendations are limited.")
    degraded.extend(validate_config(CONFIG))
    return {
        "app_version": APP_VERSION,
        "season": league.season,
        "week": league.week,
        "mode": "Demo league" if league.id == "demo" else "Session league",
        "projection_model_version": artifact["model_version"],
        "simulation_model_version": SIMULATION_MODEL_VERSION,
        "training_cutoff": artifact["training_cutoff"],
        "provider_states": [{"Provider": row.provider, "State": row.state, "Updated": row.updated or "Unknown"} for row in provider_rows],
        "degraded_features": degraded or ["No degraded features detected for this session."],
        "config": config_summary(CONFIG),
        "checked_at": datetime.now(UTC).isoformat(),
    }
