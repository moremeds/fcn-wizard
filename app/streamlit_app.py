from __future__ import annotations
from dataclasses import fields
from pathlib import Path

import pandas as pd
import streamlit as st

from fcn_wizard.analysis import TickerMetrics, analyze_basket, analyze_pair, analyze_ticker, decision_summary, metrics_frame
from fcn_wizard.config import IbConfig, ProductConfig, read_universe_file
from fcn_wizard.market_data import connect_ib, fetch_returns
from fcn_wizard.quotes import compare_pb_quotes
from fcn_wizard.run_storage import load_latest_table, save_run_table
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
        "quoted_coupon": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "dealer_margin": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "tenor_iv": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "surface_ki_vol": lambda value: "" if pd.isna(value) else f"{value:.1%}",
        "vol_used_for_ki": lambda value: "" if pd.isna(value) else f"{value:.1%}",
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
            "quoted_coupon": "Quoted Coupon",
            "dealer_margin": "Dealer Margin",
            "tenor_iv": "Tenor IV",
            "surface_ki_vol": "Surface KI Vol",
            "vol_used_for_ki": "KI Vol",
            "above_200dma": "Above 200DMA",
            "drawdown_3m": "3M DD",
            "max_drawdown_5y": "5Y Max DD",
            "crash_5y": "50% Crash",
            "stock_adv_usd": "Stock ADV",
        }
    )


def metrics_rows_from_frame(df: pd.DataFrame) -> list[TickerMetrics]:
    metric_fields = {field.name for field in fields(TickerMetrics)}
    rows: list[TickerMetrics] = []
    for record in df.to_dict("records"):
        clean = {
            key: (None if pd.isna(value) else value)
            for key, value in record.items()
            if key in metric_fields
        }
        rows.append(TickerMetrics(**clean))
    return rows


def build_fair_values_from_session_state() -> pd.DataFrame:
    rows: list[dict] = []
    candidate_df = st.session_state.get("single_df")
    if isinstance(candidate_df, pd.DataFrame) and "symbol" in candidate_df.columns:
        fair_col = "fair_coupon_proxy"
        if fair_col in candidate_df.columns:
            for record in candidate_df[["symbol", fair_col]].dropna(subset=[fair_col]).to_dict("records"):
                rows.append({"symbols": record["symbol"], "fair_coupon_proxy": record[fair_col]})
    basket_df = st.session_state.get("last_basket_df")
    if isinstance(basket_df, pd.DataFrame):
        for record in basket_df.to_dict("records"):
            if "symbols" in record and pd.notna(record.get("fair_coupon_proxy")):
                rows.append({"symbols": record["symbols"], "fair_coupon_proxy": record["fair_coupon_proxy"]})
            elif "a" in record and "b" in record and pd.notna(record.get("pair_fair_coupon_proxy")):
                rows.append(
                    {
                        "symbols": f"{record['a']}/{record['b']}",
                        "fair_coupon_proxy": record["pair_fair_coupon_proxy"],
                    }
                )
    return pd.DataFrame(rows)


def display_single_card(row):
    st.subheader(row.symbol)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Spot", num(row.spot))
    c2.metric("Score", f"{row.score:.2f}")
    c3.metric("KI probability", pct(row.p_ki))
    c4.metric("Fair coupon proxy", pct(row.fair_coupon_proxy))
    c5.metric("Dealer margin", pct(row.dealer_margin))
    c6.metric("VRP", pct(row.vrp))

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
                "Tenor IV": pct(row.tenor_iv),
                "Surface KI vol": pct(row.surface_ki_vol),
                "KI vol": pct(row.vol_used_for_ki),
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
    quoted_coupon = st.number_input(
        "Quoted coupon",
        min_value=0.0,
        max_value=2.0,
        value=0.0,
        step=0.01,
        help="Annualized PB quote as decimal coupon; 0 disables margin comparison.",
    )
    quoted_coupon_value = quoted_coupon if quoted_coupon > 0 else None
    fetch_tenor_iv = st.checkbox(
        "Fetch tenor IV",
        False,
        help="Uses nearest-expiry ATM option IV for KI probability; requires option market data and is slower.",
    )
    fetch_surface_iv = st.checkbox(
        "Fit downside IV surface",
        False,
        help="Fits a simple SVI surface and uses downside wing vol for KI; slow and requires option market data.",
    )

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

