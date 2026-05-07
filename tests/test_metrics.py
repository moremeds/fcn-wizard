from __future__ import annotations

import unittest

import numpy as np

from fcn_wizard.metrics import (
    autocall_alive_months_from_paths,
    black_scholes_put,
    choose_tenor_vol,
    down_in_put_proxy,
    down_in_put_rr,
    joint_ki_prob_mc,
    joint_ki_prob_nd,
)


class BasketMetricsTest(unittest.TestCase):
    def test_joint_ki_prob_nd_matches_pair_engine_for_two_assets(self):
        pair = joint_ki_prob_mc(0.45, 0.55, 0.60, n_sims=5_000, seed=7)
        nd = joint_ki_prob_nd(
            vols=[0.45, 0.55],
            corr_matrix=np.array([[1.0, 0.60], [0.60, 1.0]]),
            n_sims=5_000,
            seed=7,
        )
        self.assertAlmostEqual(nd["p_either"], pair[0], places=12)
        self.assertAlmostEqual(nd["p_all"], pair[1], places=12)

    def test_joint_ki_prob_nd_supports_three_assets(self):
        result = joint_ki_prob_nd(
            vols=[0.40, 0.50, 0.60],
            corr_matrix=np.array(
                [
                    [1.0, 0.5, 0.4],
                    [0.5, 1.0, 0.6],
                    [0.4, 0.6, 1.0],
                ]
            ),
            n_sims=2_000,
            seed=11,
        )
        self.assertGreaterEqual(result["p_either"], result["p_all"])
        self.assertEqual(len(result["p_by_asset"]), 3)

    def test_choose_tenor_vol_prefers_matching_tenor_iv(self):
        self.assertEqual(choose_tenor_vol(iv_30d=0.30, rv_30d=0.25, tenor_iv=0.42), 0.42)

    def test_choose_tenor_vol_falls_back_to_30d_iv_then_rv(self):
        self.assertEqual(choose_tenor_vol(iv_30d=0.30, rv_30d=0.25, tenor_iv=None), 0.30)
        self.assertEqual(choose_tenor_vol(iv_30d=None, rv_30d=0.25, tenor_iv=None), 0.25)

    def test_down_in_put_proxy_positive_for_risky_input(self):
        value = down_in_put_proxy(spot=100, strike=100, barrier=50, tenor_years=1.0, rate=0.04, vol=0.60)
        self.assertGreater(value, 0)
        self.assertLess(value, 100)

    def test_autocall_alive_months_uses_first_observation_hit(self):
        paths = np.array(
            [
                [1.00, 1.01, 1.02, 1.03],
                [1.00, 0.99, 0.98, 0.97],
            ]
        )
        months = autocall_alive_months_from_paths(paths, ko_level=1.02, observation_steps=[1, 2, 3], steps_per_month=1)
        self.assertEqual(months, 2.5)

    def test_down_in_put_rr_is_bounded_by_vanilla_put(self):
        vanilla = black_scholes_put(spot=100, strike=100, tenor_years=1.0, rate=0.04, vol=0.60)
        dip = down_in_put_rr(spot=100, strike=100, barrier=50, tenor_years=1.0, rate=0.04, vol=0.60)

        self.assertGreaterEqual(dip, 0)
        self.assertLessEqual(dip, vanilla)

    def test_down_in_put_rr_converges_to_vanilla_as_barrier_approaches_spot(self):
        vanilla = black_scholes_put(spot=100, strike=100, tenor_years=1.0, rate=0.04, vol=0.60)
        dip = down_in_put_rr(spot=100, strike=100, barrier=99.0, tenor_years=1.0, rate=0.04, vol=0.60)

        self.assertLess(abs(dip - vanilla), 1.0)

    def test_down_in_put_rr_is_near_zero_for_remote_barrier(self):
        value = down_in_put_rr(spot=100, strike=100, barrier=1, tenor_years=1.0, rate=0.04, vol=0.30)

        self.assertLess(value, 0.01)

    def test_down_in_put_rr_rejects_unsupported_strike_below_barrier(self):
        with self.assertRaisesRegex(ValueError, "strike must be greater than or equal to barrier"):
            down_in_put_rr(spot=100, strike=40, barrier=50, tenor_years=1.0, rate=0.04, vol=0.30)


if __name__ == "__main__":
    unittest.main()
