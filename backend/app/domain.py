from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field


class DataState(StrEnum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    STALE = "STALE"
    DEMO = "DEMO"
    UNAVAILABLE = "UNAVAILABLE"


class ProviderReliabilityState(StrEnum):
    FRESH = "Fresh"
    STALE = "Stale"
    UNAVAILABLE = "Unavailable"
    PARTIAL = "Partial"
    RATE_LIMITED = "Rate limited"
    AUTH_REQUIRED = "Authentication required"


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
    division_id: str | None = None
    owner: str | None = None
    wins: float = 0
    losses: float = 0
    ties: float = 0
    points_for: float = 0
    points_against: float = 0


class LeagueRuleSet(BaseModel):
    regular_season_start: int = 1
    regular_season_end: int = 14
    playoff_start: int | None = None
    playoff_end: int | None = None
    first_round_byes: int = 0
    playoff_matchup_period_length: int = 1
    tiebreaker: str = "record_then_points_for"
    reseeding: str = "fixed"
    median_games: bool = False
    division_winner_priority: bool = False
    unsupported: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    raw: dict[str, object] = Field(default_factory=dict)


class Matchup(BaseModel):
    id: str
    period: int
    home_team_id: str
    away_team_id: str
    home_score: float | None = None
    away_score: float | None = None
    is_complete: bool = False
    is_current: bool = False
    is_playoff: bool = False
    raw: dict[str, object] = Field(default_factory=dict)


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
    rules: LeagueRuleSet = Field(default_factory=LeagueRuleSet)
    schedule: list[Matchup] = Field(default_factory=list)
    raw_settings: dict[str, object] = Field(default_factory=dict)


class Projection(BaseModel):
    player_id: str
    week: int | None = None
    baseline_source: str = "Input projection"
    baseline_value: float = 0
    baseline_projection: float | None = None
    market_adjustment: float = 0
    final_projection: float | None = None
    mean: float
    floor: float
    median: float
    ceiling: float
    confidence: float
    adjustments: list[dict[str, float | str]] = Field(default_factory=list)
    uncertainty_label: str = "Heuristic uncertainty estimate"
    interval_level: float | None = None
    model_name: str = "phase1_fallback"
    model_version: str = "phase1"
    important_features: list[dict[str, float | str]] = Field(default_factory=list)
    data_completeness: float = 0
    confidence_label: str = "limited"
    fallback_used: bool = True
    fallback_reason: str = "Model artifact unavailable"
    training_cutoff: str | None = None
    reasons: list[str]
    missing: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    market_data_available: bool = False
    market_data_quality: str = "unavailable"
    generated_at: str | None = None


class ProviderReliability(BaseModel):
    provider: str
    status: ProviderReliabilityState
    retrieved_at: str | None = None
    freshness: str = "unknown"
    is_stale: bool = False
    error_code: str | None = None
    fallback_used: bool = False
    message: str = ""


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
    is_complete: bool = True
    missing_slots: list[str] = Field(default_factory=list)
    explanation: str = ""


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
    drop_safety: str = "Situational drop"
    faab_guidance: dict[str, object] = Field(default_factory=dict)


class ProviderStatus(BaseModel):
    provider: str
    category: str
    state: DataState
    updated: str | None = None
    key_configured: bool = False
    used_by: list[str] = Field(default_factory=list)
    impact: str
    unavailable_behavior: str = "Calculation falls back to the baseline and lowers confidence."


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
    status: str = "UNAVAILABLE"
    sample_size: int
    points_mae: float
    points_rmse: float = 0
    mean_bias: float = 0
    brier_score: float
    confidence_bias: float
    verdict: str
    buckets: list[dict[str, float]]
    minimum_sample: int = 20
    is_demo: bool = False


class DecisionRecommendation(BaseModel):
    decision_id: str
    category: str
    priority: str
    title: str
    recommended_action: str
    baseline_action: str | None = None
    expected_points_change: float | None = None
    win_probability_change: float | None = None
    playoff_probability_change: float | None = None
    lower_impact: float | None = None
    upper_impact: float | None = None
    confidence: str = "Medium"
    robustness: str = "Moderately robust"
    deadline: str | None = None
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    data_freshness: list[str] = Field(default_factory=list)
    model_versions: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class RosterPositionOutlook(BaseModel):
    position: str
    starter_strength: float
    bench_depth: int
    reliable_options: int
    injury_exposure: str
    weekly_volatility: str
    drop_flexibility: str
    summary: str


class WeeklyBrief(BaseModel):
    league_name: str
    team_name: str
    week: int
    matchup_summary: str
    expected_score: float
    win_probability: float
    playoff_probability: float | None = None
    championship_probability: float | None = None
    biggest_weakness: str | None = None
    best_position: str | None = None
    roster_summary: str
    top_actions: list[DecisionRecommendation]
    position_outlook: list[RosterPositionOutlook] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
