from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fcn_wizard.config import ProductConfig
from fcn_wizard.run_storage import save_run_table
from fcn_wizard.workflows.bootstrap import bootstrap_candidates


class BootstrapCandidatesTest(unittest.TestCase):
    def test_bootstrap_loads_latest_history_and_marks_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_run_table(
                pd.DataFrame([{"symbol": "NVDA", "score": 7.0}]),
                output_dir=output_dir,
                kind="candidates",
                run_id="20260507_120000",
            )

            result = bootstrap_candidates(
                output_dir=output_dir,
                universe=["AAPL"],
                run_config={},
                product=ProductConfig(),
                refresh=lambda symbols, product: pd.DataFrame([{"symbol": "AAPL"}]),
            )

            self.assertEqual(result.source, "history")
            self.assertEqual(result.run_id, "20260507_120000")
            self.assertEqual(
                result.frame.to_dict("records"),
                [{"symbol": "NVDA", "score": 7.0, "run_source": "history"}],
            )

    def test_bootstrap_runs_default_universe_when_history_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            result = bootstrap_candidates(
                output_dir=output_dir,
                universe=["NVDA", "TSLA"],
                run_config={"source": "unit-test"},
                product=ProductConfig(),
                refresh=lambda symbols, product: pd.DataFrame(
                    [{"symbol": symbol, "score": 1.0} for symbol in symbols]
                ),
            )

            self.assertEqual(result.source, "fresh")
            self.assertEqual(result.frame["symbol"].tolist(), ["NVDA", "TSLA"])
            self.assertEqual(result.frame["run_source"].tolist(), ["fresh", "fresh"])
            self.assertTrue((output_dir / "run_index.csv").exists())

    def test_bootstrap_force_refresh_ignores_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_run_table(
                pd.DataFrame([{"symbol": "OLD", "score": 7.0}]),
                output_dir=output_dir,
                kind="candidates",
                run_id="20260507_120000",
            )

            result = bootstrap_candidates(
                output_dir=output_dir,
                universe=["NEW"],
                run_config={},
                product=ProductConfig(),
                force_refresh=True,
                refresh=lambda symbols, product: pd.DataFrame([{"symbol": "NEW", "score": 2.0}]),
            )

            self.assertEqual(result.source, "fresh")
            self.assertEqual(
                result.frame.to_dict("records"),
                [{"symbol": "NEW", "score": 2.0, "run_source": "fresh"}],
            )


if __name__ == "__main__":
    unittest.main()
