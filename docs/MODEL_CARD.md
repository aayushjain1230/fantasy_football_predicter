# Fourth Down Projection Model Card

These metrics are generated from the committed deterministic fixture dataset. They validate the architecture and test harness; they are not production accuracy claims.

| Position | Sample | MAE | RMSE | Bias | Baseline MAE | Improvement % | 80% Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| QB | 2 | 2.392 | 2.396 | -2.392 | 3.0 | 20.26 | 0.5 |
| RB | 2 | 2.349 | 2.771 | 1.47 | 3.65 | 35.65 | 0.5 |
| TE | 2 | 0.295 | 0.313 | 0.295 | 10.433 | 97.17 | 0.5 |
| WR | 2 | 0.892 | 1.016 | 0.486 | 12.917 | 93.1 | 0.5 |

Target: one player in one NFL week, canonical PPR fantasy points.
Prediction timestamp: before kickoff; feature engineering shifts player and position history so the current game is excluded.
Supported positions: QB, RB, WR, TE. K and DST use the Phase 1 fallback.
Artifacts are JSON files under `models/projections/latest/` and are safe to inspect without loading executable serialized objects.
