from pathlib import Path

from app.domain import League, Player, Team
from app.projection_service import (
    FEATURE_NAMES,
    ProjectionContext,
    ProjectionService,
    build_training_rows,
    evaluate_rows,
    load_csv,
    train_position_artifacts,
)
from app.scoring import FantasyScoring, fantasy_points


FIXTURE = Path(__file__).parent / "fixtures" / "historical_player_weeks.csv"


def test_scoring_calculates_common_ppr_rules():
    row = {
        "passing_yards": 250,
        "passing_touchdowns": 2,
        "interceptions": 1,
        "rushing_yards": 30,
        "rushing_touchdowns": 1,
        "receptions": 2,
        "receiving_yards": 10,
        "receiving_touchdowns": 0,
        "fumbles_lost": 1,
        "two_point_conversions": 1,
    }
    assert fantasy_points(row) == 28.0


def test_espn_scoring_preserves_unsupported_settings():
    scoring = FantasyScoring.from_espn({"3": 0.05, "9999": 4})
    assert scoring.passing_yards == 0.05
    assert scoring.unsupported_settings == {"9999": 4.0}


def test_training_features_are_shifted_and_exclude_current_week():
    rows = build_training_rows(load_csv(FIXTURE))
    first_qb = next(row for row in rows if row["player_id"] == "qb_a" and row["season"] == 2022 and row["week"] == 1)
    second_qb = next(row for row in rows if row["player_id"] == "qb_a" and row["season"] == 2022 and row["week"] == 2)
    assert first_qb["games_played"] == 0
    assert second_qb["prev_points"] == first_qb["target"]
    assert second_qb["rolling3_points"] == first_qb["target"]
    assert second_qb["prev_points"] != second_qb["target"]


def test_training_is_deterministic_and_artifacts_validate(tmp_path):
    rows = build_training_rows(load_csv(FIXTURE))
    a = train_position_artifacts(rows, tmp_path / "a")
    b = train_position_artifacts(rows, tmp_path / "b")
    assert a["dataset_fingerprint"] == b["dataset_fingerprint"]
    qb = ProjectionService(tmp_path / "a").load_artifact("QB")
    assert qb is not None
    assert qb["features"] == FEATURE_NAMES


def test_projection_service_uses_artifact_and_orders_interval(tmp_path):
    rows = build_training_rows(load_csv(FIXTURE))
    train_position_artifacts(rows, tmp_path)
    service = ProjectionService(tmp_path)
    player = Player(id="qb_a", name="Test Quarterback", position="QB", team="BAL", eligible_slots={"QB", "SUPERFLEX"}, mean=20, stdev=5)
    league = League(id="x", name="x", season=2024, week=5, user_team_id="1", roster_slots=["QB"], teams=[Team(id="1", name="x", players=[player])])
    feature_row = next(row for row in rows if row["player_id"] == "qb_a" and row["season"] == 2024 and row["week"] == 4)
    projection = service.project_player(player, league=league, context=ProjectionContext(week=5, feature_row=feature_row, external_baseline=20))
    assert not projection.fallback_used
    assert projection.floor <= projection.median <= projection.ceiling
    assert projection.model_version == "phase2_fixture_v1"
    assert projection.important_features


def test_missing_or_corrupt_artifact_falls_back(tmp_path):
    (tmp_path / "QB.json").write_text("{not-json", encoding="utf-8")
    service = ProjectionService(tmp_path)
    player = Player(id="qb", name="QB", position="QB", team="BAL", eligible_slots={"QB"}, mean=12, stdev=4)
    projection = service.project_player(player, week=1)
    assert projection.fallback_used
    assert "artifact" in projection.fallback_reason.lower()


def test_fixture_evaluation_reports_interval_coverage(tmp_path):
    rows = build_training_rows(load_csv(FIXTURE))
    train_position_artifacts(rows, tmp_path)
    qb = ProjectionService(tmp_path).load_artifact("QB")
    test_rows = [row for row in rows if row["position"] == "QB" and row["season"] == 2024 and row["week"] >= 3]
    report = evaluate_rows(qb, test_rows)
    assert report["sample_size"] == 2
    assert "interval_coverage_80" in report
