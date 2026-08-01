from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.projection_service import FEATURE_NAMES, build_training_rows, dataset_fingerprint, load_csv, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build leakage-safe player-week modeling dataset.")
    parser.add_argument("--source", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "historical_player_weeks.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "training_dataset.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "processed" / "data_quality_report.json")
    args = parser.parse_args()

    rows = build_training_rows(load_csv(args.source))
    fields = ["season", "week", "player_id", "player_name", "normalized_name", "position", "team", "opponent", *FEATURE_NAMES, "target", "low_history"]
    write_csv(args.output, rows, fields)
    report = {
        "source": str(args.source),
        "output": str(args.output),
        "rows": len(rows),
        "positions": sorted({row["position"] for row in rows}),
        "dataset_fingerprint": dataset_fingerprint(rows),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "leakage_policy": "features are shifted and never include the current player-week target",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