product = ProductConfig(
    tenor_days=int(round(tenor_months / 12 * 252)),
    ki_barrier=ki_barrier,
    expected_loss_given_ki=expected_loss,
    expected_alive_months=expected_alive,
    discount_rate=discount_rate,
)

query = st.text_area("Ticker Query", value=default_symbols, height=80, help="Enter one or more tickers separated by commas.")
run_col, load_col = st.columns([1, 1])
with run_col:
    run = st.button("Analyze", type="primary", help="Fetch IBKR data and build the decision table.")
with load_col:
    load_latest = st.button("Load latest saved run", help="Open the most recent saved candidate table without fetching IBKR data.")

if "bootstrapped" not in st.session_state:
    st.session_state["bootstrapped"] = True
    loaded = load_latest_table(output_dir=Path("outputs"), kind="candidates")
    if loaded is not None:
        df, record = loaded
        rows = metrics_rows_from_frame(df)
        st.session_state["single_rows"] = rows
        st.session_state["single_df"] = df
        st.session_state["breakdowns"] = {}
        st.session_state["product"] = product
        st.session_state["ib_config"] = ib_config
        st.session_state["loaded_run"] = record
        st.session_state["run_source_label"] = "Loaded from previous run"
    elif universe_path.exists():
        symbols = read_universe_file(universe_path)
        if symbols:
            with st.spinner("No previous run found. Running configured default universe."):
                ib = None
                try:
                    ib = connect_ib(ib_config.host, ib_config.port, ib_config.client_id, ib_config.timeout)
                    rows = []
                    breakdowns = {}
                    for symbol in symbols:
                        metrics, breakdown = analyze_ticker(
                            ib,
                            symbol,
                            product,
                            toggles=toggles,
                            fetch_skew_enabled=False,
                            fetch_tenor_iv_enabled=fetch_tenor_iv,
                            fetch_surface_iv_enabled=fetch_surface_iv,
                            raw_dir=Path("outputs/raw"),
                            quoted_coupon=quoted_coupon_value,
                        )
                        rows.append(metrics)
                        breakdowns[symbol] = breakdown
                    df = metrics_frame(rows)
                    record = save_run_table(
                        df,
                        output_dir=Path("outputs"),
                        kind="candidates",
                        metadata={
                            "source": "streamlit_bootstrap",
                            "symbols": symbols,
                            "tenor_days": product.tenor_days,
                            "ki_barrier": product.ki_barrier,
                            "expected_loss_given_ki": product.expected_loss_given_ki,
                            "expected_alive_months": product.expected_alive_months,
                            "discount_rate": product.discount_rate,
                            "quoted_coupon": quoted_coupon_value,
                            "fetch_tenor_iv": fetch_tenor_iv,
                            "fetch_surface_iv": fetch_surface_iv,
                        },
                    )
                    st.session_state["single_rows"] = rows
                    st.session_state["single_df"] = df
                    st.session_state["breakdowns"] = breakdowns
                    st.session_state["product"] = product
                    st.session_state["ib_config"] = ib_config
                    st.session_state["loaded_run"] = record
                    st.session_state["run_source_label"] = "No previous run found; ran configured default universe"
                except Exception as exc:
                    detail = str(exc) or exc.__class__.__name__
                    st.session_state["run_source_label"] = f"No previous run found; default universe run failed: {detail}"
                    st.warning(st.session_state["run_source_label"])
                finally:
                    if ib is not None:
                        ib.disconnect()

