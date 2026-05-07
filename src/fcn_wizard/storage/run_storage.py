from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


INDEX_FILE = "run_index.csv"
RUNS_DIR = "runs"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    kind: str
    created_at: str
    row_count: int
    artifact_path: Path
    metadata_path: Path


def make_run_id(now: Optional[datetime] = None) -> str:
    timestamp = now or datetime.now()
    return timestamp.strftime("%Y%m%d_%H%M%S_%f")


def save_run_table(
    df: pd.DataFrame,
    output_dir: Path | str = Path("outputs"),
    kind: str = "candidates",
    metadata: Optional[dict] = None,
    run_id: Optional[str] = None,
) -> RunRecord:
    output_path = Path(output_dir)
    resolved_run_id = run_id or make_run_id()
    run_dir = output_path / RUNS_DIR / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = run_dir / f"{kind}.csv"
    metadata_path = run_dir / "metadata.json"
    created_at = datetime.now().isoformat(timespec="seconds")

    df.to_csv(artifact_path, index=False)
    merged_metadata = _read_metadata(metadata_path)
    merged_metadata.update(metadata or {})
    artifacts = dict(merged_metadata.get("artifacts", {}))
    artifacts[kind] = artifact_path.name
    merged_metadata.update(
        {
            "run_id": resolved_run_id,
            "created_at": merged_metadata.get("created_at", created_at),
            "artifacts": artifacts,
        }
    )
    metadata_path.write_text(json.dumps(merged_metadata, indent=2, sort_keys=True) + "\n")

    record = RunRecord(
        run_id=resolved_run_id,
        kind=kind,
        created_at=created_at,
        row_count=len(df),
        artifact_path=artifact_path,
        metadata_path=metadata_path,
    )
    _upsert_index(output_path / INDEX_FILE, record)
    return record


def load_latest_table(
    output_dir: Path | str = Path("outputs"),
    kind: str = "candidates",
) -> Optional[tuple[pd.DataFrame, RunRecord]]:
    output_path = Path(output_dir)
    index_path = output_path / INDEX_FILE
    if not index_path.exists():
        return None

    index = pd.read_csv(index_path)
    if index.empty or "kind" not in index.columns:
        return None

    matches = index[index["kind"] == kind].copy()
    if matches.empty:
        return None

    matches = matches.sort_values(["created_at", "run_id"], ascending=[False, False])
    for _, row in matches.iterrows():
        artifact_path = output_path / str(row["artifact_path"])
        metadata_path = output_path / str(row["metadata_path"])
        if artifact_path.exists():
            record = RunRecord(
                run_id=str(row["run_id"]),
                kind=str(row["kind"]),
                created_at=str(row["created_at"]),
                row_count=int(row["row_count"]),
                artifact_path=artifact_path,
                metadata_path=metadata_path,
            )
            return pd.read_csv(artifact_path), record
    return None


def _read_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _upsert_index(index_path: Path, record: RunRecord) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": record.run_id,
        "kind": record.kind,
        "created_at": record.created_at,
        "row_count": record.row_count,
        "artifact_path": str(record.artifact_path.relative_to(index_path.parent)),
        "metadata_path": str(record.metadata_path.relative_to(index_path.parent)),
    }
    if index_path.exists():
        index = pd.read_csv(index_path)
        keep = ~((index["run_id"] == record.run_id) & (index["kind"] == record.kind))
        index = pd.concat([index[keep], pd.DataFrame([row])], ignore_index=True)
    else:
        index = pd.DataFrame([row])
    index = index.sort_values(["created_at", "run_id", "kind"]).reset_index(drop=True)
    index.to_csv(index_path, index=False)
