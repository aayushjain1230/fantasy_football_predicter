# Fourth Down Draft Experience

## Product flow

Draft has three steps: **Draft Setup**, **My Draft Plan**, and **Live Draft**. Setup must be confirmed before recommendations appear. After confirmation, only My Draft Plan and Live Draft are primary tabs.

## Correctness fixes

The previous manager count was copied from a helper that preferred `settings.size`, then silently used the returned team count, then silently used 12. A slider immediately wrote that value back over ESPN settings. The new resolver records the source, exposes disagreements, and requires confirmation.

The previous draft seat began as the hardcoded session value `6`. It had no source or confirmation state, and ESPN draft-order assignments were not normalized. Team ID, team-list order, standings, roster order, and schedule order are never draft-seat evidence. The new resolver accepts only ESPN `draftOrder`, first-round live draft evidence, or explicit user confirmation.

## Recommendation method

The internal board combines available league scoring and roster structure with ESPN projections, ADP, draft rank, injury state, pool order, roster fit, meaningful value-cliff tiers, market cost, risk of waiting, and deterministic mock-draft completed-roster evidence. ESPN market rank is an input, not the answer. Missing ADP alone does not remove a player.

Availability is deliberately labeled **Unlikely to return**, **Could return**, or **Likely available later**. It is not presented as a calibrated percentage. Round plans show realistic target groups and backups rather than promising that one exact player will survive.

## ESPN synchronization

Live Draft starts only after ESPN returns at least one completed pick or the user explicitly starts manual mode. ESPN refresh is manual and rate-limited. A refresh replaces draft state only when completed ESPN picks are returned; an empty or failed refresh preserves current manual state. Fourth Down does not claim push or second-by-second synchronization.

## Security

Fourth Down never requests an ESPN email or password. Private leagues may use session-only `espn_s2` and `SWID` cookies inside the advanced instructions. They are not placed in URLs, logs, exports, databases, environment variables, or shared caches and are wiped on disconnect/reset. The browser-extension handoff is labeled future-only until implemented and tested.

## Current limitations

ESPN fantasy endpoints are unofficial and may change. Raw-stat league-specific projections are not available for every player, so unusual scoring formats can fall back to generic ESPN projections with reduced confidence. The deterministic mock layer is decision support, not a validated forecast of individual opponent behavior. No paid or protected rankings are scraped.
