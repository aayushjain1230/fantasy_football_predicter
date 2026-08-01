import json
from pathlib import Path

from app.artifacts import validate_projection_artifact
from app.config import load_config, validate_config
from app.demo import demo_league
from app.evaluation import evaluate_prediction_ledger, record_outcome, record_player_prediction
from app.exporting import safe_csv_value
from app.operations import DEGRADATION_MATRIX, health_summary
from app.projection_service import DEFAULT_PROJECTION_SERVICE, FEATURE_NAMES, MODEL_VERSION


def test_config_precedence_and_cloud_cookie_warning():
    config = load_config({"APP_ENV": "streamlit", "ESPN_S2": "cookie", "ESPN_SWID": "swid", "CURRENT_NFL_SEASON": "2027"})
    assert config.current_nfl_season == 2027
    assert config.cloud_mode
    assert any("ESPN cookies" in warning for warning in validate_config(config))


def test_projection_artifact_validation_rejects_bad_metadata(tmp_path):
    path = tmp_path / "QB.json"
    path.write_text(json.dumps({"metadata": {"model_version": "bad", "position": "QB"}, "features": FEATURE_NAMES, "algorithm": "ridge_linear_regression"}), encoding="utf-8")
    result = validate_projection_artifact(path)
    assert not result["valid"]
    assert "incompatible model version" in result["errors"]


def test_default_projection_artifacts_are_valid_or_fallback_labeled():
    league = demo_league()
    player = next(p for p in league.teams[0].players if p.position == "QB")
    projection = DEFAULT_PROJECTION_SERVICE.project_player(player, league=league, week=league.week)
    assert projection.model_version in {MODEL_VERSION, "phase1"}
    if projection.model_version == "phase1":
        assert projection.fallback_used


def test_safe_csv_value_prefixes_spreadsheet_formulas():
    assert safe_csv_value("=cmd") == "'=cmd"
    assert safe_csv_value("+SUM(A1:A2)") == "'+SUM(A1:A2)"
    assert safe_csv_value("plain") == "plain"


def test_health_summary_is_safe_and_contains_degradation_matrix():
    summary = health_summary(demo_league())
    assert summary["app_version"]
    assert summary["provider_states"]
    assert DEGRADATION_MATRIX
    text = json.dumps(summary).lower()
    assert "espn_s2" not in text
    assert "swid" not in text


def test_prediction_ledger_requires_minimum_sample_before_metrics():
    league = demo_league()
    player = league.teams[0].players[0]
    projection = DEFAULT_PROJECTION_SERVICE.project_player(player, league=league, week=league.week)
    pid = record_player_prediction(league, player, projection)
    record_outcome(pid, actual_points=projection.mean + 1, final_player_status="ACTIVE")
    result = evaluate_prediction_ledger(minimum_sample=1000)
    assert result["status"] == "UNAVAILABLE"
    assert result["sample_size"] >= 1
