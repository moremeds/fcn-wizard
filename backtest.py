from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from fcn_wizard.config import ProductConfig, read_universe_file
from fcn_wizard.data.market_data import connect_ib, fetch_forward_price_history, fetch_history
from fcn_wizard.analysis import TickerMetrics
from fcn_wizard.metrics import (
    above_200dma,
    drawdown_3m,
    fair_coupon_proxy,
    iv_rank,
    max_drawdown,
    realized_vol,
    single_name_ki_prob,
    stock_adv_usd,
)
from fcn_wizard.scoring import ScoreToggles, score_single
from fcn_wizard.workflows.backtest import replay_as_of_date, score_ki_rank_correlation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Point-in-time replay backtest for FCN screener scoring.")
    parser.add_argument("--as-of-date", required=True, help="Historical date such as 2024-01-15.")
    parser.add_argument("--universe-file", default="config/default_universe.txt")
    parser.add_argument("--output", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497)
    parser.add_argument("--client-id", type=int, default=44)
    parser.add_argument("--skip-skew", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    universe = read_universe_file(args.universe_file)
    product = ProductConfig()
    ib = connect_ib(args.host, args.port, args.client_id)
    end_datetime = pd.Timestamp(args.as_of_date).strftime("%Y%m%d 23:59:59 US/Eastern")

    def screen_at_date(symbol: str, product_config: ProductConfig) -> dict:
        df = fetch_history(ib, symbol, 252, "TRADES", end_datetime=end_datetime)
        if df is None or df.empty:
            raise RuntimeError(f"No historical prices for {symbol} as of {args.as_of_date}")
        prices = df["close"]
        iv_df = fetch_history(ib, symbol, 252, "OPTION_IMPLIED_VOLATILITY", end_datetime=end_datetime)
        iv_current = None
        iv_rank_value = None
        if iv_df is not None and "close" in iv_df.columns:
            iv_series = iv_df["close"].dropna()
            if len(iv_series) > 30:
                iv_current = float(iv_series.iloc[-1])
                iv_rank_value = iv_rank(iv_series)
        rv_30d = realized_vol(prices, 30)
        vol = iv_current or rv_30d
        p_ki = single_name_ki_prob(vol, product_config.ki_barrier, product_config.tenor_days) if vol else None
        dd_3m = drawdown_3m(prices)
        df_5y = fetch_history(ib, symbol, 252 * 5, "TRADES", end_datetime=end_datetime)
        max_dd_5y = max_drawdown(df_5y["close"]) if df_5y is not None and not df_5y.empty else None
        crash_5y = int(max_dd_5y is not None and max_dd_5y <= -product_config.ki_barrier) if max_dd_5y is not None else None
        metrics = TickerMetrics(
            symbol=symbol,
            spot=float(prices.iloc[-1]),
            iv_30d_current=iv_current,
            iv_rank=iv_rank_value,
            rv_30d=rv_30d,
            vrp=(iv_current - rv_30d) if iv_current is not None and rv_30d is not None else None,
            above_200dma=above_200dma(prices),
            drawdown_3m=dd_3m,
            max_drawdown_5y=max_dd_5y,
            crash_5y=crash_5y,
            stock_adv_usd=stock_adv_usd(df),
            p_ki=p_ki,
            fair_coupon_proxy=fair_coupon_proxy(p_ki) if p_ki is not None else None,
        )
        score, _ = score_single(metrics, ScoreToggles())
        return {
            "symbol": symbol,
            "spot": metrics.spot,
            "iv_30d_current": iv_current,
            "iv_rank": iv_rank_value,
            "rv_30d": rv_30d,
            "p_ki": p_ki,
            "fair_coupon_proxy": metrics.fair_coupon_proxy,
            "score": score,
        }

    try:
        result = replay_as_of_date(
            args.as_of_date,
            universe,
            product,
            screen_at_date=screen_at_date,
            fetch_forward_prices=lambda symbol, as_of_date, days: fetch_forward_price_history(ib, symbol, as_of_date, days)
            or pd.Series(dtype=float),
        )
    finally:
        ib.disconnect()

    corr = score_ki_rank_correlation(result)
    output = Path(args.output) if args.output else Path("outputs") / f"backtest_{args.as_of_date}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    result.rows.to_csv(output, index=False)
    print(result.rows.to_string(index=False))
    print(f"Spearman(score, KI outcome): {corr:.4f}")
    print(f"Saved {len(result.rows)} rows -> {output}")


if __name__ == "__main__":
    main()
