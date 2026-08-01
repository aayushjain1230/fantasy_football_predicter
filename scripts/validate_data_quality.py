from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "backend" / "tests" / "fixtures"
REPORT = ROOT / "data" / "quality" / "latest_report.json"


def validate_csv(path: Path, required: set[str], key_columns: tuple[str, ...]) -> dict:
    result = {"file": str(path.relative_to(ROOT)), "valid": False, "rows": 0, "errors": []}
    if not path.exists():
        result["errors"].append("missing file")
        return result
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result["rows"] = len(rows)
    if not rows:
        result["errors"].append("empty file")
        return result
    missing = required - set(rows[0])
    if missing:
        result["errors"].append(f"missing columns: {sorted(missing)}")
    seen = set()
    for index, row in enumerate(rows, 1):
        key = tuple(row.get(col, "") for col in key_columns)
        if key in seen:
            result["errors"].append(f"duplicate key near row {index}: {key}")
            break
        seen.add(key)
    result["valid"] = not result["errors"]
    return result


def main() -> None:
    checks = [
        validate_csv(FIXTURES / "historical_player_weeks.csv", {"season", "week", "player_id", "player_name", "position", "team", "opponent"}, ("season", "week", "player_id")),
        validate_csv(FIXTURES / "draft_adp.csv", {"season", "snapshot_date", "player_id", "player_name", "position", "platform", "adp"}, ("season", "snapshot_date", "platform", "player_id")),
        validate_csv(FIXTURES / "draft_outcomes.csv", {"season", "player_id", "actual_value"}, ("season", "player_id")),
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": datetime.now(UTC).isoformat(), "checks": checks, "valid": all(check["valid"] for check in checks)}
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if not payload["valid"]:
        raise SystemExit(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
