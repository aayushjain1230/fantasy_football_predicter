from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_imports_without_running():
    import streamlit_app

    assert "Home" in streamlit_app.PAGES
    assert list(streamlit_app.PAGES) == ["Home", "My Team", "Players", "Draft", "League", "Settings"]
    assert streamlit_app.PAGES["Draft"] is streamlit_app.page_draft_context
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


def test_default_connection_surface_uses_url_not_technical_identifiers():
    app_path = Path(__file__).resolve().parents[2] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    next(button for button in app.button if button.label == "Connect ESPN League").click()
    app = app.run()
    labels = [field.label for field in app.text_input]
    assert "Paste ESPN league URL" in labels
    assert "League ID" not in labels
    assert "Team ID" not in labels
    assert "espn_s2 cookie" not in labels
    assert "SWID cookie" not in labels
    assert any(button.label == "Connect ESPN" for button in app.button)
    assert [tab.label for tab in app.tabs][:3] == ["ESPN", "Sleeper", "Manual Setup"]


def test_private_connection_is_one_direct_form_without_extra_expanders():
    source = (Path(__file__).resolve().parents[2] / "streamlit_app.py").read_text(encoding="utf-8")
    assert '("Public league", "Private league")' in source
    assert 'st.text_input("ESPN secure session"' in source
    assert 'st.text_input("ESPN account session"' in source
    assert 'st.form_submit_button("Connect ESPN"' in source
    assert 'st.expander("Private league' not in source
    assert 'st.expander("One-click browser connection")' not in source


def test_connected_draft_setup_plan_and_manual_live_flow():
    from app.demo import demo_league

    app_path = Path(__file__).resolve().parents[2] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    league = demo_league()
    league.draft_pool = [
        player.model_copy(update={"average_draft_position": float(index * 8), "season_projection": player.mean * 14})
        for index, player in enumerate(league.free_agents, 1)
    ]
    app.session_state["league"] = league
    app.session_state["league_connected"] = True
    app.session_state["mode"] = "live"
    app = app.run()
    app.radio[0].set_value("Draft")
    app = app.run()
    assert any(button.label == "Confirm Draft Setup" for button in app.button)
    next(button for button in app.button if button.label == "Confirm Draft Setup").click()
    app = app.run()
    workspace = next(radio for radio in app.radio if "Live Draft" in radio.options)
    assert workspace.options == ["My Draft Plan", "Live Draft"]
    workspace.set_value("Live Draft")
    app = app.run()
    assert any(button.label == "Start Manual Live Draft" for button in app.button)
    next(button for button in app.button if button.label == "Start Manual Live Draft").click()
    app = app.run()
    assert not app.exception
    assert any("YOU’RE ON THE CLOCK" in item.value for item in app.success)
    assert any(button.label == "Drafted" for button in app.button)
    assert any(button.label == "Ignore for this pick" for button in app.button)


def test_espn_synced_picks_use_confirmed_configuration_not_provider_owner():
    import streamlit_app
    from app.demo import demo_league
    from app.draft_intelligence import build_draft_configuration

    config = build_draft_configuration(demo_league(), league_size=10, draft_slot=6, total_rounds=20, manager_count_confirmed=True, draft_slot_confirmed=True)
    picks = streamlit_app.synced_picks_for_configuration(
        [{"number": 10, "owner_slot": 99, "player_id": "a"}, {"number": 11, "owner_slot": 99, "player_id": "b"}],
        config,
    )
    assert [pick["owner_slot"] for pick in picks] == [10, 10]
    assert [pick["round"] for pick in picks] == [1, 2]


def test_every_connected_primary_page_is_simple_and_renders_without_error():
    from app.demo import demo_league

    app_path = Path(__file__).resolve().parents[2] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=60).run()
    league = demo_league()
    league.draft_pool = [
        player.model_copy(update={"average_draft_position": float(index * 8), "season_projection": player.mean * 14})
        for index, player in enumerate(league.free_agents, 1)
    ]
    app.session_state["league"] = league
    app.session_state["league_connected"] = True
    app.session_state["mode"] = "live"
    app = app.run()
    for page in ["Home", "My Team", "Players", "Draft", "Settings"]:
        navigation = next(radio for radio in app.radio if "Home" in radio.options)
        navigation.set_value(page)
        app = app.run()
        assert not app.exception, page
        visible_labels = [tab.label for tab in app.tabs] + [value for radio in app.radio for value in radio.options]
        assert not any("Lab" in label for label in visible_labels)
    navigation = next(radio for radio in app.radio if "Home" in radio.options)
    navigation.set_value("My Team")
    app = app.run()
    decision_nav = next(radio for radio in app.radio if "Set My Lineup" in radio.options)
    assert decision_nav.options == ["Set My Lineup", "Waiver Adds", "Trades"]


def test_connected_league_page_renders_concise_outlook():
    from app.demo import demo_league

    app_path = Path(__file__).resolve().parents[2] / "streamlit_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=90).run()
    app.session_state["league"] = demo_league()
    app.session_state["league_connected"] = True
    app.session_state["mode"] = "live"
    app = app.run()
    navigation = next(radio for radio in app.radio if "Home" in radio.options)
    navigation.set_value("League")
    app = app.run()
    assert not app.exception
    assert any("League Standings" in item.value for item in app.markdown)


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
