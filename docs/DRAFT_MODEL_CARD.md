# Fourth Down Draft Intelligence Model Card

These metrics are generated from deterministic fixture ADP/outcome data. They validate the architecture and must not be presented as production accuracy.

| Metric | Value |
|---|---:|
| sample_size | 4 |
| residual_mae | 0.0 |
| adp_baseline_mae | 29.375 |
| baseline_improvement_pct | 100.0 |
| multiclass_brier | 0.299 |
| macro_accuracy_fixture | 1 |

Target: ADP-relative residual in value over replacement.
Outcome classes: UNDERPERFORM below the training lower residual threshold, OUTPERFORM above the training upper residual threshold, otherwise MEET EXPECTATIONS.
Next-pick availability: ADP dispersion approximation because fixture ADP has no full pick distribution.
Production ADP refresh is disabled until legally usable ADP sources are configured and validated.
