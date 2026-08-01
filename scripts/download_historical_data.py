from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Document historical data retrieval for production training.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--fixture-only", action="store_true", help="Do not download network data; report fixture mode.")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "fixture_only" if args.fixture_only else "not_downloaded",
        "recommended_source": "nflverse weekly/player stats datasets, subject to their license and availability",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "note": "Production download is intentionally not run in CI. Use fixture data for deterministic tests.",
    }
    (args.output_dir / "download_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
