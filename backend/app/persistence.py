from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import CONFIG

def _database_path() -> Path:
    configured = CONFIG.database_url
    if CONFIG.multi_user_mode:
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
        CREATE TABLE IF NOT EXISTS prediction_ledger (
            prediction_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, season INTEGER NOT NULL,
            week INTEGER NOT NULL, player_id TEXT NOT NULL, player_name TEXT NOT NULL,
            nfl_team TEXT NOT NULL, opponent TEXT, scoring_fingerprint TEXT NOT NULL,
            expected_points REAL NOT NULL, lower_bound REAL, upper_bound REAL,
            win_probability REAL, model_version TEXT NOT NULL, feature_data_cutoff TEXT,
            provider_freshness TEXT NOT NULL, fallback_used INTEGER NOT NULL,
            eligible_for_evaluation INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS prediction_outcomes (
            prediction_id TEXT PRIMARY KEY, outcome_recorded_at TEXT NOT NULL,
            actual_points REAL, actual_outcome INTEGER, final_player_status TEXT,
            evaluation_status TEXT NOT NULL, error REAL,
            FOREIGN KEY(prediction_id) REFERENCES prediction_ledger(prediction_id)
        );
        CREATE TABLE IF NOT EXISTS decision_journal (
            decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, season INTEGER NOT NULL,
            week INTEGER NOT NULL, league_id_hash TEXT NOT NULL, decision_type TEXT NOT NULL,
            model_version TEXT NOT NULL, data_snapshot_id TEXT NOT NULL, recommendation TEXT NOT NULL,
            alternatives TEXT NOT NULL, expected_points REAL, floor REAL, ceiling REAL,
            confidence TEXT NOT NULL, explanation TEXT NOT NULL, user_action TEXT NOT NULL,
            execution_status TEXT NOT NULL, actual_outcome TEXT, evaluated_at TEXT
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


def save_prediction_ledger(row: dict) -> None:
    with connection() as db:
        db.execute(
            """
            INSERT INTO prediction_ledger(
                prediction_id,created_at,season,week,player_id,player_name,nfl_team,opponent,
                scoring_fingerprint,expected_points,lower_bound,upper_bound,win_probability,
                model_version,feature_data_cutoff,provider_freshness,fallback_used,eligible_for_evaluation
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(prediction_id) DO NOTHING
            """,
            (
                row["prediction_id"],
                row["created_at"],
                row["season"],
                row["week"],
                row["player_id"],
                row["player_name"],
                row["nfl_team"],
                row.get("opponent"),
                row["scoring_fingerprint"],
                row["expected_points"],
                row.get("lower_bound"),
                row.get("upper_bound"),
                row.get("win_probability"),
                row["model_version"],
                row.get("feature_data_cutoff"),
                json.dumps(row.get("provider_freshness", [])),
                1 if row.get("fallback_used") else 0,
                1 if row.get("eligible_for_evaluation", True) else 0,
            ),
        )
        db.commit()


def attach_prediction_outcome(prediction_id: str, actual_points: float | None, actual_outcome: int | None, final_player_status: str, evaluation_status: str) -> None:
    with connection() as db:
        pred = db.execute("SELECT expected_points FROM prediction_ledger WHERE prediction_id=?", (prediction_id,)).fetchone()
        error = None if pred is None or actual_points is None else float(pred["expected_points"]) - float(actual_points)
        db.execute(
            """
            INSERT INTO prediction_outcomes(prediction_id,outcome_recorded_at,actual_points,actual_outcome,final_player_status,evaluation_status,error)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(prediction_id) DO UPDATE SET
                outcome_recorded_at=excluded.outcome_recorded_at,
                actual_points=excluded.actual_points,
                actual_outcome=excluded.actual_outcome,
                final_player_status=excluded.final_player_status,
                evaluation_status=excluded.evaluation_status,
                error=excluded.error
            """,
            (prediction_id, datetime.now(UTC).isoformat(), actual_points, actual_outcome, final_player_status, evaluation_status, error),
        )
        db.commit()


def prediction_ledger_rows() -> list[dict]:
    with connection() as db:
        rows = db.execute(
            """
            SELECT l.*, o.actual_points, o.actual_outcome, o.final_player_status, o.evaluation_status, o.error, o.outcome_recorded_at
            FROM prediction_ledger l
            LEFT JOIN prediction_outcomes o ON l.prediction_id=o.prediction_id
            ORDER BY l.season,l.week,l.created_at
            """
        ).fetchall()
    values = []
    for row in rows:
        item = dict(row)
        item["provider_freshness"] = json.loads(item["provider_freshness"]) if item.get("provider_freshness") else []
        values.append(item)
    return values


def save_decision_journal_entry(row: dict) -> None:
    with connection() as db:
        db.execute(
            """
            INSERT INTO decision_journal(
                decision_id,created_at,season,week,league_id_hash,decision_type,model_version,
                data_snapshot_id,recommendation,alternatives,expected_points,floor,ceiling,
                confidence,explanation,user_action,execution_status,actual_outcome,evaluated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(decision_id) DO UPDATE SET
                user_action=excluded.user_action,
                execution_status=excluded.execution_status,
                actual_outcome=excluded.actual_outcome,
                evaluated_at=excluded.evaluated_at
            """,
            (
                row["decision_id"],
                row["created_at"],
                row["season"],
                row["week"],
                row["league_id_hash"],
                row["decision_type"],
                row["model_version"],
                row["data_snapshot_id"],
                json.dumps(row["recommendation"]),
                json.dumps(row["alternatives"]),
                row.get("expected_points"),
                row.get("floor"),
                row.get("ceiling"),
                row["confidence"],
                json.dumps(row["explanation"]),
                row.get("user_action", "not_recorded"),
                row.get("execution_status", "Recommendation only"),
                json.dumps(row.get("actual_outcome")) if row.get("actual_outcome") is not None else None,
                row.get("evaluated_at"),
            ),
        )
        db.commit()


def decision_journal_rows() -> list[dict]:
    with connection() as db:
        rows = db.execute("SELECT * FROM decision_journal ORDER BY created_at DESC").fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["recommendation"] = json.loads(item["recommendation"])
        item["alternatives"] = json.loads(item["alternatives"])
        item["explanation"] = json.loads(item["explanation"])
        item["actual_outcome"] = json.loads(item["actual_outcome"]) if item.get("actual_outcome") else None
        results.append(item)
    return results

def delete_all_user_data() -> None:
    with connection() as db:
        for table in ("app_state","provider_cache","predictions","draft_state","prediction_outcomes","prediction_ledger","decision_journal"): db.execute(f"DELETE FROM {table}")
        db.commit()
