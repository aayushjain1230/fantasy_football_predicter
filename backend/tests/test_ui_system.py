from ui.charts import CHART_COLORS, FOURTH_DOWN_PLOTLY_LAYOUT
from ui.components import badge, metric_card, player_card
from ui.formatting import h, percentage_points
from ui.navigation import PRIMARY_PAGES, focused_pages
from ui.styles import GLOBAL_CSS


class FakePlayer:
    name = '<script>alert("x")</script>'
    position = "WR"
    team = "DET"
    injury_status = "HEALTHY"
    availability = 1
    mean = 12.3


def test_ui_escapes_untrusted_html_values():
    assert h("<b>bad</b>") == "&lt;b&gt;bad&lt;/b&gt;"
    rendered = player_card(FakePlayer())
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_badges_use_consistent_recommendation_labels():
    assert "fd-badge-start" in badge("START")
    assert "fd-badge-hold" in badge("HOLD")
    assert "fd-badge-watch" in badge("WATCH")
    assert "fd-badge-trade" in badge("TRADE")
    assert "fd-badge-drop" in badge("DROP")


def test_global_css_contains_required_brand_tokens_and_responsive_rules():
    for token in ("--fd-bg: #080A0F", "--fd-orange: #F97316", "--fd-green: #4ADE80", "--fd-purple: #8B5CF6"):
        assert token in GLOBAL_CSS
    assert "@media (max-width: 760px)" in GLOBAL_CSS
    assert "prefers-reduced-motion" in GLOBAL_CSS


def test_navigation_stays_focused_and_draft_contextual():
    assert PRIMARY_PAGES == ("Home", "My Team", "Players", "League", "Settings")
    assert focused_pages(False) == list(PRIMARY_PAGES)
    assert focused_pages(True)[-1] == "Draft"


def test_chart_theme_and_formatting_are_consistent():
    assert FOURTH_DOWN_PLOTLY_LAYOUT["paper_bgcolor"] == "rgba(0,0,0,0)"
    assert CHART_COLORS["orange"] == "#F97316"
    assert percentage_points(0.031) == "+3.1 pts"
    assert "fd-metric-card" in metric_card("Projected Points", "123.4")
