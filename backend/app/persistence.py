from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def _database_path() -> Path:
    configured = os.getenv("DATABASE_URL", "sqlite:///./fourth_down.db")
    if os.getenv("MULTI_USER_MODE","false").lower()=="true":
        raise RuntimeError("MULTI_USER_MODE cannot use SQLite because SQLite has no row-level security. Use an authenticated PostgreSQL deployment with enforced RLS policies.")
    if not configured.startswith("sqlite:///"):
        raise RuntimeError("This local build supports SQLite only. Do not claim PostgreSQL RLS is enabled until the PostgreSQL adapter and policies are installed and tested.")
    raw = configured.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(_database_path())
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_cache (
            cache_key TEXT PRIMARY KEY, provider TEXT NOT NULL, payload TEXT NOT NULL,
            fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, league_id TEXT NOT NULL, season INTEGER NOT NULL,
            week INTEGER NOT NULL, kind TEXT NOT NULL, predicted_points REAL,
            predicted_probability REAL, actual_points REAL, actual_outcome INTEGER,
            created_at TEXT NOT NULL, UNIQUE(league_id, season, week, kind)
        );
        CREATE TABLE IF NOT EXISTS draft_state (
            league_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)
        db.commit()
        yield db
    finally:
        db.close()


def save_state(key: str, value: Any) -> None:
    now = datetime.now(UTC).isoformat()
    with connection() as db:
        db.execute("INSERT INTO app_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, json.dumps(value), now))
        db.commit()


def load_state(key: str) -> Any | None:
    with connection() as db:
        row = db.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def cache_set(key: str, provider: str, payload: Any, fetched_at: str, expires_at: str, status: str = "LIVE") -> None:
    with connection() as db:
        db.execute("INSERT INTO provider_cache(cache_key,provider,payload,fetched_at,expires_at,status) VALUES(?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at,expires_at=excluded.expires_at,status=excluded.status", (key, provider, json.dumps(payload), fetched_at, expires_at, status))
        db.commit()


def cache_get(key: str, allow_expired: bool = True) -> dict | None:
    with connection() as db:
        row = db.execute("SELECT * FROM provider_cache WHERE cache_key=?", (key,)).fetchone()
    if not row: return None
    expired = datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC)
    if expired and not allow_expired: return None
    return {"payload": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "expires_at": row["expires_at"], "status": "STALE" if expired else "CACHED"}


def record_prediction(league_id: str, season: int, week: int, kind: str, points: float | None, probability: float | None) -> None:
    with connection() as db:
        db.execute("INSERT INTO predictions(league_id,season,week,kind,predicted_points,predicted_probability,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(league_id,season,week,kind) DO UPDATE SET predicted_points=excluded.predicted_points,predicted_probability=excluded.predicted_probability", (league_id, season, week, kind, points, probability, datetime.now(UTC).isoformat()))
        db.commit()


def prediction_rows() -> list[dict]:
    with connection() as db:
        rows = db.execute("SELECT * FROM predictions ORDER BY season,week").fetchall()
    return [dict(row) for row in rows]

def delete_all_user_data() -> None:
    with connection() as db:
        for table in ("app_state","provider_cache","predictions","draft_state"): db.execute(f"DELETE FROM {table}")
        db.commit()
