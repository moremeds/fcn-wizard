"""
FCN Candidate Screener (Standalone)
====================================

Screens US-listed equities for suitability as FCN (Fixed Coupon Note)
underlyings, using only IBKR market data via ib_insync.

Scoring philosophy:
  Good FCN underlying = high IV (rich coupon) + IV richer than realized
  + healthy trend (low KI risk) + liquid options + no near-term events
  + no history of 50%+ crashes (KI safety).

Usage:
  1. Start IB Gateway or TWS with API enabled.
       Paper port = 7497, live port = 7496.
  2. pip install ib_insync pandas numpy
  3. python fcn_screener.py
  4. Output: fcn_candidates_YYYYMMDD.csv + top-10 to stdout.

Notes:
  - Skew calc requires live option market data; if you don't have
    OPRA subscription, set FETCH_SKEW = False.
  - IB pacing: max ~50 concurrent historical requests. Universe is
    batched. If you extend universe, watch for HMDS pacing violations.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Option, util

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from fcn_wizard.metrics import (
    above_200dma,
    dealer_margin,
    drawdown_3m,
    fair_coupon_proxy,
    iv_rank,
    max_drawdown,
    realized_vol,
    single_name_ki_prob,
    stock_adv_usd,
)
from fcn_wizard.run_storage import load_latest_table, save_run_table
from fcn_wizard.scoring import score_single


# ============================================================
# CONFIG
# ============================================================

IB_HOST = "127.0.0.1"
IB_PORT = 7497          # 7497 paper, 7496 live
IB_CLIENT_ID = 42
OUTPUT_DIR = "outputs"
SAVE_RAW_DATA = True

# Edit to change screening universe
UNIVERSE = [
    # Mega-cap tech (FCN PB darlings)
    "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "META", "AMZN",
    "AMD",  "AVGO", "NFLX", "ORCL", "CRM",   "ADBE",
    # High-vol single names (rich coupon, but watch tail)
    "MSTR", "COIN", "PLTR", "SHOP", "UBER",  "SNOW", "CRWD",
    # Defensive / blue-chip (lower coupon, safer)
    "JPM",  "BAC",  "WMT",  "JNJ",  "XOM",   "CVX",
    # ETFs (index-linked FCN building blocks)
    "SPY",  "QQQ",  "IWM",
]

LOOKBACK_DAYS_1Y = 252
LOOKBACK_DAYS_5Y = 252 * 5
TARGET_DTE      = 45
SKEW_DELTA      = 0.25
KI_THRESHOLD    = 0.50    # 50% drawdown = standard FCN KI

# Pacing
BATCH_SIZE      = 10
BATCH_SLEEP_SEC = 5

FETCH_SKEW = True   # set False if no OPRA / want a fast run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fcn_screener")
logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class TickerMetrics:
    symbol: str
    spot: Optional[float] = None
    iv_30d_current: Optional[float] = None
    iv_rank: Optional[float] = None             # 0-100 within last 1Y
    rv_30d: Optional[float] = None
    vrp: Optional[float] = None                 # IV - RV (decimal)
    atm_iv_45dte: Optional[float] = None
    put_skew_25d: Optional[float] = None        # 25d put IV - ATM IV
    above_200dma: Optional[bool] = None
    drawdown_3m: Optional[float] = None         # peak-to-trough last 3M
    max_drawdown_5y: Optional[float] = None     # worst 5Y peak-to-trough
    crash_5y: Optional[int] = None              # 1 if any >=50% drawdown in 5Y
    stock_adv_usd: Optional[float] = None       # liquidity proxy
    p_ki: Optional[float] = None
    fair_coupon_proxy: Optional[float] = None
    quoted_coupon: Optional[float] = None
    dealer_margin: Optional[float] = None
    score: float = 0.0
    notes: str = ""


# ============================================================
# IB FETCHERS
# ============================================================

def ib_duration(days: int) -> str:
    """IBKR requires year units for historical requests longer than 365 days."""
    return f"{round(days / 365)} Y" if days > 365 else f"{days} D"


def read_universe_file(path: str | Path) -> list[str]:
    symbols: list[str] = []
    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        symbols.extend(part.strip().upper() for part in line.split(",") if part.strip())
    return symbols


def save_raw_frame(df: Optional[pd.DataFrame], path: Path) -> None:
    if df is None or df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(path, index=False)

def fetch_history(ib: IB, symbol: str, days: int, what: str = "TRADES"):
    """Daily bars. what = 'TRADES' or 'OPTION_IMPLIED_VOLATILITY'."""
    contract = Stock(symbol, "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        return None
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=ib_duration(days),
        barSizeSetting="1 day",
        whatToShow=what,
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        return None
    df = util.df(bars)
    if df is None or df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def fetch_skew(ib: IB, symbol: str, target_dte: int, target_delta: float):
    """Return (spot, atm_iv, otm_put_iv_at_25d). Best-effort; returns
    None for missing values rather than raising."""
    stock = Stock(symbol, "SMART", "USD")
    if not ib.qualifyContracts(stock):
        return None, None, None

    # Spot
    md = ib.reqMktData(stock, "", snapshot=False)
    ib.sleep(2)
    spot = md.marketPrice() or md.last or md.close
    ib.cancelMktData(stock)
    if not spot or np.isnan(spot):
        return None, None, None

    # Option params
    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    if not chains:
        return spot, None, None
    chain = next((c for c in chains if c.exchange == "SMART"), chains[0])

    # Closest expiry to target DTE
    today = datetime.today().date()
    target = today + timedelta(days=target_dte)
    exps = sorted(chain.expirations)
    if not exps:
        return spot, None, None
    best_exp = min(
        exps,
        key=lambda e: abs((datetime.strptime(e, "%Y%m%d").date() - target).days),
    )

    strikes = sorted(chain.strikes)
    atm_strike = min(strikes, key=lambda k: abs(k - spot))

    # ATM put IV
    atm_put = Option(symbol, best_exp, atm_strike, "P", "SMART")
    if not ib.qualifyContracts(atm_put):
        return spot, None, None
    atm_md = ib.reqMktData(atm_put, "", snapshot=False)
    ib.sleep(2)
    atm_iv = (atm_md.modelGreeks.impliedVol
              if atm_md.modelGreeks else None)
    ib.cancelMktData(atm_put)

    # OTM put closest to target delta
    otm = [k for k in strikes if k < spot * 0.98][-12:]
    if not otm:
        return spot, atm_iv, None

    best_iv, best_diff = None, float("inf")
    for k in otm:
        put = Option(symbol, best_exp, k, "P", "SMART")
        try:
            if not ib.qualifyContracts(put):
                continue
            md = ib.reqMktData(put, "", snapshot=False)
            ib.sleep(1.2)
            if md.modelGreeks and md.modelGreeks.delta is not None:
                d = abs(md.modelGreeks.delta)
                diff = abs(d - target_delta)
                if diff < best_diff:
                    best_diff = diff
                    best_iv = md.modelGreeks.impliedVol
            ib.cancelMktData(put)
        except Exception as e:
            log.debug(f"{symbol} put strike {k}: {e}")
            continue

    return spot, atm_iv, best_iv


# ============================================================
# PER-TICKER PIPELINE
# ============================================================

def screen_ticker(
    ib: IB,
    symbol: str,
    fetch_skew_enabled: bool = FETCH_SKEW,
    raw_dir: Optional[Path] = None,
    quoted_coupon: Optional[float] = None,
) -> TickerMetrics:
    m = TickerMetrics(symbol=symbol)
    try:
        # 1Y prices for RV, trend, drawdown, ADV
        df_1y = fetch_history(ib, symbol, LOOKBACK_DAYS_1Y, "TRADES")
        if raw_dir:
            save_raw_frame(df_1y, raw_dir / "history_1y" / f"{symbol}.csv")
        if df_1y is None or df_1y.empty:
            m.notes = "no_history_1y"
            return m
        prices = df_1y["close"]
        m.spot = float(prices.iloc[-1])
        m.rv_30d = realized_vol(prices, 30)
        m.above_200dma = above_200dma(prices)
        m.drawdown_3m = drawdown_3m(prices)
        m.stock_adv_usd = stock_adv_usd(df_1y, 20)

        # 5Y for crash check
        df_5y = fetch_history(ib, symbol, LOOKBACK_DAYS_5Y, "TRADES")
        if raw_dir:
            save_raw_frame(df_5y, raw_dir / "history_5y" / f"{symbol}.csv")
        if df_5y is not None and not df_5y.empty:
            mdd = max_drawdown(df_5y["close"])
            m.max_drawdown_5y = mdd
            m.crash_5y = int(mdd is not None and mdd <= -KI_THRESHOLD)

        # Historical IV for IV rank
        df_iv = fetch_history(ib, symbol, LOOKBACK_DAYS_1Y, "OPTION_IMPLIED_VOLATILITY")
        if raw_dir:
            save_raw_frame(df_iv, raw_dir / "iv_1y" / f"{symbol}.csv")
        if df_iv is not None and "close" in df_iv.columns:
            iv_series = df_iv["close"].dropna()
            if len(iv_series) > 30:
                m.iv_30d_current = float(iv_series.iloc[-1])
                m.iv_rank = iv_rank(iv_series)
                if m.rv_30d is not None:
                    m.vrp = m.iv_30d_current - m.rv_30d

        # Skew (slow, optional)
        if fetch_skew_enabled:
            try:
                _, atm_iv, otm_iv = fetch_skew(ib, symbol, TARGET_DTE, SKEW_DELTA)
                if atm_iv:
                    m.atm_iv_45dte = float(atm_iv)
                if atm_iv and otm_iv:
                    m.put_skew_25d = float(otm_iv - atm_iv)
            except Exception as e:
                log.warning(f"{symbol} skew failed: {e}")

        vol_for_ki = m.iv_30d_current or m.rv_30d
        if vol_for_ki:
            m.p_ki = single_name_ki_prob(vol_for_ki, KI_THRESHOLD, LOOKBACK_DAYS_1Y)
            m.fair_coupon_proxy = fair_coupon_proxy(m.p_ki)
        m.quoted_coupon = quoted_coupon
        m.dealer_margin = dealer_margin(quoted_coupon, m.fair_coupon_proxy)

        m.score, _ = score_single(m)

    except Exception as e:
        log.exception(f"{symbol} pipeline failed")
        m.notes = f"error:{e}"
    return m


# ============================================================
# MAIN
# ============================================================

def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen FCN single-name candidates using IBKR data.")
    parser.add_argument("--host", default=IB_HOST)
    parser.add_argument("--port", type=int, default=IB_PORT)
    parser.add_argument("--client-id", type=int, default=IB_CLIENT_ID)
    parser.add_argument("--universe-file", default=None, help="Text file with one ticker per line or comma-separated tickers.")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    parser.add_argument("--save-raw", action=argparse.BooleanOptionalAction, default=SAVE_RAW_DATA)
    parser.add_argument("--fetch-skew", action=argparse.BooleanOptionalAction, default=FETCH_SKEW)
    parser.add_argument("--auto-load-latest", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--quoted-coupon", type=float, default=None, help="Annualized quoted coupon as decimal, e.g. 0.22")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--batch-sleep", type=float, default=BATCH_SLEEP_SEC)
    parser.add_argument("--top", type=int, default=10, help="Rows to print to stdout.")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)
    universe = read_universe_file(args.universe_file) if args.universe_file else UNIVERSE
    output_dir = Path(args.output_dir)
    raw_dir = output_dir / "raw" if args.save_raw else None
    output_dir.mkdir(parents=True, exist_ok=True)

    run_config = {
        "host": args.host,
        "port": args.port,
        "client_id": args.client_id,
        "universe": universe,
        "lookback_days_1y": LOOKBACK_DAYS_1Y,
        "lookback_days_5y": LOOKBACK_DAYS_5Y,
        "target_dte": TARGET_DTE,
        "skew_delta": SKEW_DELTA,
        "ki_threshold": KI_THRESHOLD,
        "fetch_skew": args.fetch_skew,
        "quoted_coupon": args.quoted_coupon,
        "save_raw": args.save_raw,
    }
    (output_dir / "single_run_config.json").write_text(json.dumps(run_config, indent=2) + "\n")

    if args.auto_load_latest and not args.force_refresh:
        loaded = load_latest_table(output_dir=output_dir, kind="candidates")
        if loaded is not None:
            df, record = loaded
            log.info(f"Loaded previous candidate run {record.run_id} from {record.artifact_path}")
            pd.set_option("display.max_columns", None)
            pd.set_option("display.width", 200)
            print(df.head(args.top).to_string(index=False))
            return

    ib = IB()
    log.info(f"Connecting to IB {args.host}:{args.port} (clientId={args.client_id})...")
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=15)
    except Exception as e:
        log.error(f"IB connection failed: {e}")
        log.error("→ Is IB Gateway / TWS running with API enabled?")
        sys.exit(1)

    log.info(f"Connected. Screening {len(universe)} tickers...")
    results: list[TickerMetrics] = []

    for batch in chunked(universe, args.batch_size):
        for symbol in batch:
            log.info(f"  → {symbol}")
            results.append(screen_ticker(ib, symbol, args.fetch_skew, raw_dir, args.quoted_coupon))
        log.info(f"Batch done; sleeping {args.batch_sleep}s for pacing...")
        ib.sleep(args.batch_sleep)

    ib.disconnect()

    # Build dataframe
    df = pd.DataFrame([asdict(r) for r in results])
    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    # Save
    today = datetime.today().strftime("%Y%m%d")
    out_path = output_dir / f"fcn_candidates_{today}.csv"
    df.to_csv(out_path, index=False)
    log.info(f"\nSaved {len(df)} rows → {out_path}")
    run_record = save_run_table(
        df,
        output_dir=output_dir,
        kind="candidates",
        metadata={**run_config, "dated_output": str(out_path)},
    )
    log.info(f"Saved run history → {run_record.artifact_path}")

    # Pretty print top 10
    cols = [
        "symbol", "spot", "iv_30d_current", "iv_rank", "rv_30d", "vrp",
        "p_ki", "fair_coupon_proxy", "put_skew_25d", "above_200dma", "drawdown_3m", "max_drawdown_5y",
        "quoted_coupon", "dealer_margin", "crash_5y", "score",
    ]
    cols = [c for c in cols if c in df.columns]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print("\n" + "=" * 70)
    print("TOP 10 FCN CANDIDATES")
    print("=" * 70)
    print(df[cols].head(args.top).to_string(index=False))
    print("=" * 70)


if __name__ == "__main__":
    main()
