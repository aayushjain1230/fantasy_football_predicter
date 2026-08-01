from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any


SAFE_EVENTS: deque[dict[str, Any]] = deque(maxlen=250)
SECRET_WORDS = ("cookie", "espn_s2", "swid", "api_key", "authorization", "secret", "token")


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[redacted]" if any(word in k.lower() for word in SECRET_WORDS) else _clean(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value[:20]]
    if isinstance(value, str):
        lowered = value.lower()
        if any(word in lowered for word in SECRET_WORDS):
            return "[redacted]"
        return value[:180]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:180]


def record_event(severity: str, component: str, code: str, **context: Any) -> None:
    SAFE_EVENTS.append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": severity,
            "component": component,
            "code": code,
            "context": _clean(context),
        }
    )


def recent_events(limit: int = 25) -> list[dict[str, Any]]:
    return list(SAFE_EVENTS)[-limit:]
