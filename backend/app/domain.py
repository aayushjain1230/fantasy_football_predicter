from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field


class DataState(StrEnum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    STALE = "STALE"
    MOCK = "MOCK"
    UNAVAILABLE = "UNAVAILABLE"


class Player(BaseModel):
    id: str
    name: str
    position: str
    team: str
    eligible_slots: set[str] = Field(default_factory=set)
    mean: float = Field(ge=0)
    stdev: float = Field(gt=0)
    availability: float = Field(default=1, ge=0, le=1)
    injury_status: str = "HEALTHY"
    rostered: bool = True


class Team(BaseModel):
    id: str
    name: str
    record: str = "0-0"
    players: list[Player]


class League(BaseModel):
    id: str
    name: str
    season: int
    week: int
    user_team_id: str
    roster_slots: list[str]
    teams: list[Team]
    free_agents: list[Player] = Field(default_factory=list)
    scoring: dict[str, float] = Field(default_factory=dict)
    playoff_team_count: int = 4
    acquisition_budget: int | None = None


class Projection(BaseModel):
    player_id: str
    mean: float
    floor: float
    median: float
    ceiling: float
    confidence: float
    reasons: list[str]
    missing: list[str] = Field(default_factory=list)


class LineupEntry(BaseModel):
    slot: str
    player: Player
    projection: Projection


class LineupResult(BaseModel):
    style: str
    starters: list[LineupEntry]
    bench: list[Player]
    expected_score: float
    floor: float
    ceiling: float
    win_probability: float
    changes: list[str]


class WaiverMove(BaseModel):
    add: Player
    drop: Player
    weekly_gain: float
    ros_gain: float
    category: str
    confidence: float
    faab_percent: int
    reasons: list[str]
    risks: list[str]


class ProviderStatus(BaseModel):
    provider: str
    category: str
    state: DataState
    updated: str | None = None
    key_configured: bool = False
    impact: str


class ImpactRange(BaseModel):
    floor: float
    median: float
    ceiling: float


class TradeResult(BaseModel):
    send: list[Player]
    receive: list[Player]
    required_drop: Player | None = None
    before: ImpactRange
    after: ImpactRange
    weekly_delta: float
    playoff_delta: float
    championship_delta: float
    acceptance_likelihood: float
    verdict: str
    reasons: list[str]
    risks: list[str]


class DraftRecommendation(BaseModel):
    player: Player
    rank: int
    vor: float
    scarcity: float
    survival_probability: float
    roster_fit: str
    risk: str
    explanation: str


class TeamStrength(BaseModel):
    team_id: str
    team_name: str
    rank: int
    expected_score: float
    playoff_probability: float
    championship_probability: float
    projected_wins: float
    wins_low: float
    wins_high: float


class CalibrationSummary(BaseModel):
    sample_size: int
    points_mae: float
    brier_score: float
    confidence_bias: float
    verdict: str
    buckets: list[dict[str, float]]
