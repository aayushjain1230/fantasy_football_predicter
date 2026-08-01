# Architecture

Fourth Down keeps backend systems as puzzle pieces behind five product destinations.

```text
Providers
  -> normalized league and player data
  -> projection, rest-of-season, and value services
  -> lineup, waiver, trade, draft, and simulation engines
  -> unified decision service
  -> Streamlit: Home, My Team, Players, League, Settings
```

Streamlit calls Python services directly. It does not start FastAPI, Next.js, or localhost APIs.

Primary backend modules:

- `providers.py`: ESPN normalization and provider states.
- `projection_service.py`: trusted JSON artifact loading and fallback projections.
- `ros_service.py`: week-specific rest-of-season aggregation.
- `engine.py`: lineup optimization and waiver evaluation.
- `advanced.py`: trade, player research, calibration, and reports.
- `simulation.py`: schedule-aware league simulation.
- `decision_service.py`: user-facing weekly brief and recommendation objects.
- `operations.py`: launch-readiness health summaries and degradation matrix.
