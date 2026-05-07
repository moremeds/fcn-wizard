from __future__ import annotations

import unittest

import pandas as pd

from fcn_wizard.analysis import build_correlation_matrix


class BasketAnalysisTest(unittest.TestCase):
    def test_build_correlation_matrix_returns_current_matrix_and_stability(self):
        index = pd.date_range("2025-01-01", periods=120)
        returns = {
            "A": pd.Series(range(120), index=index, dtype=float).pct_change().fillna(0.0),
            "B": pd.Series(range(1, 121), index=index, dtype=float).pct_change().fillna(0.0),
            "C": pd.Series(range(2, 122), index=index, dtype=float).pct_change().fillna(0.0),
        }

        matrix, stability = build_correlation_matrix(returns, ["A", "B", "C"], window=60)

        self.assertEqual(matrix.shape, (3, 3))
        self.assertEqual(list(matrix.index), ["A", "B", "C"])
        self.assertIsInstance(stability, float)


if __name__ == "__main__":
    unittest.main()
