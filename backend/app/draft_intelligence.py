from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from .domain import League, Player
from .engine import user_team
from .projection_service import DEFAULT_PROJECTION_SERVICE


DRAFT_MODEL_VERSION = "phase3_fixture_v1"
DRAFT_FEATURES = ["consensus_adp", "position_adp", "expected_vor", "phase2_expected", "phase2_uncertainty", "games_played_prev", "age", "experience", "adp_dispersion"]
OUTCOME_CLASSES = ("OUTPERFORM", "MEET EXPECTATIONS", "UNDERPERFORM")


@dataclass(frozen=True)
class DraftSettings:
    league_size: int = 12
    current_pick: int = 1
    next_pick: int = 24
    scoring_format: str = "ppr"
    draft_type: str = "snake"


def normalize_name(name: str) -> str:
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in name)
    return " ".join(part for part in cleaned.split() if part not in suffixes)


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


def snake_next_pick(current_pick: int, draft_slot: int, league_size: int) -> int:
    if current_pick < 1 or draft_slot < 1 or draft_slot > league_size:
        raise ValueError("invalid draft state")
    pick = current_pick + 1
    while True:
        round_index = (pick - 1) // league_size
        pick_in_round = ((pick - 1) % league_size) + 1
        owner_slot = pick_in_round if round_index % 2 == 0 else league_size - pick_in_round + 1
        if owner_slot == draft_slot:
            return pick
        pick += 1


def validate_adp_rows(rows: list[dict[str, Any]]) -> None:
    required = {"season", "snapshot_date", "provider", "platform", "scoring_format", "league_size", "draft_type", "player_id", "player_name", "position", "team", "adp"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"ADP rows missing columns: {sorted(missing)}")
    seen = set()
    for row in rows:
        key = (row["season"], row["snapshot_date"], row["provider"], row["platform"], row["player_id"], row["scoring_format"], row["league_size"], row["draft_type"])
        if key in seen:
            raise ValueError(f"duplicate ADP observation: {key}")
        seen.add(key)
        float(row["adp"])


def validate_outcome_rows(rows: list[dict[str, Any]]) -> None:
    required = {"season", "player_id", "actual_value", "games_played", "points_per_game", "starter_weeks", "replacement_value"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"outcome rows missing columns: {sorted(missing)}")


