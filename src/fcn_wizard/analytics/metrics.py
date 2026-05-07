from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm


def iv_rank(iv_series: pd.Series) -> Optional[float]:
    if iv_series is None or len(iv_series) < 30:
        return None
    current = iv_series.iloc[-1]
    low, high = float(iv_series.min()), float(iv_series.max())
    if high == low:
        return 50.0
    return float((current - low) / (high - low) * 100)


def realized_vol(prices: pd.Series, window: int = 30) -> Optional[float]:
    if prices is None or len(prices) < window + 1:
        return None
    log_ret = np.log(prices / prices.shift(1)).dropna()
    return float(log_ret.tail(window).std() * np.sqrt(252))


def drawdown_3m(prices: pd.Series) -> Optional[float]:
    if prices is None or len(prices) < 60:
        return None
    recent = prices.tail(63)
    return float(recent.iloc[-1] / recent.max() - 1.0)


def max_drawdown(prices: pd.Series) -> Optional[float]:
    if prices is None or len(prices) < 100:
        return None
    drawdown = prices / prices.cummax() - 1.0
    return float(drawdown.min())


def above_200dma(prices: pd.Series) -> Optional[bool]:
    if prices is None or len(prices) < 200:
        return None
    return bool(prices.iloc[-1] > prices.tail(200).mean())


def stock_adv_usd(df_history: pd.DataFrame, days: int = 20) -> Optional[float]:
    if df_history is None or df_history.empty:
        return None
    if "volume" not in df_history.columns or "close" not in df_history.columns:
        return None
    recent = df_history.tail(days)
    return float((recent["close"] * recent["volume"]).mean())


def single_name_ki_prob(vol: float, barrier: float = 0.50, days: int = 252) -> float:
    if vol is None or vol <= 0:
        return float("nan")
    sigma_t = vol * np.sqrt(days / 252.0)
    if sigma_t == 0:
        return 0.0
    return float(2.0 * norm.cdf(np.log(barrier) / sigma_t))


def fair_coupon_proxy(
    p_ki: float,
    expected_loss_given_ki: float = 0.53,
    expected_alive_months: float = 4.0,
    discount_rate: float = 0.045,
    tenor_years: float = 1.0,
) -> float:
    if p_ki is None or np.isnan(p_ki) or expected_alive_months <= 0:
        return float("nan")
    pv_expected_loss = p_ki * expected_loss_given_ki * np.exp(-discount_rate * tenor_years)
    return float(pv_expected_loss / (expected_alive_months / 12.0))


def down_in_put_proxy(
    spot: float,
    strike: float,
    barrier: float,
    tenor_years: float,
    rate: float,
    vol: float,
) -> float:
    p_ki = single_name_ki_prob(vol, barrier / spot, int(round(tenor_years * 252)))
    expected_loss = max(strike - barrier, 0.0) / strike
    return float(strike * p_ki * expected_loss * np.exp(-rate * tenor_years))


def black_scholes_put(spot: float, strike: float, tenor_years: float, rate: float, vol: float) -> float:
    if tenor_years <= 0:
        return float(max(strike - spot, 0.0))
    sigma_t = vol * np.sqrt(tenor_years)
    if sigma_t <= 0:
        return float(max(strike * np.exp(-rate * tenor_years) - spot, 0.0))
    d1 = (np.log(spot / strike) + (rate + 0.5 * vol**2) * tenor_years) / sigma_t
    d2 = d1 - sigma_t
    return float(strike * np.exp(-rate * tenor_years) * norm.cdf(-d2) - spot * norm.cdf(-d1))


def down_in_put_rr(
    spot: float,
    strike: float,
    barrier: float,
    tenor_years: float,
    rate: float,
    vol: float,
    dividend_yield: float = 0.0,
) -> float:
    """Down-and-in put value for the common FCN case K >= B.

    This function is deliberately invariant-gated and not wired into scoring yet.
    It uses a conservative first-passage activation of the vanilla put value while
    preserving the key RR boundaries required before formula-level replacement.
    """
    if barrier >= spot:
        raise ValueError("barrier must be below spot")
    if strike < barrier:
        raise ValueError("strike must be greater than or equal to barrier for the FCN DIP formula")
    vanilla = black_scholes_put(spot, strike, tenor_years, rate - dividend_yield, vol)
    if vanilla <= 0:
        return 0.0
    p_hit = single_name_ki_prob(vol, barrier / spot, int(round(tenor_years * 252)))
    if np.isnan(p_hit):
        return 0.0
    value = vanilla * max(0.0, min(1.0, p_hit))
    return float(min(max(value, 0.0), vanilla))


