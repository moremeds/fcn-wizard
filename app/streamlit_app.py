from __future__ import annotations
from pathlib import Path

import pandas as pd
import streamlit as st

from fcn_wizard.analysis import analyze_pair, analyze_ticker, decision_summary, metrics_frame
from fcn_wizard.config import IbConfig, ProductConfig, read_universe_file
from fcn_wizard.market_data import connect_ib
from fcn_wizard.scoring import ScoreToggles


st.set_page_config(page_title="FCN Wizard", layout="wide")


def parse_tickers(raw: str) -> list[str]:
    tickers: list[str] = []
    for token in raw.replace("\n", ",").split(","):
        symbol = token.strip().upper()
        if symbol:
            tickers.append(symbol)
    return list(dict.fromkeys(tickers))


def pct(value):
    if value is None or pd.isna(value):
        return None
    return f"{value:.1%}"


def num(value):
    if value is None or pd.isna(value):
        return None
    return f"{value:,.2f}"


def money(value):
    if value is None or pd.isna(value):
        return None
    return f"${value / 1e9:,.2f}B"


def candidate_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    formatters = {
        "score": lambda value: "" if pd.isna(value) else f"{value:.2f}",
        "spot": lambda value: "" if pd.isna(value) else f"${value:,.2f}",
        "iv_30d_current": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "iv_rank": lambda value: "" if pd.isna(value) else f"{value:.1f}",
        "rv_30d": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "vrp": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "p_ki": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "fair_coupon_proxy": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "above_200dma": lambda value: "" if pd.isna(value) else ("Yes" if value else "No"),
        "drawdown_3m": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "max_drawdown_5y": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "crash_5y": lambda value: "" if pd.isna(value) else ("Yes" if int(value) else "No"),
        "stock_adv_usd": lambda value: "" if pd.isna(value) else f"${value / 1e9:,.2f}B",
    }
    for column, formatter in formatters.items():
        if column in display.columns:
            display[column] = display[column].map(formatter)
    return display.rename(
        columns={
            "symbol": "Symbol",
            "score": "Score",
            "spot": "Spot",
            "iv_30d_current": "IV 30D",
            "iv_rank": "IV Rank",
            "rv_30d": "RV 30D",
            "vrp": "VRP",
            "p_ki": "KI Prob",
            "fair_coupon_proxy": "Fair Coupon Proxy",
            "above_200dma": "Above 200DMA",
            "drawdown_3m": "3M DD",
            "max_drawdown_5y": "5Y Max DD",
            "crash_5y": "50% Crash",
            "stock_adv_usd": "Stock ADV",
        }
    )


def display_single_card(row):
    st.subheader(row.symbol)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Spot", num(row.spot))
    c2.metric("Score", f"{row.score:.2f}")
    c3.metric("KI probability", pct(row.p_ki))
    c4.metric("Fair coupon proxy", pct(row.fair_coupon_proxy))
    c5.metric("VRP", pct(row.vrp))

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("**Decision Notes**")
        for note in decision_summary(row):
            st.write(f"- {note}")
    with right:
        st.markdown("**Raw Basis**")
        st.write(
            {
                "IV 30D": pct(row.iv_30d_current),
                "IV rank": num(row.iv_rank),
                "RV 30D": pct(row.rv_30d),
                "Above 200DMA": row.above_200dma,
                "3M drawdown": pct(row.drawdown_3m),
                "5Y max drawdown": pct(row.max_drawdown_5y),
                "Stock ADV": money(row.stock_adv_usd),
            }
        )


st.title("FCN Wizard")
ib_config = IbConfig()

