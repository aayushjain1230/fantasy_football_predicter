# Fourth Down

Fourth Down is a free, explainable fantasy football decision engine for ESPN leagues, focused on honest lineup, waiver, trade, draft, and league-strength decisions.

Screenshot: after deployment, add a real screenshot of the Streamlit Home or Dashboard page here. Do not use a mockup as evidence of live functionality.

> Fourth Down is independent and is not affiliated with ESPN, the NFL, or any sportsbook. Recommendations are uncertain estimates, not guarantees or betting advice.

## Current Status

Phase 1 repaired technical credibility and provides a Streamlit app deployable on Streamlit Community Cloud. Phase 2 adds a reproducible projection-service architecture with position-specific JSON model artifacts trained from a deterministic fixture dataset. Phase 3 adds fixture-backed draft-market intelligence for ADP-relative value, next-pick availability, tiers, and draft-room state. Phase 4 adds schedule-aware league simulation, playoff forecasting, scenario controls, all-play records, and schedule-luck analysis. Phase 5 consolidates those backend systems into a unified in-season decision brief and five primary product destinations. Phase 6 adds centralized configuration, safe artifact validation, operational health summaries, a real prediction-ledger path, safe exports, data-quality checks, benchmark reports, and launch-readiness documentation. The current BoringFantasyBot-inspired extension adds optional market-context models, identity resolution, recommendation previews, and a local decision journal without copying arbitrary betting scores or automated transaction behavior. Fixture artifacts validate the pipeline and integration; they are not production accuracy claims.

Implemented and verified:

- Streamlit entrypoint at `streamlit_app.py`
- Demo mode with clearly labeled sample data and no required API keys
- Public ESPN league connection when ESPN permits public access
- ESPN roster, lineup-slot, scoring, team, and free-agent normalization
- Exact legal lineup optimization with unique-player constraints
- Conservative, Balanced, and Aggressive lineup objectives
- Waiver add/drop analysis based on full legal lineup impact
- Trade analyzer with before/after legal roster impact and required-drop handling
- Draft assistant using value over replacement, positional scarcity, roster need, and heuristic risk
- Player research with projection provenance and no synthetic history
- Unified weekly brief with ranked user-facing decision objects
- Primary Streamlit navigation consolidated to Home, My Team, Players, League, and Settings
- My Team workspace with lineup, waivers, trades, roster outlook, and injury contingencies
- Players workspace with projection, market/draft, history, and model-detail sections
- League workspace with outlook, standings, scenarios, power, schedule luck, and team detail sections
- Schedule-aware League Outlook using normalized remaining matchups when available
- League scenario controls with session-local deterministic outcome constraints
- Monte Carlo playoff, seed, bye, and championship estimates
- Projected final standings with Monte Carlo standard error
- Team score distributions from legal optimized lineups
- All-play records, expected wins, schedule luck, points-against luck, and remaining schedule strength
- Power rankings separated into team strength, resume, and future outlook
- Provider status table with live/cached/stale/demo/unavailable labels
- Optional market-context provider interface with consensus calculations, unavailable fallback, and no fabricated betting lines
- Canonical player identity resolution with ambiguity detection
- Recommendation preview workflow with explicit unsupported execution status
- Local decision journal with hashed league identifiers and retrospective regret helpers
- Settings workspace with connection, provider status, methodology, privacy, and evaluation details
- Centralized configuration with required/optional/secret/local-only classifications
- Projection artifact validation with labeled fallback behavior
- Prediction ledger and controlled outcome-ingestion path for real pre-outcome evaluation
- CSV export sanitization for spreadsheet formula prefixes
- Data-quality, benchmark, data-refresh, and model-candidate workflows
- Automated tests and GitHub Actions CI

Experimental or heuristic:

