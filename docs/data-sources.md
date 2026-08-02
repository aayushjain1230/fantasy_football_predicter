# Provider Freshness and Degradation

| Failure | Expected behavior |
|---|---|
| ESPN unavailable | Preserve current session when present; otherwise offer demo mode. |
| Public league not found | Show league-ID/season error. |
| Private league detected | Explain private leagues are local-only. |
| Projection artifact missing | Use labeled fallback projection engine. |
| Current ADP unavailable | Hide market movement and label ADP unavailable. |
| Odds API unavailable | Use neutral market context. |
| Weather unavailable | Omit weather adjustment. |
| Schedule incomplete | Avoid exact playoff-status claims. |
| Free-agent pool unavailable | Disable waiver recommendations. |
| Simulation failure | Preserve point projections and show probabilities unavailable. |
| Historical dataset unavailable | Keep inference working from committed artifacts. |

Provider state labels are `LIVE`, `CACHED`, `STALE`, `DEMO`, or `UNAVAILABLE`. A configured key does not prove live data.
