from __future__ import annotations

import math
from collections import defaultdict

from pydantic import BaseModel, Field

from .domain import League, Player
from .projection_service import DEFAULT_PROJECTION_SERVICE, ProjectionService


class WeeklyRosProjection(BaseModel):
    week: int
    expected_points: float
    lower_estimate: float
    upper_estimate: float
    missing_context: list[str] = Field(default_factory=list)


class RosProjection(BaseModel):
    player_id: str
    expected_points: float
    expected_vor: float
    starter_level_weeks: int
    playoff_week_value: float
    lower_estimate: float
    upper_estimate: float
    schedule_quality: str
    bye_week: int | None = None
    missing_future_context: list[str] = Field(default_factory=list)
    weeks: list[WeeklyRosProjection] = Field(default_factory=list)


def replacement_value(league: League, position: str) -> float:
    values = sorted([p.mean for team in league.teams for p in team.players if p.position == position] + [p.mean for p in league.free_agents if p.position == position], reverse=True)
    if not values:
        return 0
    index = min(len(values) - 1, max(0, len(league.teams)))
    return values[index]


def project_ros(player: Player, league: League, projection_service: ProjectionService | None = None) -> RosProjection:
    service = projection_service or DEFAULT_PROJECTION_SERVICE
    start = max(league.week, 1)
    end = max(start, league.rules.playoff_end or league.rules.regular_season_end)
    replacement = replacement_value(league, player.position)
    weekly: list[WeeklyRosProjection] = []
    missing = {"future opponent context", "verified bye week"}
    for week in range(start, end + 1):
        projection = service.project_player(player=player, league=league, week=week)
        distance = max(0, week - league.week)
        uncertainty = player.stdev * (1 + 0.08 * distance)
        expected = max(0, projection.mean * (0.98 ** max(0, distance - 2)))
        week_missing = list(dict.fromkeys([*projection.missing, "future opponent context", "verified bye week"]))
        weekly.append(WeeklyRosProjection(week=week, expected_points=round(expected, 2), lower_estimate=round(max(0, expected - 1.28 * uncertainty), 2), upper_estimate=round(expected + 1.28 * uncertainty, 2), missing_context=week_missing))
    total = sum(row.expected_points for row in weekly)
    lower = math.sqrt(sum((row.expected_points - row.lower_estimate) ** 2 for row in weekly))
    upper = math.sqrt(sum((row.upper_estimate - row.expected_points) ** 2 for row in weekly))
    starter_threshold = max(8, replacement)
    playoff_weeks = [row for row in weekly if row.week >= (league.rules.playoff_start or league.rules.regular_season_end + 1)]
    schedule_quality = "Unknown" if missing else "Modeled"
    return RosProjection(player_id=player.id, expected_points=round(total, 1), expected_vor=round(sum(max(0, row.expected_points - replacement) for row in weekly), 1), starter_level_weeks=sum(1 for row in weekly if row.expected_points >= starter_threshold), playoff_week_value=round(sum(row.expected_points for row in playoff_weeks), 1), lower_estimate=round(max(0, total - lower), 1), upper_estimate=round(total + upper, 1), schedule_quality=schedule_quality, missing_future_context=sorted(missing), weeks=weekly)


def roster_ros_by_position(players: list[Player], league: League) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for player in players:
        totals[player.position] += project_ros(player, league).expected_vor
    return dict(totals)