- Projection uncertainty ranges
- Phase 2 fixture-trained projection artifacts
- Phase 3 fixture-trained draft intelligence artifacts
- Trade value-balance score
- Draft availability-at-next-pick score
- Market adjustment layer is disabled unless explicitly enabled and remains bounded/provenance-labeled
- Decision journal persistence is local SQLite/ephemeral on Streamlit Cloud, not permanent multi-user storage
- Phase 4 simulation correlation structure and team-score intervals
- Rest-of-season projections use week-specific projection-service calls, but future opponent and bye context are still labeled missing until integrated
- ESPN tiebreaker, reseeding, median-game, and multi-week playoff support when raw settings are ambiguous

Planned, not implemented in Phase 1:

- Original machine-learning projections
- Production historical nflverse training/backtesting
- Production ADP ingestion, consensus market snapshots, and draft-decision backtesting
- ADP breakout model
- LLM chat or OpenAI integration
- Authentication and permanent multi-user cloud storage
- Automatic ESPN transactions

## Run Locally

Requirements:

- Python 3.11 or newer

Install dependencies:

```bash
python -m pip install -e "./backend[dev]" -r requirements.txt
```

Start the Streamlit app from the repository root:

```bash
streamlit run streamlit_app.py
```

The app opens in demo mode if no league is connected.

## Streamlit Community Cloud

Deployment settings:

- Repository: this GitHub repository
- Branch: your deployment branch
- Main file path: `streamlit_app.py`
- Python version: 3.11 or newer
- Dependency file: root `requirements.txt`

Optional Streamlit secrets:

```toml
ODDS_API_KEY = ""
OPENWEATHER_API_KEY = ""
DIGEST_WEBHOOK_URL = ""
```

Do not put `ESPN_S2` or `ESPN_SWID` cookies into a shared public Streamlit deployment. Private ESPN leagues are local-only in Phase 1.

## ESPN Leagues

Demo mode:

- Works without API keys
- Uses sample players and clearly labels the data as demo data
- Is intended for testing the interface and decision workflow

Public ESPN leagues:

- Enter a numeric ESPN league ID and season on the Connect League page
- Fourth Down requests ESPN's public fantasy endpoints
- If ESPN denies access, the app explains that the league is likely private

Private ESPN leagues:

- Private league support is local-only in Phase 1
- A local single-user environment may provide `ESPN_S2` and `ESPN_SWID` through `.env`
- Public users should not paste ESPN cookies into the Streamlit UI
- Cookies are never displayed by the app and should never be committed

## Provider Table

| Provider | State Meaning | Used By | Unavailable Behavior |
|---|---|---|---|
| ESPN | Live only after a successful league response; Demo in demo mode | Rosters, teams, scoring, lineup slots, baseline projections, free agents | Demo mode remains available |
| The Odds API | Cached or stale only after a successful cached response | Bounded projection adjustment when cached data matches a team | Projection uses baseline and marks game markets missing |
| Open-Meteo | Not automatically refreshed in Streamlit Phase 1 | Weather adjustment only when a cache exists from supported backend paths | No weather adjustment is applied |
| nflverse | Download endpoint exists, but parsed usage/injury integration is not implemented | Not integrated in Phase 1 | No nflverse adjustment is made |
| Player props | Unavailable | Not integrated in Phase 1 | Player props are listed as missing |

A configured key does not prove live data. Provider status is based on the code path and available cache/session state.

## Methodology

Projection system:

- Uses a shared projection service consumed by lineups, waivers, trades, player research, reports, and simulations
- Loads trusted repository-owned JSON artifacts from `models/projections/latest/`
- Supports QB, RB, WR, and TE artifacts in Phase 2
- Falls back to the Phase 1 projection-adjustment engine for K, DST, missing artifacts, corrupt artifacts, or incompatible model versions
- Reports baseline source, baseline value, model version, training cutoff, important inputs, final value, missing inputs, reasons, limitations, and uncertainty method
- Does not load user-supplied pickle/joblib artifacts
- Preserves baseline projection, market adjustment, and final projection as separate fields
- Market data is optional; if unavailable, the projection remains baseline-driven and lists market context as missing
- The conservative market-adjustment layer is bounded, transparent, and disabled by default unless explicitly evaluated/enabled

Phase 2 prediction definition:

