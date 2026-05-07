from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from ..config import ProductConfig
from ..storage.run_storage import load_latest_table, save_run_table


@dataclass(frozen=True)
class BootstrapResult:
    frame: pd.DataFrame
    source: str
    run_id: Optional[str]


def bootstrap_candidates(
    output_dir: Path | str,
    universe: list[str],
    run_config: dict,
    product: ProductConfig,
    refresh: Callable[[list[str], ProductConfig], pd.DataFrame],
    force_refresh: bool = False,
) -> BootstrapResult:
    if not force_refresh:
        loaded = load_latest_table(output_dir=output_dir, kind="candidates")
        if loaded is not None:
            frame, record = loaded
            frame = frame.copy()
            frame["run_source"] = "history"
            return BootstrapResult(frame=frame, source="history", run_id=record.run_id)

    frame = refresh(universe, product).copy()
    frame["run_source"] = "fresh"
    record = save_run_table(
        frame,
        output_dir=output_dir,
        kind="candidates",
        metadata={**run_config, "bootstrap_source": "default_universe"},
    )
    return BootstrapResult(frame=frame, source="fresh", run_id=record.run_id)
