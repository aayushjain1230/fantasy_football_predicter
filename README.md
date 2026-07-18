# Fourth Down — Fantasy Football Decision Engine

Fourth Down is a zero-cost, Vegas-first ESPN fantasy football decision system. It connects to an ESPN league, normalizes its roster and scoring data, projects player ranges, simulates matchups, and turns those results into lineup and waiver actions with plain-English reasoning.

## Current phase

Phases 1 and 2 are implemented: ESPN connection, normalized models, provider-aware projections, lineup and waiver decisions, draft rankings, full-roster trade evaluation, player research, what-if swaps, league power rankings, final-standings simulations, calibration diagnostics, CSV reporting, FastAPI endpoints, and the responsive decision workspace. Phase 3 remains optional operational work: scheduled digests, deployment, and production-scale historical persistence.

## Free data and APIs

The app works immediately in labeled **DEMO** mode. For real data:

| Purpose | Provider | Cost | Configuration |
|---|---|---:|---|
| Public/private league | ESPN unofficial fantasy endpoints | Free | Public: league ID only. Private: `ESPN_S2`, `ESPN_SWID` |
| NFL schedules/rosters/usage | nflverse releases / `nfl_data_py` | Free | none |
| Weather | Open-Meteo | Free | none |
| Game spreads/totals | The Odds API | Free tier (500 requests/month) | `ODDS_API_KEY` |
| Storage | SQLite | Free | none |

The Odds API key is the only conventional key. Player props are not reliably free and are optional; the engine does not pretend otherwise. ESPN cookies belong only in the backend environment and are never returned to the browser.

`.env` contains your real local credentials and is ignored by Git. `.env.example` is intentionally blank: it documents supported variable names for a fresh installation and is never preferred over an existing `.env`.

## Privacy and security

The default installation stores league snapshots, provider caches, predictions, and draft state in local SQLite. It includes strict request validation, a 1 MB request limit, per-client rate limits, origin checks on state-changing requests, restrictive CORS and browser security headers, no-store API responses, Discord webhook allowlisting, and an in-app deletion control at `/privacy`. It contains no advertising or analytics tracker. Never commit `.env` or share ESPN cookies; treat them like passwords.

### RLS and AI boundaries

SQLite does not implement row-level security. The default build is therefore deliberately single-user and local. Setting `MULTI_USER_MODE=true` makes startup fail instead of pretending application filters are RLS. A hosted multi-user version must add authenticated PostgreSQL storage, enable and force RLS on every user-owned table, define owner policies using the authenticated user ID, and test cross-tenant denial before deployment.

The current Ask Engine performs local template matching and makes no LLM request. `/api/ask` nevertheless has a dedicated 10-request-per-minute limit. The future LLM boundary constructs immutable system/developer/user roles separately, HTML-escapes user content, wraps it in `UNTRUSTED_USER_INPUT` delimiters, caps its length, and never concatenates it into a system or developer message.

## Easiest start on Windows

Double-click **`Start Fourth Down.bat`** in the project folder. On the first run it creates the Python environment and installs the free dependencies. It then opens two server windows and launches `http://localhost:3000` automatically.

Keep both server windows open while using the site. Close them when finished.

From PowerShell, the same one-click launcher is:

```powershell
.\start.ps1
```

## Manual start

Backend (Python 3.11+):

```bash
python -m venv .venv
.venv/Scripts/pip install -e "backend[dev]"
.venv/Scripts/uvicorn app.main:app --app-dir backend --reload
```

Frontend (Node 20+), in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The API runs at `http://localhost:8000`. Copy `.env.example` to `.env`; never commit real cookies or keys.

Tests:

```bash
python -m pytest backend/tests
```

## Architecture

- `backend/app/domain.py`: typed normalized league and projection models
- `backend/app/providers.py`: ESPN boundary and provider status registry
- `backend/app/engine.py`: bounded projections, lineup legality, Monte Carlo, waivers
- `backend/app/main.py`: validated API surface with secret-safe errors
- `frontend/app`: landing, connection flow, and decision workspace
- `docs/AUDIT.md`: initial repository and compatibility audit

## Private ESPN connection

Log into ESPN in your browser, open Developer Tools → Application/Storage → Cookies → `espn.com`, then copy `espn_s2` and `SWID` into backend environment variables. Do not paste them into frontend code, screenshots, chat, or source control.

## Known limitations

ESPN’s endpoint is unofficial and can change. Free game odds have a monthly request budget, so production polling must be cached. nflverse injury/usage freshness depends on its published releases. Player props are optional because no dependable no-cost provider exists. Demo values are always labeled and never presented as live.