- Observation unit: one player in one NFL week
- Target: fantasy points scored during that week
- Prediction timestamp: before kickoff
- Leakage policy: rolling/aggregate features are shifted and exclude the current player-week
- Supported positions: QB, RB, WR, TE
- Current committed artifacts: deterministic fixture artifacts, not production-trained models
- Canonical scoring basis: PPR fixture scoring; raw-stat scoring adapter supports common ESPN settings where mapped

Lineup optimizer:

- Uses exact search over legal slot assignments
- Enforces unique players
- Supports QB, RB, WR, TE, FLEX, SUPERFLEX, K, and DST
- Excludes unavailable players
- Reports missing slots when a full legal lineup cannot be formed

Lineup objectives:

- Conservative: prioritizes the highest projected floor and reduces downside risk
- Balanced: maximizes adjusted expected fantasy points
- Aggressive: prioritizes ceiling and matchup-aware chance of beating the opponent
- Streamlit shows lineup recommendations as previews only; it does not submit ESPN transactions

League simulations:

- Start from current normalized standings and preserve completed results as facts
- Simulate unresolved regular-season games against the actual normalized ESPN/demo schedule when available
- Generate team score distributions from legal optimized lineups and Phase 2 projection service output
- Simulate playoff qualification, seeds, first-round byes, and championship outcomes with supported bracket assumptions
- Report Monte Carlo standard error for probabilities; this describes simulation sampling uncertainty only
- Resolve small clinch/elimination spaces with exact enumeration instead of treating finite Monte Carlo 0% or 100% as proof
- Use supported record plus points-for tiebreaking unless ESPN exposes an unsupported or ambiguous rule
- Disclose unsupported median-game, reseeding, multi-week playoff, and tiebreaker assumptions beside the results

Projection artifacts:

- `models/projections/latest/QB.json`
- `models/projections/latest/RB.json`
- `models/projections/latest/WR.json`
- `models/projections/latest/TE.json`
- `models/projections/latest/manifest.json`
- `models/projections/latest/evaluation.json`

See [docs/MODEL_CARD.md](docs/MODEL_CARD.md) for generated fixture evaluation metrics. The table is generated by `scripts/evaluate_projection_models.py`.

Draft intelligence:

- ADP means average draft position from a timestamped platform/source snapshot.
- Current committed ADP is fixture-only and must not be described as live market data.
- Consensus ADP is the median of fixture platform ADPs, with range and standard deviation preserved.
- Target: ADP-relative residual = actual value over replacement minus historical expected VOR at that ADP.
- Outcome classes are mutually exclusive: `UNDERPERFORM`, `MEET EXPECTATIONS`, and `OUTPERFORM`, using training residual thresholds.
- Performance risk and availability risk are separate displayed components.
- Next-pick availability uses an ADP-dispersion approximation because fixture data has no full pick distribution.
- Tiers are assigned from modeled expected VOR gaps.
- Draft state is stored in `st.session_state` and is not permanent storage.

Draft artifacts:

- `models/draft/latest/draft_model.json`
- `models/draft/latest/evaluation.json`

See [docs/DRAFT_MODEL_CARD.md](docs/DRAFT_MODEL_CARD.md). It is generated by `scripts/evaluate_draft_models.py`.

## Testing

Run tests:

```bash
python -m pytest backend/tests
```

Compile check:

```bash
python -m compileall -q backend streamlit_app.py
```

Headless Streamlit smoke test:

```bash
streamlit run streamlit_app.py --server.headless true
```

CI runs on pushes and pull requests and checks:

- Dependency installation
- Python compile checks
- Full Python test suite
- `streamlit_app.py` import
- Headless Streamlit health check
- Fixture historical-data build/train/evaluate smoke test
- Fixture ADP build/train/evaluate smoke test
- Data quality validation
- Deterministic performance smoke test
- Secret-pattern scan

Manual workflows:

- Data refresh validation: `.github/workflows/data-refresh.yml`
- Model candidate validation: `.github/workflows/model-candidate.yml`

