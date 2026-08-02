from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from .config import CONFIG
from .domain import League, Player, Projection
from .market import MarketContextProvider, default_market_provider
from .scoring import FantasyScoring, fantasy_points


SUPPORTED_MODEL_POSITIONS = {"QB", "RB", "WR", "TE"}
FEATURE_NAMES = ["prev_points", "rolling3_points", "rolling5_points", "games_played", "position_mean_prior", "external_baseline"]
MODEL_VERSION = "phase2_fixture_v1"
TRAINING_POLICY = {
    "target": "one player-week fantasy points scored in that NFL week",
    "prediction_timestamp": "before kickoff for the player-week being predicted",
    "leakage_policy": "rolling and aggregate features are shifted; current-week stats and future games are excluded",
    "supported_positions": sorted(SUPPORTED_MODEL_POSITIONS),
    "minimum_history": "one prior player game for player-specific history; otherwise position prior/external baseline fallback",
    "scoring": "canonical PPR fixture model; league-specific scoring adapter is supported separately for raw stats",
}


@dataclass(frozen=True)
class ProjectionContext:
    week: int
    feature_row: dict[str, float] | None = None
    external_baseline: float | None = None
    missing_inputs: tuple[str, ...] = ()


def normalize_team(team: str) -> str:
    aliases = {"JAC": "JAX", "LA": "LAR", "WSH": "WAS"}
    return aliases.get((team or "").upper(), (team or "").upper())


def normalize_player_name(name: str) -> str:
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in name)
    return " ".join(part for part in cleaned.split() if part not in suffixes)


def validate_source_rows(rows: list[dict[str, Any]]) -> None:
    required = {"season", "week", "player_id", "player_name", "position", "team", "opponent"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"historical data missing required columns: {sorted(missing)}")
    seen = set()
    for row in rows:
        key = (row["season"], row["week"], row["player_id"])
        if key in seen:
            raise ValueError(f"duplicate player-week observation: {key}")
        seen.add(key)
        if row["position"] not in SUPPORTED_MODEL_POSITIONS:
            continue
        int(row["season"])
        int(row["week"])


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"no rows in {path}")
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_training_rows(source_rows: list[dict[str, Any]], scoring: FantasyScoring | None = None) -> list[dict[str, Any]]:
    validate_source_rows(source_rows)
    scoring = scoring or FantasyScoring.canonical_ppr()
    rows = []
    for raw in source_rows:
        if raw["position"] not in SUPPORTED_MODEL_POSITIONS:
            continue
        row = {**raw}
        row["team"] = normalize_team(row["team"])
        row["opponent"] = normalize_team(row["opponent"])
        row["fantasy_points"] = fantasy_points(row, scoring)
        rows.append(row)
    rows.sort(key=lambda r: (int(r["season"]), int(r["week"]), r["player_id"]))

    history: dict[str, list[float]] = defaultdict(list)
    position_history: dict[str, list[float]] = defaultdict(list)
    processed = []
    for row in rows:
        player_hist = history[row["player_id"]]
        pos_hist = position_history[row["position"]]
        prior = mean(pos_hist) if pos_hist else 8.0
        external = float(row.get("external_baseline", "") or prior)
        processed.append(
            {
                "season": int(row["season"]),
                "week": int(row["week"]),
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "normalized_name": normalize_player_name(row["player_name"]),
                "position": row["position"],
                "team": row["team"],
                "opponent": row["opponent"],
                "prev_points": player_hist[-1] if player_hist else prior,
                "rolling3_points": mean(player_hist[-3:]) if player_hist else prior,
                "rolling5_points": mean(player_hist[-5:]) if player_hist else prior,
                "games_played": len(player_hist),
                "position_mean_prior": prior,
                "external_baseline": external,
                "target": row["fantasy_points"],
                "low_history": len(player_hist) < 3,
            }
        )
        history[row["player_id"]].append(row["fantasy_points"])
        position_history[row["position"]].append(row["fantasy_points"])
    return processed


