from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from .cache_policy import private_league_hash


@dataclass
class DecisionJournalEntry:
    decision_id: str
    created_at: str
    season: int
    week: int
    league_id_hash: str
    decision_type: str
    model_version: str
    data_snapshot_id: str
    recommendation: dict[str, object]
    alternatives: list[dict[str, object]]
    expected_points: float | None
    floor: float | None
    ceiling: float | None
    confidence: str
    explanation: list[str]
    user_action: str = "not_recorded"
    execution_status: str = "Recommendation only"
    actual_outcome: dict[str, object] | None = None
    evaluated_at: str | None = None

    def to_row(self) -> dict[str, object]:
        return asdict(self)


def create_decision_entry(
    *,
    season: int,
    week: int,
    league_id: str,
    decision_type: str,
    model_version: str,
    data_snapshot_id: str,
    recommendation: dict[str, object],
    alternatives: list[dict[str, object]],
    expected_points: float | None,
    floor: float | None,
    ceiling: float | None,
    confidence: str,
    explanation: list[str],
    execution_status: str = "Recommendation only",
) -> DecisionJournalEntry:
    return DecisionJournalEntry(
        decision_id=str(uuid4()),
        created_at=datetime.now(UTC).isoformat(),
        season=season,
        week=week,
        league_id_hash=private_league_hash(league_id),
        decision_type=decision_type,
        model_version=model_version,
        data_snapshot_id=data_snapshot_id,
        recommendation=recommendation,
        alternatives=alternatives,
        expected_points=expected_points,
        floor=floor,
        ceiling=ceiling,
        confidence=confidence,
        explanation=explanation,
        execution_status=execution_status,
    )


def evaluate_decision(entry: DecisionJournalEntry, actual_points_by_player: dict[str, float], valid_alternative_player_ids: list[str]) -> DecisionJournalEntry:
    recommended_id = str(entry.recommendation.get("player_id", ""))
    recommended_actual = actual_points_by_player.get(recommended_id)
    valid_actuals = [actual_points_by_player[player_id] for player_id in valid_alternative_player_ids if player_id in actual_points_by_player]
    best_alternative = max(valid_actuals) if valid_actuals else None
    regret = None
    if recommended_actual is not None and best_alternative is not None:
        regret = round(best_alternative - recommended_actual, 3)
    error = None
    if recommended_actual is not None and entry.expected_points is not None:
        error = round(entry.expected_points - recommended_actual, 3)
    entry.actual_outcome = {
        "recommended_actual_points": recommended_actual,
        "best_valid_alternative_points": best_alternative,
        "absolute_error": abs(error) if error is not None else None,
        "regret": regret,
        "improved_lineup": regret is not None and regret <= 0,
    }
    entry.evaluated_at = datetime.now(UTC).isoformat()
    return entry
