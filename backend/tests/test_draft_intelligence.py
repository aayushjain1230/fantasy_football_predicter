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
    league_draft_type,
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
    assert snake_next_pick(current_pick=0, draft_slot=12, league_size=12) == 12
    assert snake_next_pick(current_pick=12, draft_slot=12, league_size=12) == 13
    assert snake_next_pick(current_pick=13, draft_slot=12, league_size=12) == 36


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
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 10)
        player.season_projection = player.mean * 14
    board = service.current_board(league, DraftSettings(current_pick=1, next_pick=24), drafted_ids=set())
    assert board
    row = board[0]
    assert row["confidence"] == "ESPN live ADP + season projection"
    assert "probability" in row["availability_method"]
    assert "tier" in row


def test_missing_live_espn_draft_fields_returns_no_board(tmp_path):
    service = DraftIntelligenceService(tmp_path)
    board = service.current_board(demo_league(), DraftSettings(current_pick=1, next_pick=24), drafted_ids=set())
    assert board == []


def test_espn_rank_produces_board_when_projection_and_adp_are_missing(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.espn_rank = index
    board = DraftIntelligenceService(tmp_path).current_board(
        league, DraftSettings(current_pick=1, next_pick=24), drafted_ids=set()
    )
    assert board
    assert board[0]["consensus_adp"] == 1
    assert board[0]["season_projection"] is None
    assert board[0]["confidence"] == "ESPN live draft rank; season projection unavailable"


def test_pick_plan_uses_live_values_and_returns_ranked_backups(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 9)
        player.season_projection = player.mean * 14
    service = DraftIntelligenceService(tmp_path)
    settings = DraftSettings(league_size=len(league.teams), current_pick=1, next_pick=8)
    plan = service.pick_plan(league, settings, set(), [], backup_count=3)
    assert len(plan) == min(4, len([p for p in league.free_agents if p.position in {"QB", "RB", "WR", "TE"}]))
    assert all(not row["fallback_used"] for row in plan)
    assert plan == sorted(plan, key=lambda row: (row["pick_score"], row["expected_vor"]), reverse=True)
    assert all("ESPN ADP" in row["recommendation_reason"] for row in plan)


def test_draft_strategy_changes_scoring_and_is_explained(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 9)
        player.season_projection = player.mean * 14
    service = DraftIntelligenceService(tmp_path)
    settings = DraftSettings(league_size=len(league.teams), current_pick=1, next_pick=8)
    safe = service.pick_plan(league, settings, set(), [], strategy="safe")
    aggressive = service.pick_plan(league, settings, set(), [], strategy="aggressive")
    assert safe and aggressive
    assert all(row["strategy"] == "safe" for row in safe)
    assert all(row["strategy"] == "aggressive" for row in aggressive)
    assert [row["pick_score"] for row in safe] != [row["pick_score"] for row in aggressive]


def test_draft_insights_are_roster_and_pick_aware(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(18 + index * 8)
        player.season_projection = player.mean * 14
    settings = DraftSettings(league_size=len(league.teams), current_pick=25, next_pick=40)
    insights = DraftIntelligenceService(tmp_path).draft_insights(
        league,
        settings,
        drafted_ids=set(),
        user_drafted_positions=["RB", "WR"],
    )
    assert insights["best"]
    assert insights["strong"]
    assert insights["round"] == 1 + (settings.current_pick - 1) // settings.league_size
    assert {row["position"] for row in insights["needs"]} == {"QB", "RB", "WR", "TE"}
    assert next(row for row in insights["needs"] if row["position"] == "RB")["filled"] == 1
    assert all(row["expected_vor"] > 0 for row in insights["sleepers"])
    assert all(row["consensus_adp"] > settings.current_pick for row in insights["sleepers"])


def test_draft_insights_return_no_fake_groups_without_live_fields(tmp_path):
    insights = DraftIntelligenceService(tmp_path).draft_insights(
        demo_league(), DraftSettings(), drafted_ids=set(), user_drafted_positions=[]
    )
    assert insights == {"needs": [], "best": [], "strong": [], "sleepers": []}


def test_overall_pick_plan_maps_targets_to_snake_slot(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 5)
        player.season_projection = player.mean * 14
    plan = DraftIntelligenceService(tmp_path).overall_pick_plan(league, draft_slot=2, rounds=3)
    assert [row["overall_pick"] for row in plan] == [2, 7, 10][: len(plan)]
    assert len({row["player_id"] for row in plan}) == len(plan)
    assert all(len(row["backups"]) <= 3 for row in plan)


def test_last_slot_overall_plan_keeps_back_to_back_turn(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 5)
        player.season_projection = player.mean * 14
    last_slot = len(league.teams)
    plan = DraftIntelligenceService(tmp_path).overall_pick_plan(league, draft_slot=last_slot, rounds=2)
    assert [row["overall_pick"] for row in plan] == [last_slot, last_slot + 1]


def test_league_draft_type_uses_espn_settings():
    league = demo_league()
    league.raw_settings = {"draftSettings": {"type": "SNAKE"}}
    assert league_draft_type(league) == "snake"
    league.raw_settings = {"draftSettings": {"type": "AUCTION"}}
    assert league_draft_type(league) == "auction"


def test_drafted_players_are_removed(tmp_path):
    dataset = build_draft_dataset(load_csv(ADP), load_csv(OUTCOMES))
    train_draft_artifact(dataset, tmp_path)
    league = demo_league()
    first = league.teams[0].players[0]
    board = DraftIntelligenceService(tmp_path).current_board(league, DraftSettings(current_pick=1, next_pick=24), drafted_ids={first.id})
    assert all(row["player_id"] != first.id for row in board)
