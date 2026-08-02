from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any


def h(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def fantasy_points(value: float | int | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{float(value):.1f}"


def percentage(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{float(value):.0%}"


def percentage_points(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{float(value) * 100:+.1f} pts"


def rank(value: int | None) -> str:
    if value is None:
        return "Unranked"
    suffix = "th"
    if value % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def freshness(value: str | None) -> str:
    if not value:
        return "Unknown freshness"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return f"{parsed:%b} {parsed.day}, {parsed:%Y %I:%M %p}"
    except Exception:
        return value


def confidence_label(value: str | float | None) -> str:
    if value is None:
        return "Confidence unavailable"
    if isinstance(value, (int, float)):
        if value >= 0.75:
            return "High confidence"
        if value >= 0.5:
            return "Medium confidence"
        return "Low confidence"
    text = str(value).strip()
    return text if text else "Confidence unavailable"


def missing(value: Any, fallback: str = "Unavailable") -> str:
    return fallback if value in {None, ""} else str(value)
