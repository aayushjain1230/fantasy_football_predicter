from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Record current ADP refresh status.")
    parser.add_argument("--output", type=Path, default=Path("data/raw/current_adp_refresh_report.json"))
    parser.add_argument("--fixture-only", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "fixture_only" if args.fixture_only else "not_configured",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "note": "No production ADP provider is configured. Do not label fixture ADP as live or consensus market data.",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
