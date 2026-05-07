"""
Worst-of FCN Pair Screener (Standalone)
========================================

Companion to fcn_screener.py. Takes a universe of single-name FCN
candidates and ranks PAIRS for worst-of FCN structures.

Why this matters:
  HK PB worst-of FCNs typically combine 2-3 names. Investor short
  correlation: lower correlation = higher coupon, but also higher
  joint KI probability. This screener quantifies the trade-off via
  Monte Carlo and ranks pairs by:
    - Combined single-name FCN scores (both names good individually)
    - Joint KI probability (1Y, 50% barrier) via correlated MC
    - Correlation regime stability
    - Coupon uplift estimate vs single-name FCN

Workflow:
  1. Run fcn_screener.py first → produces fcn_candidates_YYYYMMDD.csv
  2. Run this script. It auto-loads the most recent candidates CSV.
  3. Output: fcn_pairs_YYYYMMDD.csv + top-15 to stdout.

If no candidates CSV exists, falls back to UNIVERSE_FALLBACK below.

Usage:
  pip install ib_insync pandas numpy
  python fcn_pair_screener.py
"""

import glob
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from itertools import combinations
from typing import Optional

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, util


# ============================================================
# CONFIG
# ============================================================

IB_HOST = "127.0.0.1"
IB_PORT = 7497
IB_CLIENT_ID = 43

# Used only if no fcn_candidates_*.csv found in cwd
UNIVERSE_FALLBACK = [
    "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "META", "AMZN",
    "AMD", "AVGO", "NFLX", "MSTR", "COIN", "PLTR",
]

TOP_N_FROM_CSV   = 15      # take top-N from screener 1 output
LOOKBACK_DAYS    = 252 * 2 # 2Y returns for correlation
DEFAULT_VOL      = 0.45    # fallback if IV not in CSV
KI_BARRIER       = 0.50    # 50% drawdown
TENOR_DAYS       = 252     # 1Y FCN tenor
N_MC_SIMS        = 20_000  # MC paths per pair
RNG_SEED         = 42

BATCH_SIZE       = 10
BATCH_SLEEP_SEC  = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fcn_pair_screener")


# ============================================================
# LOAD CANDIDATES
# ============================================================

def load_candidates() -> pd.DataFrame:
    files = sorted(glob.glob("fcn_candidates_*.csv"))
    if not files:
        log.warning("No fcn_candidates_*.csv found — using UNIVERSE_FALLBACK")
        return pd.DataFrame({
            "symbol": UNIVERSE_FALLBACK,
            "score": [0.0] * len(UNIVERSE_FALLBACK),
            "iv_30d_current": [DEFAULT_VOL] * len(UNIVERSE_FALLBACK),
        })

    latest = files[-1]
    log.info(f"Loading candidates from {latest}")
    df = pd.read_csv(latest)

    # Take top-N by score (or all if fewer)
    df = df.sort_values("score", ascending=False).head(TOP_N_FROM_CSV)
    keep = ["symbol", "score"]
    if "iv_30d_current" in df.columns:
        keep.append("iv_30d_current")
    if "rv_30d" in df.columns:
        keep.append("rv_30d")
    return df[keep].reset_index(drop=True)


# ============================================================
# IB DATA
# ============================================================

def fetch_returns(ib: IB, symbol: str, days: int) -> Optional[pd.Series]:
    contract = Stock(symbol, "SMART", "USD")
    if not ib.qualifyContracts(contract):
        return None
    duration = f"{round(days / 365)} Y" if days > 365 else f"{days} D"
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        return None
    df = util.df(bars)
    if df is None or df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    log_ret = np.log(df["close"] / df["close"].shift(1)).dropna()
    log_ret.name = symbol
    return log_ret


# ============================================================
# CORRELATION & STABILITY
# ============================================================

def pair_correlation(r1: pd.Series, r2: pd.Series, window: int = 60):
    """Returns (current_corr_60d, full_corr, rolling_corr_std)."""
    df = pd.concat([r1, r2], axis=1).dropna()
    if len(df) < window + 30:
        return None, None, None
    full = df.iloc[:, 0].corr(df.iloc[:, 1])
    rolling = df.iloc[:, 0].rolling(window).corr(df.iloc[:, 1]).dropna()
    if rolling.empty:
        return None, full, None
    current = float(rolling.iloc[-1])
    stability = float(rolling.std())
    return current, float(full), stability


# ============================================================
# MONTE CARLO JOINT KI
# ============================================================