with st.sidebar:
    st.header("Product Terms", help="Assumptions for the FCN payoff and fair coupon proxy.")
    tenor_months = st.slider("Tenor", 3, 24, 12, 1, help="Longer = more time to hit KI.")
    ki_barrier = st.slider("KI barrier", 0.40, 0.80, 0.50, 0.05, help="Lower barrier = safer note.")
    expected_loss = st.slider("Loss given KI", 0.35, 0.80, 0.53, 0.01, help="Bigger loss requires bigger coupon.")
    expected_alive = st.slider("Expected alive months", 1.0, 12.0, 4.0, 0.5, help="Shorter life = fewer coupons.")
    discount_rate = st.slider("Discount rate", 0.00, 0.10, 0.045, 0.005, help="Used to discount expected loss.")

    st.header("Score Factors", help="Choose which raw signals count in the candidate score.")
    iv_rank_factor = st.checkbox("IV rank", True, help="High IV can support coupon.")
    vrp_factor = st.checkbox("Vol risk premium", True, help="IV above realized vol is better.")
    skew_factor = st.checkbox("Put skew", True, help="Extreme skew signals tail risk.")
    trend_factor = st.checkbox("Trend", True, help="Above 200DMA is healthier.")
    drawdown_factor = st.checkbox("Recent drawdown", True, help="Recent stress raises KI risk.")
    liquidity_factor = st.checkbox("Liquidity", True, help="More volume is cleaner.")
    crash_factor = st.checkbox("Crash history", True, help="Past 50% crash matters.")
    toggles = ScoreToggles(
        iv_rank=iv_rank_factor,
        vrp=vrp_factor,
        skew=skew_factor,
        trend=trend_factor,
        drawdown=drawdown_factor,
        liquidity=liquidity_factor,
        crash_history=crash_factor,
    )

    st.header("Pair Model", help="Assumptions for worst-of pair correlation and KI simulation.")
    corr_lookback = st.slider("Correlation lookback days", 126, 756, 504, 21, help="Longer = smoother correlation.")
    corr_window = st.slider("Rolling correlation window", 30, 120, 60, 5, help="Shorter = reacts faster.")
    n_sims = st.select_slider(
        "MC paths",
        options=[2_000, 5_000, 10_000, 20_000, 50_000],
        value=10_000,
        help="More paths = smoother, slower.",
    )


default_symbols = ""
universe_path = Path("config/default_universe.txt")
if universe_path.exists():
    default_symbols = ", ".join(read_universe_file(universe_path)[:8])

query = st.text_area("Ticker Query", value=default_symbols, height=80, help="Enter one or more tickers separated by commas.")
run = st.button("Analyze", type="primary", help="Fetch IBKR data and build the decision table.")

product = ProductConfig(
    tenor_days=int(round(tenor_months / 12 * 252)),
    ki_barrier=ki_barrier,
    expected_loss_given_ki=expected_loss,
    expected_alive_months=expected_alive,
    discount_rate=discount_rate,
)

if run:
    symbols = parse_tickers(query)
    if not symbols:
        st.warning("Enter at least one ticker.")
        st.stop()

    rows = []
    breakdowns = {}
    progress = st.progress(0, text="Connecting to IBKR")
    try:
        ib = connect_ib(ib_config.host, ib_config.port, ib_config.client_id, ib_config.timeout)
    except Exception as exc:
        detail = str(exc) or exc.__class__.__name__
        st.error(f"IBKR connection failed: {detail}")
        st.stop()

    try:
        for idx, symbol in enumerate(symbols, start=1):
            progress.progress((idx - 1) / len(symbols), text=f"Analyzing {symbol}")
            metrics, breakdown = analyze_ticker(
                ib,
                symbol,
                product,
                toggles=toggles,
                fetch_skew_enabled=False,
                raw_dir=Path("outputs/raw"),
            )
            rows.append(metrics)
            breakdowns[symbol] = breakdown
        progress.progress(1.0, text="Analysis complete")
    finally:
        ib.disconnect()

    df = metrics_frame(rows)
    st.session_state["single_rows"] = rows
    st.session_state["single_df"] = df
    st.session_state["breakdowns"] = breakdowns
    st.session_state["product"] = product
    st.session_state["ib_config"] = ib_config

