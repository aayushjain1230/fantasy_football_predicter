from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Literal

from pydantic import BaseModel, Field

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


class DraftConfiguration(BaseModel):
    league_size: int = Field(ge=4, le=20)
    draft_type: Literal["snake", "linear", "auction"]
    draft_slot: int | None = None
    current_overall_pick: int = Field(default=1, ge=1)
    total_rounds: int = Field(default=16, ge=1, le=30)
    scoring_format: str
    scoring_rules: dict[str, float] = Field(default_factory=dict)
    starting_slots: list[str] = Field(default_factory=list)
    bench_slots: int = Field(default=0, ge=0)
    ir_slots: int = Field(default=0, ge=0)
    flex_eligible_positions: set[str] = Field(default_factory=lambda: {"RB", "WR", "TE"})
    superflex_eligible_positions: set[str] = Field(default_factory=lambda: {"QB", "RB", "WR", "TE"})
    keeper_player_ids: set[str] = Field(default_factory=set)
    keeper_costs: dict[str, int] = Field(default_factory=dict)
    roster_limits: dict[str, int] = Field(default_factory=dict)
    user_owned_picks: list[int] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unsupported_settings: list[str] = Field(default_factory=list)
    sources: dict[str, str] = Field(default_factory=dict)
    manager_count_confirmed: bool = False
    draft_slot_confirmed: bool = False


class DraftSetupResolution(BaseModel):
    value: int | None = None
    source: Literal["espn_settings", "espn_teams", "espn_draft_order", "espn_live_draft", "manual", "unavailable"] = "unavailable"
    confirmed: bool = False
    conflict_values: list[int] = Field(default_factory=list)
    message: str = ""


class DraftSelection(BaseModel):
    overall_pick: int = Field(ge=1)
    round_number: int = Field(ge=1)
    pick_in_round: int = Field(ge=1)
    owner_slot: int = Field(ge=1)
    player_id: str
    player_name: str
    position: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "manual"


class DraftState(BaseModel):
    configuration: DraftConfiguration
    selections: list[DraftSelection] = Field(default_factory=list)
    current_overall_pick: int = Field(default=1, ge=1)

    @property
    def drafted_player_ids(self) -> set[str]:
        return {selection.player_id for selection in self.selections}

    @property
    def next_user_pick(self) -> int | None:
        if self.configuration.draft_slot is None:
            return None
        return next_owned_pick(self.current_overall_pick, self.configuration.draft_slot, self.configuration.league_size, self.configuration.draft_type)

    def record(self, selection: DraftSelection) -> "DraftState":
        if selection.player_id in self.drafted_player_ids:
            raise ValueError("PLAYER_ALREADY_DRAFTED")
        if selection.overall_pick != self.current_overall_pick:
            raise ValueError("PICK_OUT_OF_SEQUENCE")
        return self.model_copy(update={"selections": [*self.selections, selection], "current_overall_pick": selection.overall_pick + 1})

    def undo(self) -> "DraftState":
        if not self.selections:
            return self
        return self.model_copy(update={"selections": self.selections[:-1], "current_overall_pick": self.selections[-1].overall_pick})

    def correct(self, overall_pick: int, selection: DraftSelection) -> "DraftState":
        if overall_pick < 1 or overall_pick >= self.current_overall_pick:
            raise ValueError("PICK_NOT_RECORDED")
        existing = next((item for item in self.selections if item.overall_pick == overall_pick), None)
        if existing is None:
            raise ValueError("PICK_NOT_RECORDED")
        if any(item.player_id == selection.player_id and item.overall_pick != overall_pick for item in self.selections):
            raise ValueError("PLAYER_ALREADY_DRAFTED")
        corrected = [selection if item.overall_pick == overall_pick else item for item in self.selections]
        return self.model_copy(update={"selections": corrected})

    def reset(self, *, confirmed: bool = False) -> "DraftState":
        if not confirmed:
            raise ValueError("RESET_CONFIRMATION_REQUIRED")
        return self.model_copy(update={"selections": [], "current_overall_pick": 1})


