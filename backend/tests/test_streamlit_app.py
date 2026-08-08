from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_imports_without_running():
    import streamlit_app

    assert "Home" in streamlit_app.PAGES
    assert list(streamlit_app.PAGES) == ["Home", "My Team", "Players", "League", "Settings"]
    forbidden = {
        "Lineup Lab",
        "Waiver Lab",
        "Trade Lab",
        "Projection Lab",
        "Simulation Lab",
        "Model Lab",
        "Research Lab",
        "Model Performance",
        "Trust Center",
        "Data Sources",
        "Methodology",
        "Backtesting",
        "Historical Explorer",
        "Playoff Machine",
        "Schedule Analysis",
    }
    assert not forbidden.intersection(streamlit_app.PAGES)


def test_streamlit_app_does_not_load_shared_espn_cookies_from_streamlit_secrets():
    import streamlit_app

    assert "ESPN_S2" not in streamlit_app.OPTIONAL_SECRET_KEYS
    assert "ESPN_SWID" not in streamlit_app.OPTIONAL_SECRET_KEYS


def test_streamlit_starts_disconnected_without_displaying_demo_league():
    app_path = Path(__file__).resolve().parents[2] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not app.exception
    rendered = "\n".join(item.value for item in app.markdown)
    assert "The Sunday League" not in rendered
    assert "DEMO DATA" not in rendered
    assert "No league connected" in rendered
    assert app.radio[0].options == ["Home", "Settings"]
    assert any(button.label == "Connect ESPN League" for button in app.button)


def test_no_synthetic_sine_trend_left_in_backend():
    root = Path(__file__).resolve().parents[1] / "app"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "math.sin" not in text
    assert "weekly_trend = [" not in text


def test_secret_placeholders_are_not_real_values():
    example = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml.example"
    text = example.read_text(encoding="utf-8")
    assert "ODDS_API_KEY = \"\"" in text
    assert "ESPN_S2" in text
    assert "secret-cookie-value" not in text
