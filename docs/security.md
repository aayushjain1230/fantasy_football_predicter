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
- ESPN cookies are local-only and not read from Streamlit secrets.
- Projection artifacts are repository-owned JSON files with schema and metadata validation.
- CSV exports sanitize formula-like values.
- FastAPI middleware limits request size, applies CORS checks, and rate-limits sensitive endpoints.
- Discord webhook validation restricts host and scheme.
- Settings exposes safe health summaries, not raw logs or secrets.

Remaining limitations:

- Streamlit session state is not authentication or permanent tenant isolation.
- SQLite is local/ephemeral and not cloud multi-user storage.
- ESPN fantasy endpoints are unofficial and can change.
- No third-party analytics are enabled by default.
