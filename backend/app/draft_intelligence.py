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
    if current_pick < 0 or draft_slot < 1 or draft_slot > league_size:
        raise ValueError("invalid draft state")
    pick = current_pick + 1
    while True:
        round_index = (pick - 1) // league_size
        pick_in_round = ((pick - 1) % league_size) + 1
        owner_slot = pick_in_round if round_index % 2 == 0 else league_size - pick_in_round + 1
        if owner_slot == draft_slot:
            return pick
        pick += 1


def league_draft_type(league: League) -> str:
    draft = league.raw_settings.get("draftSettings", {}) if isinstance(league.raw_settings, dict) else {}
    raw_type = str(draft.get("type") or draft.get("draftType") or "SNAKE").upper()
    if any(label in raw_type for label in ("AUCTION", "SALARY")):
        return "auction"
    if any(label in raw_type for label in ("LINEAR", "STANDARD")):
        return "linear"
    return "snake"


def league_team_count(league: League) -> int:
    """Prefer ESPN's configured league size; the team list can be partial pre-draft."""
    configured = league.raw_settings.get("size") if isinstance(league.raw_settings, dict) else None
    try:
        size = int(configured)
    except (TypeError, ValueError):
        size = len(league.teams)
    return max(2, size or len(league.teams) or 12)


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
        drafted_ids = drafted_ids or set()
        players = [
            player
            for player in league.free_agents
            if player.id not in drafted_ids
            and player.position in {"QB", "RB", "WR", "TE"}
            and (player.average_draft_position is not None or player.espn_rank is not None)
        ]
        if not players:
            return []
        replacement = {
            position: replacement_level(league, position, season=True)
            for position in {player.position for player in players}
        }
        base_rows = []
        for player in players:
            season_value = float(player.season_projection) if player.season_projection is not None else None
            vor = season_value - replacement.get(player.position, 0) if season_value is not None else None
            market_pick = float(player.average_draft_position or player.espn_rank or 9999)
            base_rows.append(
                {
                    "player_id": player.id,
                    "player_name": player.name,
                    "position": player.position,
                    "team": player.team,
                    "consensus_adp": round(market_pick, 2),
                    "adp_available": player.average_draft_position is not None,
                    "espn_rank": player.espn_rank,
                    "percent_owned": player.percent_owned,
                    "injury_status": player.injury_status,
                    "season_projection": round(season_value, 2) if season_value is not None else None,
                    "expected_vor": round(vor, 2) if vor is not None else None,
                }
            )
        projected = [row for row in base_rows if row["expected_vor"] is not None]
        if projected:
            projected_order = sorted(projected, key=lambda row: row["expected_vor"], reverse=True)
            projection_rank = {row["player_id"]: rank for rank, row in enumerate(projected_order, 1)}
            for row in base_rows:
                market_rank = row["consensus_adp"]
                row["composite_rank"] = (market_rank + projection_rank.get(row["player_id"], market_rank)) / 2
        else:
            for row in base_rows:
                row["composite_rank"] = row["consensus_adp"]
        by_value = sorted(base_rows, key=lambda row: (row["composite_rank"], row["consensus_adp"]))
        value_rank = {row["player_id"]: rank for rank, row in enumerate(by_value, 1)}
        for row in base_rows:
            row["value_rank"] = value_rank[row["player_id"]]
            row["adp_relative_value"] = round(row["consensus_adp"] - row["value_rank"], 2)
            row["tier"] = 1 + (row["value_rank"] - 1) // max(1, settings.league_size)
            if row["season_projection"] is not None and row["adp_available"]:
                row["confidence"] = "ESPN live ADP + season projection"
            elif row["season_projection"] is not None:
                row["confidence"] = "ESPN draft rank + season projection"
            else:
                row["confidence"] = "ESPN live draft rank; season projection unavailable"
            row["availability_method"] = "ESPN average draft position; no fabricated next-pick probability"
            row["fallback_used"] = False
        return sorted(base_rows, key=lambda row: (row["value_rank"], row["consensus_adp"]))

    def pick_plan(
        self,
        league: League,
        settings: DraftSettings,
        drafted_ids: set[str],
        user_drafted_positions: list[str],
        backup_count: int = 5,
        strategy: str = "balanced",
        recent_drafted_positions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank the best current pick and backups from live ESPN values only."""
        board = self.current_board(league, settings, drafted_ids)
        if not board:
            return []
        roster_targets = {
            position: sum(1 for slot in league.roster_slots if slot == position)
            for position in ("QB", "RB", "WR", "TE")
        }
        if "FLEX" in league.roster_slots:
            roster_targets["RB"] += 1
            roster_targets["WR"] += 1
        counts = {position: user_drafted_positions.count(position) for position in roster_targets}
        strategy = strategy if strategy in {"safe", "balanced", "aggressive"} else "balanced"
        round_number = 1 + (settings.current_pick - 1) // max(1, settings.league_size)
        is_superflex = "SUPERFLEX" in league.roster_slots
        recent = list(recent_drafted_positions or [])[-6:]
        scored = []
        for row in board:
            position = row["position"]
            need = max(0, roster_targets.get(position, 1) - counts.get(position, 0))
            need_bonus = min(3.0, need * 1.25)
            if position == "QB" and not is_superflex and round_number <= 4:
                need_bonus *= 0.35
            if counts.get(position, 0) >= roster_targets.get(position, 1) and position in {"QB", "TE"} and round_number < 9:
                need_bonus -= 2.0
            urgency = max(0.0, min(4.0, (settings.next_pick - row["consensus_adp"]) / max(2, settings.league_size)))
            run_bonus = min(2.0, recent.count(position) * 0.45) if recent.count(position) >= 2 else 0
            wait_penalty = max(0.0, (row["consensus_adp"] - settings.next_pick) / max(2, settings.league_size))
            value_score = max(-4.0, min(6.0, row["adp_relative_value"] / max(2, settings.league_size / 2)))
            projection_component = row["expected_vor"] / 20 if row["expected_vor"] is not None else max(0, 4 - row["consensus_adp"] / max(12, settings.league_size * 2))
            injury_penalty = 2.5 if row.get("injury_status") in {"OUT", "INJURY RESERVE", "DOUBTFUL"} else 0.75 if row.get("injury_status") == "QUESTIONABLE" else 0
            missing_projection_penalty = 1.5 if row["season_projection"] is None else 0
            if strategy == "safe":
                score = projection_component * 1.35 + need_bonus * 1.15 + urgency * 0.9 + value_score * 0.45 + run_bonus * 0.7 - wait_penalty * 1.2 - injury_penalty * 1.5 - missing_projection_penalty
            elif strategy == "aggressive":
                score = projection_component * 0.8 + need_bonus * 0.65 + urgency * 1.15 + value_score * 1.5 + run_bonus * 1.2 - wait_penalty * 0.35 - injury_penalty * 0.45 - missing_projection_penalty * 0.25
            else:
                score = projection_component + need_bonus + urgency + value_score + run_bonus - wait_penalty * 0.75 - injury_penalty - missing_projection_penalty * 0.5
            reason = (
                f"{strategy.title()} strategy; ESPN ADP/rank {row['consensus_adp']}; value rank {row['value_rank']}; "
                f"{position} roster need {need}; recent {position} picks {recent.count(position)}; round {round_number}; next scheduled pick {settings.next_pick}."
            )
            scored.append({**row, "pick_score": round(score, 2), "strategy": strategy, "recommendation_reason": reason})
        return sorted(scored, key=lambda row: (row["pick_score"], row["expected_vor"] or 0), reverse=True)[: backup_count + 1]

    def draft_insights(
        self,
        league: League,
        settings: DraftSettings,
        drafted_ids: set[str],
        user_drafted_positions: list[str],
        strategy: str = "balanced",
        recent_drafted_positions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build live, roster-aware draft groups without inventing unavailable data."""
        board = self.current_board(league, settings, drafted_ids)
        if not board:
            return {"needs": [], "best": [], "strong": [], "sleepers": []}

        starter_targets = {
            position: sum(1 for slot in league.roster_slots if slot == position)
            for position in ("QB", "RB", "WR", "TE")
        }
        if "FLEX" in league.roster_slots:
            # FLEX creates a shared RB/WR need; do not pretend it is two required starters.
            rb_count = user_drafted_positions.count("RB")
            wr_count = user_drafted_positions.count("WR")
            starter_targets["RB" if rb_count <= wr_count else "WR"] += 1
        if "SUPERFLEX" in league.roster_slots:
            starter_targets["QB"] += 1

        counts = {position: user_drafted_positions.count(position) for position in starter_targets}
        round_number = 1 + (settings.current_pick - 1) // max(1, settings.league_size)
        needs = []
        for position, target in starter_targets.items():
            filled = counts.get(position, 0)
            gap = max(0, target - filled)
            board_at_position = [row for row in board if row["position"] == position]
            top_vor = next((row["expected_vor"] for row in board_at_position if row["expected_vor"] is not None), 0)
            priority_score = gap * 10 + top_vor / 20
            if gap:
                label = "STARTER NEEDED"
            elif position in {"RB", "WR"} and round_number >= 5 and filled < target + 2:
                label = "DEPTH NEEDED"
                priority_score += 2
            else:
                label = "FILLED"
            needs.append({"position": position, "filled": filled, "target": target, "gap": gap, "priority": label, "priority_score": round(priority_score, 2)})
        needs.sort(key=lambda row: (row["priority_score"], row["gap"]), reverse=True)

        plan = self.pick_plan(league, settings, drafted_ids, user_drafted_positions, backup_count=9, strategy=strategy, recent_drafted_positions=recent_drafted_positions)
        strong = sorted(board, key=lambda row: row["value_rank"])[:8]
        sleeper_pool = [
            row for row in board
            if row["adp_relative_value"] >= max(6, settings.league_size / 2)
            and row["consensus_adp"] >= settings.current_pick + max(6, settings.league_size // 2)
            and row["expected_vor"] is not None
            and row["expected_vor"] > 0
        ]
        sleepers = sorted(sleeper_pool, key=lambda row: (row["adp_relative_value"], row["expected_vor"]), reverse=True)[:8]
        return {
            "needs": needs,
            "best": plan,
            "strong": strong,
            "sleepers": sleepers,
            "round": round_number,
            "method": "Live ESPN season projection, ADP, value over replacement, roster slots, and recorded picks",
        }

    def overall_pick_plan(
        self,
        league: League,
        draft_slot: int,
        rounds: int = 8,
        keeper_positions: list[str] | None = None,
        strategy: str = "balanced",
    ) -> list[dict[str, Any]]:
        """Create a pre-draft slot plan; availability is an ADP window, not a promise."""
        league_size = league_team_count(league)
        draft_slot = min(max(1, draft_slot), league_size)
        chosen_ids: set[str] = set()
        positions = list(keeper_positions or [])
        recommendations: list[dict[str, Any]] = []
        previous_pick = 0
        for round_number in range(1, rounds + 1):
            pick_number = snake_next_pick(previous_pick, draft_slot, league_size)
            next_pick = snake_next_pick(pick_number, draft_slot, league_size)
            board = self.current_board(league, DraftSettings(league_size=league_size, current_pick=pick_number, next_pick=next_pick), chosen_ids)
            likely_gone = {
                row["player_id"]
                for row in board
                if row["consensus_adp"] < pick_number - max(3, league_size * 0.45)
            }
            plan = self.pick_plan(
                league,
                DraftSettings(league_size=league_size, current_pick=pick_number, next_pick=next_pick),
                chosen_ids | likely_gone,
                positions,
                backup_count=3,
                strategy=strategy,
            )
            if not plan:
                break
            choice = plan[0]
            recommendations.append({**choice, "round": round_number, "overall_pick": pick_number, "backups": [row["player_name"] for row in plan[1:4]]})
            chosen_ids.add(choice["player_id"])
            positions.append(choice["position"])
            previous_pick = pick_number
        return recommendations


def replacement_level(league: League, position: str, *, season: bool = False) -> float:
    teams = league_team_count(league)
    slot_count = sum(1 for slot in league.roster_slots if slot == position)
    flex_share = 0.35 if position in {"RB", "WR", "TE"} and "FLEX" in league.roster_slots else 0
    superflex_share = 0.5 if position == "QB" and "SUPERFLEX" in league.roster_slots else 0
    starters = teams * max(1, slot_count + flex_share + superflex_share)
    all_players = [p for t in league.teams for p in t.players if p.position == position] + [p for p in league.free_agents if p.position == position]
    values = sorted(
        (
            float(p.season_projection)
            if season and p.season_projection is not None
            else p.mean * 14
            for p in all_players
            if not season or p.season_projection is not None
        ),
        reverse=True,
    )
    index = min(len(values) - 1, max(0, int(starters) - 1))
    return values[index] if values else 0.0


DEFAULT_DRAFT_SERVICE = DraftIntelligenceService()