def consensus_adp(adp_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validate_adp_rows(adp_rows)
    grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in adp_rows:
        key = (int(row["season"]), row["player_id"], row["scoring_format"], int(row["league_size"]), row["draft_type"])
        grouped[key].append(row)
    results = []
    for (season, player_id, scoring, league_size, draft_type), values in grouped.items():
        adps = sorted(float(row["adp"]) for row in values)
        first = values[0]
        results.append(
            {
                "season": season,
                "player_id": player_id,
                "player_name": first["player_name"],
                "normalized_name": normalize_name(first["player_name"]),
                "position": first["position"],
                "team": first["team"],
                "scoring_format": scoring,
                "league_size": league_size,
                "draft_type": draft_type,
                "consensus_adp": round(median(adps), 2),
                "earliest_adp": min(adps),
                "latest_adp": max(adps),
                "adp_range": round(max(adps) - min(adps), 2),
                "adp_stddev": round(pstdev(adps), 3) if len(adps) > 1 else 0.0,
                "platform_count": len({row["platform"] for row in values}),
                "snapshot_date": max(row["snapshot_date"] for row in values),
                "providers": ",".join(sorted({row["provider"] for row in values})),
                "redistribution": "fixture data only; production ADP source terms must be reviewed",
            }
        )
    return sorted(results, key=lambda row: (row["season"], row["consensus_adp"]))


def _position_rank(rows: list[dict[str, Any]]) -> dict[str, int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["position"]].append(row)
    ranks = {}
    for values in grouped.values():
        for rank, row in enumerate(sorted(values, key=lambda item: item["consensus_adp"]), 1):
            ranks[row["player_id"]] = rank
    return ranks


def expected_value_curve(training_rows: list[dict[str, Any]]) -> dict[str, Any]:
    curves: dict[str, list[dict[str, float]]] = {}
    for position in sorted({row["position"] for row in training_rows}):
        values = [row for row in training_rows if row["position"] == position]
        buckets: dict[int, list[float]] = defaultdict(list)
        for row in values:
            bucket = int((float(row["consensus_adp"]) - 1) // 24) + 1
            buckets[bucket].append(float(row["actual_vor"]))
        points = []
        prior = mean(float(row["actual_vor"]) for row in values)
        running = prior
        for bucket in sorted(buckets):
            running = min(running, mean(buckets[bucket])) if points else mean(buckets[bucket])
            ordered = sorted(buckets[bucket])
            points.append({"bucket": bucket, "expected_vor": round(running, 3), "lower": ordered[0], "median": median(ordered), "upper": ordered[-1], "sample_size": len(ordered)})
        curves[position] = points
    return curves


def expected_vor_at_adp(curves: dict[str, Any], position: str, adp: float) -> float:
    buckets = curves.get(position) or []
    if not buckets:
        return 0.0
    bucket = int((adp - 1) // 24) + 1
    closest = min(buckets, key=lambda item: abs(item["bucket"] - bucket))
    return float(closest["expected_vor"])


def build_draft_dataset(adp_rows: list[dict[str, Any]], outcome_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validate_outcome_rows(outcome_rows)
    adp = consensus_adp(adp_rows)
    ranks = _position_rank(adp)
    outcomes = {(int(row["season"]), row["player_id"]): row for row in outcome_rows}
    joined = []
    for row in adp:
        outcome = outcomes.get((row["season"], row["player_id"]))
        if not outcome:
            continue
        actual_value = float(outcome["actual_value"])
        replacement = float(outcome["replacement_value"])
        actual_vor = actual_value - replacement
        joined.append(
            {
                **row,
                "position_adp": ranks[row["player_id"]],
                "actual_value": actual_value,
                "games_played": int(outcome["games_played"]),
                "points_per_game": float(outcome["points_per_game"]),
                "starter_weeks": int(outcome["starter_weeks"]),
                "replacement_value": replacement,
                "actual_vor": round(actual_vor, 3),
                "performance_component": float(outcome["points_per_game"]),
                "availability_component": int(outcome["games_played"]),
                "age": float(outcome.get("age", 26) or 26),
                "experience": float(outcome.get("experience", 3) or 3),
                "games_played_prev": float(outcome.get("games_played_prev", 12) or 12),
                "phase2_expected": float(outcome.get("phase2_expected", 10) or 10),
                "phase2_uncertainty": float(outcome.get("phase2_uncertainty", 5) or 5),
            }
        )
    curves = expected_value_curve([row for row in joined if row["season"] < max(r["season"] for r in joined)])
    residuals = []
    for row in joined:
        expected = expected_vor_at_adp(curves, row["position"], row["consensus_adp"])
        residual = row["actual_vor"] - expected
        row["expected_value_at_adp"] = round(expected, 3)
        row["adp_relative_residual"] = round(residual, 3)
        residuals.append(residual)
    thresholds = fit_outcome_thresholds([row for row in joined if row["season"] < max(r["season"] for r in joined)])
    for row in joined:
        row["outcome_class"] = classify_residual(row["adp_relative_residual"], thresholds[row["position"]])
    return joined


def fit_outcome_thresholds(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    thresholds = {}
    for position in sorted({row["position"] for row in rows}):
        residuals = sorted(float(row["adp_relative_residual"]) for row in rows if row["position"] == position)
        if not residuals:
            thresholds[position] = {"underperform_lt": -5.0, "outperform_gt": 5.0}
            continue
        lower = residuals[max(0, int(len(residuals) * 0.33) - 1)]
        upper = residuals[min(len(residuals) - 1, int(len(residuals) * 0.67))]
        if lower >= upper:
            lower, upper = lower - 1.0, upper + 1.0
        thresholds[position] = {"underperform_lt": round(lower, 3), "outperform_gt": round(upper, 3)}
    return thresholds


def classify_residual(residual: float, thresholds: dict[str, float]) -> str:
    if residual < thresholds["underperform_lt"]:
        return "UNDERPERFORM"
    if residual > thresholds["outperform_gt"]:
        return "OUTPERFORM"
    return "MEET EXPECTATIONS"


def dataset_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    max_score = max(scores.values())
    exps = {key: math.exp(value - max_score) for key, value in scores.items()}
    total = sum(exps.values())
    return {key: value / total for key, value in exps.items()}


def train_draft_artifact(rows: list[dict[str, Any]], artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    train_rows = [row for row in rows if int(row["season"]) <= 2023]
    test_rows = [row for row in rows if int(row["season"]) >= 2024]
    thresholds = fit_outcome_thresholds(train_rows)
    curves = expected_value_curve(train_rows)
    residual_prior = {position: mean([float(row["adp_relative_residual"]) for row in train_rows if row["position"] == position]) for position in sorted({row["position"] for row in train_rows})}
    class_rates = {}
    for position in sorted({row["position"] for row in train_rows}):
        values = [row for row in train_rows if row["position"] == position]
        class_rates[position] = {klass: (sum(row["outcome_class"] == klass for row in values) + 1) / (len(values) + len(OUTCOME_CLASSES)) for klass in OUTCOME_CLASSES}
    artifact = {
        "metadata": {
            "model_version": DRAFT_MODEL_VERSION,
            "model_type": "fixture_smoothed_adp_residual_model",
            "target": "ADP-relative residual in value over replacement",
            "feature_names": DRAFT_FEATURES,
            "training_period": "fixture seasons through 2023",
            "validation_period": "not separate in fixture; production must use chronological validation",
            "test_period": "fixture 2024",
            "adp_sources": ["fixture_platform_a", "fixture_platform_b"],
            "scoring_format": "ppr",
            "league_assumptions": "12-team managed snake draft",
            "dataset_fingerprint": dataset_fingerprint(rows),
            "calibration_method": "training class-rate smoothing plus residual distance heuristic",
            "created_at": datetime.now(UTC).isoformat(),
        },
        "thresholds": thresholds,
        "expected_value_curves": curves,
        "residual_prior": residual_prior,
        "class_rates": class_rates,
    }
    artifact["evaluation"] = evaluate_draft_artifact(artifact, test_rows)
    (artifact_dir / "draft_model.json").write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    (artifact_dir / "evaluation.json").write_text(json.dumps(artifact["evaluation"], indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def predict_draft_player(artifact: dict[str, Any], player_row: dict[str, Any], settings: DraftSettings | None = None) -> dict[str, Any]:
    settings = settings or DraftSettings()
    adp = float(player_row["consensus_adp"])
    position = player_row["position"]
    expected_at_cost = expected_vor_at_adp(artifact["expected_value_curves"], position, adp)
    expected_vor = float(player_row.get("expected_vor", player_row.get("actual_vor", expected_at_cost)))
    residual = expected_vor - expected_at_cost + float(artifact["residual_prior"].get(position, 0))
    thresholds = artifact["thresholds"].get(position, {"underperform_lt": -5, "outperform_gt": 5})
    rates = artifact["class_rates"].get(position, {klass: 1 / 3 for klass in OUTCOME_CLASSES})
    scores = {
        "OUTPERFORM": rates["OUTPERFORM"] + max(0, residual - thresholds["outperform_gt"]) / 20,
        "MEET EXPECTATIONS": rates["MEET EXPECTATIONS"] - abs(residual) / 60,
        "UNDERPERFORM": rates["UNDERPERFORM"] + max(0, thresholds["underperform_lt"] - residual) / 20,
    }
    probs = _softmax(scores)
    availability = availability_at_next_pick(adp, float(player_row.get("adp_stddev", 8) or 8), settings.next_pick)
    return {
        "player_id": player_row["player_id"],
        "player_name": player_row["player_name"],
        "position": position,
        "team": player_row.get("team", ""),
        "consensus_adp": round(adp, 2),
        "expected_vor": round(expected_vor, 2),
        "expected_value_at_adp": round(expected_at_cost, 2),
        "adp_relative_value": round(residual, 2),
        "outperform_probability": round(probs["OUTPERFORM"], 3),
        "meet_probability": round(probs["MEET EXPECTATIONS"], 3),
        "underperform_probability": round(probs["UNDERPERFORM"], 3),
        "performance_risk": round(max(0, float(player_row.get("phase2_uncertainty", 5)) / 20), 3),
        "availability_risk": round(max(0, 1 - float(player_row.get("games_played_prev", 12)) / 17), 3),
        "available_next_pick_probability": availability["probability_available"],
        "selected_before_next_pick_probability": availability["probability_selected_before"],
        "expected_selection_range": availability["expected_selection_range"],
        "availability_method": availability["method"],
        "confidence": "fixture-limited",
        "model_version": artifact["metadata"]["model_version"],
    }


def availability_at_next_pick(adp: float, adp_stddev: float, next_pick: int) -> dict[str, Any]:
    spread = max(4.0, adp_stddev or 8.0)
    z = (next_pick - adp) / spread
    probability = 1 / (1 + math.exp(-z))
    return {
        "probability_available": round(probability, 3),
        "probability_selected_before": round(1 - probability, 3),
        "expected_selection_range": f"{max(1, round(adp - spread))}-{round(adp + spread)}",
        "method": "ADP dispersion approximation; not a learned survival model",
        "sample_size": None,
        "freshness": "fixture snapshot",
    }


def assign_tiers(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in predictions:
        by_position[row["position"]].append(row)
    tiered = []
    for position, rows in by_position.items():
        rows = sorted(rows, key=lambda row: row["expected_vor"], reverse=True)
        tier = 1
        previous = None
        for row in rows:
            gap = 0 if previous is None else previous["expected_vor"] - row["expected_vor"]
            if previous is not None and gap >= 4:
                tier += 1
            tiered.append({**row, "tier": tier, "gap_to_previous_tier": round(gap, 2)})
            previous = row
    return sorted(tiered, key=lambda row: (-row["expected_vor"], row["consensus_adp"]))


def evaluate_draft_artifact(artifact: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"sample_size": 0}
    predictions = []
    for row in rows:
        pred = predict_draft_player(artifact, row)
        predicted_class = max({"OUTPERFORM": pred["outperform_probability"], "MEET EXPECTATIONS": pred["meet_probability"], "UNDERPERFORM": pred["underperform_probability"]}, key=lambda k: {"OUTPERFORM": pred["outperform_probability"], "MEET EXPECTATIONS": pred["meet_probability"], "UNDERPERFORM": pred["underperform_probability"]}[k])
        predictions.append((pred, predicted_class, row["outcome_class"], float(row["adp_relative_residual"])))
    mae = mean(abs(pred["adp_relative_value"] - actual) for pred, _, _, actual in predictions)
    brier = mean(sum(((pred[f"{klass.lower().split()[0]}_probability"] if klass != "MEET EXPECTATIONS" else pred["meet_probability"]) - (1 if actual == klass else 0)) ** 2 for klass in OUTCOME_CLASSES) for pred, _, actual, _ in predictions)
    accuracy = mean(predicted == actual for _, predicted, actual, _ in predictions)
    adp_baseline_mae = mean(abs(0 - actual) for _, _, _, actual in predictions)
    return {
        "sample_size": len(rows),
        "residual_mae": round(mae, 3),
        "adp_baseline_mae": round(adp_baseline_mae, 3),
        "baseline_improvement_pct": round(((adp_baseline_mae - mae) / adp_baseline_mae) * 100, 2) if adp_baseline_mae else 0,
        "multiclass_brier": round(brier, 3),
        "macro_accuracy_fixture": round(accuracy, 3),
    }


class DraftIntelligenceService:
    def __init__(self, artifact_dir: Path | None = None):
        self.artifact_dir = artifact_dir or Path(__file__).resolve().parents[2] / "models" / "draft" / "latest"
        self._artifact: dict[str, Any] | None | bool = False

    def load_artifact(self) -> dict[str, Any] | None:
        if self._artifact is not False:
            return self._artifact
        path = self.artifact_dir / "draft_model.json"
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            if artifact["metadata"]["model_version"] != DRAFT_MODEL_VERSION:
                raise ValueError("incompatible draft model")
        except Exception:
            artifact = None
        self._artifact = artifact
        return artifact

    def current_board(self, league: League, settings: DraftSettings, drafted_ids: set[str] | None = None) -> list[dict[str, Any]]:
        artifact = self.load_artifact()
        players = [p for t in league.teams for p in t.players] + league.free_agents
        drafted_ids = drafted_ids or set()
        board_rows = []
        for index, player in enumerate(players, 1):
            if player.id in drafted_ids or player.position not in {"QB", "RB", "WR", "TE"}:
                continue
            projection = DEFAULT_PROJECTION_SERVICE.project_player(player, league=league, week=league.week)
            fallback_adp = index * 8 + {"QB": 18, "RB": 4, "WR": 6, "TE": 24}.get(player.position, 50)
            row = {
                "player_id": player.id,
                "player_name": player.name,
                "position": player.position,
                "team": player.team,
                "consensus_adp": fallback_adp,
                "position_adp": index,
                "adp_stddev": 10,
                "expected_vor": projection.mean * 14 - replacement_level(league, player.position),
                "phase2_uncertainty": max(1, projection.ceiling - projection.floor),
                "games_played_prev": 12,
            }
            if artifact:
                board_rows.append(predict_draft_player(artifact, row, settings))
            else:
                board_rows.append({**row, "fallback_used": True, "fallback_reason": "Draft artifact unavailable", "available_next_pick_probability": availability_at_next_pick(fallback_adp, 10, settings.next_pick)["probability_available"], "tier": None})
        return assign_tiers(board_rows) if artifact else sorted(board_rows, key=lambda r: r["expected_vor"], reverse=True)


def replacement_level(league: League, position: str) -> float:
    teams = max(1, len(league.teams))
    slot_count = sum(1 for slot in league.roster_slots if slot == position)
    flex_share = 0.35 if position in {"RB", "WR", "TE"} and "FLEX" in league.roster_slots else 0
    superflex_share = 0.5 if position == "QB" and "SUPERFLEX" in league.roster_slots else 0
    starters = teams * max(1, slot_count + flex_share + superflex_share)
    all_players = [p for t in league.teams for p in t.players if p.position == position] + [p for p in league.free_agents if p.position == position]
    values = sorted((p.mean * 14 for p in all_players), reverse=True)
    index = min(len(values) - 1, max(0, int(starters) - 1))
    return values[index] if values else 0.0


DEFAULT_DRAFT_SERVICE = DraftIntelligenceService()
