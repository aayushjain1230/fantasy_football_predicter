from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.evaluation import record_outcome  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach controlled outcomes to existing Fourth Down prediction-ledger rows.")
    parser.add_argument("csv_path", type=Path, help="CSV with prediction_id, actual_points, actual_outcome, final_player_status, evaluation_status")
    args = parser.parse_args()
    with args.csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"prediction_id", "actual_points", "evaluation_status"}
    if not rows or required - set(rows[0]):
        raise SystemExit(f"Outcome CSV must include {sorted(required)}")
    for row in rows:
        actual_points = float(row["actual_points"]) if row.get("actual_points") else None
        actual_outcome = int(row["actual_outcome"]) if row.get("actual_outcome") not in {None, ""} else None
        record_outcome(row["prediction_id"], actual_points, actual_outcome, row.get("final_player_status", "UNKNOWN"), row.get("evaluation_status", "ELIGIBLE"))
    print(f"attached {len(rows)} outcomes")


if __name__ == "__main__":
    main()
