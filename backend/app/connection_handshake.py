from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class OneTimeConnection:
    code: str
    state: str
    expires_in_seconds: int


class OneTimeConnectionStore:
    """In-memory handshake primitive for a future dedicated HTTPS service.

    It intentionally stores only hashes and no ESPN authentication material.
    Streamlit does not expose this as an endpoint.
    """

    def __init__(self, ttl_seconds: int = 300, issue_limit: int = 6, window_seconds: int = 60):
        self.ttl = min(300, max(1, ttl_seconds))
        self.issue_limit = max(1, issue_limit)
        self.window = max(1, window_seconds)
        self._codes: dict[str, tuple[str, float]] = {}
        self._issues: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def issue(self, client_key: str) -> OneTimeConnection:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._issues.get(client_key, []) if stamp > now - self.window]
            if len(recent) >= self.issue_limit:
                raise ValueError("RATE_LIMITED")
            recent.append(now)
            self._issues[client_key] = recent
            code = secrets.token_urlsafe(32)
            state = secrets.token_urlsafe(32)
            self._codes[self._hash(code)] = (self._hash(state), now + self.ttl)
        return OneTimeConnection(code, state, self.ttl)

    def redeem(self, code: str, state: str) -> bool:
        key = self._hash(code)
        with self._lock:
            row = self._codes.pop(key, None)
        if not row:
            return False
        expected_state, expires = row
        return time.monotonic() <= expires and secrets.compare_digest(expected_state, self._hash(state))

    def revoke(self, code: str) -> None:
        with self._lock:
            self._codes.pop(self._hash(code), None)
