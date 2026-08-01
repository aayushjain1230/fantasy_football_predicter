from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.projection_service import build_training_rows, load_csv, train_position_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Train position-specific projection artifacts.")
    parser.add_argument("--source", type=Path, default=ROOT / "backend" / "tests" / "fixtures" / "historical_player_weeks.csv")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "models" / "projections" / "latest")
    args = parser.parse_args()
    rows = build_training_rows(load_csv(args.source))
    result = train_position_artifacts(rows, args.artifact_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
