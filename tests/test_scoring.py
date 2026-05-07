from __future__ import annotations

import unittest
from types import SimpleNamespace

from fcn_wizard.scoring import ScoreToggles, score_pair, score_single


class PairScoringTest(unittest.TestCase):
    def test_pair_score_rewards_coupon_uplift_sweet_spot(self):
        score, breakdown = score_pair(
            {
                "score_a": 0.0,
                "score_b": 0.0,
                "corr_60d": 0.4,
                "corr_stability": 0.15,
                "p_ki_either": 0.4,
                "coupon_uplift": 1.5,
            }
        )

        self.assertEqual(score, 0.5)
        self.assertIn("Coupon uplift", [row["factor"] for row in breakdown])


class SingleScoringTest(unittest.TestCase):
    def test_score_single_matches_documented_high_quality_candidate(self):
        metrics = SimpleNamespace(
            iv_rank=75,
            vrp=0.06,
            put_skew_25d=0.04,
            above_200dma=True,
            drawdown_3m=-0.10,
            stock_adv_usd=1.5e9,
            crash_5y=0,
        )

        score, rows = score_single(metrics, ScoreToggles())

        self.assertEqual(score, 9.5)
        self.assertEqual(
            [row["factor"] for row in rows],
            [
                "IV Rank",
                "VRP",
                "Put Skew",
                "Trend",
                "3M Drawdown",
                "Liquidity",
                "5Y Crash",
            ],
        )


if __name__ == "__main__":
    unittest.main()
