from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_csv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def export_metadata(label: str, season: int, week: int, model_version: str) -> list[str]:
    return ["Fourth Down export", datetime.now(UTC).isoformat(), f"Season {season}", f"Week {week}", label, f"Model {model_version}"]