SLOT_ELIGIBILITY = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"}, "SUPERFLEX": {"QB", "RB", "WR", "TE"},
    "DST": {"DST"}, "K": {"K"},
}


def owner_of_pick(overall_pick: int, league_size: int, draft_type: str) -> int:
    if overall_pick < 1 or league_size < 2 or draft_type == "auction":
        raise ValueError("pick ownership is unavailable")
    pick_in_round = (overall_pick - 1) % league_size + 1
    round_number = (overall_pick - 1) // league_size + 1
    return league_size - pick_in_round + 1 if draft_type == "snake" and round_number % 2 == 0 else pick_in_round


def pick_for_slot(round_number: int, draft_slot: int, league_size: int, draft_type: str) -> int:
    if round_number < 1 or not 1 <= draft_slot <= league_size or draft_type == "auction":
        raise ValueError("invalid draft order")
    pick_in_round = league_size - draft_slot + 1 if draft_type == "snake" and round_number % 2 == 0 else draft_slot
    return (round_number - 1) * league_size + pick_in_round


def picks_for_slot(draft_slot: int, league_size: int, rounds: int, draft_type: str) -> list[int]:
    if draft_type == "auction":
        return []
    return [pick_for_slot(round_number, draft_slot, league_size, draft_type) for round_number in range(1, rounds + 1)]


def live_draft_started(completed_picks: list[dict[str, Any]], manual_started: bool = False) -> bool:
    return bool(completed_picks or manual_started)


def ignored_for_current_pick(ignored_player_ids: set[str], previous_pick: int, current_pick: int) -> set[str]:
    return set(ignored_player_ids) if previous_pick == current_pick else set()


