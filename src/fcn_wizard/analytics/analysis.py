from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
import pandas as pd

from ..config import ProductConfig
from ..data.market_data import (
    fetch_atm_iv_for_dte,
    fetch_history,
    fetch_option_surface_sample,
    fetch_returns,
    fetch_skew,
    save_raw_frame,
)
from .vol_surface import fit_svi, wing_adjusted_ki_vol
from .metrics import (
    above_200dma,
    choose_tenor_vol,
    coupon_uplift_proxy,
    dealer_margin,
    drawdown_3m,
    fair_coupon_proxy,
    iv_rank,
    joint_ki_prob_mc,
    joint_ki_prob_nd,
    max_drawdown,
    pair_correlation,
    realized_vol,
    single_name_ki_prob,
    stock_adv_usd,
)
from .scoring import ScoreToggles, score_basket, score_pair, score_single

if TYPE_CHECKING:
    from ib_insync import IB


@dataclass
class TickerMetrics:
    symbol: str
    spot: Optional[float] = None
    iv_30d_current: Optional[float] = None
    iv_rank: Optional[float] = None
    rv_30d: Optional[float] = None
    vrp: Optional[float] = None
    atm_iv_45dte: Optional[float] = None
    put_skew_25d: Optional[float] = None
    above_200dma: Optional[bool] = None
    drawdown_3m: Optional[float] = None
    max_drawdown_5y: Optional[float] = None
    crash_5y: Optional[int] = None
    stock_adv_usd: Optional[float] = None
    p_ki: Optional[float] = None
    fair_coupon_proxy: Optional[float] = None
    quoted_coupon: Optional[float] = None
    dealer_margin: Optional[float] = None
    tenor_iv: Optional[float] = None
    tenor_iv_dte: Optional[int] = None
    surface_ki_vol: Optional[float] = None
    surface_fit_points: Optional[int] = None
    vol_used_for_ki: Optional[float] = None
    score: float = 0.0
    notes: str = ""


