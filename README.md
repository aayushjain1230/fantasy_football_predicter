# Fourth Down

Fourth Down is a free, explainable fantasy football decision engine for ESPN leagues, focused on honest lineup, waiver, trade, draft, and league-strength decisions.

Screenshot: after deployment, add a real screenshot of the Streamlit Home or Dashboard page here. Do not use a mockup as evidence of live functionality.

> Fourth Down is independent and is not affiliated with ESPN, the NFL, or any sportsbook. Recommendations are uncertain estimates, not guarantees or betting advice.

## Current Status

The production Streamlit app is live-data-only. It requires a successful ESPN league connection and never substitutes sample players, fixture projections, synthetic history, invented ADP, or made-up recommendations. If ESPN does not supply a required field, the affected feature clearly reports that it is unavailable. Repository fixture artifacts remain solely for isolated development tests and are not used for connected ESPN recommendations.

Implemented and verified:

- Streamlit entrypoint at `streamlit_app.py`
- Connection-first interface with no demo-data path
- Public ESPN league connection when ESPN permits public access
- ESPN roster, lineup-slot, scoring, team, and free-agent normalization
- Exact legal lineup optimization with unique-player constraints
- Conservative, Balanced, and Aggressive lineup objectives
- Waiver add/drop analysis based on full legal lineup impact
- Trade analyzer with before/after legal roster impact and required-drop handling
- Draft assistant using ESPN's live player pool, ADP, rankings, and season projections
- Live snake-draft room with draft-slot awareness, roster-needs scoring, a best pick, ranked backups, and pick-by-pick recalculation
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
- Provider status table with live/cached/stale/unavailable labels
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

Calculated estimates (real inputs, modeled outputs):

- Projection uncertainty ranges
- Trade value-balance score
- Market adjustment layer is disabled unless explicitly enabled and remains bounded/provenance-labeled
- Decision journal persistence is local SQLite/ephemeral on Streamlit Cloud, not permanent multi-user storage
- Phase 4 simulation correlation structure and team-score intervals
- Rest-of-season waiver gain is shown only when ESPN supplies season projections for both players
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

The app opens in a connection-first state with no league data displayed. A successful live ESPN connection is required before decision pages become available.

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

Do not put one user's `ESPN_S2` or `ESPN_SWID` cookies into shared Streamlit
deployment secrets. Private-league users can enter both values in password
fields during connection; Fourth Down uses them for that ESPN request and does
not persist them.

### The Odds API in the website

After connecting a league, open **Settings → Data Freshness → The Odds API**.
Paste your key into the password field and select **Validate and use key**. The
key lives only in that Streamlit browser session and is never written to the
repository, `.env`, SQLite, provider cache, exports, or league data. Validation
uses The Odds API sports endpoint. Select **Refresh live NFL odds** only when
you want a new NFL totals/spreads/moneylines snapshot; the app displays the
provider-reported request cost and remaining credits and suppresses refreshes
inside a 15-minute window.

For a private local installation, `ODDS_API_KEY` in `.env` remains supported.
For a shared Streamlit deployment, prefer the session field so each user owns
their key and quota.

## ESPN Leagues

Public ESPN leagues:

- Enter a numeric ESPN league ID and season on the Connect League page
- Fourth Down requests ESPN's public fantasy endpoints
- If ESPN denies access, the app explains that the league is likely private

Private ESPN leagues:

- Enter the numeric league ID, season, and both `espn_s2` and `SWID` values
- The credential fields are password-masked and cleared when the form submits
- Credentials are sent only to ESPN for the connection request and are not
  stored in SQLite, exports, URLs, caches, or the connected league object
- A local single-user environment may instead provide `ESPN_S2` and
  `ESPN_SWID` through `.env`
- Only enter ESPN credentials on a deployment you trust, and never commit them

## Provider Table

| Provider | State Meaning | Used By | Unavailable Behavior |
|---|---|---|---|
| ESPN | Live only after a successful league response | Rosters, opponent rosters, scoring, lineup slots, weekly/season projections, ADP, rankings, and free agents | The affected recommendation remains unavailable |
| The Odds API | Cached or stale only after a successful cached response | Bounded projection adjustment when cached data matches a team | Projection uses baseline and marks game markets missing |
| Open-Meteo | Not automatically refreshed in Streamlit Phase 1 | Weather adjustment only when a cache exists from supported backend paths | No weather adjustment is applied |
| nflverse | Download endpoint exists, but parsed usage/injury integration is not implemented | Not integrated in Phase 1 | No nflverse adjustment is made |
| Player props | Unavailable | Not integrated in Phase 1 | Player props are listed as missing |

A configured key does not prove live data. Provider status is based on the code path and available cache/session state.

## Methodology

Projection system:

- Uses a shared projection service consumed by lineups, waivers, trades, player research, reports, and simulations
- Uses ESPN weekly projections for connected ESPN players
- Never substitutes repository fixture artifacts for a connected ESPN player
- Marks projections and dependent recommendations unavailable when ESPN omits the required value
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
- Repository model artifacts are test-only and are not production data sources

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
- Simulate unresolved regular-season games against the actual normalized ESPN schedule when available
- Generate team score distributions from legal optimized lineups and ESPN projection inputs
- Simulate playoff qualification, seeds, first-round byes, and championship outcomes with supported bracket assumptions
- Report Monte Carlo standard error for probabilities; this describes simulation sampling uncertainty only
- Resolve small clinch/elimination spaces with exact enumeration instead of treating finite Monte Carlo 0% or 100% as proof
- Use supported record plus points-for tiebreaking unless ESPN exposes an unsupported or ambiguous rule
- Disclose unsupported median-game, reseeding, multi-week playoff, and tiebreaker assumptions beside the results

Test-only projection artifacts:

- `models/projections/latest/QB.json`
- `models/projections/latest/RB.json`
- `models/projections/latest/WR.json`
- `models/projections/latest/TE.json`
- `models/projections/latest/manifest.json`
- `models/projections/latest/evaluation.json`

These artifacts support repeatable tests only. They are not shown as live accuracy and are not used for connected ESPN players.

Draft intelligence:

- ADP is ESPN's average draft position from the connected live player pool.
- Players without both ESPN ADP and ESPN season projection are omitted rather than estimated.
- Value rank compares ESPN season projection against the connected league's replacement level.
- No fabricated next-pick availability probability or historical performance class is displayed.
- Tiers are assigned from the live value ranking.
- Draft state is stored in `st.session_state` and is not permanent storage.

Test-only draft artifacts:

- `models/draft/latest/draft_model.json`
- `models/draft/latest/evaluation.json`

These files validate offline code paths only and do not drive the production draft board.

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