if load_latest:
    loaded = load_latest_table(output_dir=Path("outputs"), kind="candidates")
    if loaded is None:
        st.warning("No saved candidate run found.")
    else:
        df, record = loaded
        rows = metrics_rows_from_frame(df)
        st.session_state["single_rows"] = rows
        st.session_state["single_df"] = df
        st.session_state["breakdowns"] = {}
        st.session_state["product"] = product
        st.session_state["ib_config"] = ib_config
        st.session_state["loaded_run"] = record
        st.session_state["run_source_label"] = "Loaded from previous run"
        st.success(f"Loaded saved run {record.run_id} with {record.row_count} rows.")

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
                fetch_tenor_iv_enabled=fetch_tenor_iv,
                fetch_surface_iv_enabled=fetch_surface_iv,
                raw_dir=Path("outputs/raw"),
                quoted_coupon=quoted_coupon_value,
            )
            rows.append(metrics)
            breakdowns[symbol] = breakdown
        progress.progress(1.0, text="Analysis complete")
    finally:
        ib.disconnect()

    df = metrics_frame(rows)
    record = save_run_table(
        df,
        output_dir=Path("outputs"),
        kind="candidates",
        metadata={
            "source": "streamlit",
            "symbols": symbols,
            "tenor_days": product.tenor_days,
            "ki_barrier": product.ki_barrier,
            "expected_loss_given_ki": product.expected_loss_given_ki,
            "expected_alive_months": product.expected_alive_months,
            "discount_rate": product.discount_rate,
            "quoted_coupon": quoted_coupon_value,
            "fetch_tenor_iv": fetch_tenor_iv,
            "fetch_surface_iv": fetch_surface_iv,
        },
    )
    st.session_state["single_rows"] = rows
    st.session_state["single_df"] = df
    st.session_state["breakdowns"] = breakdowns
    st.session_state["product"] = product
    st.session_state["ib_config"] = ib_config
    st.session_state["loaded_run"] = record
    st.session_state["run_source_label"] = "Fresh IBKR analysis"

