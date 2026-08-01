from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.draft_intelligence import build_draft_dataset, load_csv, train_draft_artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Train fixture draft intelligence artifacts.")
    parser.add_argument("--adp", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "draft_adp.csv")
    parser.add_argument("--outcomes", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "draft_outcomes.csv")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "models" / "draft" / "latest")
    args = parser.parse_args()
    rows = build_draft_dataset(load_csv(args.adp), load_csv(args.outcomes))
    artifact = train_draft_artifact(rows, args.artifact_dir)
    print(json.dumps({"model_version": artifact["metadata"]["model_version"], "evaluation": artifact["evaluation"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