if "single_df" in st.session_state:
    rows = st.session_state["single_rows"]
    df = st.session_state["single_df"]
    breakdowns = st.session_state["breakdowns"]

    st.divider()
    st.header("Candidate Ranking")

    display_cols = [
        "symbol", "score", "spot", "iv_30d_current", "iv_rank", "rv_30d", "vrp",
        "p_ki", "fair_coupon_proxy", "above_200dma", "drawdown_3m",
        "max_drawdown_5y", "crash_5y", "stock_adv_usd",
    ]
    ranking_df = df[display_cols].sort_values("score", ascending=False)
    st.dataframe(candidate_display_frame(ranking_df), use_container_width=True, hide_index=True)
    st.download_button(
        "Download candidate table",
        df.to_csv(index=False),
        file_name="fcn_candidates_query.csv",
        mime="text/csv",
    )

    st.header("Single-Name Decision Support")
    for row in sorted(rows, key=lambda item: item.score, reverse=True):
        with st.expander(f"{row.symbol}: score {row.score:.2f}", expanded=row == sorted(rows, key=lambda item: item.score, reverse=True)[0]):
            display_single_card(row)
            breakdown_df = pd.DataFrame(breakdowns.get(row.symbol, []))
            if not breakdown_df.empty:
                st.markdown("**Score Breakdown**")
                st.dataframe(breakdown_df, use_container_width=True)

    if len(rows) >= 2:
        st.divider()
        st.header("Worst-of Pair Analysis")
        symbols = [row.symbol for row in rows]
        c1, c2 = st.columns(2)
        with c1:
            leg_a = st.selectbox("Leg A", symbols, index=0)
        with c2:
            leg_b = st.selectbox("Leg B", symbols, index=1)

        if st.button("Analyze Pair"):
            if leg_a == leg_b:
                st.warning("Choose two different tickers.")
                st.stop()
            row_map = {row.symbol: row for row in rows}
            ib_config = st.session_state["ib_config"]
            product = st.session_state["product"]
            try:
                ib = connect_ib(ib_config.host, ib_config.port, ib_config.client_id + 1, ib_config.timeout)
                pair_row, pair_breakdown = analyze_pair(
                    ib,
                    row_map[leg_a],
                    row_map[leg_b],
                    product,
                    lookback_days=corr_lookback,
                    window=corr_window,
                    n_sims=n_sims,
                )
            except Exception as exc:
                st.error(f"Pair analysis failed: {exc}")
                st.stop()
            finally:
                try:
                    ib.disconnect()
                except Exception:
                    pass

            st.subheader(f"{leg_a} / {leg_b}")
            p1, p2, p3, p4, p5 = st.columns(5)
            p1.metric("Pair score", f"{pair_row['pair_score']:.2f}")
            p2.metric("60D corr", f"{pair_row['corr_60d']:.2f}")
            p3.metric("Corr stability", f"{pair_row['corr_stability']:.2f}")
            p4.metric("Either KI", pct(pair_row["p_ki_either"]))
            p5.metric("Fair coupon proxy", pct(pair_row["pair_fair_coupon_proxy"]))

            if pair_row["corr_60d"] < 0.5:
                st.warning("Correlation is low for a worst-of note; dispersion risk is the main concern.")
            if pair_row["p_ki_either"] > 0.30:
                st.warning("Joint KI probability is not low; quoted coupon should be large enough to pay for this risk.")
            if pair_row["corr_stability"] < 0.10 and pair_row["p_ki_either"] < 0.20:
                st.success("Pair risk looks controlled under the current assumptions.")

            st.markdown("**Pair Raw Metrics**")
            st.dataframe(pd.DataFrame([pair_row]), use_container_width=True)
            st.markdown("**Pair Score Breakdown**")
            st.dataframe(pd.DataFrame(pair_breakdown), use_container_width=True)
