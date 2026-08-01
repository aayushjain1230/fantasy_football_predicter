from pathlib import Path


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


def test_streamlit_app_does_not_load_espn_cookies_from_streamlit_secrets():
    import streamlit_app

    assert "ESPN_S2" not in streamlit_app.OPTIONAL_SECRET_KEYS
    assert "ESPN_SWID" not in streamlit_app.OPTIONAL_SECRET_KEYS


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
