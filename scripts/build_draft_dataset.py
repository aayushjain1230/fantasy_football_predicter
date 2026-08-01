from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.draft_intelligence import build_draft_dataset, dataset_fingerprint, load_csv, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fixture draft intelligence dataset.")
    parser.add_argument("--adp", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "draft_adp.csv")
    parser.add_argument("--outcomes", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "draft_outcomes.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "draft_dataset.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "processed" / "draft_data_quality_report.json")
    args = parser.parse_args()
    rows = build_draft_dataset(load_csv(args.adp), load_csv(args.outcomes))
    fields = list(rows[0].keys())
    write_csv(args.output, rows, fields)
    report = {"rows": len(rows), "positions": sorted({row["position"] for row in rows}), "dataset_fingerprint": dataset_fingerprint(rows), "adp_source": str(args.adp), "outcome_source": str(args.outcomes), "unresolved_players": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
