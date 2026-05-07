from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fcn_wizard.storage.snapshots import init_snapshot_db, save_candidate_snapshot


class SnapshotStoreTest(unittest.TestCase):
    def test_save_candidate_snapshot_round_trips_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "fcn.duckdb"
            init_snapshot_db(db_path)
            saved = save_candidate_snapshot(
                db_path,
                pd.DataFrame([{"symbol": "NVDA", "score": 7.0, "p_ki": 0.2}]),
                as_of_date="2026-05-07",
                run_id="run-1",
            )
            self.assertEqual(saved, 1)


if __name__ == "__main__":
    unittest.main()