if "single_df" in st.session_state:
    rows = st.session_state["single_rows"]
    df = st.session_state["single_df"]
    breakdowns = st.session_state["breakdowns"]
    loaded_run = st.session_state.get("loaded_run")

    st.divider()
    st.header("Candidate Ranking")
    if loaded_run:
        st.caption(f"Run: {loaded_run.run_id} ({loaded_run.row_count} rows)")
    if st.session_state.get("run_source_label"):
        st.caption(st.session_state["run_source_label"])

    display_cols = [
        "symbol", "score", "spot", "iv_30d_current", "iv_rank", "rv_30d", "vrp",
        "p_ki", "fair_coupon_proxy", "quoted_coupon", "dealer_margin", "tenor_iv", "surface_ki_vol", "vol_used_for_ki", "above_200dma", "drawdown_3m",
        "max_drawdown_5y", "crash_5y", "stock_adv_usd",
    ]
    display_cols = [column for column in display_cols if column in df.columns]
    ranking_df = df[display_cols].sort_values("score", ascending=False)
    st.dataframe(candidate_display_frame(ranking_df), use_container_width=True, hide_index=True)
    st.download_button(
        "Download candidate table",
        df.to_csv(index=False),
        file_name="fcn_candidates_query.csv",
        mime="text/csv",
    )

    st.header("PB Quote Comparison")
    quote_file = st.file_uploader("PB quote CSV", type=["csv"])
    if quote_file is not None:
        quotes = pd.read_csv(quote_file)
        fair_values = build_fair_values_from_session_state()
        if fair_values.empty:
            st.warning("No fair coupon values are loaded yet.")
        else:
            quote_comparison = compare_pb_quotes(quotes, fair_values)
            st.dataframe(quote_comparison, use_container_width=True, hide_index=True)

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
        st.header("Worst-of Basket Analysis")
        symbols = [row.symbol for row in rows]
        basket_size = st.radio("Basket size", [2, 3], horizontal=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            leg_a = st.selectbox("Leg A", symbols, index=0)
        with c2:
            leg_b = st.selectbox("Leg B", symbols, index=1)
        with c3:
            leg_c = None
            if basket_size == 3:
                leg_c = st.selectbox("Leg C", symbols, index=2 if len(symbols) > 2 else 0)

        if st.button("Analyze Basket"):
            selected = [leg_a, leg_b] if basket_size == 2 else [leg_a, leg_b, leg_c]
            if len(set(selected)) != len(selected):
                st.warning("Choose different tickers for each leg.")
                st.stop()
            row_map = {row.symbol: row for row in rows}
            ib_config = st.session_state["ib_config"]
            product = st.session_state["product"]
            ib = None
            try:
                ib = connect_ib(ib_config.host, ib_config.port, ib_config.client_id + 1, ib_config.timeout)
                if basket_size == 2:
                    pair_row, pair_breakdown = analyze_pair(
                        ib,
                        row_map[leg_a],
                        row_map[leg_b],
                        product,
                        lookback_days=corr_lookback,
                        window=corr_window,
                        n_sims=n_sims,
                    )
                    pair_record = save_run_table(
                        pd.DataFrame([pair_row]),
                        output_dir=Path("outputs"),
                        kind="pairs",
                        metadata={
                            "source": "streamlit",
                            "leg_a": leg_a,
                            "leg_b": leg_b,
                            "basket_size": basket_size,
                            "correlation_lookback_days": corr_lookback,
                            "correlation_window": corr_window,
                            "n_sims": n_sims,
                        },
                        run_id=getattr(st.session_state.get("loaded_run"), "run_id", None),
                    )
                else:
                    returns = {}
                    for symbol in selected:
                        series = fetch_returns(ib, symbol, corr_lookback)
                        if series is None:
                            raise ValueError(f"Missing return history for {symbol}.")
                        returns[symbol] = series
                    pair_row, pair_breakdown = analyze_basket(
                        [row_map[symbol] for symbol in selected],
                        returns,
                        product,
                        window=corr_window,
                        n_sims=n_sims,
                    )
                    pair_record = save_run_table(
                        pd.DataFrame([pair_row]),
                        output_dir=Path("outputs"),
                        kind="baskets",
                        metadata={
                            "source": "streamlit",
                            "symbols": selected,
                            "basket_size": basket_size,
                            "correlation_lookback_days": corr_lookback,
                            "correlation_window": corr_window,
                            "n_sims": n_sims,
                        },
                        run_id=getattr(st.session_state.get("loaded_run"), "run_id", None),
                    )
            except Exception as exc:
                st.error(f"Basket analysis failed: {exc}")
                st.stop()
            finally:
                try:
                    if ib is not None:
                        ib.disconnect()
                except Exception:
                    pass

            title = " / ".join(selected)
            st.subheader(title)
            st.caption(f"Saved basket run: {pair_record.run_id}")
            p1, p2, p3, p4, p5 = st.columns(5)
            score_value = pair_row.get("pair_score", pair_row.get("basket_score"))
            corr_value = pair_row.get("corr_60d", pair_row.get("corr_avg"))
            fair_value = pair_row.get("pair_fair_coupon_proxy", pair_row.get("fair_coupon_proxy"))
            p1.metric("Basket score", f"{score_value:.2f}")
            p2.metric("Correlation", f"{corr_value:.2f}")
            p3.metric("Corr stability", f"{pair_row['corr_stability']:.2f}")
            p4.metric("Either KI", pct(pair_row["p_ki_either"]))
            p5.metric("Fair coupon proxy", pct(fair_value))

            if corr_value < 0.5:
                st.warning("Correlation is low for a worst-of note; dispersion risk is the main concern.")
            if pair_row["p_ki_either"] > 0.30:
                st.warning("Joint KI probability is not low; quoted coupon should be large enough to pay for this risk.")
            if pair_row["corr_stability"] < 0.10 and pair_row["p_ki_either"] < 0.20:
                st.success("Pair risk looks controlled under the current assumptions.")

            st.markdown("**Basket Raw Metrics**")
            basket_df = pd.DataFrame([pair_row])
            st.session_state["last_basket_df"] = basket_df
            st.dataframe(basket_df, use_container_width=True)
            st.markdown("**Basket Score Breakdown**")
            st.dataframe(pd.DataFrame(pair_breakdown), use_container_width=True)
