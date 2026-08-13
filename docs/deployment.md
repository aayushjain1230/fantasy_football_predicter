# Deployment

Streamlit Community Cloud settings:

- Main file path: `streamlit_app.py`
- Python version: 3.11 or newer
- Dependency file: `requirements.txt`

Optional secrets:

```toml
ODDS_API_KEY = ""
OPENWEATHER_API_KEY = ""
DIGEST_WEBHOOK_URL = ""
```

Do not configure one user's ESPN session values as shared deployment secrets.
Private-league users can use the collapsed session-only fallback on a deployment
they trust. Values stay in the Streamlit session to support **Sync now**, are
never persisted in repository storage or URLs, and are removed by **Disconnect
ESPN** or session reset.

## Browser extension deployment boundary

`browser_extension/` is deliberately non-operational. Streamlit Community Cloud
does not provide the dedicated authenticated HTTPS endpoint required to exchange
ESPN session material safely. Before enabling it, deploy and audit a separate
service that supports random single-use codes, expiry of five minutes or less,
CSRF state validation, strict origin/extension allowlists, rate limiting,
redacted logs, revocation, and encryption at rest if any session material is
persisted. Until then the popup states that connection is unavailable.

Startup behavior:

- Demo mode works without optional keys.
- Model artifacts are validated before use.
- Missing optional providers degrade affected adjustments only.
- Streamlit does not train models or download datasets during interactive use.

Health checks:

```bash
streamlit run streamlit_app.py --server.headless true
```
