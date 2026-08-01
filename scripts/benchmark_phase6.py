from __future__ import annotations

import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.advanced import evaluate_trade  # noqa: E402
from app.decision_service import build_weekly_brief  # noqa: E402
from app.demo import demo_league  # noqa: E402
from app.engine import optimize_lineup, waiver_moves  # noqa: E402
from app.projection_service import DEFAULT_PROJECTION_SERVICE  # noqa: E402
from app.simulation import simulate_league  # noqa: E402


REPORT = ROOT / "reports" / "phase6_benchmark.json"


def timed(name: str, fn):
    start = time.perf_counter()
    value = fn()
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {"operation": name, "elapsed_ms": elapsed_ms, "ok": value is not None}


def main() -> None:
    league = demo_league()
    team = league.teams[0]
    opponent = league.teams[1]
    rows = [
        timed("weekly brief", lambda: build_weekly_brief(league)),
        timed("player projection", lambda: DEFAULT_PROJECTION_SERVICE.project_player(team.players[0], league=league, week=league.week)),
        timed("lineup optimization", lambda: optimize_lineup(team.players, league.roster_slots, league=league)),
        timed("waiver analysis", lambda: waiver_moves(league)),
        timed("trade evaluation", lambda: evaluate_trade(league, [team.players[0].id], [opponent.players[0].id], opponent.id)),
        timed("quick simulation", lambda: simulate_league(league, simulations=100, seed=6)),
        timed("standard simulation", lambda: simulate_league(league, simulations=1000, seed=6)),
        timed("player search filter", lambda: [p for t in league.teams for p in t.players if "a" in p.name.lower()][:50]),
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"report": "Phase 6 deterministic demo benchmark", "rows": rows}
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
