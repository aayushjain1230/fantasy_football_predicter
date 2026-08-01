from pathlib import Path

from app.demo import demo_league
from app.draft_intelligence import (
    OUTCOME_CLASSES,
    DraftIntelligenceService,
    DraftSettings,
    availability_at_next_pick,
    build_draft_dataset,
    classify_residual,
    consensus_adp,
    fit_outcome_thresholds,
    load_csv,
    snake_next_pick,
    train_draft_artifact,
)


ADP = Path(__file__).parent / "fixtures" / "draft_adp.csv"
OUTCOMES = Path(__file__).parent / "fixtures" / "draft_outcomes.csv"


def test_consensus_adp_preserves_platform_dispersion():
    rows = consensus_adp(load_csv(ADP))
    rb_2024 = next(row for row in rows if row["season"] == 2024 and row["player_id"] == "rb_a")
    assert rb_2024["consensus_adp"] == 8.5
    assert rb_2024["adp_range"] == 3.0
    assert rb_2024["platform_count"] == 2
    assert rb_2024["snapshot_date"] == "2024-08-25"


def test_draft_dataset_targets_are_adp_relative_and_separate_availability():
    dataset = build_draft_dataset(load_csv(ADP), load_csv(OUTCOMES))
    row = dataset[0]
    assert "expected_value_at_adp" in row
    assert "adp_relative_residual" in row
    assert "performance_component" in row
    assert "availability_component" in row
    assert row["outcome_class"] in OUTCOME_CLASSES


def test_outcome_classes_are_mutually_exclusive():
    dataset = build_draft_dataset(load_csv(ADP), load_csv(OUTCOMES))
    thresholds = fit_outcome_thresholds([row for row in dataset if row["season"] <= 2023])
    for position, limits in thresholds.items():
        assert limits["underperform_lt"] < limits["outperform_gt"]
        labels = {classify_residual(value, limits) for value in [limits["underperform_lt"] - 1, (limits["underperform_lt"] + limits["outperform_gt"]) / 2, limits["outperform_gt"] + 1]}
        assert labels == set(OUTCOME_CLASSES)


def test_snake_next_pick_odd_and_even_rounds():
    assert snake_next_pick(current_pick=1, draft_slot=6, league_size=12) == 6
    assert snake_next_pick(current_pick=6, draft_slot=6, league_size=12) == 19
    assert snake_next_pick(current_pick=19, draft_slot=6, league_size=12) == 30


def test_availability_estimate_is_monotonic():
    early = availability_at_next_pick(adp=20, adp_stddev=6, next_pick=30)
    late = availability_at_next_pick(adp=40, adp_stddev=6, next_pick=30)
    assert early["probability_available"] > late["probability_available"]
    assert early["probability_available"] + early["probability_selected_before"] == 1
    assert "approximation" in early["method"]


def test_training_artifact_probabilities_sum_and_board_tiers(tmp_path):
    dataset = build_draft_dataset(load_csv(ADP), load_csv(OUTCOMES))
    artifact = train_draft_artifact(dataset, tmp_path)
    assert artifact["metadata"]["model_version"] == "phase3_fixture_v1"
    service = DraftIntelligenceService(tmp_path)
    board = service.current_board(demo_league(), DraftSettings(current_pick=1, next_pick=24), drafted_ids=set())
    assert board
    row = board[0]
    total = row["outperform_probability"] + row["meet_probability"] + row["underperform_probability"]
    assert abs(total - 1) <= 0.002
    assert "tier" in row


def test_missing_draft_artifact_uses_labeled_fallback(tmp_path):
    service = DraftIntelligenceService(tmp_path)
    board = service.current_board(demo_league(), DraftSettings(current_pick=1, next_pick=24), drafted_ids=set())
    assert board
    assert board[0]["fallback_used"]
    assert "unavailable" in board[0]["fallback_reason"].lower()


def test_drafted_players_are_removed(tmp_path):
    dataset = build_draft_dataset(load_csv(ADP), load_csv(OUTCOMES))
    train_draft_artifact(dataset, tmp_path)
    league = demo_league()
    first = league.teams[0].players[0]
    board = DraftIntelligenceService(tmp_path).current_board(league, DraftSettings(current_pick=1, next_pick=24), drafted_ids={first.id})
    assert all(row["player_id"] != first.id for row in board)
