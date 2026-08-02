from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any


@dataclass(frozen=True)
class CachePolicy:
    name: str
    ttl: timedelta
    private: bool = False


CACHE_POLICIES = {
    "league_config": CachePolicy("league_config", timedelta(hours=12), private=True),
    "roster": CachePolicy("roster", timedelta(minutes=10), private=True),
    "injuries": CachePolicy("injuries", timedelta(minutes=15), private=False),
    "odds": CachePolicy("odds", timedelta(minutes=10), private=False),
    "historical_stats": CachePolicy("historical_stats", timedelta(days=7), private=False),
    "model_artifact": CachePolicy("model_artifact", timedelta(days=365), private=False),
    "projection": CachePolicy("projection", timedelta(minutes=20), private=True),
}


def stable_cache_key(provider: str, category: str, **dimensions: Any) -> str:
    payload = {"provider": provider, "category": category, **dimensions}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:24]


def private_league_hash(league_id: str, salt: str = "fourth-down") -> str:
    return hashlib.sha256(f"{salt}:{league_id}".encode()).hexdigest()[:16]
