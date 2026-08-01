from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.projection_service import build_training_rows, evaluate_rows, load_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved projection artifacts.")
    parser.add_argument("--source", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "historical_player_weeks.csv")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "models" / "projections" / "latest")
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "projections" / "latest" / "evaluation.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs" / "MODEL_CARD.md")
    args = parser.parse_args()
    rows = build_training_rows(load_csv(args.source))
    report = {}
    for path in sorted(args.artifact_dir.glob("*.json")):
        if path.name in {"manifest.json", "evaluation.json"}:
            continue
        artifact = json.loads(path.read_text(encoding="utf-8"))
        position = artifact["metadata"]["position"]
        test_rows = [row for row in rows if row["position"] == position and int(row["season"]) == 2024 and int(row["week"]) >= 3]
        report[position] = evaluate_rows(artifact, test_rows)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# Fourth Down Projection Model Card", "", "These metrics are generated from the committed deterministic fixture dataset. They validate the architecture and test harness; they are not production accuracy claims.", ""]
    lines += ["| Position | Sample | MAE | RMSE | Bias | Baseline MAE | Improvement % | 80% Coverage |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for position, metrics in sorted(report.items()):
        lines.append(f"| {position} | {metrics.get('sample_size', 0)} | {metrics.get('mae', 0)} | {metrics.get('rmse', 0)} | {metrics.get('mean_bias', 0)} | {metrics.get('baseline_mae', 0)} | {metrics.get('baseline_improvement_pct', 0)} | {metrics.get('interval_coverage_80', 0)} |")
    lines += ["", "Target: one player in one NFL week, canonical PPR fantasy points.", "Prediction timestamp: before kickoff; feature engineering shifts player and position history so the current game is excluded.", "Supported positions: QB, RB, WR, TE. K and DST use the Phase 1 fallback.", "Artifacts are JSON files under `models/projections/latest/` and are safe to inspect without loading executable serialized objects."]
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
