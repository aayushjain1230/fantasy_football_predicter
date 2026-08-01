from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import CONFIG
from .projection_service import FEATURE_NAMES, MODEL_VERSION, SUPPORTED_MODEL_POSITIONS


MAX_ARTIFACT_BYTES = 512_000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_projection_artifact(path: Path) -> dict[str, Any]:
    result = {"path": path.name, "valid": False, "hash": None, "size_bytes": 0, "errors": []}
    if not path.exists():
        result["errors"].append("missing artifact")
        return result
    size = path.stat().st_size
    result["size_bytes"] = size
    if size > MAX_ARTIFACT_BYTES:
        result["errors"].append("artifact exceeds safe size limit")
        return result
    try:
        result["hash"] = sha256(path)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        metadata = artifact.get("metadata", {})
        if metadata.get("model_version") != MODEL_VERSION:
            result["errors"].append("incompatible model version")
        if metadata.get("position") not in SUPPORTED_MODEL_POSITIONS:
            result["errors"].append("unsupported position")
        if artifact.get("features") != FEATURE_NAMES:
            result["errors"].append("feature order mismatch")
        if artifact.get("algorithm") != "ridge_linear_regression":
            result["errors"].append("unexpected model algorithm")
        if not metadata.get("training_cutoff"):
            result["errors"].append("missing training cutoff")
        if not metadata.get("dataset_fingerprint"):
            result["errors"].append("missing dataset fingerprint")
    except Exception as exc:
        result["errors"].append(f"artifact parse failed: {exc.__class__.__name__}")
    result["valid"] = not result["errors"]
    return result


def validate_projection_artifacts(artifact_dir: Path | None = None) -> list[dict[str, Any]]:
    artifact_dir = artifact_dir or CONFIG.model_artifact_dir
    return [validate_projection_artifact(artifact_dir / f"{position}.json") for position in sorted(SUPPORTED_MODEL_POSITIONS)]


def projection_artifact_summary(artifact_dir: Path | None = None) -> dict[str, Any]:
    rows = validate_projection_artifacts(artifact_dir)
    valid = sum(1 for row in rows if row["valid"])
    training_cutoffs = []
    for row in rows:
        path = (artifact_dir or CONFIG.model_artifact_dir) / row["path"]
        if row["valid"]:
            metadata = json.loads(path.read_text(encoding="utf-8"))["metadata"]
            training_cutoffs.append(metadata.get("training_cutoff"))
    return {"valid_artifacts": valid, "total_artifacts": len(rows), "model_version": MODEL_VERSION, "training_cutoff": sorted(set(training_cutoffs))[-1] if training_cutoffs else None, "rows": rows}