def dataset_fingerprint(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    aug = [matrix[i][:] + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            aug[pivot][col] = 1e-12
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        aug[col] = [x / div for x in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [aug[row][i] - factor * aug[col][i] for i in range(n + 1)]
    return [aug[i][-1] for i in range(n)]


def fit_ridge(rows: list[dict[str, Any]], alpha: float = 1.0) -> dict[str, Any]:
    names = ["intercept", *FEATURE_NAMES]
    p = len(names)
    xtx = [[0.0 for _ in range(p)] for _ in range(p)]
    xty = [0.0 for _ in range(p)]
    for row in rows:
        x = [1.0, *[float(row[name]) for name in FEATURE_NAMES]]
        y = float(row["target"])
        for i in range(p):
            xty[i] += x[i] * y
            for j in range(p):
                xtx[i][j] += x[i] * x[j]
    for i in range(1, p):
        xtx[i][i] += alpha
    coefficients = _solve_linear_system(xtx, xty)
    return {"algorithm": "ridge_linear_regression", "features": FEATURE_NAMES, "coefficients": dict(zip(names, coefficients))}


def predict_from_model(model: dict[str, Any], row: dict[str, float]) -> float:
    coeffs = model["coefficients"]
    value = float(coeffs.get("intercept", 0))
    for name in model["features"]:
        value += float(coeffs.get(name, 0)) * float(row.get(name, 0))
    return value


def metrics(actuals: list[float], predictions: list[float], baselines: list[float] | None = None) -> dict[str, float]:
    if not actuals:
        return {"sample_size": 0}
    errors = [p - a for p, a in zip(predictions, actuals)]
    abs_errors = [abs(e) for e in errors]
    mae = mean(abs_errors)
    rmse = math.sqrt(mean([e * e for e in errors]))
    ybar = mean(actuals)
    ss_tot = sum((a - ybar) ** 2 for a in actuals)
    ss_res = sum((p - a) ** 2 for p, a in zip(predictions, actuals))
    result = {
        "sample_size": len(actuals),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "mean_bias": round(mean(errors), 3),
        "median_absolute_error": round(median(abs_errors), 3),
        "r2": round(1 - ss_res / ss_tot, 3) if ss_tot else 0.0,
    }
    if baselines:
        base_mae = mean([abs(b - a) for b, a in zip(baselines, actuals)])
        result["baseline_mae"] = round(base_mae, 3)
        result["baseline_improvement_pct"] = round(((base_mae - mae) / base_mae) * 100, 2) if base_mae else 0.0
    return result


def evaluate_rows(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    predictions = [predict_from_model(model, row) for row in rows]
    actuals = [float(row["target"]) for row in rows]
    baselines = [float(row["rolling3_points"]) for row in rows]
    residuals = [actual - pred for actual, pred in zip(actuals, predictions)]
    lower = []
    upper = []
    if residuals:
        sorted_abs = sorted(abs(x) for x in residuals)
        q80 = sorted_abs[min(len(sorted_abs) - 1, int(0.8 * (len(sorted_abs) - 1)))]
        lower = [pred - q80 for pred in predictions]
        upper = [pred + q80 for pred in predictions]
    coverage = mean([lo <= actual <= hi for lo, actual, hi in zip(lower, actuals, upper)]) if lower else 0
    return {**metrics(actuals, predictions, baselines), "interval_coverage_80": round(coverage, 3)}


def train_position_artifacts(rows: list[dict[str, Any]], artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = dataset_fingerprint(rows)
    results: dict[str, Any] = {"model_version": MODEL_VERSION, "dataset_fingerprint": fingerprint, "positions": {}}
    for position in sorted(SUPPORTED_MODEL_POSITIONS):
        pos_rows = [row for row in rows if row["position"] == position]
        train_rows = [row for row in pos_rows if int(row["season"]) <= 2023]
        validation_rows = [row for row in pos_rows if int(row["season"]) == 2024 and int(row["week"]) <= 2]
        test_rows = [row for row in pos_rows if int(row["season"]) == 2024 and int(row["week"]) >= 3]
        if len(train_rows) < 2:
            continue
        model = fit_ridge(train_rows, alpha=2.0)
        residual_rows = validation_rows or train_rows
        residuals = [float(row["target"]) - predict_from_model(model, row) for row in residual_rows]
        abs_residuals = sorted(abs(x) for x in residuals) or [6.0]
        q80 = abs_residuals[min(len(abs_residuals) - 1, int(0.8 * (len(abs_residuals) - 1)))]
        metadata = {
            "model_version": MODEL_VERSION,
            "position": position,
            "algorithm": model["algorithm"],
            "feature_names": model["features"],
            "training_start": "2022",
            "training_cutoff": "2023",
            "validation_period": "2024 weeks 1-2",
            "test_period": "2024 weeks 3-4 fixture",
            "scoring_basis": "canonical_ppr_fixture",
            "dataset_fingerprint": fingerprint,
            "created_at": datetime.now(UTC).isoformat(),
            "leakage_policy": TRAINING_POLICY["leakage_policy"],
        }
        artifact = {**model, "metadata": metadata, "interval": {"method": "validation_absolute_residual", "level": 0.8, "half_width": round(q80, 3)}}
        artifact["evaluation"] = {
            "validation": evaluate_rows(artifact, validation_rows) if validation_rows else {},
            "test": evaluate_rows(artifact, test_rows) if test_rows else {},
        }
        (artifact_dir / f"{position}.json").write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
        results["positions"][position] = artifact["evaluation"]
    (artifact_dir / "manifest.json").write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    return results


class ProjectionService:
    def __init__(self, artifact_dir: Path | None = None, market_provider: MarketContextProvider | None = None, enable_market_adjustments: bool | None = None):
        self.artifact_dir = artifact_dir or Path(__file__).resolve().parents[2] / "models" / "projections" / "latest"
        self._artifacts: dict[str, dict[str, Any] | None] = {}
        self.market_provider = market_provider or default_market_provider()
        self.enable_market_adjustments = CONFIG.enable_market_adjustments if enable_market_adjustments is None else enable_market_adjustments

    def load_artifact(self, position: str) -> dict[str, Any] | None:
        if position not in SUPPORTED_MODEL_POSITIONS:
            return None
        if position in self._artifacts:
            return self._artifacts[position]
        path = self.artifact_dir / f"{position}.json"
        try:
            from .artifacts import validate_projection_artifact

            validation = validate_projection_artifact(path)
            if not validation["valid"]:
                raise ValueError("; ".join(validation["errors"]))
            artifact = json.loads(path.read_text(encoding="utf-8"))
            if artifact["metadata"]["model_version"] != MODEL_VERSION:
                raise ValueError("incompatible model version")
            if artifact["features"] != FEATURE_NAMES:
                raise ValueError("feature order mismatch")
        except Exception:
            artifact = None
        self._artifacts[position] = artifact
        return artifact

    def project_player(self, player: Player, league: League | None = None, week: int | None = None, context: ProjectionContext | None = None) -> Projection:
        from .engine import project as fallback_project

        artifact = self.load_artifact(player.position)
        context = context or ProjectionContext(week=week or (league.week if league else 0), external_baseline=player.mean)
        fallback = fallback_project(player)
        fallback = fallback.model_copy(
            update={
                "baseline_projection": fallback.baseline_value,
                "market_adjustment": 0,
                "final_projection": fallback.mean,
                "market_data_available": False,
                "market_data_quality": "unavailable",
                "generated_at": datetime.now(UTC).isoformat(),
            }
        )
        if not artifact:
            return fallback.model_copy(update={"week": context.week, "fallback_used": True, "fallback_reason": "No trusted Phase 2 artifact for this position", "model_name": "phase1_fallback", "model_version": "phase1"})
        if context.feature_row:
            feature_row = {name: float(context.feature_row.get(name, player.mean)) for name in FEATURE_NAMES}
            missing = list(context.missing_inputs)
        else:
            feature_row = {
                "prev_points": player.mean,
                "rolling3_points": player.mean,
                "rolling5_points": player.mean,
                "games_played": 0.0,
                "position_mean_prior": player.mean,
                "external_baseline": context.external_baseline if context.external_baseline is not None else player.mean,
            }
            missing = ["current historical feature row"]
        expected = predict_from_model(artifact, feature_row)
        half_width = float(artifact["interval"]["half_width"])
        lower = expected - half_width
        upper = expected + half_width
        ranked = sorted([(name, feature_row[name], abs(float(artifact["coefficients"].get(name, 0)) * feature_row[name])) for name in FEATURE_NAMES], key=lambda x: x[2], reverse=True)[:4]
        completeness = 1 - min(1, len(missing) / 5)
        market_adjustment, market_available, market_quality, market_missing, market_reason = self._market_adjustment(player)
        final_expected = max(0, expected + market_adjustment)
        return Projection(
            player_id=player.id,
            week=context.week,
            baseline_source="Phase 2 position-specific historical model",
            baseline_value=round(float(context.external_baseline if context.external_baseline is not None else player.mean), 2),
            baseline_projection=round(expected, 2),
            market_adjustment=round(market_adjustment, 2),
            final_projection=round(final_expected, 2),
            mean=round(final_expected, 2),
            median=round(final_expected, 2),
            floor=round(max(0, lower + market_adjustment), 2),
            ceiling=round(max(0, upper + market_adjustment), 2),
            confidence=round(max(0.3, min(0.85, completeness * 0.75)), 2),
            adjustments=[{"name": "market_context", "points": round(market_adjustment, 2), "source": market_reason, "enabled": self.enable_market_adjustments}],
            uncertainty_label="80% interval estimated from validation residuals",
            interval_level=0.8,
            model_name=artifact["algorithm"],
            model_version=artifact["metadata"]["model_version"],
            important_features=[{"feature": name, "value": round(value, 3), "contribution_magnitude": round(weight, 3)} for name, value, weight in ranked],
            data_completeness=round(completeness, 2),
            confidence_label="limited" if completeness < 0.7 else "moderate",
            fallback_used=False,
            fallback_reason="",
            training_cutoff=artifact["metadata"]["training_cutoff"],
            reasons=["Projection generated by a position-specific historical model.", "Feature values are pregame or shifted historical aggregates.", market_reason],
            missing=[*missing, *market_missing],
            limitations=["Fixture artifacts demonstrate the architecture; production accuracy requires full historical nflverse training data.", "Teammate and game-correlation effects are not fully modeled in Phase 2."],
            market_data_available=market_available,
            market_data_quality=market_quality,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _market_adjustment(self, player: Player) -> tuple[float, bool, str, list[str], str]:
        market = self.market_provider.get_player_market(player.id)
        if not market.available:
            return 0.0, False, market.metadata.data_quality, ["validated market context"], market.unavailable_reason or "Market adjustment is unavailable and not applied."
        if not self.enable_market_adjustments:
            return 0.0, True, market.metadata.data_quality, [], "Market context was retrieved but the unvalidated adjustment layer is disabled by default."
        signals = [value for value in (market.receptions, market.rushing_yards, market.receiving_yards, market.passing_yards) if value is not None]
        if not signals:
            return 0.0, True, market.metadata.data_quality, ["matched player prop line"], "No supported player prop line matched this player."
        raw = min(1.5, max(-1.5, (sum(signals) / len(signals) - player.mean * 4) / 30))
        return raw, True, market.metadata.data_quality, [], "Conservative market adjustment layer is enabled; adjustment is bounded and reported separately."


DEFAULT_PROJECTION_SERVICE = ProjectionService()
