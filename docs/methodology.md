# Methodology

Fourth Down starts from available player baselines and adds only bounded, explainable adjustments when data is actually present.

Core methods:

- Lineups use exact legal assignment with unique-player constraints.
- Projections use trusted JSON artifacts for QB/RB/WR/TE when valid, otherwise labeled fallback.
- Rest-of-season value sums week-specific projection-service outputs and replacement value.
- Waivers compare the full legal roster before and after an add/drop.
- Trades compare complete rosters, required drops, and value balance.
- League outlook simulates actual normalized remaining matchups when schedule data is available.
- The decision service ranks actions by urgency, expected impact, confidence, robustness, and deadline.

Unsupported or ambiguous ESPN rules are displayed as limitations rather than treated as exact.
