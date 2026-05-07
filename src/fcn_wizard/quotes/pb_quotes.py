from __future__ import annotations

import pandas as pd


def normalize_symbols(value: str) -> str:
    return "/".join(
        sorted(part.strip().upper() for part in value.replace(",", "/").split("/") if part.strip())
    )


def compare_pb_quotes(quotes: pd.DataFrame, fair_values: pd.DataFrame) -> pd.DataFrame:
    left = quotes.copy()
    right = fair_values.copy()
    left["symbols"] = left["symbols"].map(normalize_symbols)
    right["symbols"] = right["symbols"].map(normalize_symbols)
    merged = left.merge(right[["symbols", "fair_coupon_proxy"]], on="symbols", how="left")
    merged["dealer_margin"] = merged["fair_coupon_proxy"] - merged["quoted_coupon"]
    return merged.sort_values(["symbols", "dealer_margin"], ascending=[True, False]).reset_index(drop=True)
