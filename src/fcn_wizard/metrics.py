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


def pair_correlation(r1: pd.Series, r2: pd.Series, window: int = 60):
    df = pd.concat([r1, r2], axis=1).dropna()
    if len(df) < window + 30:
        return None, None, None
    full = float(df.iloc[:, 0].corr(df.iloc[:, 1]))
    rolling = df.iloc[:, 0].rolling(window).corr(df.iloc[:, 1]).dropna()
    if rolling.empty:
        return None, full, None
    return float(rolling.iloc[-1]), full, float(rolling.std())


def joint_ki_prob_mc(
    vol_a: float,
    vol_b: float,
    rho: float,
    barrier: float = 0.50,
    days: int = 252,
    n_sims: int = 20_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    rho = max(min(float(rho), 0.999), -0.999)
    chol = np.linalg.cholesky(np.array([[1.0, rho], [rho, 1.0]]))
    z = rng.standard_normal(size=(n_sims, days, 2)) @ chol.T

    diff_a = -0.5 * vol_a**2 * dt + vol_a * np.sqrt(dt) * z[:, :, 0]
    diff_b = -0.5 * vol_b**2 * dt + vol_b * np.sqrt(dt) * z[:, :, 1]
    min_a = np.exp(np.cumsum(diff_a, axis=1).min(axis=1))
    min_b = np.exp(np.cumsum(diff_b, axis=1).min(axis=1))

    hit_a = min_a <= barrier
    hit_b = min_b <= barrier
    p_either = float((hit_a | hit_b).mean())
    p_both = float((hit_a & hit_b).mean())
    return p_either, p_both, p_either - p_both
