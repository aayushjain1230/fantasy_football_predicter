# Evaluation

Fourth Down separates fixture validation from real live performance.

Real evaluation requires:

1. A prediction recorded before the outcome is known.
2. A later outcome attached to the original prediction ID.
3. A supported scoring configuration.
4. Enough eligible samples before reporting metrics.

The prediction ledger stores:

- Prediction ID and timestamp
- Season and week
- Player identifiers
- Scoring fingerprint
- Expected points and interval
- Model version and feature cutoff
- Provider freshness
- Fallback status

Outcomes are stored separately and joined by prediction ID. Retroactively generated predictions must not be counted as live forecasts.

Use:

```bash
python scripts/ingest_prediction_outcomes.py outcomes.csv
```

Settings shows real evaluation only when sample size is sufficient. Demo or fixture metrics are interface and pipeline checks, not evidence of production accuracy.
