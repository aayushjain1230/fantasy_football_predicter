from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from statistics import mean, median
from typing import Any

from .domain import League, Player, Projection
from .persistence import attach_prediction_outcome, prediction_ledger_rows, save_prediction_ledger


def scoring_fingerprint(scoring: dict[str, float]) -> str:
    return hashlib.sha256(json.dumps(scoring, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def prediction_id(league: League, player: Player, projection: Projection, kind: str = "player_week") -> str:
    basis = f"{league.id}:{league.season}:{projection.week or league.week}:{player.id}:{kind}:{projection.model_version}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def record_player_prediction(league: League, player: Player, projection: Projection, provider_freshness: list[dict[str, Any]] | None = None, opponent: str | None = None) -> str:
    pid = prediction_id(league, player, projection)
    save_prediction_ledger(
        {
            "prediction_id": pid,
            "created_at": datetime.now(UTC).isoformat(),
            "season": league.season,
            "week": projection.week or league.week,
            "player_id": player.id,
            "player_name": player.name,
            "nfl_team": player.team,
            "opponent": opponent,
            "scoring_fingerprint": scoring_fingerprint(league.scoring),
            "expected_points": projection.mean,
            "lower_bound": projection.floor,
            "upper_bound": projection.ceiling,
            "win_probability": None,
            "model_version": projection.model_version,
            "feature_data_cutoff": projection.training_cutoff,
            "provider_freshness": provider_freshness or [],
            "fallback_used": projection.fallback_used,
            "eligible_for_evaluation": True,
        }
    )
    return pid


def record_outcome(prediction_id_value: str, actual_points: float | None, actual_outcome: int | None = None, final_player_status: str = "UNKNOWN", evaluation_status: str = "ELIGIBLE") -> None:
    attach_prediction_outcome(prediction_id_value, actual_points, actual_outcome, final_player_status, evaluation_status)


def evaluate_prediction_ledger(minimum_sample: int = 20) -> dict[str, Any]:
    rows = [row for row in prediction_ledger_rows() if row.get("eligible_for_evaluation") and row.get("evaluation_status") == "ELIGIBLE" and row.get("actual_points") is not None]
    if len(rows) < minimum_sample:
        return {
            "status": "UNAVAILABLE",
            "sample_size": len(rows),
            "minimum_sample": minimum_sample,
            "message": "Real evaluation unavailable until enough pre-outcome predictions have matched outcomes.",
            "metrics": {},
        }
    errors = [float(row["expected_points"]) - float(row["actual_points"]) for row in rows]
    abs_errors = [abs(error) for error in errors]
    covered = [float(row["lower_bound"]) <= float(row["actual_points"]) <= float(row["upper_bound"]) for row in rows if row.get("lower_bound") is not None and row.get("upper_bound") is not None]
    by_position: dict[str, list[float]] = {}
    for row, error in zip(rows, errors):
        position = str(row["player_id"]).split("-")[0]
        by_position.setdefault(position, []).append(abs(error))
    return {
        "status": "AVAILABLE",
        "sample_size": len(rows),
        "minimum_sample": minimum_sample,
        "metrics": {
            "mae": round(mean(abs_errors), 3),
            "rmse": round(math.sqrt(mean([error * error for error in errors])), 3),
            "bias": round(mean(errors), 3),
            "median_absolute_error": round(median(abs_errors), 3),
            "interval_coverage": round(mean(covered), 3) if covered else None,
            "fallback_sample": sum(1 for row in rows if row.get("fallback_used")),
        },
    }
