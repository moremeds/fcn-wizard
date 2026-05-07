from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fcn_wizard.run_storage import load_latest_table, save_run_table


class RunStorageTest(unittest.TestCase):
    def test_save_run_table_writes_artifact_metadata_and_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            df = pd.DataFrame([{"symbol": "NVDA", "score": 7.5}])

            record = save_run_table(
                df,
                output_dir=output_dir,
                kind="candidates",
                metadata={"source": "unit-test"},
                run_id="20260507_120000",
            )

            self.assertEqual(record.run_id, "20260507_120000")
            self.assertEqual(record.kind, "candidates")
            self.assertEqual(record.row_count, 1)
            self.assertTrue((output_dir / "runs" / "20260507_120000" / "candidates.csv").exists())
            self.assertTrue((output_dir / "runs" / "20260507_120000" / "metadata.json").exists())
            self.assertTrue((output_dir / "run_index.csv").exists())

            metadata = json.loads((output_dir / "runs" / "20260507_120000" / "metadata.json").read_text())
            self.assertEqual(metadata["source"], "unit-test")
            self.assertEqual(metadata["artifacts"]["candidates"], "candidates.csv")

    def test_load_latest_table_returns_most_recent_saved_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_run_table(
                pd.DataFrame([{"symbol": "AAPL", "score": 1.0}]),
                output_dir=output_dir,
                kind="candidates",
                run_id="20260507_120000",
            )
            save_run_table(
                pd.DataFrame([{"symbol": "TSLA", "score": 2.0}]),
                output_dir=output_dir,
                kind="candidates",
                run_id="20260507_130000",
            )

            loaded = load_latest_table(output_dir=output_dir, kind="candidates")

            self.assertIsNotNone(loaded)
            table, record = loaded
            self.assertEqual(record.run_id, "20260507_130000")
            self.assertEqual(table.to_dict("records"), [{"symbol": "TSLA", "score": 2.0}])

    def test_load_latest_table_returns_none_without_saved_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(load_latest_table(output_dir=Path(temp_dir), kind="candidates"))


if __name__ == "__main__":
    unittest.main()
