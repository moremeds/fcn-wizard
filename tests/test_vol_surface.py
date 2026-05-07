from __future__ import annotations

import unittest

import numpy as np

from fcn_wizard.analytics.vol_surface import fit_svi, svi_total_variance, wing_adjusted_ki_vol


class VolSurfaceTest(unittest.TestCase):
    def test_svi_fit_recovers_smooth_positive_surface(self):
        k = np.array([-0.5, -0.25, 0.0, 0.25, 0.5])
        true_params = {"a": 0.02, "b": 0.10, "rho": -0.40, "m": 0.0, "sigma": 0.30}
        w = svi_total_variance(k, **true_params)

        params = fit_svi(k, w)
        fitted = svi_total_variance(k, **params)

        self.assertTrue(np.all(fitted > 0))
        self.assertLess(float(np.mean(np.abs(fitted - w))), 0.01)

    def test_wing_adjusted_ki_vol_uses_barrier_moneyness(self):
        params = {"a": 0.02, "b": 0.10, "rho": -0.40, "m": 0.0, "sigma": 0.30}
        vol = wing_adjusted_ki_vol(spot=100, barrier=50, tenor_years=1.0, svi_params=params)

        self.assertGreater(vol, 0)


if __name__ == "__main__":
    unittest.main()
