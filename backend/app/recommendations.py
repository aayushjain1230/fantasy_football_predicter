from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class RecommendationStatus(StrEnum):
    RECOMMENDATION_ONLY = "Recommendation only"
    PREVIEW = "Preview"
    READY_FOR_CONFIRMATION = "Ready for confirmation"
    EXECUTED = "Executed"
    FAILED = "Failed"
    UNSUPPORTED = "Unsupported"


@dataclass
class RecommendationPreview:
    recommendation_id: str
    status: RecommendationStatus
    decision_type: str
    current: dict[str, object]
    recommended: dict[str, object]
    expected_points_difference: float | None = None
    floor_difference: float | None = None
    ceiling_difference: float | None = None
    win_probability_difference: float | None = None
    reasons: list[str] = field(default_factory=list)
    confidence: str = "Medium"
    data_freshness: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def generate_recommendation(decision_type: str, current: dict[str, object], recommended: dict[str, object], **kwargs: object) -> RecommendationPreview:
    return RecommendationPreview(recommendation_id=str(uuid4()), status=RecommendationStatus.RECOMMENDATION_ONLY, decision_type=decision_type, current=current, recommended=recommended, **kwargs)


def validate_recommendation(preview: RecommendationPreview) -> RecommendationPreview:
    status = RecommendationStatus.PREVIEW if preview.current != preview.recommended else RecommendationStatus.RECOMMENDATION_ONLY
    preview.status = status
    return preview


def require_confirmation(preview: RecommendationPreview, *, supported_execution: bool = False) -> RecommendationPreview:
    preview.status = RecommendationStatus.READY_FOR_CONFIRMATION if supported_execution else RecommendationStatus.UNSUPPORTED
    return preview


def execute_if_supported(preview: RecommendationPreview, *, confirmed: bool, supported_execution: bool = False) -> RecommendationPreview:
    if not supported_execution:
        preview.status = RecommendationStatus.UNSUPPORTED
    elif not confirmed:
        preview.status = RecommendationStatus.READY_FOR_CONFIRMATION
    else:
        preview.status = RecommendationStatus.EXECUTED
    return preview
