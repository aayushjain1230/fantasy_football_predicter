from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.draft_intelligence import build_draft_dataset, evaluate_draft_artifact, load_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate fixture draft intelligence artifact.")
    parser.add_argument("--adp", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "draft_adp.csv")
    parser.add_argument("--outcomes", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "draft_outcomes.csv")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "models" / "draft" / "latest")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs" / "DRAFT_MODEL_CARD.md")
    args = parser.parse_args()
    artifact = json.loads((args.artifact_dir / "draft_model.json").read_text(encoding="utf-8"))
    rows = build_draft_dataset(load_csv(args.adp), load_csv(args.outcomes))
    test_rows = [row for row in rows if int(row["season"]) >= 2024]
    report = evaluate_draft_artifact(artifact, test_rows)
    (args.artifact_dir / "evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Fourth Down Draft Intelligence Model Card",
        "",
        "These metrics are generated from deterministic fixture ADP/outcome data. They validate the architecture and must not be presented as production accuracy.",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in report.items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "Target: ADP-relative residual in value over replacement.",
        "Outcome classes: UNDERPERFORM below the training lower residual threshold, OUTPERFORM above the training upper residual threshold, otherwise MEET EXPECTATIONS.",
        "Next-pick availability: ADP dispersion approximation because fixture ADP has no full pick distribution.",
        "Production ADP refresh is disabled until legally usable ADP sources are configured and validated.",
    ]
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
