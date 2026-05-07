from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .ib_compat import ensure_event_loop

ensure_event_loop()

from ib_insync import IB, Option, Stock, util


def ib_duration(days: int) -> str:
    """IBKR requires year units for historical requests longer than 365 days."""
    return f"{round(days / 365)} Y" if days > 365 else f"{days} D"


def connect_ib(host: str, port: int, client_id: int, timeout: int = 15) -> IB:
    ensure_event_loop()
    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=timeout)
    return ib


def fetch_history(ib: IB, symbol: str, days: int, what: str = "TRADES") -> Optional[pd.DataFrame]:
    contract = Stock(symbol.upper(), "SMART", "USD")
    if not ib.qualifyContracts(contract):
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
    return df.set_index("date").sort_index()


def fetch_returns(ib: IB, symbol: str, days: int) -> Optional[pd.Series]:
    df = fetch_history(ib, symbol, days, "TRADES")
    if df is None or df.empty:
        return None
    returns = np.log(df["close"] / df["close"].shift(1)).dropna()
    returns.name = symbol.upper()
    return returns


def fetch_skew(ib: IB, symbol: str, target_dte: int = 45, target_delta: float = 0.25):
    symbol = symbol.upper()
    stock = Stock(symbol, "SMART", "USD")
    if not ib.qualifyContracts(stock):
        return None, None, None

    md = ib.reqMktData(stock, "", snapshot=False)
    ib.sleep(2)
    spot = md.marketPrice() or md.last or md.close
    ib.cancelMktData(stock)
    if not spot or np.isnan(spot):
        return None, None, None

    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    if not chains:
        return spot, None, None
    chain = next((c for c in chains if c.exchange == "SMART"), chains[0])

    target = datetime.today().date() + timedelta(days=target_dte)
    expirations = sorted(chain.expirations)
    if not expirations:
        return spot, None, None
    expiry = min(expirations, key=lambda e: abs((datetime.strptime(e, "%Y%m%d").date() - target).days))

    strikes = sorted(chain.strikes)
    atm_strike = min(strikes, key=lambda k: abs(k - spot))
    atm_put = Option(symbol, expiry, atm_strike, "P", "SMART")
    if not ib.qualifyContracts(atm_put):
        return spot, None, None
    atm_md = ib.reqMktData(atm_put, "", snapshot=False)
    ib.sleep(2)
    atm_iv = atm_md.modelGreeks.impliedVol if atm_md.modelGreeks else None
    ib.cancelMktData(atm_put)

    otm_strikes = [k for k in strikes if k < spot * 0.98][-12:]
    best_iv, best_diff = None, float("inf")
    for strike in otm_strikes:
        put = Option(symbol, expiry, strike, "P", "SMART")
        if not ib.qualifyContracts(put):
            continue
        md = ib.reqMktData(put, "", snapshot=False)
        ib.sleep(1.2)
        if md.modelGreeks and md.modelGreeks.delta is not None:
            diff = abs(abs(md.modelGreeks.delta) - target_delta)
            if diff < best_diff:
                best_diff = diff
                best_iv = md.modelGreeks.impliedVol
        ib.cancelMktData(put)
    return spot, atm_iv, best_iv


def save_raw_frame(df: Optional[pd.DataFrame], path: Path) -> None:
    if df is None or df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(path, index=False)
