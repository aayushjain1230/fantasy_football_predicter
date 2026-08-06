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

Do not configure one user's `ESPN_S2` or `ESPN_SWID` as shared deployment
secrets. Private-league users enter both values in password fields when
connecting. The values are used for that ESPN request and are not persisted by
Fourth Down. Users should only enter them on a deployment they trust.

Startup behavior:

- Demo mode works without optional keys.
- Model artifacts are validated before use.
- Missing optional providers degrade affected adjustments only.
- Streamlit does not train models or download datasets during interactive use.

Health checks:

```bash
streamlit run streamlit_app.py --server.headless true
```
