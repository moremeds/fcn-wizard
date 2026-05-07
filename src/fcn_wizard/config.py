from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_UNIVERSE = [
    "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "META", "AMZN",
    "AMD", "AVGO", "NFLX", "ORCL", "CRM", "ADBE",
    "MSTR", "COIN", "PLTR", "SHOP", "UBER", "SNOW", "CRWD",
    "JPM", "BAC", "WMT", "JNJ", "XOM", "CVX",
    "SPY", "QQQ", "IWM",
]


@dataclass(frozen=True)
class IbConfig:
    host: str = "127.0.0.1"
    port: int = 4001
    client_id: int = 99
    timeout: int = 15


@dataclass(frozen=True)
class ProductConfig:
    tenor_days: int = 252
    ki_barrier: float = 0.50
    expected_loss_given_ki: float = 0.53
    expected_alive_months: float = 4.0
    discount_rate: float = 0.045


def read_universe_file(path: str | Path) -> list[str]:
    symbols: list[str] = []
    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        symbols.extend(part.strip().upper() for part in line.split(",") if part.strip())
    return symbols