Ordinary tests mock ESPN/network behavior and must not consume live API quota.

## Architecture

```text
fantasy_football/
  streamlit_app.py              Streamlit deployment entrypoint
  requirements.txt              Streamlit deployment dependencies
  .streamlit/
    config.toml                 Streamlit UI/server defaults
    secrets.toml.example        Safe optional secret names only
  backend/
    app/
      domain.py                 Pydantic models
      demo.py                   Demo league fixtures
      engine.py                 Projection adjustment, exact lineup optimizer, waivers
      advanced.py               Trades, draft, player research, rankings, calibration
      providers.py              ESPN normalization and provider status reporting
      projection_service.py     Shared Phase 2 projection service and JSON artifact loader
      simulation.py             Schedule-aware league simulation, scenarios, standings, and schedule-luck metrics
      decision_service.py       Unified weekly brief and recommendation layer
      config.py                 Centralized Phase 6 configuration
      artifacts.py              Safe artifact validation
      operations.py             Health summary and degradation matrix
      evaluation.py             Prediction ledger evaluation helpers
      exporting.py              Safe export utilities
      scoring.py                Fantasy scoring adapter
      persistence.py            Local SQLite helper for local/single-user use
      main.py                   Existing FastAPI API, preserved
    tests/                      Python tests
  scripts/                      Fixture data pipeline, training, evaluation
  models/projections/latest/    Trusted JSON projection artifacts
  models/draft/latest/          Trusted JSON draft intelligence artifacts
  frontend/                     Existing Next.js frontend, preserved
```

Streamlit calls Python service functions directly. It does not start FastAPI as a subprocess and does not make localhost HTTP calls.

## Security and Privacy

- Public Streamlit state is stored in `st.session_state` per browser session
- Streamlit session state can reset when the browser or server reconnects
- Session state is not authentication, tenant isolation, or permanent storage
- SQLite is local or ephemeral and is not appropriate for permanent multi-user cloud storage
- `.streamlit/secrets.toml` and `.env` are ignored by Git
- ESPN cookies should be treated like passwords
- The app does not log, display, or persist ESPN cookies in the Streamlit UI
- Fourth Down does not include ads, tracking, betting advice, or automatic ESPN transactions

## Known Limitations

- ESPN fantasy endpoints are unofficial and may change
- Public ESPN access depends on ESPN permitting the league response
- Private league support needs a secure authenticated design before public hosting
- No historical weekly player trend is shown unless a real source is integrated
- No nflverse usage/injury data is consumed by projections in Phase 1
- Phase 2 committed artifacts are trained from small fixtures; production historical nflverse artifacts still need a reliable data retrieval run
- No player prop source is integrated
- Calibration metrics are unavailable until enough real predictions and outcomes are stored
- Prediction-ledger evaluation remains unavailable until real pre-outcome predictions are recorded and matched to outcomes
- Decision-journal regret compares recommendations only against alternatives that were valid at decision time
- ESPN playoff tiebreakers, reseeding, median games, and multi-week playoff rounds are conditional when raw settings are unavailable or ambiguous
- Current live partial scoring is not mixed with full projections; current-week simulation is pregame-only unless final
- Player/team correlation modeling remains limited and is labeled as heuristic
- One demo schedule is synthetic and visibly labeled; production credibility depends on ESPN returning a complete public schedule
- Trade value balance and draft availability are heuristics, not trained predictions
- Fixture draft probabilities are architecture checks, not production-calibrated probabilities

## Roadmap

Recommended repository rename: consider renaming `fantasy_football_predicter` to `fourth-down` or `fantasy-football-decision-engine`.

Later phases may add:

- Real historical data ingestion
- Trained projection models
- Authentication and persistent multi-user storage
- More data-provider integrations
- Richer frontends built on the same domain logic

## Deeper Documentation

- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
- [Data sources and degradation](docs/data-sources.md)
- [Methodology](docs/methodology.md)
- [Evaluation](docs/evaluation.md)
- [Security and privacy](docs/security.md)
- [Screenshot guide](docs/screenshots.md)
