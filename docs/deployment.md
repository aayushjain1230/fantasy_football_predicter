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

Do not configure `ESPN_S2` or `ESPN_SWID` in a shared public deployment. Private ESPN leagues are local-only until a reviewed authentication and tenant-isolation design exists.

Startup behavior:

- Demo mode works without optional keys.
- Model artifacts are validated before use.
- Missing optional providers degrade affected adjustments only.
- Streamlit does not train models or download datasets during interactive use.

Health checks:

```bash
streamlit run streamlit_app.py --server.headless true
```
