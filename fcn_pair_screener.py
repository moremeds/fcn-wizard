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

import logging
import sys
import argparse
from dataclasses import dataclass, asdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, util

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from fcn_wizard.analysis import TickerMetrics, analyze_basket
from fcn_wizard.config import ProductConfig
from fcn_wizard.metrics import coupon_uplift_proxy, joint_ki_prob_mc, pair_correlation, single_name_ki_prob
from fcn_wizard.run_storage import load_latest_table, save_run_table
from fcn_wizard.scoring import score_pair as score_pair_with_breakdown


# ============================================================
# CONFIG
# ============================================================

IB_HOST = "127.0.0.1"
IB_PORT = 7497
IB_CLIENT_ID = 43
OUTPUT_DIR = "outputs"

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

def load_candidates(input_dir: str | Path = OUTPUT_DIR) -> pd.DataFrame:
    loaded = load_latest_table(output_dir=input_dir, kind="candidates")
    if loaded is not None:
        df, record = loaded
        log.info(f"Loading candidates from run history {record.artifact_path}")
        return _top_candidates(df)

    files = sorted(Path(input_dir).glob("fcn_candidates_*.csv"))
    if not files:
        files = sorted(Path(".").glob("fcn_candidates_*.csv"))
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
    return _top_candidates(df)


def _top_candidates(df: pd.DataFrame) -> pd.DataFrame:
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
    total, _ = score_pair_with_breakdown(asdict(p))
    return total


# ============================================================
# MAIN
# ============================================================

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank worst-of FCN pairs using the latest single-name run.")
    parser.add_argument("--host", default=IB_HOST)
    parser.add_argument("--port", type=int, default=IB_PORT)
    parser.add_argument("--client-id", type=int, default=IB_CLIENT_ID)
    parser.add_argument("--input-dir", default=OUTPUT_DIR, help="Directory containing run history or dated candidate CSVs.")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Directory where pair run history is stored.")
    parser.add_argument("--basket-size", type=int, choices=[2, 3], default=2)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)
    candidates = load_candidates(args.input_dir)
    log.info(f"Working with {len(candidates)} candidates")
    log.info(f"\n{candidates.to_string(index=False)}\n")

    ib = IB()
    log.info(f"Connecting to IB {args.host}:{args.port}...")
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=15)
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

    # Build vol and score maps
    iv_map: dict[str, float] = {}
    rv_map: dict[str, float] = {}
    if "iv_30d_current" in candidates.columns:
        for _, row in candidates.iterrows():
            iv = row["iv_30d_current"]
            iv_map[row["symbol"]] = float(iv) if pd.notna(iv) else DEFAULT_VOL
    if "rv_30d" in candidates.columns:
        for _, row in candidates.iterrows():
            rv = row["rv_30d"]
            if pd.notna(rv):
                rv_map[row["symbol"]] = float(rv)
    score_map = dict(zip(candidates["symbol"], candidates["score"]))

    # Single-name KI probs (cache)
    single_ki = {
        s: single_name_ki_prob(iv_map.get(s, DEFAULT_VOL))
        for s in returns.keys()
    }

    # Iterate pairs or triples
    log.info("\nComputing basket metrics...")
    syms = list(returns.keys())
    baskets = list(combinations(syms, args.basket_size))
    log.info(f"Total baskets: {len(baskets)}")

    if args.basket_size == 2:
        results: list[PairMetrics] = []
        for k, (a, b) in enumerate(baskets):
            if (k + 1) % 20 == 0:
                log.info(f"  pair {k+1}/{len(baskets)}")

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
        df = pd.DataFrame([asdict(r) for r in results])
        score_column = "pair_score"
        output_kind = "pairs"
        output_label = "pairs"
        filename_prefix = "fcn_pairs"
    else:
        product = ProductConfig(tenor_days=TENOR_DAYS, ki_barrier=KI_BARRIER)
        basket_results: list[dict] = []
        for k, symbols in enumerate(baskets):
            if (k + 1) % 20 == 0:
                log.info(f"  basket {k+1}/{len(baskets)}")
            rows = [
                TickerMetrics(
                    symbol=symbol,
                    score=float(score_map.get(symbol, 0.0)),
                    iv_30d_current=iv_map.get(symbol, DEFAULT_VOL),
                    rv_30d=rv_map.get(symbol),
                )
                for symbol in symbols
            ]
            try:
                basket_row, _ = analyze_basket(rows, returns, product, window=60, n_sims=N_MC_SIMS)
            except Exception as e:
                log.warning(f"  basket analysis failed for {symbols}: {e}")
                continue
            basket_results.append(basket_row)
        df = pd.DataFrame(basket_results)
        score_column = "basket_score"
        output_kind = "baskets"
        output_label = "baskets"
        filename_prefix = "fcn_baskets"

    if df.empty:
        log.error("No basket results produced.")
        sys.exit(1)

    # Output
    df = df.sort_values(score_column, ascending=False).reset_index(drop=True)

    today = datetime.today().strftime("%Y%m%d")
    out_path = f"{filename_prefix}_{today}.csv"
    df.to_csv(out_path, index=False)
    log.info(f"Saved {len(df)} {output_label} → {out_path}")
    run_record = save_run_table(
        df,
        output_dir=args.output_dir,
        kind=output_kind,
        metadata={
            "host": args.host,
            "port": args.port,
            "client_id": args.client_id,
            "input_dir": args.input_dir,
            "dated_output": out_path,
            "basket_size": args.basket_size,
            "top_n_from_csv": TOP_N_FROM_CSV,
            "lookback_days": LOOKBACK_DAYS,
            "ki_barrier": KI_BARRIER,
            "tenor_days": TENOR_DAYS,
            "n_mc_sims": N_MC_SIMS,
        },
    )
    log.info(f"Saved {output_label} run history → {run_record.artifact_path}")

    if args.basket_size == 2:
        cols = [
            "a", "b", "score_a", "score_b", "iv_a", "iv_b",
            "corr_60d", "corr_stability",
            "p_ki_a", "p_ki_b", "p_ki_either", "p_ki_both",
            "coupon_uplift", "pair_score",
        ]
        title = "TOP 15 WORST-OF FCN PAIRS"
    else:
        cols = [
            "symbols", "score_avg", "corr_avg", "corr_stability",
            "p_ki_either", "p_ki_all", "fair_coupon_proxy", "basket_score",
        ]
        title = "TOP 15 WORST-OF FCN BASKETS"
    cols = [c for c in cols if c in df.columns]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 220)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)
    print(df[cols].head(15).to_string(index=False))
    print("=" * 90)
    if args.basket_size == 2:
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
    else:
        print(f"""
Reading the columns:
  corr_avg        : average pairwise correlation across the basket
  corr_stability  : average std of rolling pairwise correlation
  p_ki_either     : MC P(at least one name hits 50% KI in 1Y)
  p_ki_all        : MC P(all names hit 50% KI in 1Y)
  fair_coupon_proxy: annualized model fair coupon proxy for the basket
  basket_score    : combined screener score (higher = more attractive)
""")


if __name__ == "__main__":
    main()
