# Phase 1 Audit Notes

Fourth Down Phase 1 focuses on technical credibility for a deployable Streamlit app.

Current guarantees:

- Demo data is labeled as `DEMO`.
- Provider states use `LIVE`, `CACHED`, `STALE`, `DEMO`, and `UNAVAILABLE`.
- Missing odds, weather, player props, nflverse usage, or historical trends are shown as missing or unavailable.
- The lineup optimizer uses exact legal assignment rather than a sequential greedy choice.
- Calibration reports real metrics only when enough prediction/outcome pairs exist.
- Streamlit session state is treated as temporary session state, not authentication or permanent storage.
- Phase 2 projection artifacts are JSON files loaded from repository-owned paths, not user-supplied pickle/joblib files.
- Fixture model metrics are labeled as fixture validation, not production accuracy.
- Phase 3 ADP and draft-intelligence metrics are fixture-only unless a legal production ADP source is configured.
- Phase 5 primary Streamlit navigation is consolidated around user goals: Home, My Team, Players, League, and Settings. Model, simulation, provider, and methodology details are nested features rather than primary destinations.

Explicit non-goals for Phase 1:

- No trained projection model.
- No production-trained historical projection model.
- No LLM or OpenAI integration.
- Phase 4 adds a schedule-aware simulator, Playoff Machine, all-play records, expected wins, and schedule-luck views. Remaining caveats: ambiguous ESPN tiebreakers, reseeding, median-game settings, and multi-week playoff rounds are disclosed as unsupported or conditional instead of treated as exact.
- No private-league cookie handling in a shared public Streamlit deployment.
- No permanent multi-user cloud storage.
- No production ADP refresh or full draft-decision backtest.
