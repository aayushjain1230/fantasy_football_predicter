from app.demo import demo_league
from app.ros_service import project_ros, replacement_value


def test_ros_projection_uses_remaining_weeks_and_labels_missing_future_context():
    league = demo_league()
    player = league.teams[0].players[0]
    ros = project_ros(player, league)
    assert len(ros.weeks) == (league.rules.playoff_end - league.week + 1)
    assert ros.expected_points == round(sum(week.expected_points for week in ros.weeks), 1)
    assert ros.upper_estimate > ros.expected_points > ros.lower_estimate
    assert "future opponent context" in ros.missing_future_context
    assert "verified bye week" in ros.missing_future_context


def test_replacement_value_is_position_specific():
    league = demo_league()
    assert replacement_value(league, "QB") > 0
    assert replacement_value(league, "NOT_A_POSITION") == 0
