from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from ..config import ProductConfig


@dataclass(frozen=True)
class BacktestResult:
    as_of_date: str
    rows: pd.DataFrame


def forward_ki_outcome(forward_prices: pd.Series, initial_spot: float, barrier: float) -> bool:
    if forward_prices.empty:
        return False
    return bool((forward_prices <= initial_spot * barrier).any())


def score_ki_rank_correlation(result: BacktestResult) -> float:
    frame = result.rows[["score", "ki_outcome"]].dropna().copy()
    if len(frame) < 2:
        return float("nan")
    frame["ki_numeric"] = frame["ki_outcome"].astype(int)
    return float(frame["score"].corr(frame["ki_numeric"], method="spearman"))


def replay_as_of_date(
    as_of_date: str,
    universe: list[str],
    product: ProductConfig,
    screen_at_date: Callable[[str, ProductConfig], dict],
    fetch_forward_prices: Callable[[str, str, int], pd.Series],
) -> BacktestResult:
    rows: list[dict] = []
    for symbol in universe:
        metrics = screen_at_date(symbol, product)
        forward = fetch_forward_prices(symbol, as_of_date, product.tenor_days)
        initial_spot = float(metrics["spot"])
        rows.append(
            {
                **metrics,
                "as_of_date": as_of_date,
                "ki_outcome": forward_ki_outcome(forward, initial_spot, product.ki_barrier),
            }
        )
    return BacktestResult(as_of_date=as_of_date, rows=pd.DataFrame(rows))
