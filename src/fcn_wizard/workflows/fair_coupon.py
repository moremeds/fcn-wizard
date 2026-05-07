from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..metrics import fair_coupon_proxy
from ..quotes import normalize_symbols


def pair_symbol(row: pd.Series) -> str:
    if "symbols" in row and pd.notna(row["symbols"]):
        return normalize_symbols(str(row["symbols"]))
    return normalize_symbols(f"{row['a']}/{row['b']}")


def ensure_pair_fair_coupon(
    pairs: pd.DataFrame,
    expected_loss_given_ki: float = 0.50,
    expected_alive_months: float = 4.0,
    discount_rate: float = 0.045,
    tenor_years: float = 1.0,
) -> pd.DataFrame:
    result = pairs.copy()
    result["symbols"] = result.apply(pair_symbol, axis=1)
    if "pair_fair_coupon_proxy" not in result.columns and "fair_coupon_proxy" in result.columns:
        result["pair_fair_coupon_proxy"] = result["fair_coupon_proxy"]
    if "pair_fair_coupon_proxy" not in result.columns:
        result["pair_fair_coupon_proxy"] = result["p_ki_either"].map(
            lambda p_ki: fair_coupon_proxy(
                p_ki,
                expected_loss_given_ki,
                expected_alive_months,
                discount_rate,
                tenor_years,
            )
        )
    return result


def quote_verdict(dealer_margin: float) -> str:
    if dealer_margin >= 0.10:
        return "expensive_vs_model"
    if dealer_margin >= -0.02:
        return "fair"
    return "cheap_vs_model"


def rank_quotes_against_fair_coupon(pairs: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    fair = ensure_pair_fair_coupon(pairs)
    quote_rows = quotes.copy()
    quote_rows["symbols"] = quote_rows["symbols"].map(normalize_symbols)
    merged = quote_rows.merge(
        fair[["symbols", "pair_fair_coupon_proxy"]],
        on="symbols",
        how="left",
    )
    merged = merged.rename(columns={"pair_fair_coupon_proxy": "fair_coupon"})
    merged["dealer_margin"] = merged["fair_coupon"] - merged["quoted_coupon"]
    merged["verdict"] = merged["dealer_margin"].map(quote_verdict)
    return merged.sort_values(["symbols", "dealer_margin"], ascending=[True, False]).reset_index(drop=True)


def load_pairs(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path)


def load_quotes(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path)
