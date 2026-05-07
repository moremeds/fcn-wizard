from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def init_snapshot_db(db_path: Path | str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            """
            create table if not exists candidate_snapshots (
                as_of_date varchar,
                run_id varchar,
                symbol varchar,
                score double,
                p_ki double,
                fair_coupon_proxy double
            )
            """
        )


def save_candidate_snapshot(
    db_path: Path | str,
    frame: pd.DataFrame,
    as_of_date: str,
    run_id: str,
) -> int:
    init_snapshot_db(db_path)
    rows = frame.copy()
    rows["as_of_date"] = as_of_date
    rows["run_id"] = run_id
    for column in ["symbol", "score", "p_ki", "fair_coupon_proxy"]:
        if column not in rows.columns:
            rows[column] = None
    rows = rows[["as_of_date", "run_id", "symbol", "score", "p_ki", "fair_coupon_proxy"]]
    with duckdb.connect(str(db_path)) as conn:
        conn.register("snapshot_rows", rows)
        conn.execute("insert into candidate_snapshots select * from snapshot_rows")
    return len(rows)
