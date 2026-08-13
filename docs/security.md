# Security and Privacy Review

Threats considered:

- Secret exposure through Streamlit, logs, exports, or exceptions.
- Private league data leakage through shared caches.
- Unsafe model artifact loading.
- Path traversal and unvalidated file access.
- CSV formula injection.
- Unbounded request sizes and denial-of-service risks.
- Unsafe webhook URLs.
- Stack traces and raw provider responses reaching users.

Controls implemented:

- Streamlit session state holds connected league state; shared caches are avoided for private league objects.
- Shared ESPN cookies are not read from Streamlit secrets.
- Private-league session values are hidden in a collapsed advanced fallback,
  password-masked, passed only as ESPN cookies, and never put in URLs, logs,
  SQLite, exports, shared provider caches, or the normalized league/state models.
- They remain in Streamlit session memory only to support explicit synchronization.
  Disconnect ESPN invalidates the session cache and removes the values.
- League URLs reject token-, cookie-, SWID-, and authorization-like query keys.
- The centralized `ActiveLeagueState` contains metadata only and cannot contain
  authentication material.
- The browser extension is visibly disabled. It has no cookie read or transfer
  implementation because no audited HTTPS handshake service is deployed.
- Projection artifacts are repository-owned JSON files with schema and metadata validation.
- CSV exports sanitize formula-like values.
- FastAPI middleware limits request size, applies CORS checks, and rate-limits sensitive endpoints.
- Discord webhook validation restricts host and scheme.
- Settings exposes safe health summaries, not raw logs or secrets.

Remaining limitations:

- Streamlit session state is not authentication or permanent tenant isolation.
- Users must enter ESPN credentials only into a deployment they trust; the
  deployment operator controls the server process that makes the ESPN request.
- SQLite is local/ephemeral and not cloud multi-user storage.
- ESPN fantasy endpoints are unofficial and can change.
- Streamlit Community Cloud is not the dedicated REST service required for a
  one-click extension handshake. Such a service must use random five-minute
  single-use codes, CSRF state, rate limiting, encrypted persistence if any,
  revocation, redacted logs, and strict origin/extension allowlists.
- No third-party analytics are enabled by default.