def analyze_ticker(
    ib: IB,
    symbol: str,
    product: ProductConfig,
    toggles: ScoreToggles = ScoreToggles(),
    fetch_skew_enabled: bool = False,
    fetch_tenor_iv_enabled: bool = False,
    fetch_surface_iv_enabled: bool = False,
    raw_dir: Optional[Path] = None,
    quoted_coupon: Optional[float] = None,
) -> tuple[TickerMetrics, list[dict]]:
    symbol = symbol.upper().strip()
    metrics = TickerMetrics(symbol=symbol)

    df_1y = fetch_history(ib, symbol, 252, "TRADES")
    save_raw_frame(df_1y, raw_dir / "history_1y" / f"{symbol}.csv") if raw_dir else None
    if df_1y is None or df_1y.empty:
        metrics.notes = "No 1Y price history returned by IBKR."
        return metrics, []

    prices = df_1y["close"]
    metrics.spot = float(prices.iloc[-1])
    metrics.rv_30d = realized_vol(prices, 30)
    metrics.above_200dma = above_200dma(prices)
    metrics.drawdown_3m = drawdown_3m(prices)
    metrics.stock_adv_usd = stock_adv_usd(df_1y, 20)

    df_5y = fetch_history(ib, symbol, 252 * 5, "TRADES")
    save_raw_frame(df_5y, raw_dir / "history_5y" / f"{symbol}.csv") if raw_dir else None
    if df_5y is not None and not df_5y.empty:
        metrics.max_drawdown_5y = max_drawdown(df_5y["close"])
        metrics.crash_5y = int(metrics.max_drawdown_5y is not None and metrics.max_drawdown_5y <= -product.ki_barrier)

    df_iv = fetch_history(ib, symbol, 252, "OPTION_IMPLIED_VOLATILITY")
    save_raw_frame(df_iv, raw_dir / "iv_1y" / f"{symbol}.csv") if raw_dir else None
    if df_iv is not None and "close" in df_iv.columns:
        iv_series = df_iv["close"].dropna()
        if len(iv_series) > 30:
            metrics.iv_30d_current = float(iv_series.iloc[-1])
            metrics.iv_rank = iv_rank(iv_series)
            if metrics.rv_30d is not None:
                metrics.vrp = metrics.iv_30d_current - metrics.rv_30d

    if fetch_skew_enabled:
        _, atm_iv, otm_iv = fetch_skew(ib, symbol, 45, 0.25)
        metrics.atm_iv_45dte = float(atm_iv) if atm_iv else None
        metrics.put_skew_25d = float(otm_iv - atm_iv) if atm_iv and otm_iv else None

    if fetch_tenor_iv_enabled:
        tenor_iv, actual_dte = fetch_atm_iv_for_dte(ib, symbol, product.tenor_days)
        metrics.tenor_iv = tenor_iv
        metrics.tenor_iv_dte = actual_dte

    if fetch_surface_iv_enabled and metrics.spot:
        surface = fetch_option_surface_sample(ib, symbol, product.tenor_days)
        save_raw_frame(surface, raw_dir / "option_surface" / f"{symbol}.csv") if raw_dir else None
        if surface is not None and len(surface) >= 5:
            try:
                params = fit_svi(surface["log_moneyness"].to_numpy(), surface["total_variance"].to_numpy())
                metrics.surface_ki_vol = wing_adjusted_ki_vol(
                    spot=metrics.spot,
                    barrier=metrics.spot * product.ki_barrier,
                    tenor_years=product.tenor_days / 252.0,
                    svi_params=params,
                )
                metrics.surface_fit_points = len(surface)
            except Exception:
                metrics.surface_fit_points = len(surface)

    metrics.vol_used_for_ki = metrics.surface_ki_vol or choose_tenor_vol(
        metrics.iv_30d_current,
        metrics.rv_30d,
        metrics.tenor_iv,
    )
    if metrics.vol_used_for_ki:
        metrics.p_ki = single_name_ki_prob(metrics.vol_used_for_ki, product.ki_barrier, product.tenor_days)
        metrics.fair_coupon_proxy = fair_coupon_proxy(
            metrics.p_ki,
            product.expected_loss_given_ki,
            product.expected_alive_months,
            product.discount_rate,
            product.tenor_days / 252.0,
        )
    metrics.quoted_coupon = quoted_coupon
    metrics.dealer_margin = dealer_margin(quoted_coupon, metrics.fair_coupon_proxy)

    metrics.score, breakdown = score_single(metrics, toggles)
    return metrics, breakdown


def metrics_frame(items: list[TickerMetrics]) -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in items])


def decision_summary(metrics: TickerMetrics) -> list[str]:
    notes: list[str] = []
    if metrics.vrp is not None:
        if metrics.vrp > 0.05:
            notes.append("Volatility premium is strong: IV is materially above realized vol.")
        elif metrics.vrp < 0:
            notes.append("Volatility premium is weak: realized vol is at or above IV.")
    if metrics.p_ki is not None:
        if metrics.p_ki < 0.10:
            notes.append("Modeled KI probability is low under the simple GBM screen.")
        elif metrics.p_ki < 0.25:
            notes.append("Modeled KI probability is moderate; coupon needs to compensate for tail risk.")
        else:
            notes.append("Modeled KI probability is high; treat coupon as payment for real downside risk.")
    if metrics.max_drawdown_5y is not None and metrics.max_drawdown_5y <= -0.50:
        notes.append("Historical 50% drawdown occurred, so KI is not merely theoretical.")
    if metrics.above_200dma is False:
        notes.append("Trend filter is weak: spot is below the 200DMA.")
    if not notes:
        notes.append("No major red flags from the enabled basic filters.")
    return notes


