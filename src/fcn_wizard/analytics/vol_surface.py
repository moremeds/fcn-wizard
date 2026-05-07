from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


def svi_total_variance(k: np.ndarray, a: float, b: float, rho: float, m: float, sigma: float) -> np.ndarray:
    k = np.asarray(k, dtype=float)
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma**2))


def fit_svi(log_moneyness: np.ndarray, total_variance: np.ndarray) -> dict:
    k = np.asarray(log_moneyness, dtype=float)
    w = np.asarray(total_variance, dtype=float)

    def residual(raw: np.ndarray) -> np.ndarray:
        a, log_b, raw_rho, m, log_sigma = raw
        params = {
            "a": a,
            "b": np.exp(log_b),
            "rho": np.tanh(raw_rho),
            "m": m,
            "sigma": np.exp(log_sigma),
        }
        return svi_total_variance(k, **params) - w

    result = least_squares(residual, x0=np.array([0.01, np.log(0.1), 0.0, 0.0, np.log(0.3)]))
    a, log_b, raw_rho, m, log_sigma = result.x
    return {
        "a": float(a),
        "b": float(np.exp(log_b)),
        "rho": float(np.tanh(raw_rho)),
        "m": float(m),
        "sigma": float(np.exp(log_sigma)),
    }


def wing_adjusted_ki_vol(spot: float, barrier: float, tenor_years: float, svi_params: dict) -> float:
    log_moneyness = np.array([np.log(barrier / spot)])
    total_var = svi_total_variance(log_moneyness, **svi_params)[0]
    return float(np.sqrt(max(total_var, 0.0) / tenor_years))