def autocall_alive_months_from_paths(
    paths: np.ndarray,
    ko_level: float,
    observation_steps: list[int],
    steps_per_month: int = 21,
) -> float:
    alive_steps = []
    last_step = paths.shape[1] - 1
    for path in paths:
        hit_step = next((step for step in observation_steps if step < len(path) and path[step] >= ko_level), last_step)
        alive_steps.append(hit_step)
    return float(np.mean(alive_steps) / steps_per_month)


def choose_tenor_vol(
    iv_30d: float | None,
    rv_30d: float | None,
    tenor_iv: float | None,
) -> float | None:
    return tenor_iv or iv_30d or rv_30d


def dealer_margin(quoted_coupon: float | None, fair_coupon: float | None) -> float | None:
    if quoted_coupon is None or fair_coupon is None:
        return None
    if np.isnan(quoted_coupon) or np.isnan(fair_coupon):
        return None
    return float(fair_coupon - quoted_coupon)


def coupon_uplift_proxy(p_ki_single_a: float, p_ki_single_b: float, p_ki_pair: float) -> float:
    best_single = min(p_ki_single_a, p_ki_single_b)
    if best_single <= 0:
        return float("nan")
    return float(p_ki_pair / best_single)


def pair_correlation(r1: pd.Series, r2: pd.Series, window: int = 60):
    df = pd.concat([r1, r2], axis=1).dropna()
    if len(df) < window + 30:
        return None, None, None
    full = float(df.iloc[:, 0].corr(df.iloc[:, 1]))
    rolling = df.iloc[:, 0].rolling(window).corr(df.iloc[:, 1]).dropna()
    if rolling.empty:
        return None, full, None
    return float(rolling.iloc[-1]), full, float(rolling.std())


def joint_ki_prob_nd(
    vols: list[float],
    corr_matrix: np.ndarray,
    barrier: float = 0.50,
    days: int = 252,
    n_sims: int = 20_000,
    seed: int = 42,
) -> dict:
    vols_array = np.asarray(vols, dtype=float)
    corr = np.asarray(corr_matrix, dtype=float)
    n_assets = len(vols_array)
    if corr.shape != (n_assets, n_assets):
        raise ValueError("corr_matrix shape must match vols")
    corr = np.clip(corr.copy(), -0.999, 0.999)
    np.fill_diagonal(corr, 1.0)
    chol = np.linalg.cholesky(corr)
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    z = rng.standard_normal(size=(n_sims, days, n_assets)) @ chol.T
    drift = -0.5 * vols_array**2 * dt
    diffusion = vols_array * np.sqrt(dt)
    log_paths = np.cumsum(drift + diffusion * z, axis=1)
    min_paths = np.exp(log_paths.min(axis=1))
    hits = min_paths <= barrier
    return {
        "p_either": float(hits.any(axis=1).mean()),
        "p_all": float(hits.all(axis=1).mean()),
        "p_exactly_one": float((hits.sum(axis=1) == 1).mean()),
        "p_by_asset": hits.mean(axis=0).astype(float).tolist(),
    }


def joint_ki_prob_mc(
    vol_a: float,
    vol_b: float,
    rho: float,
    barrier: float = 0.50,
    days: int = 252,
    n_sims: int = 20_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    result = joint_ki_prob_nd(
        vols=[vol_a, vol_b],
        corr_matrix=np.array([[1.0, rho], [rho, 1.0]]),
        barrier=barrier,
        days=days,
        n_sims=n_sims,
        seed=seed,
    )
    return result["p_either"], result["p_all"], result["p_exactly_one"]
