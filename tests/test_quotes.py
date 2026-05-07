from __future__ import annotations

import unittest
from io import StringIO

import pandas as pd

from fcn_wizard.analysis import TickerMetrics
from fcn_wizard.metrics import dealer_margin
from fcn_wizard.quotes import compare_pb_quotes
from fcn_wizard.workflows.fair_coupon import rank_quotes_against_fair_coupon


class QuoteMetricsTest(unittest.TestCase):
    def test_dealer_margin_is_fair_coupon_minus_quote(self):
        self.assertAlmostEqual(dealer_margin(0.22, 0.28), 0.06)

    def test_dealer_margin_returns_none_without_quote(self):
        self.assertIsNone(dealer_margin(None, 0.18))

    def test_ticker_metrics_has_quote_fields(self):
        row = TickerMetrics(symbol="NVDA", fair_coupon_proxy=0.18, quoted_coupon=0.22)
        self.assertEqual(row.quoted_coupon, 0.22)


class FairCouponWorkflowTest(unittest.TestCase):
    def test_rank_quotes_against_pair_fair_coupon(self):
        pairs = pd.DataFrame(
            [
                {
                    "a": "NVDA",
                    "b": "TSLA",
                    "p_ki_either": 0.50,
                    "pair_fair_coupon_proxy": 0.75,
                }
            ]
        )
        quotes = pd.read_csv(
            StringIO(
                "pb,symbols,quoted_coupon\n"
                "PB_A,NVDA/TSLA,0.22\n"
                "PB_B,NVDA/TSLA,0.28\n"
            )
        )

        ranked = rank_quotes_against_fair_coupon(pairs, quotes)

        self.assertEqual(ranked.iloc[0]["pb"], "PB_A")
        self.assertAlmostEqual(ranked.iloc[0]["dealer_margin"], 0.53)
        self.assertEqual(ranked.iloc[0]["verdict"], "expensive_vs_model")

    def test_compare_pb_quotes_ranks_largest_client_shortfall_first(self):
        quotes = pd.read_csv(
            StringIO(
                "pb,symbols,quoted_coupon\n"
                "PB_A,NVDA/TSLA,0.22\n"
                "PB_B,NVDA/TSLA,0.25\n"
            )
        )
        fair = pd.DataFrame([{"symbols": "NVDA/TSLA", "fair_coupon_proxy": 0.28}])

        result = compare_pb_quotes(quotes, fair)

        self.assertEqual(result.iloc[0]["pb"], "PB_A")
        self.assertAlmostEqual(result.iloc[0]["dealer_margin"], 0.06)


if __name__ == "__main__":
    unittest.main()
