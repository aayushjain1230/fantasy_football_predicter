from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable, TypeVar

import httpx

from .domain import ProviderReliability, ProviderReliabilityState

LOGGER = logging.getLogger("fourth_down.providers")
T = TypeVar("T")


def redact_secret(value: str) -> str:
    redacted = value
    for token in ("ODDS_API_KEY", "ESPN_S2", "ESPN_SWID", "OPENWEATHER_API_KEY"):
        redacted = redacted.replace(token, f"{token[:4]}...")
    if len(redacted) > 240:
        redacted = redacted[:237] + "..."
    return redacted


@dataclass
class ProviderCooldown:
    provider: str
    until: datetime | None = None

    def active(self, now: datetime | None = None) -> bool:
        return bool(self.until and (now or datetime.now(UTC)) < self.until)

    def trip(self, seconds: int) -> None:
        self.until = datetime.now(UTC) + timedelta(seconds=seconds)


async def with_provider_retries(
    provider: str,
    call: Callable[[], Awaitable[T]],
    *,
    retries: int = 1,
    base_delay: float = 0.15,
    cooldown: ProviderCooldown | None = None,
) -> tuple[T | None, ProviderReliability]:
    if cooldown and cooldown.active():
        return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.RATE_LIMITED, is_stale=True, error_code="COOLDOWN", fallback_used=True, message="Provider cooldown is active.")
    for attempt in range(retries + 1):
        try:
            value = await call()
            return value, ProviderReliability(provider=provider, status=ProviderReliabilityState.FRESH, retrieved_at=datetime.now(UTC).isoformat(), freshness="fresh")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.AUTH_REQUIRED, error_code=str(status), fallback_used=True, message="Authentication required.")
            if status == 429:
                if cooldown:
                    cooldown.trip(60)
                return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.RATE_LIMITED, error_code="429", fallback_used=True, message="Rate limited.")
            LOGGER.warning("Provider %s failed: %s", provider, redact_secret(str(exc)))
            return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.UNAVAILABLE, error_code=str(status), fallback_used=True)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt < retries:
                await asyncio.sleep(base_delay * (2**attempt) + random.Random(attempt).random() * 0.05)
                continue
            return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.UNAVAILABLE, error_code=exc.__class__.__name__, fallback_used=True, message="Provider request timed out or could not connect.")
        except Exception as exc:
            LOGGER.warning("Provider %s unexpected failure: %s", provider, redact_secret(str(exc)))
            return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.UNAVAILABLE, error_code=exc.__class__.__name__, fallback_used=True)
    return None, ProviderReliability(provider=provider, status=ProviderReliabilityState.UNAVAILABLE, fallback_used=True)