def next_owned_pick(current_overall_pick: int, draft_slot: int, league_size: int, draft_type: str) -> int | None:
    if draft_type == "auction":
        return None
    start_round = max(1, (max(1, current_overall_pick) - 1) // league_size + 1)
    for round_number in range(start_round, start_round + 31):
        pick = pick_for_slot(round_number, draft_slot, league_size, draft_type)
        if pick >= current_overall_pick:
            return pick
    return None


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
    pick = next_owned_pick(current_pick + 1, draft_slot, league_size, "snake")
    if pick is None:
        raise ValueError("no future pick")
    return pick


def league_draft_type(league: League) -> str:
    draft = league.raw_settings.get("draftSettings", {}) if isinstance(league.raw_settings, dict) else {}
    raw_type = str(draft.get("type") or draft.get("draftType") or "SNAKE").upper()
    if any(label in raw_type for label in ("AUCTION", "SALARY")):
        return "auction"
    if any(label in raw_type for label in ("LINEAR", "STANDARD")):
        return "linear"
    return "snake"


def league_team_count(league: League) -> int:
    """Compatibility helper. New UI must use resolve_manager_count and confirmation."""
    configured = league.raw_settings.get("size") if isinstance(league.raw_settings, dict) else None
    try:
        size = int(configured)
    except (TypeError, ValueError):
        size = len(league.teams)
    return max(2, size or len(league.teams) or 12)


def resolve_manager_count(league: League, manual_value: int | None = None, *, manual_confirmed: bool = False) -> DraftSetupResolution:
    settings = league.raw_settings if isinstance(league.raw_settings, dict) else {}
    configured = settings.get("size")
    try:
        espn_size = int(configured)
        if not 4 <= espn_size <= 20:
            espn_size = None
    except (TypeError, ValueError):
        espn_size = None
    team_count = len({team.id for team in league.teams if team.id})
    team_count = team_count if 4 <= team_count <= 20 else None
    if manual_confirmed and manual_value is not None:
        value = min(20, max(4, int(manual_value)))
        return DraftSetupResolution(value=value, source="manual", confirmed=True, message="Confirmed by you.")
    if espn_size and team_count and espn_size != team_count:
        return DraftSetupResolution(value=None, source="unavailable", confirmed=False, conflict_values=sorted({team_count, espn_size}), message=f"ESPN reports {espn_size} managers, but {team_count} teams were returned.")
    if espn_size:
        return DraftSetupResolution(value=espn_size, source="espn_settings", confirmed=False, message=f"ESPN settings report {espn_size} managers. Please confirm.")
    if team_count:
        return DraftSetupResolution(value=team_count, source="espn_teams", confirmed=False, message=f"ESPN returned {team_count} unique teams. Please confirm the league is fully populated.")
    return DraftSetupResolution(message="ESPN did not provide a reliable manager count. Enter it manually.")


def resolve_draft_slot(league: League, manual_value: int | None = None, *, manual_confirmed: bool = False) -> DraftSetupResolution:
    settings = league.raw_settings if isinstance(league.raw_settings, dict) else {}
    order = settings.get("_draft_order") or {}
    live_order = settings.get("_live_draft_order") or {}
    for source_name, values in (("espn_draft_order", order), ("espn_live_draft", live_order)):
        if isinstance(values, dict):
            raw_slot = values.get(str(league.user_team_id)) or values.get(league.user_team_id)
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                slot = 0
            if slot > 0:
                return DraftSetupResolution(value=slot, source=source_name, confirmed=False, message="ESPN published this team’s draft-order assignment. Please confirm.")
    if manual_confirmed and manual_value is not None:
        return DraftSetupResolution(value=max(1, int(manual_value)), source="manual", confirmed=True, message="Confirmed by you.")
    return DraftSetupResolution(value=manual_value, source="unavailable", confirmed=False, message="ESPN has not published your draft order yet.")


def build_draft_configuration(
    league: League,
    *,
    league_size: int | None = None,
    draft_slot: int | None = None,
    current_overall_pick: int = 1,
    total_rounds: int | None = None,
    keeper_player_ids: set[str] | None = None,
    manager_count_confirmed: bool = False,
    draft_slot_confirmed: bool = False,
    draft_type: str | None = None,
    scoring_format: str | None = None,
    starting_slots: list[str] | None = None,
    bench_slots: int | None = None,
) -> DraftConfiguration:
    settings = league.raw_settings if isinstance(league.raw_settings, dict) else {}
    counts = (settings.get("rosterSettings") or {}).get("lineupSlotCounts") or {}
    bench = int(counts.get("20", counts.get(20, 0)) or 0) if bench_slots is None else int(bench_slots)
    ir = int(counts.get("21", counts.get(21, 0)) or 0)
    size = min(20, max(4, int(league_size or league_team_count(league))))
    resolved_draft_type = draft_type or league_draft_type(league)
    scoring_items = (settings.get("scoringSettings") or {}).get("scoringItems") or []
    reception_points = next((float(item.get("points", 0) or 0) for item in scoring_items if int(item.get("statId", -1)) == 53), 0)
    resolved_scoring_format = scoring_format or ("full PPR" if reception_points >= 0.75 else "half PPR" if reception_points > 0 else "standard")
    assumptions = []
    if not counts:
        assumptions.append("ESPN did not expose bench/IR counts; editable defaults are shown.")
    resolved_slots = list(starting_slots if starting_slots is not None else league.roster_slots)
    rounds = total_rounds or max(1, len(resolved_slots) + bench)
    owned = picks_for_slot(draft_slot, size, rounds, resolved_draft_type) if draft_slot and resolved_draft_type != "auction" else []
    return DraftConfiguration(
        league_size=size,
        draft_type=resolved_draft_type,
        draft_slot=draft_slot,
        current_overall_pick=current_overall_pick,
        total_rounds=rounds,
        scoring_format=resolved_scoring_format,
        scoring_rules=league.scoring,
        starting_slots=resolved_slots,
        bench_slots=bench,
        ir_slots=ir,
        keeper_player_ids=set(keeper_player_ids or set()),
        user_owned_picks=owned,
        assumptions=assumptions,
        sources={"league_size": "ESPN settings.size", "draft_type": "ESPN draftSettings", "roster": "ESPN lineupSlotCounts", "scoring": "ESPN scoringItems"},
        manager_count_confirmed=manager_count_confirmed,
        draft_slot_confirmed=draft_slot_confirmed,
    )


def best_roster_assignment(player_positions: list[str], starting_slots: list[str]) -> dict[str, Any]:
    """Exact maximum-cardinality assignment for fixed and flexible starter slots."""
    ordered_slots = sorted(enumerate(starting_slots), key=lambda item: len(SLOT_ELIGIBILITY.get(item[1], {item[1]})))
    best: list[tuple[int, int]] = []

    def search(slot_index: int, used: set[int], assigned: list[tuple[int, int]]) -> None:
        nonlocal best
        if len(assigned) + len(ordered_slots) - slot_index <= len(best):
            return
        if slot_index == len(ordered_slots):
            if len(assigned) > len(best):
                best = list(assigned)
            return
        original_slot_index, slot = ordered_slots[slot_index]
        eligible = SLOT_ELIGIBILITY.get(slot, {slot})
        for player_index, position in enumerate(player_positions):
            if player_index not in used and position in eligible:
                search(slot_index + 1, used | {player_index}, [*assigned, (original_slot_index, player_index)])
        search(slot_index + 1, used, assigned)

    search(0, set(), [])
    assigned_slots = {slot_index for slot_index, _ in best}
    return {
        "filled": len(best),
        "assignments": [{"slot": starting_slots[slot_index], "position": player_positions[player_index], "player_index": player_index} for slot_index, player_index in sorted(best)],
        "gaps": [slot for index, slot in enumerate(starting_slots) if index not in assigned_slots],
    }


def marginal_roster_fit(player_positions: list[str], candidate_position: str, starting_slots: list[str]) -> float:
    before = best_roster_assignment(player_positions, starting_slots)["filled"]
    after = best_roster_assignment([*player_positions, candidate_position], starting_slots)["filled"]
    return float(after - before)


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
        self._mock_cache: dict[str, dict[str, float]] = {}

    def _mock_completed_roster_scores(
        self,
        candidates: list[dict[str, Any]],
        settings: DraftSettings,
        user_positions: list[str],
        starting_slots: list[str],
    ) -> dict[str, float]:
        """Fast deterministic mock evidence; opponents vary around ADP and positional runs."""
        key = hashlib.sha256(json.dumps({"players": [(row["player_id"], row["consensus_adp"], row.get("expected_vor")) for row in candidates], "settings": settings.__dict__, "positions": user_positions, "slots": starting_slots}, sort_keys=True, default=str).encode()).hexdigest()
        if key in self._mock_cache:
            return self._mock_cache[key]
        scores: dict[str, float] = {}
        for candidate in candidates[:12]:
            outcomes = []
            for simulation in range(24):
                rng = random.Random(f"{key}:{candidate['player_id']}:{simulation}")
                remaining = [row for row in candidates if row["player_id"] != candidate["player_id"]]
                roster = [*user_positions, candidate["position"]]
                value = float(candidate.get("expected_vor") or max(0, 80 - candidate["consensus_adp"]))
                selection = settings.current_pick + 1
                for _round in range(5):
                    opponent_picks = max(0, min(settings.league_size * 2, settings.next_pick - selection))
                    for _ in range(opponent_picks):
                        if not remaining:
                            break
                        visible = sorted(remaining, key=lambda row: abs(row["consensus_adp"] - selection) + rng.uniform(0, settings.league_size * 0.9))[:8]
                        chosen = rng.choice(visible)
                        remaining.remove(chosen)
                        selection += 1
                    if not remaining:
                        break
                    choice = max(remaining[:40], key=lambda row: (float(row.get("expected_vor") or 0) / 25) + 2.5 * marginal_roster_fit(roster, row["position"], starting_slots) + rng.uniform(-0.35, 0.35))
                    remaining.remove(choice)
                    roster.append(choice["position"])
                    value += float(choice.get("expected_vor") or max(0, 80 - choice["consensus_adp"]))
                    selection = settings.next_pick + 1
                assignment = best_roster_assignment(roster, starting_slots)
                outcomes.append(value + assignment["filled"] * 8 - len(assignment["gaps"]) * 10)
            scores[candidate["player_id"]] = round(mean(outcomes), 2)
        self._mock_cache[key] = scores
        return scores

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
        using_live_draft_pool = bool(league.draft_pool)
        draftable_players = league.draft_pool or league.free_agents
        pool_rank_by_id = {player.id: rank for rank, player in enumerate(draftable_players, 1)}
        players = [
            player
            for player in draftable_players
            if player.id not in drafted_ids
            and player.position in {"QB", "RB", "WR", "TE"}
            and (
                using_live_draft_pool
                or player.average_draft_position is not None
                or player.espn_rank is not None
                or player.season_projection is not None
                or player.percent_owned is not None
            )
        ]
        if not players:
            return []
        replacement = {
            position: replacement_level(league, position, season=True)
            for position in {player.position for player in players}
        }
        fallback_order = sorted(
            players,
            key=lambda player: (
                player.average_draft_position is None and player.espn_rank is None,
                float(player.average_draft_position or player.espn_rank or player.draft_pool_rank or pool_rank_by_id[player.id]),
                -float(player.season_projection or 0),
                -float(player.percent_owned or 0),
            ),
        )
        fallback_rank = {player.id: rank for rank, player in enumerate(fallback_order, 1)}
        base_rows = []
        for player in players:
            season_value = float(player.season_projection) if player.season_projection is not None else None
            vor = season_value - replacement.get(player.position, 0) if season_value is not None else None
            live_pool_rank = player.draft_pool_rank or (pool_rank_by_id[player.id] if using_live_draft_pool else None)
            market_pick = float(player.average_draft_position or player.espn_rank or live_pool_rank or fallback_rank[player.id])
            market_source = "ESPN ADP" if player.average_draft_position is not None else "ESPN draft rank" if player.espn_rank is not None else "ESPN live player-pool order" if live_pool_rank is not None else "ESPN season projection order" if player.season_projection is not None else "ESPN ownership order"
            base_rows.append(
                {
                    "player_id": player.id,
                    "player_name": player.name,
                    "position": player.position,
                    "team": player.team,
                    "consensus_adp": round(market_pick, 2),
                    "adp_available": player.average_draft_position is not None,
                    "market_source": market_source,
                    "espn_rank": player.espn_rank,
                    "percent_owned": player.percent_owned,
                    "injury_status": player.injury_status,
                    "season_projection": round(season_value, 2) if season_value is not None else None,
                    "expected_vor": round(vor, 2) if vor is not None else None,
                    "points_per_game": round(season_value / 17, 2) if season_value is not None else None,
                    "floor": round(max(0, season_value * 0.78), 2) if season_value is not None else None,
                    "median": round(season_value, 2) if season_value is not None else None,
                    "ceiling": round(season_value * 1.22, 2) if season_value is not None else None,
                    "risk": "High" if str(player.injury_status).upper() not in {"ACTIVE", "HEALTHY"} else "Medium" if season_value is None else "Low",
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
            row["fourth_down_rank"] = value_rank[row["player_id"]]
            row["adp_relative_value"] = round(row["consensus_adp"] - row["value_rank"], 2)
            if row["season_projection"] is not None and row["adp_available"]:
                row["confidence"] = "ESPN live ADP + season projection"
            elif row["season_projection"] is not None:
                row["confidence"] = f"{row['market_source']} + ESPN season projection"
            else:
                row["confidence"] = f"{row['market_source']}; season projection unavailable"
            row["availability_method"] = "ESPN average draft position; no fabricated next-pick probability"
            row["fallback_used"] = False
        for position in {row["position"] for row in base_rows}:
            position_rows = sorted(
                [row for row in base_rows if row["position"] == position],
                key=lambda row: row["expected_vor"] if row["expected_vor"] is not None else -row["composite_rank"],
                reverse=True,
            )
            values = [row["expected_vor"] if row["expected_vor"] is not None else -row["composite_rank"] for row in position_rows]
            gaps = [max(0.0, values[index] - values[index + 1]) for index in range(len(values) - 1)]
            typical_gap = median(gaps) if gaps else 0
            spread = pstdev(gaps) if len(gaps) > 1 else 0
            cliff = max(3.0 if any(row["expected_vor"] is not None for row in position_rows) else 2.0, typical_gap + spread)
            tier = 1
            for index, row in enumerate(position_rows):
                row["tier"] = tier
                row["tier_drop_after_player"] = round(gaps[index], 2) if index < len(gaps) else 0.0
                if index < len(gaps) and gaps[index] >= cliff:
                    tier += 1
            tier_counts = {number: sum(1 for row in position_rows if row["tier"] == number) for number in range(1, tier + 1)}
            for row in position_rows:
                row["players_remaining_in_tier"] = tier_counts[row["tier"]]
        for row in base_rows:
            stddev = max(6.0, row["consensus_adp"] * 0.18)
            z = (settings.next_pick - row["consensus_adp"]) / stddev
            available = 1 - (0.5 * (1 + math.erf(z / math.sqrt(2))))
            available = max(0.05, min(0.95, round(available / 0.05) * 0.05))
            row["availability_probability"] = available
            row["availability_label"] = "Likely available later" if available >= 0.7 else "Could return" if available >= 0.35 else "Unlikely to return"
            row["availability_method"] = "Heuristic ADP/rank availability probability; not historically calibrated"
            row["cost_of_waiting"] = round((1 - available) * float(row.get("tier_drop_after_player") or 0), 2)
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
        counts = {position: user_drafted_positions.count(position) for position in ("QB", "RB", "WR", "TE")}
        strategy = strategy if strategy in {"safe", "balanced", "aggressive"} else "balanced"
        round_number = 1 + (settings.current_pick - 1) // max(1, settings.league_size)
        is_superflex = "SUPERFLEX" in league.roster_slots
        recent = list(recent_drafted_positions or [])[-6:]
        scored = []
        for row in board:
            position = row["position"]
            fills_open_starter = marginal_roster_fit(user_drafted_positions, position, league.roster_slots)
            need = int(fills_open_starter)
            need_bonus = 2.25 * fills_open_starter
            if position == "QB" and not is_superflex and round_number <= 4:
                need_bonus *= 0.35
            fixed_capacity = sum(1 for slot in league.roster_slots if position in SLOT_ELIGIBILITY.get(slot, {slot}))
            if counts.get(position, 0) >= fixed_capacity and position in {"QB", "TE"} and round_number < 9:
                need_bonus -= 2.0
            urgency = max(0.0, min(4.0, (settings.next_pick - row["consensus_adp"]) / max(2, settings.league_size)))
            run_bonus = min(2.0, recent.count(position) * 0.45) if recent.count(position) >= 2 else 0
            wait_penalty = max(0.0, (row["consensus_adp"] - settings.next_pick) / max(2, settings.league_size))
            waiting_cost_component = min(3.0, float(row.get("cost_of_waiting") or 0) / 8)
            value_score = max(-4.0, min(6.0, row["adp_relative_value"] / max(2, settings.league_size / 2)))
            projection_component = row["expected_vor"] / 20 if row["expected_vor"] is not None else max(0, 4 - row["consensus_adp"] / max(12, settings.league_size * 2))
            injury_penalty = 2.5 if row.get("injury_status") in {"OUT", "INJURY RESERVE", "DOUBTFUL"} else 0.75 if row.get("injury_status") == "QUESTIONABLE" else 0
            missing_projection_penalty = 1.5 if row["season_projection"] is None else 0
            if strategy == "safe":
                score = projection_component * 1.35 + need_bonus * 1.15 + urgency * 0.9 + value_score * 0.45 + run_bonus * 0.7 + waiting_cost_component * 0.8 - wait_penalty * 1.2 - injury_penalty * 1.5 - missing_projection_penalty
            elif strategy == "aggressive":
                score = projection_component * 0.8 + need_bonus * 0.65 + urgency * 1.15 + value_score * 1.5 + run_bonus * 1.2 + waiting_cost_component * 1.2 - wait_penalty * 0.35 - injury_penalty * 0.45 - missing_projection_penalty * 0.25
            else:
                score = projection_component + need_bonus + urgency + value_score + run_bonus + waiting_cost_component - wait_penalty * 0.75 - injury_penalty - missing_projection_penalty * 0.5
            reason_parts = []
            if fills_open_starter:
                reason_parts.append(f"fills an open {position} or flex starter")
            if row.get("players_remaining_in_tier", 0) <= 2:
                reason_parts.append(f"only {row.get('players_remaining_in_tier', 0)} remain in Tier {row.get('tier')}")
            if row["availability_label"] == "Unlikely to return":
                reason_parts.append(f"unlikely to return at pick {settings.next_pick}")
            elif row.get("adp_relative_value", 0) > 3:
                reason_parts.append("costs less than Fourth Down’s value rank")
            if not reason_parts:
                reason_parts.append("strongest roster-adjusted value among realistic options")
            reason = "; ".join(reason_parts[:3]).capitalize() + "."
            scored.append({**row, "pick_score": round(score, 2), "strategy": strategy, "recommendation_reason": reason})
        mock_scores = self._mock_completed_roster_scores(scored, settings, user_drafted_positions, league.roster_slots)
        if mock_scores:
            ordered_mock = sorted(mock_scores, key=mock_scores.get, reverse=True)
            mock_rank = {player_id: rank for rank, player_id in enumerate(ordered_mock, 1)}
            for row in scored:
                row["completed_roster_quality"] = mock_scores.get(row["player_id"])
                row["pick_score"] = round(row["pick_score"] + max(0, 13 - mock_rank.get(row["player_id"], 13)) * 0.08, 2)
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

        assignment = best_roster_assignment(user_drafted_positions, league.roster_slots)
        counts = {position: user_drafted_positions.count(position) for position in ("QB", "RB", "WR", "TE")}
        round_number = 1 + (settings.current_pick - 1) // max(1, settings.league_size)
        needs = []
        for position in ("QB", "RB", "WR", "TE"):
            filled = counts.get(position, 0)
            gap = int(marginal_roster_fit(user_drafted_positions, position, league.roster_slots))
            board_at_position = [row for row in board if row["position"] == position]
            top_vor = next((row["expected_vor"] for row in board_at_position if row["expected_vor"] is not None), 0)
            priority_score = gap * 10 + top_vor / 20
            if gap:
                label = "STARTER NEEDED"
            elif position in {"RB", "WR"} and round_number >= 5 and filled < 4:
                label = "DEPTH NEEDED"
                priority_score += 2
            else:
                label = "FILLED"
            needs.append({"position": position, "filled": filled, "target": "shared slots", "gap": gap, "priority": label, "priority_score": round(priority_score, 2)})
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
            "roster_assignment": assignment,
            "method": "Live ESPN season projection, ADP, value over replacement, roster slots, and recorded picks",
        }

    def overall_pick_plan(
        self,
        league: League,
        draft_slot: int,
        rounds: int = 8,
        keeper_positions: list[str] | None = None,
        strategy: str = "balanced",
        draft_type: str | None = None,
        league_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """Create a pre-draft slot plan; availability is an ADP window, not a promise."""
        league_size = int(league_size or league_team_count(league))
        draft_slot = min(max(1, draft_slot), league_size)
        chosen_ids: set[str] = set()
        positions = list(keeper_positions or [])
        recommendations: list[dict[str, Any]] = []
        draft_type = draft_type or league_draft_type(league)
        for round_number in range(1, rounds + 1):
            pick_number = pick_for_slot(round_number, draft_slot, league_size, draft_type)
            next_pick = pick_for_slot(round_number + 1, draft_slot, league_size, draft_type)
            board = self.current_board(league, DraftSettings(league_size=league_size, current_pick=pick_number, next_pick=next_pick, draft_type=draft_type), chosen_ids)
            likely_gone = {
                row["player_id"]
                for row in board
                if row["consensus_adp"] < pick_number - max(3, league_size * 0.45)
            }
            plan = self.pick_plan(
                league,
                DraftSettings(league_size=league_size, current_pick=pick_number, next_pick=next_pick, draft_type=draft_type),
                chosen_ids | likely_gone,
                positions,
                backup_count=7,
                strategy=strategy,
            )
            if not plan:
                break
            choice = plan[0]
            primary = plan[:3]
            backups = plan[3:6]
            skill_positions = {row["position"] for row in primary}
            instruction = f"Prioritize the strongest remaining {' or '.join(sorted(skill_positions))} tier. Do not force a position if that tier is gone."
            recommendations.append({
                **choice, "round": round_number, "overall_pick": pick_number,
                "primary_targets": primary, "backup_targets": backups,
                "backups": [row["player_name"] for row in backups], "instruction": instruction,
            })
            chosen_ids.add(choice["player_id"])
            positions.append(choice["position"])
        return recommendations

    def turn_pair_plan(
        self,
        league: League,
        settings: DraftSettings,
        draft_slot: int,
        drafted_ids: set[str],
        user_drafted_positions: list[str],
        strategy: str = "balanced",
    ) -> list[dict[str, Any]]:
        """Jointly rank consecutive snake-turn selections."""
        if settings.draft_type != "snake" or owner_of_pick(settings.current_pick, settings.league_size, "snake") != draft_slot:
            return []
        second_pick = next_owned_pick(settings.current_pick + 1, draft_slot, settings.league_size, "snake")
        if second_pick != settings.current_pick + 1:
            return []
        first_options = self.pick_plan(league, settings, drafted_ids, user_drafted_positions, backup_count=5, strategy=strategy)
        pairs = []
        for first in first_options:
            second_settings = DraftSettings(league_size=settings.league_size, current_pick=second_pick, next_pick=snake_next_pick(second_pick, draft_slot, settings.league_size), draft_type="snake")
            second_options = self.pick_plan(
                league,
                second_settings,
                drafted_ids | {first["player_id"]},
                [*user_drafted_positions, first["position"]],
                backup_count=2,
                strategy=strategy,
            )
            for second in second_options:
                diversity_bonus = 0.5 if first["position"] != second["position"] else 0
                pairs.append({"first": first, "second": second, "pair_score": round(first["pick_score"] + second["pick_score"] + diversity_bonus, 2)})
        return sorted(pairs, key=lambda row: row["pair_score"], reverse=True)[:3]


def replacement_level(league: League, position: str, *, season: bool = False) -> float:
    teams = league_team_count(league)
    slot_count = sum(1 for slot in league.roster_slots if slot == position)
    flex_share = 0.35 if position in {"RB", "WR", "TE"} and "FLEX" in league.roster_slots else 0
    superflex_share = 0.5 if position == "QB" and "SUPERFLEX" in league.roster_slots else 0
    starters = teams * max(1, slot_count + flex_share + superflex_share)
    if league.draft_pool:
        all_players = [player for player in league.draft_pool if player.position == position]
    else:
        by_id = {player.id: player for team in league.teams for player in team.players if player.position == position}
        by_id.update({player.id: player for player in league.free_agents if player.position == position})
        all_players = list(by_id.values())
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
