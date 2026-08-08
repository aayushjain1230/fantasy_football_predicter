from pathlib import Path

import pytest

from app.demo import demo_league
from app.draft_intelligence import (
    OUTCOME_CLASSES,
    DraftIntelligenceService,
    DraftSelection,
    DraftSettings,
    DraftState,
    availability_at_next_pick,
    build_draft_dataset,
    build_draft_configuration,
    best_roster_assignment,
    classify_residual,
    consensus_adp,
    fit_outcome_thresholds,
    league_draft_type,
    league_team_count,
    load_csv,
    marginal_roster_fit,
    next_owned_pick,
    owner_of_pick,
    pick_for_slot,
    picks_for_slot,
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


def test_configured_espn_league_size_wins_over_partial_team_list():
    league = demo_league()
    league.raw_settings = {"size": 12}
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(10 + index * 5)
        player.season_projection = player.mean * 14
    assert len(league.teams) != 12
    assert league_team_count(league) == 12
    plan = DraftIntelligenceService().overall_pick_plan(league, draft_slot=12, rounds=2)
    assert [row["overall_pick"] for row in plan] == [12, 13]


@pytest.mark.parametrize("league_size", [8, 10, 12, 14])
@pytest.mark.parametrize("draft_type", ["snake", "linear"])
def test_every_pick_has_one_owner_and_every_slot_one_pick_per_round(league_size, draft_type):
    rounds = 20
    all_picks = []
    for slot in range(1, league_size + 1):
        owned = picks_for_slot(slot, league_size, rounds, draft_type)
        assert len(owned) == rounds
        assert all(owner_of_pick(pick, league_size, draft_type) == slot for pick in owned)
        all_picks.extend(owned)
    assert sorted(all_picks) == list(range(1, league_size * rounds + 1))


def test_snake_examples_and_turns_are_exact():
    assert picks_for_slot(1, 12, 5, "snake") == [1, 24, 25, 48, 49]
    assert picks_for_slot(3, 12, 5, "snake") == [3, 22, 27, 46, 51]
    assert picks_for_slot(6, 12, 5, "snake") == [6, 19, 30, 43, 54]
    assert picks_for_slot(10, 12, 5, "snake") == [10, 15, 34, 39, 58]
    assert picks_for_slot(12, 12, 5, "snake") == [12, 13, 36, 37, 60]
    assert next_owned_pick(12, 12, 12, "snake") == 12
    assert next_owned_pick(13, 12, 12, "snake") == 13
    assert next_owned_pick(14, 12, 12, "snake") == 36


def test_auction_has_no_owned_pick_order():
    assert picks_for_slot(1, 12, 20, "auction") == []
    assert next_owned_pick(1, 1, 12, "auction") is None
    with pytest.raises(ValueError):
        owner_of_pick(1, 12, "auction")


def test_flex_and_superflex_are_exact_shared_assignments():
    flex = best_roster_assignment(["RB", "WR"], ["RB", "FLEX"])
    assert flex["filled"] == 2
    assert marginal_roster_fit(["RB"], "WR", ["RB", "FLEX"]) == 1
    assert marginal_roster_fit(["RB", "WR"], "TE", ["RB", "FLEX"]) == 0
    superflex = best_roster_assignment(["QB", "QB", "RB"], ["QB", "SUPERFLEX", "RB"])
    assert superflex["filled"] == 3
    assert [row["position"] for row in superflex["assignments"]].count("QB") == 2


def test_configuration_reads_bench_scoring_and_override():
    league = demo_league()
    league.raw_settings = {
        "size": 12,
        "draftSettings": {"type": "SNAKE"},
        "rosterSettings": {"lineupSlotCounts": {"20": 7, "21": 2}},
        "scoringSettings": {"scoringItems": [{"statId": 53, "points": 1}]},
    }
    config = build_draft_configuration(league, league_size=10, draft_slot=10, total_rounds=18)
    assert config.league_size == 10
    assert config.bench_slots == 7
    assert config.ir_slots == 2
    assert config.scoring_format == "full PPR"
    assert config.user_owned_picks[:2] == [10, 11]


def test_canonical_state_prevents_duplicates_and_undoes_exactly():
    config = build_draft_configuration(demo_league(), league_size=12, draft_slot=6)
    state = DraftState(configuration=config)
    selection = DraftSelection(overall_pick=1, round_number=1, pick_in_round=1, owner_slot=1, player_id="p1", player_name="Player", position="RB")
    state = state.record(selection)
    assert state.current_overall_pick == 2
    with pytest.raises(ValueError, match="PLAYER_ALREADY_DRAFTED"):
        state.record(selection.model_copy(update={"overall_pick": 2}))
    restored = state.undo()
    assert restored.selections == []
    assert restored.current_overall_pick == 1


def test_value_cliff_tiers_and_waiting_fields_exist(tmp_path):
    league = demo_league()
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 8)
        player.season_projection = player.mean * 14
    board = DraftIntelligenceService(tmp_path).current_board(league, DraftSettings(current_pick=1, next_pick=20), set())
    assert board
    assert all("tier_drop_after_player" in row for row in board)
    assert all(row["availability_label"] in {"LOW", "MEDIUM", "HIGH"} for row in board)
    assert all(0.05 <= row["availability_probability"] <= 0.95 for row in board)
    assert all(row["cost_of_waiting"] >= 0 for row in board)


def test_snake_turn_pair_is_jointly_ranked(tmp_path):
    league = demo_league()
    league.raw_settings = {"size": 4, "draftSettings": {"type": "SNAKE"}}
    for index, player in enumerate(league.free_agents, 1):
        player.average_draft_position = float(index * 4)
        player.season_projection = player.mean * 14
    settings = DraftSettings(league_size=4, current_pick=4, next_pick=5, draft_type="snake")
    pairs = DraftIntelligenceService(tmp_path).turn_pair_plan(league, settings, 4, set(), [], "balanced")
    assert pairs
    assert all(row["first"]["player_id"] != row["second"]["player_id"] for row in pairs)
    assert pairs == sorted(pairs, key=lambda row: row["pair_score"], reverse=True)


def test_drafted_players_are_removed(tmp_path):
    dataset = build_draft_dataset(load_csv(ADP), load_csv(OUTCOMES))
    train_draft_artifact(dataset, tmp_path)
    league = demo_league()
    first = league.teams[0].players[0]
    board = DraftIntelligenceService(tmp_path).current_board(league, DraftSettings(current_pick=1, next_pick=24), drafted_ids={first.id})
    assert all(row["player_id"] != first.id for row in board)
    marginal_roster_fit,
    next_owned_pick,
    owner_of_pick,
    pick_for_slot,
    picks_for_slot,