def analyze_pair(
    ib: IB,
    a: TickerMetrics,
    b: TickerMetrics,
    product: ProductConfig,
    lookback_days: int = 252 * 2,
    window: int = 60,
    n_sims: int = 20_000,
) -> tuple[dict, list[dict]]:
    r1 = fetch_returns(ib, a.symbol, lookback_days)
    r2 = fetch_returns(ib, b.symbol, lookback_days)
    if r1 is None or r2 is None:
        raise ValueError("Missing return history for one or both pair legs.")
    corr_60d, corr_full, corr_stability = pair_correlation(r1, r2, window)
    if corr_60d is None:
        raise ValueError("Insufficient overlapping return history for pair analysis.")

    vol_a = a.iv_30d_current or a.rv_30d
    vol_b = b.iv_30d_current or b.rv_30d
    if not vol_a or not vol_b:
        raise ValueError("Missing volatility estimate for one or both pair legs.")
    p_either, p_both, p_one = joint_ki_prob_mc(
        vol_a,
        vol_b,
        corr_60d,
        product.ki_barrier,
        product.tenor_days,
        n_sims=n_sims,
    )
    row = {
        "a": a.symbol,
        "b": b.symbol,
        "score_a": a.score,
        "score_b": b.score,
        "iv_a": vol_a,
        "iv_b": vol_b,
        "corr_60d": corr_60d,
        "corr_full": corr_full,
        "corr_stability": corr_stability,
        "p_ki_a": a.p_ki,
        "p_ki_b": b.p_ki,
        "p_ki_either": p_either,
        "p_ki_both": p_both,
        "p_ki_only_one": p_one,
    }
    if a.p_ki is not None and b.p_ki is not None:
        row["coupon_uplift"] = coupon_uplift_proxy(a.p_ki, b.p_ki, p_either)
    row["pair_score"], breakdown = score_pair(row)
    row["pair_fair_coupon_proxy"] = fair_coupon_proxy(
        p_either,
        product.expected_loss_given_ki,
        product.expected_alive_months,
        product.discount_rate,
        product.tenor_days / 252.0,
    )
    return row, breakdown


def build_correlation_matrix(
    returns: dict[str, pd.Series],
    symbols: list[str],
    window: int = 60,
) -> tuple[pd.DataFrame, float]:
    frame = pd.concat([returns[symbol].rename(symbol) for symbol in symbols], axis=1)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < window + 30:
        raise ValueError("Insufficient overlapping return history for basket analysis.")
    current = frame.tail(window).corr()
    rolling_stabilities = []
    for left_idx, left in enumerate(symbols):
        for right in symbols[left_idx + 1:]:
            rolling = frame[left].rolling(window).corr(frame[right]).dropna()
            if not rolling.empty:
                rolling_stabilities.append(float(rolling.std()))
    stability = float(pd.Series(rolling_stabilities).mean()) if rolling_stabilities else float("nan")
    return current, stability


def analyze_basket(
    rows: list[TickerMetrics],
    returns: dict[str, pd.Series],
    product: ProductConfig,
    window: int = 60,
    n_sims: int = 20_000,
) -> tuple[dict, list[dict]]:
    symbols = [row.symbol for row in rows]
    corr_matrix, corr_stability = build_correlation_matrix(returns, symbols, window)
    vols = [
        row.vol_used_for_ki or row.iv_30d_current or row.rv_30d
        for row in rows
    ]
    if any(vol is None for vol in vols):
        raise ValueError("Missing volatility estimate for one or more basket legs.")
    ki = joint_ki_prob_nd(
        vols=[float(vol) for vol in vols],
        corr_matrix=corr_matrix.to_numpy(),
        barrier=product.ki_barrier,
        days=product.tenor_days,
        n_sims=n_sims,
    )
    off_diag = corr_matrix.where(~np.eye(len(symbols), dtype=bool)).stack()
    row = {
        "symbols": "/".join(symbols),
        "score_avg": float(pd.Series([item.score for item in rows]).mean()),
        "corr_avg": float(off_diag.mean()),
        "corr_stability": corr_stability,
        "p_ki_either": ki["p_either"],
        "p_ki_all": ki["p_all"],
        "fair_coupon_proxy": fair_coupon_proxy(
            ki["p_either"],
            product.expected_loss_given_ki,
            product.expected_alive_months,
            product.discount_rate,
            product.tenor_days / 252.0,
        ),
    }
    row["basket_score"], breakdown = score_basket(row)
    return row, breakdown