def joint_ki_prob_mc(
    vol_a: float, vol_b: float, rho: float,
    barrier: float = KI_BARRIER, days: int = TENOR_DAYS,
    n_sims: int = N_MC_SIMS, seed: int = RNG_SEED,
) -> tuple[float, float, float]:
    """
    Returns (P_either_hits, P_both_hit, P_only_one). Uses GBM with zero
    drift (risk-neutral approximation, dropping rates for screening).
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    n_steps = days

    cov = np.array([[1.0, rho], [rho, 1.0]])
    try:
        L = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        # rho out of range
        rho = max(min(rho, 0.999), -0.999)
        cov = np.array([[1.0, rho], [rho, 1.0]])
        L = np.linalg.cholesky(cov)

    z = rng.standard_normal(size=(n_sims, n_steps, 2))
    z = z @ L.T  # correlated normals

    drift_a = -0.5 * vol_a ** 2 * dt
    drift_b = -0.5 * vol_b ** 2 * dt
    diff_a = drift_a + vol_a * np.sqrt(dt) * z[:, :, 0]
    diff_b = drift_b + vol_b * np.sqrt(dt) * z[:, :, 1]

    log_path_a = np.cumsum(diff_a, axis=1)
    log_path_b = np.cumsum(diff_b, axis=1)
    min_a = np.exp(log_path_a.min(axis=1))
    min_b = np.exp(log_path_b.min(axis=1))

    hit_a = min_a <= barrier
    hit_b = min_b <= barrier
    p_either = float((hit_a | hit_b).mean())
    p_both = float((hit_a & hit_b).mean())
    p_one = p_either - p_both
    return p_either, p_both, p_one


def single_name_ki_prob(vol: float, barrier: float = KI_BARRIER,
                        days: int = TENOR_DAYS) -> float:
    """Closed-form continuous barrier hit probability under GBM (no drift)."""
    if vol is None or vol <= 0:
        return float("nan")
    sigma_T = vol * np.sqrt(days / 252.0)
    if sigma_T == 0:
        return 0.0
    log_b = np.log(barrier)
    # GBM no-drift: P(min S_t <= B) = 2 * N(log(B) / sigma_T)
    from scipy.stats import norm
    return 2.0 * norm.cdf(log_b / sigma_T)


# ============================================================
# COUPON UPLIFT ESTIMATE
# ============================================================

def coupon_uplift_proxy(p_ki_single_a: float, p_ki_single_b: float,
                        p_ki_pair: float) -> float:
    """
    Proxy for coupon uplift: ratio of pair KI prob over the better
    (lower-risk) single name. >1 means pair is riskier and should pay
    more coupon. Useful for ranking.
    """
    best_single = min(p_ki_single_a, p_ki_single_b)
    if best_single <= 0:
        return float("nan")
    return p_ki_pair / best_single


# ============================================================
# SCORING
# ============================================================

@dataclass
class PairMetrics:
    a: str
    b: str
    score_a: float = 0.0
    score_b: float = 0.0
    iv_a: Optional[float] = None
    iv_b: Optional[float] = None
    corr_60d: Optional[float] = None
    corr_full: Optional[float] = None
    corr_stability: Optional[float] = None
    p_ki_a: Optional[float] = None
    p_ki_b: Optional[float] = None
    p_ki_either: Optional[float] = None
    p_ki_both: Optional[float] = None
    coupon_uplift: Optional[float] = None
    pair_score: float = 0.0


def score_pair(p: PairMetrics) -> float:
    s = (p.score_a + p.score_b) / 2.0  # base = average of single-name scores

    # Correlation: higher is better for investor (less dispersion = lower joint KI)
    if p.corr_60d is not None:
        if p.corr_60d > 0.7:
            s += 1.5
        elif p.corr_60d > 0.5:
            s += 1.0
        elif p.corr_60d > 0.3:
            s += 0.0
        else:
            s -= 1.0  # low corr = nasty worst-of for investor

    # Correlation stability — penalize regime-shift pairs
    if p.corr_stability is not None:
        if p.corr_stability < 0.10:
            s += 0.5
        elif p.corr_stability > 0.20:
            s -= 0.5

    # Joint KI penalty (absolute level)
    if p.p_ki_either is not None:
        if p.p_ki_either < 0.15:
            s += 1.5
        elif p.p_ki_either < 0.30:
            s += 0.5
        elif p.p_ki_either > 0.50:
            s -= 1.5

    # Coupon uplift sweet spot: 1.3-1.8x = good (worth the extra risk)
    if p.coupon_uplift is not None:
        if 1.2 < p.coupon_uplift < 1.8:
            s += 0.5
        elif p.coupon_uplift > 2.5:
            s -= 0.5

    return round(s, 2)


# ============================================================
# MAIN
# ============================================================

def main():
    candidates = load_candidates()
    log.info(f"Working with {len(candidates)} candidates")
    log.info(f"\n{candidates.to_string(index=False)}\n")

    ib = IB()
    log.info(f"Connecting to IB {IB_HOST}:{IB_PORT}...")
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=15)
    except Exception as e:
        log.error(f"IB connection failed: {e}")
        sys.exit(1)

    # Fetch daily returns for each candidate
    log.info("Fetching daily returns...")
    returns: dict[str, pd.Series] = {}
    for i, sym in enumerate(candidates["symbol"].tolist()):
        log.info(f"  [{i+1}/{len(candidates)}] {sym}")
        r = fetch_returns(ib, sym, LOOKBACK_DAYS)
        if r is not None and len(r) > 100:
            returns[sym] = r
        else:
            log.warning(f"  → skipping {sym} (insufficient data)")
        if (i + 1) % BATCH_SIZE == 0:
            log.info(f"  pacing pause {BATCH_SLEEP_SEC}s...")
            ib.sleep(BATCH_SLEEP_SEC)

    ib.disconnect()
    log.info(f"Got returns for {len(returns)} names")

    # Build IV map
    iv_map: dict[str, float] = {}
    if "iv_30d_current" in candidates.columns:
        for _, row in candidates.iterrows():
            iv = row["iv_30d_current"]
            iv_map[row["symbol"]] = float(iv) if pd.notna(iv) else DEFAULT_VOL
    score_map = dict(zip(candidates["symbol"], candidates["score"]))

    # Single-name KI probs (cache)
    single_ki = {
        s: single_name_ki_prob(iv_map.get(s, DEFAULT_VOL))
        for s in returns.keys()
    }

    # Iterate pairs
    log.info("\nComputing pair metrics...")
    results: list[PairMetrics] = []
    syms = list(returns.keys())
    pairs = list(combinations(syms, 2))
    log.info(f"Total pairs: {len(pairs)}")

    for k, (a, b) in enumerate(pairs):
        if (k + 1) % 20 == 0:
            log.info(f"  pair {k+1}/{len(pairs)}")

        cur_corr, full_corr, stab = pair_correlation(returns[a], returns[b])
        if cur_corr is None:
            continue

        vol_a = iv_map.get(a, DEFAULT_VOL)
        vol_b = iv_map.get(b, DEFAULT_VOL)

        try:
            p_either, p_both, _ = joint_ki_prob_mc(
                vol_a, vol_b, cur_corr,
                barrier=KI_BARRIER, days=TENOR_DAYS,
                n_sims=N_MC_SIMS, seed=RNG_SEED,
            )
        except Exception as e:
            log.warning(f"  MC failed for ({a},{b}): {e}")
            continue

        pm = PairMetrics(
            a=a, b=b,
            score_a=float(score_map.get(a, 0.0)),
            score_b=float(score_map.get(b, 0.0)),
            iv_a=vol_a, iv_b=vol_b,
            corr_60d=cur_corr, corr_full=full_corr, corr_stability=stab,
            p_ki_a=single_ki.get(a),
            p_ki_b=single_ki.get(b),
            p_ki_either=p_either, p_ki_both=p_both,
            coupon_uplift=coupon_uplift_proxy(
                single_ki.get(a, 0.0), single_ki.get(b, 0.0), p_either
            ),
        )
        pm.pair_score = score_pair(pm)
        results.append(pm)

    # Output
    df = pd.DataFrame([asdict(r) for r in results])
    df = df.sort_values("pair_score", ascending=False).reset_index(drop=True)

    today = datetime.today().strftime("%Y%m%d")
    out_path = f"fcn_pairs_{today}.csv"
    df.to_csv(out_path, index=False)
    log.info(f"Saved {len(df)} pairs → {out_path}")

    cols = [
        "a", "b", "score_a", "score_b", "iv_a", "iv_b",
        "corr_60d", "corr_stability",
        "p_ki_a", "p_ki_b", "p_ki_either", "p_ki_both",
        "coupon_uplift", "pair_score",
    ]
    cols = [c for c in cols if c in df.columns]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 220)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    print("\n" + "=" * 90)
    print("TOP 15 WORST-OF FCN PAIRS")
    print("=" * 90)
    print(df[cols].head(15).to_string(index=False))
    print("=" * 90)
    print(f"""
Reading the columns:
  corr_60d        : 60-day rolling correlation (current)
  corr_stability  : std of rolling 60d correlation (lower = more stable regime)
  p_ki_a / p_ki_b : single-name 1Y 50% KI probability (closed-form GBM)
  p_ki_either     : MC P(at least one name hits 50% KI in 1Y)
  p_ki_both       : MC P(both hit) — for double-trouble tail
  coupon_uplift   : p_ki_either / min(p_ki_a, p_ki_b)
                    >1 means pair is riskier than safer single name
  pair_score      : combined screener score (higher = more attractive)
""")


if __name__ == "__main__":
    main()
