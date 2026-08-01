from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_ESPN_STATS = {
    "3": "passing_yards",
    "4": "passing_touchdowns",
    "20": "interceptions",
    "24": "rushing_yards",
    "25": "rushing_touchdowns",
    "42": "receptions",
    "43": "receiving_yards",
    "44": "receiving_touchdowns",
    "53": "fumbles_lost",
    "72": "two_point_conversions",
}


@dataclass(frozen=True)
class FantasyScoring:
    passing_yards: float = 0.04
    passing_touchdowns: float = 4.0
    interceptions: float = -2.0
    rushing_yards: float = 0.1
    rushing_touchdowns: float = 6.0
    receptions: float = 1.0
    receiving_yards: float = 0.1
    receiving_touchdowns: float = 6.0
    fumbles_lost: float = -2.0
    two_point_conversions: float = 2.0
    bonuses: dict[str, float] = field(default_factory=dict)
    unsupported_settings: dict[str, float] = field(default_factory=dict)
    scoring_basis: str = "canonical_ppr"

    @classmethod
    def canonical_ppr(cls) -> "FantasyScoring":
        return cls()

    @classmethod
    def from_espn(cls, scoring: dict[str, float] | None) -> "FantasyScoring":
        if not scoring:
            return cls()
        values: dict[str, Any] = {}
        unsupported: dict[str, float] = {}
        for stat_id, points in scoring.items():
            field_name = SUPPORTED_ESPN_STATS.get(str(stat_id))
            if field_name:
                values[field_name] = float(points)
            else:
                unsupported[str(stat_id)] = float(points)
        return cls(**values, unsupported_settings=unsupported, scoring_basis="espn_supported_subset")


def fantasy_points(row: dict[str, Any], scoring: FantasyScoring | None = None) -> float:
    scoring = scoring or FantasyScoring.canonical_ppr()
    value = (
        float(row.get("passing_yards", 0) or 0) * scoring.passing_yards
        + float(row.get("passing_touchdowns", 0) or 0) * scoring.passing_touchdowns
        + float(row.get("interceptions", 0) or 0) * scoring.interceptions
        + float(row.get("rushing_yards", 0) or 0) * scoring.rushing_yards
        + float(row.get("rushing_touchdowns", 0) or 0) * scoring.rushing_touchdowns
        + float(row.get("receptions", 0) or 0) * scoring.receptions
        + float(row.get("receiving_yards", 0) or 0) * scoring.receiving_yards
        + float(row.get("receiving_touchdowns", 0) or 0) * scoring.receiving_touchdowns
        + float(row.get("fumbles_lost", 0) or 0) * scoring.fumbles_lost
        + float(row.get("two_point_conversions", 0) or 0) * scoring.two_point_conversions
    )
    return round(value, 3)
