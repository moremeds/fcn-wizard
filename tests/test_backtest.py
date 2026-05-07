from __future__ import annotations

import unittest

import pandas as pd

from fcn_wizard.workflows.backtest import BacktestResult, forward_ki_outcome, score_ki_rank_correlation


class PointInTimeBacktestTest(unittest.TestCase):
    def test_forward_ki_outcome_flags_barrier_touch_after_t0(self):
        prices = pd.Series(
            [100, 95, 80, 49, 70],
            index=pd.date_range("2024-01-15", periods=5, freq="D"),
        )

        outcome = forward_ki_outcome(prices, initial_spot=100, barrier=0.50)

        self.assertTrue(outcome)

    def test_forward_ki_outcome_false_when_barrier_not_touched(self):
        prices = pd.Series(
            [100, 95, 80, 51, 70],
            index=pd.date_range("2024-01-15", periods=5, freq="D"),
        )

        outcome = forward_ki_outcome(prices, initial_spot=100, barrier=0.50)

        self.assertFalse(outcome)

    def test_score_ki_rank_correlation_returns_negative_when_high_scores_avoid_ki(self):
        result = BacktestResult(
            as_of_date="2024-01-15",
            rows=pd.DataFrame(
                [
                    {"symbol": "SAFE", "score": 9.0, "ki_outcome": False},
                    {"symbol": "RISKY", "score": 1.0, "ki_outcome": True},
                ]
            ),
        )

        corr = score_ki_rank_correlation(result)

        self.assertLess(corr, 0)


if __name__ == "__main__":
    unittest.main()
