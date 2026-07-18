# Architecture and compatibility audit

The repository was empty at the start of this build, so there were no imports, interfaces, models, or tests to preserve or repair. The supplied specification was treated as the source contract.

Key architecture decisions:

- One normalized domain model isolates all decision code from ESPN response shapes.
- Projections store mean and uncertainty; context changes are bounded and traceable instead of unexplained point bonuses.
- Lineup and waiver decisions share one simulation/projection path.
- Providers publish explicit freshness states (`LIVE`, `CACHED`, `STALE`, `MOCK`, `UNAVAILABLE`).
- Secrets are read only by the backend and omitted from serialized models and errors.
- Missing odds, weather, or props degrades confidence/status rather than producing fabricated live metrics.

Phase 2 engines now reuse the same projection and legal-lineup path as Phase 1. Draft recommendations use value over replacement, scarcity, need, and uncertainty; trades compare whole rosters; power and standings share deterministic season simulations; trust metrics remain read-only. Phase 3 deployment and scheduled notification operations remain optional.
