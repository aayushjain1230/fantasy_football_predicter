# Fourth Down

**A free, explainable ESPN fantasy football decision engine.**

Fourth Down connects to an ESPN fantasy league, understands its scoring and roster rules, collects free contextual data, simulates outcomes, and turns those results into lineup, waiver, trade, draft, and season decisions.

The project is designed to run locally without paid infrastructure. It never presents unavailable or sample data as live information.

> Fourth Down is an independent fantasy analysis project. It is not affiliated with ESPN, the NFL, or any sportsbook. Projections are uncertain estimates, not guarantees or betting advice.

## Contents

- [What the application does](#what-the-application-does)
- [Technology](#technology)
- [Quick start on Windows](#quick-start-on-windows)
- [Environment configuration](#environment-configuration)
- [Connecting an ESPN league](#connecting-an-espn-league)
- [Data providers and cost](#data-providers-and-cost)
- [Application pages](#application-pages)
- [How recommendations work](#how-recommendations-work)
- [Manual development setup](#manual-development-setup)
- [Docker](#docker)
- [Testing](#testing)
- [API overview](#api-overview)
- [Security and privacy](#security-and-privacy)
- [GitHub Secrets](#github-secrets)
- [SSR and SEO](#ssr-and-seo)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Project structure](#project-structure)

## What the application does

Fourth Down includes:

- Public and private ESPN league connection
- ESPN roster, scoring, lineup-slot, playoff, and free-agent normalization
- Safe, balanced, and upside lineup optimization
- Monte Carlo matchup and season simulation
- Waiver add/drop analysis with FAAB guidance
- Full-roster trade evaluation and generated offers
- Draft recommendations using value over replacement, need, scarcity, and risk
- Searchable player research pages
- What-if roster simulations
- League power rankings
- Projected final standings
- Calibration and model-trust metrics
- CSV and PDF reports
- Provider freshness and availability statuses
- Template-based Ask Engine with no paid LLM
- Optional Discord weekly digest
- Installable PWA support
- Server-rendered public SEO pages
- Local SQLite persistence
- Docker configuration
- Clearly labeled demo mode

## Technology

### Frontend

- Next.js 15 App Router
- React 19
- TypeScript
- Server-side rendering for public SEO pages
- Static/private application routes where appropriate
- Responsive CSS and Lucide icons
- PWA manifest and service worker

### Backend

- Python 3.11+
- FastAPI
- Pydantic validation
- HTTPX provider clients
- SQLite persistence
- Deterministic Monte Carlo simulation

## Quick start on Windows

### 1. Create your private environment file

From the project folder:

```powershell
Copy-Item .env.example .env
```

Open `.env` and enter your private values. Do not add real values to `.env.example`.

### 2. Start Fourth Down

Double-click:

```text
Start Fourth Down.bat
```

Or run this from PowerShell:

```powershell
& ".\Start Fourth Down.bat"
```

The launcher:

1. Loads `.env`.
2. Finds an installed or bundled Python runtime.
3. Creates `.venv` when needed.
4. Installs backend dependencies on the first run.
5. Installs frontend dependencies when needed.
6. Creates a production frontend build when needed.
7. Starts the backend at `http://localhost:8000`.
8. Starts the website at `http://localhost:3000`.
9. Opens the website automatically.

Keep both PowerShell server windows open while using the application. Close those windows when finished.

### 3. Verify the application

- Website: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health`
- Interactive API documentation: `http://localhost:8000/docs`

## Environment configuration

`.env.example` is committed to GitHub because it contains variable names and safe defaults only. `.env` contains real local values and is ignored by Git.

```env
ESPN_S2=
ESPN_SWID=
ODDS_API_KEY=
OPENWEATHER_API_KEY=
DIGEST_WEBHOOK_URL=

DATABASE_URL=sqlite:///./fourth_down.db
ALLOW_DEMO_MODE=true

NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

MAX_REQUEST_BYTES=1048576
MULTI_USER_MODE=false
APP_TENANT_ID=local
```

### Variable reference

| Variable | Required | Secret | Purpose |
|---|---:|---:|---|
| `ESPN_S2` | Private leagues only | Yes | ESPN authentication cookie from the user's browser session |
| `ESPN_SWID` | Private leagues only | Yes | ESPN `SWID` authentication cookie |
| `ODDS_API_KEY` | Recommended | Yes | Free-tier game spreads, totals, and moneylines |
| `OPENWEATHER_API_KEY` | No | Yes | Optional weather fallback; Open-Meteo needs no key |
| `DIGEST_WEBHOOK_URL` | No | Yes | Optional Discord weekly digest webhook |
| `DATABASE_URL` | Yes | No | Local SQLite database location |
| `ALLOW_DEMO_MODE` | No | No | Enables clearly labeled sample data when no league is connected |
| `NEXT_PUBLIC_API_URL` | Yes | No | Browser-visible FastAPI address |
| `NEXT_PUBLIC_SITE_URL` | Deployment | No | Canonical public website URL for metadata and sitemap |
| `ALLOWED_ORIGINS` | Yes | No | Comma-separated browser origins permitted by the API |
| `MAX_REQUEST_BYTES` | No | No | Maximum API request size; default is 1 MB |
| `MULTI_USER_MODE` | Yes | No | Must remain `false` with SQLite |
| `APP_TENANT_ID` | No | No | Reserved local tenant identifier |

Never prefix backend secrets with `NEXT_PUBLIC_`. Next.js exposes variables with that prefix to browser code.

## Connecting an ESPN league

Open `/connect` or select **Connect ESPN** from the landing page.

Enter:

1. ESPN league ID
2. Season year
3. ESPN team ID, or leave it blank to select the first team

The league ID is the numeric ID in the ESPN fantasy league URL. It is not the league name.

### Public leagues

Public leagues require only the league ID and season. No ESPN API key is required.

### Private leagues

Private leagues require the `espn_s2` and `SWID` cookie values from the user's own logged-in ESPN browser session.

General browser steps:

1. Log into ESPN.
2. Open the ESPN fantasy league.
3. Open browser Developer Tools.
4. Open **Application** or **Storage**.
5. Open **Cookies** for `espn.com`.
6. Copy `espn_s2` into `ESPN_S2` in `.env`.
7. Copy `SWID` into `ESPN_SWID` in `.env`.
8. Restart Fourth Down.

Treat both cookies like passwords. Never paste them into the website, GitHub source files, screenshots, issue reports, or chat messages.

### Friendly connection errors

The connection flow distinguishes:

- `LEAGUE_NOT_FOUND`: no league exists for that ID and season
- `TEAM_NOT_FOUND`: the team ID is not part of the league
- `ESPN_AUTH_REQUIRED`: private league access was denied
- `ESPN_RATE_LIMITED`: ESPN temporarily limited requests
- `ESPN_TIMEOUT`: ESPN did not respond in time
- `ESPN_UNREACHABLE`: the backend could not reach ESPN
- `INVALID_INPUT`: an ID or year is incorrectly formatted
- `ENGINE_OFFLINE`: the FastAPI server is not running

Each error includes a plain-language explanation, suggested next action, stable error code, and retry guidance.

## Data providers and cost

The default configuration uses only free providers.

| Category | Provider | Cost | Key required | Refresh policy |
|---|---|---:|---:|---|
| ESPN league data | ESPN unofficial fantasy endpoints | Free | Private leagues only | On connection and manual refresh |
| Game odds | The Odds API | Free tier | Yes | Six-hour cache; forced refresh limited to once per 15 minutes |
| Weather | Open-Meteo | Free | No | Three-hour cache |
| NFL rosters/open data | nflverse releases | Free | No | Daily cache |
| Storage | SQLite | Free | No | Local |
| Digest | Discord webhook | Free | Webhook URL | Manual or scheduled externally |

### Player props

Reliable player-prop APIs are generally not available on a dependable free tier. Player props are optional and may be shown as unavailable. The engine continues to operate using game totals, spreads, moneylines, role, injury, weather, and league context.

### Provider statuses

Every provider reports one of:

- `LIVE`
- `CACHED`
- `STALE`
- `MOCK`
- `UNAVAILABLE`

Missing data lowers confidence or removes a specific adjustment. It is never silently replaced with fake live data.

## Application pages

| Route | Purpose |
|---|---|
| `/` | Server-rendered landing page |
| `/methodology` | Server-rendered explanation of the model |
| `/privacy` | Server-rendered privacy policy and local-data deletion |
| `/connect` | ESPN connection flow |
| `/dashboard` | Weekly overview and immediate actions |
| `/lineup` | Safe, balanced, and upside lineup paths |
| `/waivers` | Add/drop and FAAB recommendations |
| `/trades` | Trade builder and generated offers |
| `/draft` | Draft board and live pick state |
| `/players` | Player search |
| `/players/[playerId]` | Player projection and research details |
| `/what-if` | Free-form roster swap simulator |
| `/power-rankings` | Simulated league strength |
| `/standings-projection` | Projected final wins and confidence bands |
| `/reports` | CSV and PDF exports |
| `/trust` | Calibration metrics and reliability diagnostics |
| `/data-sources` | Provider status and recommendation impact |
| `/settings` | League and credential-configuration status |

## How recommendations work

### Projection baseline

Player projections begin with expected fantasy output and uncertainty. When available, game markets provide a bounded scoring prior.

### Bounded context

Weather, injury status, availability, and role information modify expected output or variance within strict limits. The engine does not award unexplained fantasy-point bonuses.

### Legal roster construction

Lineup optimization respects position eligibility, duplicate-player prevention, FLEX, and SUPERFLEX slots.

### Simulation

The engine samples player and team score distributions to estimate:

- Expected score
- Floor and ceiling
- Weekly win probability
- Playoff probability
- Championship probability
- Final-standings ranges

Simulation functions use deterministic seeds during tests so results are reproducible.

### Waivers

Waiver recommendations compare the roster before and after the actual add/drop move. They include weekly gain, rest-of-season gain, confidence, suggested FAAB, reasons, and risks.

### Trades

Trades compare the complete legal roster before and after the deal, including required drops for uneven trades. Acceptance likelihood is a value-balance estimate, not a prediction of another manager's behavior.

### Draft

Draft recommendations consider:

- Value over replacement
- Positional scarcity
- Current roster need
- Risk and variance
- Estimated chance the player reaches the next selection
- Persisted live-draft pick state

### Calibration

The Trust Center reports metrics such as point-projection mean absolute error and win-probability Brier score. Diagnostics are read-only and do not silently retrain or modify live projections.

## Manual development setup

### Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- npm or pnpm

### Backend

From the repository root:

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
uvicorn app.main:app --app-dir backend --reload
```

Backend URLs:

- API: `http://localhost:8000`
- Documentation: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/health`

### Frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Or with pnpm:

```powershell
cd frontend
pnpm install
pnpm run dev
```

Open `http://localhost:3000`.

### Production frontend build

```powershell
cd frontend
npm run build
npm run start
```

## Docker

Create `.env`, then run:

```powershell
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

Docker uses a local volume-mounted `data` directory for SQLite. That directory is ignored by Git.

Stop containers with:

```powershell
docker compose down
```

## Testing

Install development dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

Compile-check the backend:

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend\app
```

Build and type-check the frontend:

```powershell
cd frontend
npm run build
```

### Validated stress scenarios

The local test pass has covered:

- Hundreds of lineup optimizations
- Extreme projection-factor inputs
- 10,000 season simulations
- Concurrent SQLite writes
- Concurrent API traffic
- Expected HTTP 429 throttling
- Malformed-input fuzzing
- Secret-leak checks
- Oversized request rejection
- Hostile-origin rejection
- ESPN failure mapping
- Prompt-role isolation and delimiter breakout attempts
- AI endpoint throttling
- Raw SSR HTML and crawler headers
- Real Odds API, Open-Meteo, and nflverse connectivity

Provider calls should not be placed in ordinary unit tests because they consume quotas and make tests network-dependent.

## API overview

Important endpoints include:

```text
GET    /api/health
POST   /api/connect
GET    /api/overview
GET    /api/lineup
GET    /api/waivers
GET    /api/draft
POST   /api/draft/pick
DELETE /api/draft
GET    /api/trades
POST   /api/trades/evaluate
GET    /api/players
GET    /api/players/{player_id}
GET    /api/what-if/options
POST   /api/what-if
GET    /api/power-rankings
GET    /api/standings-projection
GET    /api/trust
GET    /api/data-sources
GET    /api/reports/weekly.csv
GET    /api/reports/weekly.pdf
POST   /api/ask
POST   /api/digest/send
POST   /api/providers/odds/refresh
GET    /api/providers/weather/{team}
POST   /api/providers/nflverse/refresh
GET    /api/privacy
DELETE /api/privacy/data
GET    /api/settings
```

Expected errors use a structured response:

```json
{
  "detail": {
    "code": "LEAGUE_NOT_FOUND",
    "message": "No ESPN league was found with that ID for this season.",
    "hint": "Check for a mistyped league ID and confirm the season year, then try again.",
    "retryable": false
  }
}
```

## Security and privacy

### Secrets

- `.env` is ignored by Git.
- `.env.example` contains no real values.
- ESPN cookies and provider keys remain backend-only.
- Secret values are not returned by settings or error endpoints.
- Backend stack traces are not exposed to the browser.

### Input validation

- League, team, and player IDs use strict patterns and length limits.
- Questions are normalized and length-limited.
- API requests are limited to 1 MB by default.
- Invalid requests return friendly structured errors.

### Request security

- Restrictive CORS origins
- Origin validation for state-changing browser requests
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- Restrictive Content Security Policy
- No-referrer policy
- Restricted browser permissions
- `no-store` API responses
- Discord webhook hostname and path allowlisting

### Rate limits

The in-memory sliding-window limiter uses separate buckets:

- Ask/AI-like endpoint: 10 requests per minute per client
- Sensitive provider, connection, digest, and privacy endpoints: 12 requests per minute per client
- General API endpoints: 120 requests per minute per client

Rate-limited responses use HTTP 429 and include `Retry-After`.

The Odds API has an additional minimum 15-minute forced-refresh interval and a six-hour normal cache.

### Ask Engine and prompt injection

The shipped Ask Engine performs local template matching. It does not call an LLM.

The future LLM boundary:

- Constructs system, developer, and user roles separately
- Never concatenates user text into a privileged role
- Escapes HTML and delimiter characters
- Wraps input in `UNTRUSTED_USER_INPUT` delimiters
- Limits user input to 300 characters
- Treats engine output as separate trusted context
- Prohibits secret or hidden-prompt disclosure

### SQLite and RLS

SQLite does not support row-level security. This build is intentionally local and single-user.

Setting:

```env
MULTI_USER_MODE=true
```

while using SQLite makes startup fail. The project refuses to claim that application filtering is RLS.

A hosted multi-user edition requires:

- Authentication
- PostgreSQL
- An owner/user ID on every user-owned row
- `ENABLE ROW LEVEL SECURITY`
- `FORCE ROW LEVEL SECURITY`
- Read, insert, update, and delete policies
- Cross-tenant denial tests

### Local-data deletion

The `/privacy` page provides a deletion control requiring the exact confirmation:

```text
DELETE MY DATA
```

It deletes saved league state, provider caches, prediction history, and draft state. It does not edit `.env`.

## GitHub Secrets

Do not upload `.env` to GitHub.

For GitHub Actions or deployment, add values under:

**Repository → Settings → Secrets and variables → Actions**

Recommended GitHub Secrets:

- `ESPN_S2`
- `ESPN_SWID`
- `ODDS_API_KEY`
- `OPENWEATHER_API_KEY`
- `DIGEST_WEBHOOK_URL`

Recommended non-sensitive GitHub Variables:

- `NEXT_PUBLIC_SITE_URL`
- `ALLOWED_ORIGINS`
- `MAX_REQUEST_BYTES`
- `MULTI_USER_MODE`
- `APP_TENANT_ID`

GitHub Secrets do not automatically appear in a deployed application. A deployment workflow must explicitly configure the hosting platform's runtime environment. Never echo secrets in workflow logs or bake them into a frontend bundle or Docker image.

## SSR and SEO

Public pages are dynamically server-rendered:

- `/`
- `/methodology`
- `/privacy`

They include:

- Crawlable HTML without requiring client JavaScript
- Unique titles and descriptions
- Canonical URLs
- Open Graph metadata
- `SoftwareApplication` structured data
- Server-generated `robots.txt`
- Server-generated `sitemap.xml`

Personalized application routes return:

```text
X-Robots-Tag: noindex, nofollow, noarchive
```

This prevents search engines from indexing league dashboards and private fantasy data.

Before public deployment, set:

```env
NEXT_PUBLIC_SITE_URL=https://your-real-domain.example
ALLOWED_ORIGINS=https://your-real-domain.example
```

Google cannot index a localhost installation.

## Deploy the website to Netlify

The repository is already configured by `netlify.toml`. Netlify must build the
Git repository; do not drag-and-drop `.next` or upload it as a static folder.
The root and frontend `.nvmrc` files pin Node.js 20. The committed pnpm lockfile
selects pnpm without requiring Corepack to verify a `packageManager` signature.

1. In Netlify, connect this GitHub repository using **Add new project** >
   **Import an existing project**.
2. Keep the repository root as the repository being connected. The committed
   configuration sets the build base to `frontend`, runs `pnpm build`, and uses
   `.next` as the Next.js output.
3. Under **Project configuration** > **Environment variables**, add:

   ```env
   NEXT_PUBLIC_API_URL=https://your-backend-domain.example
   NEXT_PUBLIC_SITE_URL=https://your-netlify-domain.netlify.app
   ```

   `NEXT_PUBLIC_API_URL` is the public URL of the separately deployed FastAPI
   backend. It is not the Netlify URL. Do not add ESPN cookies or AI API keys to
   variables beginning with `NEXT_PUBLIC_`; secrets belong only on the backend.
4. Push these files to GitHub. Then open **Deploys** > **Trigger deploy** and
   choose **Clear cache and deploy site**.

A successful deploy log should identify **Next.js** and create Netlify server
or edge functions. If the deploy still says **Framework: unknown**, open
**Project configuration** > **Build & deploy** > **Continuous deployment** >
**Build settings**, remove stale UI overrides, and redeploy. The committed
`netlify.toml` is authoritative and sets the base directory to `frontend`.

After deployment, verify `/`, `/methodology`, `/robots.txt`, and `/sitemap.xml`.
The first two pages must return rendered HTML, not Netlify's generic 404.

## Troubleshooting

### `Fourth Down is not running`

Keep both PowerShell server windows open. If either closed, run:

```powershell
& ".\Start Fourth Down.bat"
```

### PowerShell blocks scripts

The batch launcher already uses an execution-policy bypass for its process. For manual startup:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Python is not found

Install Python 3.11+ and select **Add Python to PATH**, or run Fourth Down through Codex where the launcher can use the bundled Python runtime.

### Node.js is not found

Install the current Node.js 20+ LTS release, then rerun the launcher.

### League not found

- Confirm the numeric league ID.
- Confirm the season year.
- Open the same league in ESPN to verify it still exists.
- For a private league, confirm the ESPN cookies are current.

### ESPN authentication required

Refresh `ESPN_S2` and `ESPN_SWID` from a current logged-in ESPN session, update `.env`, and restart the application.

### League connects but players are missing

ESPN may not have populated the season's rosters yet, or private cookies may be stale. Check the connection warning, verify the league in ESPN, refresh cookies, and reconnect.

### Odds are unavailable

- Confirm `ODDS_API_KEY` is present in `.env`.
- Restart the backend after changing `.env`.
- Check the Data Sources page.
- Respect the free monthly request quota.

### Frontend build reports OneDrive `readlink EINVAL`

OneDrive can occasionally corrupt generated `.next` cache links. Close the frontend server, delete only `frontend/.next`, and rebuild:

```powershell
Remove-Item -LiteralPath ".\frontend\.next" -Recurse -Force
& ".\Start Fourth Down.bat"
```

`.next` contains generated build artifacts and is ignored by Git.

### Port 3000 or 8000 is already in use

Close old Fourth Down server windows before starting a new copy. Do not run multiple launchers simultaneously.

### GitHub does not contain `.env`

That is intentional. GitHub should contain `.env.example`, while every user creates a private local `.env` or configures GitHub/hosting secrets.

## Known limitations

- ESPN's fantasy endpoints are unofficial and may change without notice.
- A specific real league can expose ESPN response variations that demo fixtures do not cover.
- Player props are not reliably free and remain optional.
- The Odds API free tier has a monthly quota.
- nflverse freshness depends on upstream releases.
- SQLite is appropriate for a local single-user installation, not a hosted multi-user service.
- The current rate limiter is in-memory. A multi-instance deployment requires a shared limiter such as Redis or a platform gateway.
- The current Ask Engine is template-based, not a general-purpose AI assistant.
- Calibration begins with a small sample and becomes meaningful only after real predictions and outcomes accumulate.
- Discord scheduling requires an external scheduler, such as GitHub Actions, or a manually triggered request.
- Public deployment is not included automatically; hosting configuration depends on the selected provider.

## Project structure

```text
fantasy_football/
├── backend/
│   ├── app/
│   │   ├── advanced.py       # Draft, trade, rankings, what-if, calibration
│   │   ├── demo.py           # Clearly labeled sample league
│   │   ├── domain.py         # Typed normalized models
│   │   ├── engine.py         # Projections, lineup optimization, waivers
│   │   ├── errors.py         # Structured user-friendly errors
│   │   ├── live_providers.py # Odds, weather, nflverse adapters
│   │   ├── main.py           # FastAPI routes
│   │   ├── persistence.py    # SQLite state, cache, and predictions
│   │   ├── prompting.py      # Future LLM role and delimiter boundary
│   │   ├── providers.py      # ESPN normalization and source statuses
│   │   └── security.py       # Request limits, origins, rate limiting, headers
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── app/                  # Next.js routes, metadata, sitemap, robots
│   ├── components/           # Shared interface components
│   ├── lib/api.ts            # Typed API client and friendly errors
│   ├── public/sw.js          # Privacy-aware service worker
│   ├── Dockerfile
│   └── package.json
├── docs/AUDIT.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Start Fourth Down.bat
├── start.ps1
└── README.md
```

## Development principles

Fourth Down prioritizes:

- Honest uncertainty
- Free and reproducible infrastructure
- Secret-safe integrations
- League-specific decisions
- Typed boundaries
- Explainable recommendations
- Deterministic tests
- Graceful degradation
- Accessible responsive design

It deliberately avoids:

- Fake live data
- Guaranteed-win claims
- Paid dependencies in the default workflow
- Arbitrary fantasy-point boosts
- Browser exposure of backend secrets
- Indexing personalized league pages
- Pretending SQLite provides RLS
