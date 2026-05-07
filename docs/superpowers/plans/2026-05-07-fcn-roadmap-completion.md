# FCN Roadmap Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining partial/not-done FCN Wizard items: automatic latest-run bootstrap with default-universe fallback, quoted-coupon/dealer-margin support, standalone fair-coupon quote comparison, shared script/package logic, 3-name baskets, tenor IV support, DIP valuation, autocall-aware duration, point-in-time backtesting, and PB quote comparison.

**Architecture:** Keep the standalone scripts runnable, but move reusable math, scoring, storage, data access, and orchestration into clearly named subpackages under `src/fcn_wizard`. Existing top-level package modules remain as compatibility facades so current imports keep working while implementation logic moves into `analytics/`, `storage/`, `data/`, `workflows/`, and `quotes/`. Build features in layers: package organization first, storage/bootstrap second, quote and scoring fields third, generic basket analytics fourth, then model-quality upgrades and quote/backtest workflows. Each layer gets focused unit tests before production code.

**Tech Stack:** Python 3.11+, `pandas`, `numpy`, `scipy`, `ib_insync`, `streamlit`, `unittest`, existing Playwright dashboard smoke test. Add `duckdb` only if implementing prospective production snapshots after point-in-time replay.

**Test convention:** All Python tests in this plan are run with `unittest`. When a later task says to extend an existing test file, put the shown assertions inside a `unittest.TestCase` method if the snippet is not already wrapped in a class. Do not leave module-level `def test_*` functions; `unittest discover` will not run them.

---

## File Map

- Create: `src/fcn_wizard/analytics/`  
  Core calculations and ranking: `metrics.py`, `scoring.py`, `analysis.py`.
- Create: `src/fcn_wizard/storage/`  
  Persistence: `run_storage.py` now and optional `snapshots.py` in Phase 7B.
- Create: `src/fcn_wizard/data/`  
  IBKR market data adapters: `market_data.py`.
- Create: `src/fcn_wizard/workflows/`  
  User-facing workflow orchestration: `bootstrap.py`, `fair_coupon.py`, `backtest.py`.
- Create: `src/fcn_wizard/quotes/`  
  PB quote import and comparison: `pb_quotes.py`.
- Modify: `src/fcn_wizard/metrics.py`, `src/fcn_wizard/scoring.py`, `src/fcn_wizard/analysis.py`, `src/fcn_wizard/market_data.py`, `src/fcn_wizard/run_storage.py`  
  Keep these as compatibility facades that re-export the organized subpackage implementations.
- Modify: `src/fcn_wizard/config.py`  
  Add quote and bootstrap config fields. Keep config at package root because it is small and used everywhere.
- Modify: `fcn_screener.py`  
  Stop duplicating metric/scoring rules; use package helpers and add `--auto-load-latest`, `--quoted-coupon`, `--force-refresh`.
- Modify: `fcn_pair_screener.py`  
  Use package basket engine; support `--basket-size 2|3`, history bootstrap, and pair/triple run storage.
- Create: `fair_coupon.py`  
  Standalone quote-comparison script that reads pair results, calculates fair coupon/dealer margin, and ranks PB quotes.
- Modify: `app/streamlit_app.py`  
  Auto-load latest run on startup, mark history-loaded data, run default universe if no history exists, add quote/dealer-margin UI, add 3-name basket UI.
- Modify: `README.md` and `fcn_framework_reference.md`  
  Document the implemented workflows and move finished roadmap items out of future-work language.
- Add/Modify tests:
  - `tests/test_package_facades.py`
  - `tests/test_bootstrap.py`
  - `tests/test_run_storage.py`
  - `tests/test_scoring.py`
  - `tests/test_metrics.py`
  - `tests/test_basket_analysis.py`
  - `tests/test_quotes.py`
  - Existing `tests/streamlit.spec.ts`

---

## Phase 0: Package Organization Before Feature Growth

### Task 0: Move Logic into Clear Subdirectories with Backward-Compatible Facades

**Files:**
- Create: `src/fcn_wizard/analytics/__init__.py`
- Create: `src/fcn_wizard/analytics/metrics.py`
- Create: `src/fcn_wizard/analytics/scoring.py`
- Create: `src/fcn_wizard/analytics/analysis.py`
- Create: `src/fcn_wizard/storage/__init__.py`
- Create: `src/fcn_wizard/storage/run_storage.py`
- Create: `src/fcn_wizard/data/__init__.py`
- Create: `src/fcn_wizard/data/market_data.py`
- Modify: `src/fcn_wizard/metrics.py`
- Modify: `src/fcn_wizard/scoring.py`
- Modify: `src/fcn_wizard/analysis.py`
- Modify: `src/fcn_wizard/run_storage.py`
- Modify: `src/fcn_wizard/market_data.py`
- Create: `tests/test_package_facades.py`

- [x] **Step 1: Write facade import tests**

Create `tests/test_package_facades.py`:

```python
from __future__ import annotations

import unittest


class PackageFacadeTest(unittest.TestCase):
    def test_analytics_and_legacy_metrics_import_same_functions(self):
        from fcn_wizard.analytics.metrics import fair_coupon_proxy as organized
        from fcn_wizard.metrics import fair_coupon_proxy as legacy

        self.assertIs(legacy, organized)

    def test_storage_and_legacy_run_storage_import_same_functions(self):
        from fcn_wizard.run_storage import save_run_table as legacy
        from fcn_wizard.storage.run_storage import save_run_table as organized

        self.assertIs(legacy, organized)

    def test_data_and_legacy_market_data_import_same_functions(self):
        from fcn_wizard.data.market_data import ib_duration as organized
        from fcn_wizard.market_data import ib_duration as legacy

        self.assertIs(legacy, organized)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_package_facades
```

Expected: fail because the organized subpackages do not exist.

- [x] **Step 3: Move files without changing behavior**

Move current implementation bodies:

```text
src/fcn_wizard/metrics.py      -> src/fcn_wizard/analytics/metrics.py
src/fcn_wizard/scoring.py      -> src/fcn_wizard/analytics/scoring.py
src/fcn_wizard/analysis.py     -> src/fcn_wizard/analytics/analysis.py
src/fcn_wizard/run_storage.py  -> src/fcn_wizard/storage/run_storage.py
src/fcn_wizard/market_data.py  -> src/fcn_wizard/data/market_data.py
```

Create `__init__.py` files:

```python
"""Analytics helpers for FCN Wizard."""
```

```python
"""Persistence helpers for FCN Wizard."""
```

```python
"""Market data adapters for FCN Wizard."""
```

Replace legacy root files with compatibility facades:

```python
from .analytics.metrics import *  # noqa: F401,F403
```

```python
from .analytics.scoring import *  # noqa: F401,F403
```

```python
from .analytics.analysis import *  # noqa: F401,F403
```

```python
from .storage.run_storage import *  # noqa: F401,F403
```

```python
from .data.market_data import *  # noqa: F401,F403
```

Update imports inside moved files:

```python
from ..config import ProductConfig
from ..data.market_data import fetch_history, fetch_returns, fetch_skew, save_raw_frame
from .metrics import fair_coupon_proxy, joint_ki_prob_mc, pair_correlation, single_name_ki_prob
from .scoring import ScoreToggles, score_pair, score_single
```

- [x] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_package_facades
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Expected: package facade tests and existing tests pass.

- [x] **Step 5: Verify scripts still compile**

Run:

```bash
.venv/bin/python -m py_compile \
  fcn_screener.py \
  fcn_pair_screener.py \
  app/streamlit_app.py \
  src/fcn_wizard/*.py \
  src/fcn_wizard/analytics/*.py \
  src/fcn_wizard/storage/*.py \
  src/fcn_wizard/data/*.py
```

Expected: exits 0.

---

## Phase 1: Automatic Previous-Run Bootstrap

### Task 1: Test Latest-Run Bootstrap

**Files:**
- Create: `tests/test_bootstrap.py`
- Create: `src/fcn_wizard/workflows/__init__.py`
- Create: `src/fcn_wizard/workflows/bootstrap.py`
- Modify: `src/fcn_wizard/bootstrap.py`
- Modify: `app/streamlit_app.py`
- Modify: `fcn_screener.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_bootstrap.py`:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fcn_wizard.workflows.bootstrap import bootstrap_candidates
from fcn_wizard.config import ProductConfig
from fcn_wizard.run_storage import save_run_table


class BootstrapCandidatesTest(unittest.TestCase):
    def test_bootstrap_loads_latest_history_and_marks_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_run_table(
                pd.DataFrame([{"symbol": "NVDA", "score": 7.0}]),
                output_dir=output_dir,
                kind="candidates",
                run_id="20260507_120000",
            )

            result = bootstrap_candidates(
                output_dir=output_dir,
                universe=["AAPL"],
                run_config={},
                product=ProductConfig(),
                refresh=lambda symbols, product: pd.DataFrame([{"symbol": "AAPL"}]),
            )

            self.assertEqual(result.source, "history")
            self.assertEqual(result.run_id, "20260507_120000")
            self.assertEqual(result.frame.to_dict("records"), [{"symbol": "NVDA", "score": 7.0}])

    def test_bootstrap_runs_default_universe_when_history_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            result = bootstrap_candidates(
                output_dir=output_dir,
                universe=["NVDA", "TSLA"],
                run_config={"source": "unit-test"},
                product=ProductConfig(),
                refresh=lambda symbols, product: pd.DataFrame(
                    [{"symbol": symbol, "score": 1.0} for symbol in symbols]
                ),
            )

            self.assertEqual(result.source, "fresh")
            self.assertEqual(result.frame["symbol"].tolist(), ["NVDA", "TSLA"])
            self.assertTrue((output_dir / "run_index.csv").exists())

    def test_bootstrap_force_refresh_ignores_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_run_table(
                pd.DataFrame([{"symbol": "OLD", "score": 7.0}]),
                output_dir=output_dir,
                kind="candidates",
                run_id="20260507_120000",
            )

            result = bootstrap_candidates(
                output_dir=output_dir,
                universe=["NEW"],
                run_config={},
                product=ProductConfig(),
                force_refresh=True,
                refresh=lambda symbols, product: pd.DataFrame([{"symbol": "NEW", "score": 2.0}]),
            )

            self.assertEqual(result.source, "fresh")
            self.assertEqual(result.frame.to_dict("records"), [{"symbol": "NEW", "score": 2.0}])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_bootstrap
```

Expected: fail with `ModuleNotFoundError: No module named 'fcn_wizard.workflows'`.

- [x] **Step 3: Implement minimal bootstrap module**

Create `src/fcn_wizard/workflows/bootstrap.py`:

```python
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
```

Create root compatibility facade `src/fcn_wizard/bootstrap.py`:

```python
from .workflows.bootstrap import *  # noqa: F401,F403
```

- [x] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_bootstrap
```

Expected: 3 tests pass.

- [x] **Step 5: Wire dashboard startup**

Modify `app/streamlit_app.py` so on first page load it first tries history, then automatically runs `config/default_universe.txt` exactly once if no history exists:

```python
if "bootstrapped" not in st.session_state:
    st.session_state["bootstrapped"] = True
    loaded = load_latest_table(output_dir=Path("outputs"), kind="candidates")
    if loaded is not None:
        df, record = loaded
        st.session_state["single_rows"] = metrics_rows_from_frame(df)
        st.session_state["single_df"] = df
        st.session_state["breakdowns"] = {}
        st.session_state["loaded_run"] = record
        st.session_state["run_source_label"] = "Loaded from previous run"
    else:
        symbols = read_universe_file(Path("config/default_universe.txt"))
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
                        raw_dir=Path("outputs/raw"),
                    )
                    rows.append(metrics)
                    breakdowns[symbol] = breakdown
                df = metrics_frame(rows)
                record = save_run_table(
                    df,
                    output_dir=Path("outputs"),
                    kind="candidates",
                    metadata={"source": "streamlit_bootstrap", "symbols": symbols},
                )
                st.session_state["single_rows"] = rows
                st.session_state["single_df"] = df
                st.session_state["breakdowns"] = breakdowns
                st.session_state["loaded_run"] = record
                st.session_state["run_source_label"] = "No previous run found; ran configured default universe"
            except Exception as exc:
                st.session_state["run_source_label"] = f"No previous run found; default universe run failed: {exc}"
                st.warning(st.session_state["run_source_label"])
            finally:
                if ib is not None:
                    ib.disconnect()
```

Add a clearly visible caption near the ranking table:

```python
if st.session_state.get("run_source_label"):
    st.caption(st.session_state["run_source_label"])
```

Use the `bootstrapped` session-state guard so Streamlit reruns do not repeatedly reconnect to IBKR.

- [x] **Step 6: Wire CLI startup**

Modify `fcn_screener.py`:

```python
parser.add_argument("--auto-load-latest", action=argparse.BooleanOptionalAction, default=False)
parser.add_argument("--force-refresh", action="store_true")
```

Before connecting to IBKR:

```python
if args.auto_load_latest and not args.force_refresh:
    loaded = load_latest_table(output_dir=output_dir, kind="candidates")
    if loaded is not None:
        df, record = loaded
        log.info(f"Loaded previous candidate run {record.run_id} from {record.artifact_path}")
        print(df.head(args.top).to_string(index=False))
        return
```

If no previous run exists, continue with the configured universe from `config/default_universe.txt` or `UNIVERSE`.

- [x] **Step 7: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_bootstrap tests.test_run_storage
.venv/bin/python -m py_compile fcn_screener.py app/streamlit_app.py src/fcn_wizard/bootstrap.py src/fcn_wizard/workflows/bootstrap.py
```

Expected: tests pass and compile exits 0.

---

## Phase 2: Fair Coupon and PB Overcharge Detection

### Task 2: Add Quote Fields and Client-Cost Dealer Margin

**Files:**
- Modify: `src/fcn_wizard/config.py`
- Modify: `src/fcn_wizard/analysis.py`
- Modify: `fcn_screener.py`
- Modify: `app/streamlit_app.py`
- Create: `tests/test_quotes.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_quotes.py`:

```python
from __future__ import annotations

import unittest

from fcn_wizard.analysis import TickerMetrics
from fcn_wizard.metrics import dealer_margin


class QuoteMetricsTest(unittest.TestCase):
    def test_dealer_margin_is_fair_coupon_minus_quote(self):
        self.assertAlmostEqual(dealer_margin(0.22, 0.28), 0.06)

    def test_dealer_margin_returns_none_without_quote(self):
        self.assertIsNone(dealer_margin(None, 0.18))

    def test_ticker_metrics_has_quote_fields(self):
        row = TickerMetrics(symbol="NVDA", fair_coupon_proxy=0.18, quoted_coupon=0.22)
        self.assertEqual(row.quoted_coupon, 0.22)
```

This sign convention is intentional for PB quote evaluation: `dealer_margin = fair_coupon - quoted_coupon`. Positive values flag that the quote is worse for the client than model fair value; this is the main "is the banker overcharging me?" column.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_quotes
```

Expected: fail because `dealer_margin` and `quoted_coupon` do not exist.

- [x] **Step 3: Add quote helpers and fields**

In `src/fcn_wizard/metrics.py`:

```python
def dealer_margin(quoted_coupon: float | None, fair_coupon: float | None) -> float | None:
    if quoted_coupon is None or fair_coupon is None:
        return None
    return float(fair_coupon - quoted_coupon)
```

Sign convention: positive `dealer_margin` means model fair coupon is above the PB quote, so the client is being underpaid versus model fair value. Negative means the PB quote is richer than model fair value.

In `src/fcn_wizard/analysis.py`, extend `TickerMetrics`:

```python
quoted_coupon: Optional[float] = None
dealer_margin: Optional[float] = None
```

Add an optional parameter to `analyze_ticker`:

```python
quoted_coupon: Optional[float] = None,
```

After `fair_coupon_proxy` is computed:

```python
metrics.quoted_coupon = quoted_coupon
metrics.dealer_margin = dealer_margin(quoted_coupon, metrics.fair_coupon_proxy)
```

- [x] **Step 4: Add script/UI inputs**

In `fcn_screener.py`:

```python
parser.add_argument("--quoted-coupon", type=float, default=None, help="Annualized quoted coupon as decimal, e.g. 0.22")
```

Add `quoted_coupon` and `dealer_margin` fields to its local dataclass or, preferably, move it to package `TickerMetrics` in Phase 3.

In `app/streamlit_app.py` sidebar:

```python
quoted_coupon = st.number_input("Quoted coupon", min_value=0.0, max_value=2.0, value=0.0, step=0.01)
quoted_coupon_value = quoted_coupon if quoted_coupon > 0 else None
```

Pass `quoted_coupon=quoted_coupon_value` into `analyze_ticker`.

- [x] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_quotes
.venv/bin/python -m py_compile app/streamlit_app.py fcn_screener.py src/fcn_wizard/analysis.py src/fcn_wizard/metrics.py
```

Expected: tests pass and compile exits 0.

### Task 2B: Add Standalone Fair-Coupon Quote Comparison Script

**Files:**
- Create: `src/fcn_wizard/workflows/fair_coupon.py`
- Create: `fair_coupon.py`
- Create: `src/fcn_wizard/quotes/__init__.py`
- Create: `src/fcn_wizard/quotes/pb_quotes.py`
- Modify: `tests/test_quotes.py`
- Modify: `README.md`
- Modify: `fcn_framework_reference.md`

- [x] **Step 1: Write fair-coupon workflow tests**

Append to `tests/test_quotes.py`:

```python
from io import StringIO

import pandas as pd

from fcn_wizard.workflows.fair_coupon import rank_quotes_against_fair_coupon


class FairCouponWorkflowTest(unittest.TestCase):
    def test_rank_quotes_against_pair_fair_coupon(self):
        pairs = pd.DataFrame(
            [
                {
                    "a": "NVDA",
                    "b": "TSLA",
                    "p_ki_either": 0.50,
                    "pair_fair_coupon_proxy": 0.75,
                }
            ]
        )
        quotes = pd.read_csv(
            StringIO(
                "pb,symbols,quoted_coupon\n"
                "PB_A,NVDA/TSLA,0.22\n"
                "PB_B,NVDA/TSLA,0.28\n"
            )
        )

        ranked = rank_quotes_against_fair_coupon(pairs, quotes)

        self.assertEqual(ranked.iloc[0]["pb"], "PB_A")
        self.assertAlmostEqual(ranked.iloc[0]["dealer_margin"], 0.53)
        self.assertEqual(ranked.iloc[0]["verdict"], "expensive_vs_model")
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_quotes
```

Expected: fail because `fcn_wizard.workflows.fair_coupon` and `fcn_wizard.quotes` do not exist.

- [x] **Step 3: Implement quote utilities**

Create `src/fcn_wizard/quotes/pb_quotes.py`:

```python
from __future__ import annotations

import pandas as pd


def normalize_symbols(value: str) -> str:
    return "/".join(sorted(part.strip().upper() for part in value.replace(",", "/").split("/") if part.strip()))


def compare_pb_quotes(quotes: pd.DataFrame, fair_values: pd.DataFrame) -> pd.DataFrame:
    left = quotes.copy()
    right = fair_values.copy()
    left["symbols"] = left["symbols"].map(normalize_symbols)
    right["symbols"] = right["symbols"].map(normalize_symbols)
    merged = left.merge(right[["symbols", "fair_coupon_proxy"]], on="symbols", how="left")
    merged["dealer_margin"] = merged["fair_coupon_proxy"] - merged["quoted_coupon"]
    return merged.sort_values(["symbols", "dealer_margin"], ascending=[True, False]).reset_index(drop=True)
```

Create `src/fcn_wizard/quotes/__init__.py`:

```python
from .pb_quotes import *  # noqa: F401,F403
```

- [x] **Step 4: Implement workflow helper**

Create `src/fcn_wizard/workflows/fair_coupon.py`:

```python
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
```

- [x] **Step 5: Add standalone CLI script**

Create root-level `fair_coupon.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from fcn_wizard.run_storage import load_latest_table
from fcn_wizard.workflows.fair_coupon import load_pairs, load_quotes, rank_quotes_against_fair_coupon


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare PB FCN quotes against modeled fair coupon.")
    parser.add_argument("--pairs-file", default=None, help="Pair result CSV. Defaults to latest saved pair run.")
    parser.add_argument("--quotes-file", required=True, help="CSV with columns: pb,symbols,quoted_coupon")
    parser.add_argument("--output", default="outputs/fair_coupon_quotes.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.pairs_file:
        pairs = load_pairs(args.pairs_file)
    else:
        loaded = load_latest_table(output_dir=Path("outputs"), kind="pairs")
        if loaded is None:
            raise SystemExit("No pair results found. Run fcn_pair_screener.py first or pass --pairs-file.")
        pairs, _ = loaded
    quotes = load_quotes(args.quotes_file)
    ranked = rank_quotes_against_fair_coupon(pairs, quotes)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(out_path, index=False)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 180)
    print(ranked.to_string(index=False))
    print(f"Saved {len(ranked)} quote rows -> {out_path}")


if __name__ == "__main__":
    main()
```

- [x] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_quotes
.venv/bin/python -m py_compile fair_coupon.py src/fcn_wizard/workflows/fair_coupon.py src/fcn_wizard/quotes/__init__.py src/fcn_wizard/quotes/pb_quotes.py
```

Expected: tests pass and compile exits 0.

---

## Phase 3: Remove Duplicate Standalone Logic

### Task 3: Centralize Single-Name Metrics and Scoring

**Files:**
- Modify: `fcn_screener.py`
- Modify: `fcn_pair_screener.py`
- Modify: `src/fcn_wizard/analysis.py`
- Modify: `src/fcn_wizard/scoring.py`
- Create/Modify: `tests/test_scoring.py`

- [x] **Step 1: Add regression tests for scoring parity**

Extend `tests/test_scoring.py`:

```python
from types import SimpleNamespace

from fcn_wizard.scoring import ScoreToggles, score_single


def test_score_single_matches_documented_high_quality_candidate():
    metrics = SimpleNamespace(
        iv_rank=75,
        vrp=0.06,
        put_skew_25d=0.04,
        above_200dma=True,
        drawdown_3m=-0.10,
        stock_adv_usd=1.5e9,
        crash_5y=0,
    )

    score, rows = score_single(metrics, ScoreToggles())

    assert score == 9.5
    assert [row["factor"] for row in rows] == [
        "IV Rank",
        "VRP",
        "Put Skew",
        "Trend",
        "3M Drawdown",
        "Liquidity",
        "5Y Crash",
    ]
```

- [x] **Step 2: Run tests and verify current scorer**

Run:

```bash
.venv/bin/python -m unittest tests.test_scoring
```

Expected: pass if package scoring is correct. If it fails, fix package scorer before touching scripts.

- [x] **Step 3: Refactor `fcn_screener.py`**

Remove local pure metric functions that duplicate package functions:

- `iv_rank`
- `realized_vol`
- `drawdown_3m`
- `max_drawdown`
- `above_200dma`
- `stock_adv_usd`

Replace imports:

```python
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
from fcn_wizard.scoring import score_single
```

Replace:

```python
m.score = score(m)
```

with:

```python
m.score, _ = score_single(m)
```

- [x] **Step 4: Refactor `fcn_pair_screener.py`**

Replace local `single_name_ki_prob`, `joint_ki_prob_mc`, `pair_correlation`, and `coupon_uplift_proxy` with imports:

```python
from fcn_wizard.metrics import coupon_uplift_proxy, joint_ki_prob_mc, pair_correlation, single_name_ki_prob
```

Replace local `score_pair` with package scorer adapter:

```python
from fcn_wizard.scoring import score_pair as score_pair_with_breakdown

def score_pair(p: PairMetrics) -> float:
    total, _ = score_pair_with_breakdown(asdict(p))
    return total
```

- [x] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m py_compile fcn_screener.py fcn_pair_screener.py
```

Expected: tests pass and compile exits 0.

---

## Phase 4: Generic 2-Name / 3-Name Basket Analytics

### Task 4: Add Generic N-Asset Joint KI MC

**Files:**
- Modify: `src/fcn_wizard/metrics.py`
- Create: `tests/test_metrics.py`

- [x] **Step 1: Write failing tests**

Create `tests/test_metrics.py`:

```python
from __future__ import annotations

import unittest

import numpy as np

from fcn_wizard.metrics import joint_ki_prob_mc, joint_ki_prob_nd


class BasketMetricsTest(unittest.TestCase):
    def test_joint_ki_prob_nd_matches_pair_engine_for_two_assets(self):
        pair = joint_ki_prob_mc(0.45, 0.55, 0.60, n_sims=5_000, seed=7)
        nd = joint_ki_prob_nd(
            vols=[0.45, 0.55],
            corr_matrix=np.array([[1.0, 0.60], [0.60, 1.0]]),
            n_sims=5_000,
            seed=7,
        )
        self.assertAlmostEqual(nd["p_either"], pair[0], places=12)
        self.assertAlmostEqual(nd["p_all"], pair[1], places=12)

    def test_joint_ki_prob_nd_supports_three_assets(self):
        result = joint_ki_prob_nd(
            vols=[0.40, 0.50, 0.60],
            corr_matrix=np.array(
                [
                    [1.0, 0.5, 0.4],
                    [0.5, 1.0, 0.6],
                    [0.4, 0.6, 1.0],
                ]
            ),
            n_sims=2_000,
            seed=11,
        )
        self.assertGreaterEqual(result["p_either"], result["p_all"])
        self.assertEqual(len(result["p_by_asset"]), 3)
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics
```

Expected: fail because `joint_ki_prob_nd` is missing.

- [x] **Step 3: Implement generic MC**

In `src/fcn_wizard/metrics.py`:

```python
def joint_ki_prob_nd(
    vols: list[float],
    corr_matrix: np.ndarray,
    barrier: float = 0.50,
    days: int = 252,
    n_sims: int = 20_000,
    seed: int = 42,
) -> dict:
    vols_array = np.asarray(vols, dtype=float)
    corr = np.asarray(corr_matrix, dtype=float)
    n_assets = len(vols_array)
    if corr.shape != (n_assets, n_assets):
        raise ValueError("corr_matrix shape must match vols")
    corr = corr.copy()
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -0.999, 0.999)
    np.fill_diagonal(corr, 1.0)
    chol = np.linalg.cholesky(corr)
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    z = rng.standard_normal(size=(n_sims, days, n_assets)) @ chol.T
    drift = -0.5 * vols_array**2 * dt
    diffusion = vols_array * np.sqrt(dt)
    log_paths = np.cumsum(drift + diffusion * z, axis=1)
    min_paths = np.exp(log_paths.min(axis=1))
    hits = min_paths <= barrier
    return {
        "p_either": float(hits.any(axis=1).mean()),
        "p_all": float(hits.all(axis=1).mean()),
        "p_exactly_one": float((hits.sum(axis=1) == 1).mean()),
        "p_by_asset": hits.mean(axis=0).astype(float).tolist(),
    }
```

Refactor `joint_ki_prob_mc` to call `joint_ki_prob_nd` and return its existing tuple shape.

- [x] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics
```

Expected: 2 tests pass.

### Task 5: Add Basket Size 3 to CLI and Dashboard

**Files:**
- Modify: `src/fcn_wizard/analysis.py`
- Modify: `fcn_pair_screener.py`
- Modify: `app/streamlit_app.py`
- Create: `tests/test_basket_analysis.py`

- [x] **Step 1: Write failing tests for basket orchestration**

Create `tests/test_basket_analysis.py`:

```python
from __future__ import annotations

import unittest

import pandas as pd

from fcn_wizard.analysis import build_correlation_matrix


class BasketAnalysisTest(unittest.TestCase):
    def test_build_correlation_matrix_returns_current_matrix_and_stability(self):
        index = pd.date_range("2025-01-01", periods=120)
        returns = {
            "A": pd.Series(range(120), index=index, dtype=float).pct_change().fillna(0.0),
            "B": pd.Series(range(1, 121), index=index, dtype=float).pct_change().fillna(0.0),
            "C": pd.Series(range(2, 122), index=index, dtype=float).pct_change().fillna(0.0),
        }

        matrix, stability = build_correlation_matrix(returns, ["A", "B", "C"], window=60)

        self.assertEqual(matrix.shape, (3, 3))
        self.assertEqual(list(matrix.index), ["A", "B", "C"])
        self.assertIsInstance(stability, float)
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_basket_analysis
```

Expected: fail because `build_correlation_matrix` is missing.

- [x] **Step 3: Implement basket analysis helpers**

In `src/fcn_wizard/analysis.py`:

```python
def build_correlation_matrix(
    returns: dict[str, pd.Series],
    symbols: list[str],
    window: int = 60,
) -> tuple[pd.DataFrame, float]:
    frame = pd.concat([returns[symbol].rename(symbol) for symbol in symbols], axis=1).dropna()
    if len(frame) < window + 30:
        raise ValueError("Insufficient overlapping return history for basket analysis.")
    current = frame.tail(window).corr()
    rolling_stabilities = []
    for left_idx, left in enumerate(symbols):
        for right in symbols[left_idx + 1:]:
            rolling = frame[left].rolling(window).corr(frame[right]).dropna()
            if not rolling.empty:
                rolling_stabilities.append(float(rolling.std()))
    stability = float(pd.Series(rolling_stabilities).mean()) if rolling_stabilities else float("nan")
    return current, stability
```

Add:

```python
def analyze_basket(
    rows: list[TickerMetrics],
    returns: dict[str, pd.Series],
    product: ProductConfig,
    window: int = 60,
    n_sims: int = 20_000,
) -> tuple[dict, list[dict]]:
    symbols = [row.symbol for row in rows]
    corr_matrix, corr_stability = build_correlation_matrix(returns, symbols, window)
    vols = [row.vol_used_for_ki or row.iv_30d_current or row.rv_30d for row in rows]
    if any(vol is None for vol in vols):
        raise ValueError("Missing volatility estimate for one or more basket legs.")
    ki = joint_ki_prob_nd(
        vols=[float(vol) for vol in vols],
        corr_matrix=corr_matrix.to_numpy(),
        barrier=product.ki_barrier,
        days=product.tenor_days,
        n_sims=n_sims,
    )
    row = {
        "symbols": "/".join(symbols),
        "score_avg": float(pd.Series([item.score for item in rows]).mean()),
        "corr_avg": float(corr_matrix.where(~np.eye(len(symbols), dtype=bool)).stack().mean()),
        "corr_stability": corr_stability,
        "p_ki_either": ki["p_either"],
        "p_ki_all": ki["p_all"],
        "fair_coupon_proxy": fair_coupon_proxy(
            ki["p_either"],
            product.expected_loss_given_ki,
            product.expected_alive_months,
            product.discount_rate,
            product.tenor_days / 252.0,
        ),
    }
    row["basket_score"], breakdown = score_basket(row)
    return row, breakdown
```

Add `score_basket` in `src/fcn_wizard/analytics/scoring.py` by reusing the existing pair thresholds for `corr_avg`, `corr_stability`, and `p_ki_either`.

- [x] **Step 4: Add CLI option**

In `fcn_pair_screener.py`:

```python
parser.add_argument("--basket-size", type=int, choices=[2, 3], default=2)
```

Replace:

```python
pairs = list(combinations(syms, 2))
```

with:

```python
baskets = list(combinations(syms, args.basket_size))
```

For `basket_size == 2`, preserve existing output columns. For `basket_size == 3`, output:

```python
symbols, score_avg, corr_avg, corr_stability, p_ki_either, p_ki_all, fair_coupon_proxy, basket_score
```

- [x] **Step 5: Add dashboard 3-name selector**

In `app/streamlit_app.py`, under pair analysis:

```python
basket_size = st.segmented_control("Basket size", [2, 3], default=2)
```

For size 3, show Leg C selector and call `analyze_basket`.

- [x] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics tests.test_basket_analysis
.venv/bin/python -m py_compile fcn_pair_screener.py app/streamlit_app.py src/fcn_wizard/analysis.py
```

Expected: tests pass and compile exits 0.

---

## Phase 5: Tenor IV Term Structure

### Task 6: Fetch and Use Tenor-Matched ATM IV

**Files:**
- Modify: `src/fcn_wizard/market_data.py`
- Modify: `src/fcn_wizard/analysis.py`
- Modify: `app/streamlit_app.py`
- Create/Modify: `tests/test_metrics.py`

- [x] **Step 1: Add pure selector tests**

Extend `tests/test_metrics.py`:

```python
from fcn_wizard.metrics import choose_tenor_vol


def test_choose_tenor_vol_prefers_matching_tenor_iv():
    assert choose_tenor_vol(iv_30d=0.30, rv_30d=0.25, tenor_iv=0.42) == 0.42


def test_choose_tenor_vol_falls_back_to_30d_iv_then_rv():
    assert choose_tenor_vol(iv_30d=0.30, rv_30d=0.25, tenor_iv=None) == 0.30
    assert choose_tenor_vol(iv_30d=None, rv_30d=0.25, tenor_iv=None) == 0.25
```

- [x] **Step 2: Implement selector**

In `src/fcn_wizard/metrics.py`:

```python
def choose_tenor_vol(
    iv_30d: float | None,
    rv_30d: float | None,
    tenor_iv: float | None,
) -> float | None:
    return tenor_iv or iv_30d or rv_30d
```

- [x] **Step 3: Add market-data fetcher**

In `src/fcn_wizard/market_data.py`, add:

```python
def fetch_atm_iv_for_dte(ib: IB, symbol: str, target_dte: int) -> tuple[Optional[float], Optional[int]]:
    symbol = symbol.upper()
    stock = Stock(symbol, "SMART", "USD")
    if not ib.qualifyContracts(stock):
        return None, None
    md = ib.reqMktData(stock, "", snapshot=False)
    ib.sleep(2)
    spot = md.marketPrice() or md.last or md.close
    ib.cancelMktData(stock)
    if not spot or np.isnan(spot):
        return None, None
    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    if not chains:
        return None, None
    chain = next((item for item in chains if item.exchange == "SMART"), chains[0])
    target = datetime.today().date() + timedelta(days=target_dte)
    expiry = min(chain.expirations, key=lambda value: abs((datetime.strptime(value, "%Y%m%d").date() - target).days))
    actual_dte = (datetime.strptime(expiry, "%Y%m%d").date() - datetime.today().date()).days
    strike = min(sorted(chain.strikes), key=lambda value: abs(value - spot))
    option = Option(symbol, expiry, strike, "P", "SMART")
    if not ib.qualifyContracts(option):
        return None, actual_dte
    option_md = ib.reqMktData(option, "", snapshot=False)
    ib.sleep(2)
    iv = option_md.modelGreeks.impliedVol if option_md.modelGreeks else None
    ib.cancelMktData(option)
    return (float(iv) if iv else None), actual_dte
```

- [x] **Step 4: Use tenor IV in analysis**

Extend `TickerMetrics` with:

```python
tenor_iv: Optional[float] = None
tenor_iv_dte: Optional[int] = None
vol_used_for_ki: Optional[float] = None
```

In `analyze_ticker`, optionally fetch tenor IV when `fetch_tenor_iv_enabled=True`, then:

```python
metrics.vol_used_for_ki = choose_tenor_vol(metrics.iv_30d_current, metrics.rv_30d, metrics.tenor_iv)
```

Use `vol_used_for_ki` for `single_name_ki_prob`.

- [x] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics
.venv/bin/python -m py_compile src/fcn_wizard/market_data.py src/fcn_wizard/analysis.py
```

Expected: tests pass and compile exits 0. Live IV fetch is manually verified only with IBKR and OPRA data available.

---

## Phase 5B: IV Surface and Wing-Adjusted KI Vol

### Task 6B: Fit a Simple SVI Surface and Use Downside Wing Vol for KI

**Files:**
- Create: `src/fcn_wizard/analytics/vol_surface.py`
- Modify: `src/fcn_wizard/analytics/metrics.py`
- Modify: `src/fcn_wizard/analytics/analysis.py`
- Modify: `src/fcn_wizard/data/market_data.py`
- Create/Modify: `tests/test_vol_surface.py`

- [x] **Step 1: Write synthetic SVI tests**

Create `tests/test_vol_surface.py`:

```python
from __future__ import annotations

import unittest

import numpy as np

from fcn_wizard.analytics.vol_surface import fit_svi, svi_total_variance, wing_adjusted_ki_vol


class VolSurfaceTest(unittest.TestCase):
    def test_svi_fit_recovers_smooth_positive_surface(self):
        k = np.array([-0.5, -0.25, 0.0, 0.25, 0.5])
        true_params = {"a": 0.02, "b": 0.10, "rho": -0.40, "m": 0.0, "sigma": 0.30}
        w = svi_total_variance(k, **true_params)

        params = fit_svi(k, w)
        fitted = svi_total_variance(k, **params)

        self.assertTrue(np.all(fitted > 0))
        self.assertLess(float(np.mean(np.abs(fitted - w))), 0.01)

    def test_wing_adjusted_ki_vol_uses_barrier_moneyness(self):
        params = {"a": 0.02, "b": 0.10, "rho": -0.40, "m": 0.0, "sigma": 0.30}
        vol = wing_adjusted_ki_vol(spot=100, barrier=50, tenor_years=1.0, svi_params=params)

        self.assertGreater(vol, 0)
```

- [x] **Step 2: Implement SVI helpers**

Create `src/fcn_wizard/analytics/vol_surface.py`:

```python
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


def svi_total_variance(k: np.ndarray, a: float, b: float, rho: float, m: float, sigma: float) -> np.ndarray:
    k = np.asarray(k, dtype=float)
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma**2))


def fit_svi(log_moneyness: np.ndarray, total_variance: np.ndarray) -> dict:
    k = np.asarray(log_moneyness, dtype=float)
    w = np.asarray(total_variance, dtype=float)

    def residual(raw: np.ndarray) -> np.ndarray:
        a, log_b, raw_rho, m, log_sigma = raw
        params = {
            "a": a,
            "b": np.exp(log_b),
            "rho": np.tanh(raw_rho),
            "m": m,
            "sigma": np.exp(log_sigma),
        }
        return svi_total_variance(k, **params) - w

    result = least_squares(residual, x0=np.array([0.01, np.log(0.1), 0.0, 0.0, np.log(0.3)]))
    a, log_b, raw_rho, m, log_sigma = result.x
    return {"a": float(a), "b": float(np.exp(log_b)), "rho": float(np.tanh(raw_rho)), "m": float(m), "sigma": float(np.exp(log_sigma))}


def wing_adjusted_ki_vol(spot: float, barrier: float, tenor_years: float, svi_params: dict) -> float:
    log_moneyness = np.array([np.log(barrier / spot)])
    total_var = svi_total_variance(log_moneyness, **svi_params)[0]
    return float(np.sqrt(max(total_var, 0.0) / tenor_years))
```

- [x] **Step 3: Fetch option surface samples**

In `src/fcn_wizard/data/market_data.py`, add a fetcher that returns a DataFrame with:

```text
symbol, expiry, dte, strike, spot, right, implied_vol, log_moneyness, total_variance
```

Function signature:

```python
def fetch_option_surface_sample(
    ib: IB,
    symbol: str,
    target_dte: int,
    max_options: int = 24,
) -> Optional[pd.DataFrame]:
    rows: list[dict] = []
    # Implementation follows the rules below and returns pd.DataFrame(rows)
    # with the documented columns, or None when no option IVs are available.
```

Implementation rules:

- use one expiry nearest `target_dte`
- sample strikes from roughly 50% to 120% of spot
- request puts for downside strikes and calls near/above spot
- cancel market data after each option
- sleep between requests to respect IBKR pacing

- [x] **Step 4: Use wing-adjusted vol only when surface fit is valid**

In `analysis.py`, add fields:

```python
surface_ki_vol: Optional[float] = None
surface_fit_points: Optional[int] = None
```

Use:

```python
if metrics.surface_ki_vol:
    metrics.vol_used_for_ki = metrics.surface_ki_vol
else:
    metrics.vol_used_for_ki = choose_tenor_vol(metrics.iv_30d_current, metrics.rv_30d, metrics.tenor_iv)
```

- [x] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_vol_surface tests.test_metrics
.venv/bin/python -m py_compile src/fcn_wizard/analytics/vol_surface.py src/fcn_wizard/data/market_data.py src/fcn_wizard/analytics/analysis.py
```

Expected: tests pass and compile exits 0. Live surface fetch requires IBKR option market data and is verified separately.

---

## Phase 6: DIP Value and Autocall-Aware Duration

### Task 7: Add DIP Approximation and Autocall-Aware Expected Alive Months

**Files:**
- Modify: `src/fcn_wizard/metrics.py`
- Modify: `src/fcn_wizard/analysis.py`
- Modify: `fcn_framework_reference.md`
- Modify: `tests/test_metrics.py`

- [x] **Step 1: Write tests**

Extend `tests/test_metrics.py`:

```python
from fcn_wizard.metrics import autocall_alive_months_from_paths, down_in_put_proxy


def test_down_in_put_proxy_positive_for_risky_input():
    value = down_in_put_proxy(spot=100, strike=100, barrier=50, tenor_years=1.0, rate=0.04, vol=0.60)
    assert value > 0
    assert value < 100


def test_autocall_alive_months_uses_first_observation_hit():
    paths = np.array(
        [
            [1.00, 1.01, 1.02, 1.03],
            [1.00, 0.99, 0.98, 0.97],
        ]
    )
    months = autocall_alive_months_from_paths(paths, ko_level=1.02, observation_steps=[1, 2, 3], steps_per_month=1)
    assert months == 2.5
```

- [x] **Step 2: Implement pragmatic helpers**

In `src/fcn_wizard/metrics.py`:

```python
def down_in_put_proxy(
    spot: float,
    strike: float,
    barrier: float,
    tenor_years: float,
    rate: float,
    vol: float,
) -> float:
    p_ki = single_name_ki_prob(vol, barrier / spot, int(round(tenor_years * 252)))
    expected_loss = max(strike - barrier, 0.0) / strike
    return float(strike * p_ki * expected_loss * np.exp(-rate * tenor_years))


def autocall_alive_months_from_paths(
    paths: np.ndarray,
    ko_level: float,
    observation_steps: list[int],
    steps_per_month: int = 21,
) -> float:
    alive_steps = []
    last_step = paths.shape[1] - 1
    for path in paths:
        hit_step = next((step for step in observation_steps if step < len(path) and path[step] >= ko_level), last_step)
        alive_steps.append(hit_step)
    return float(np.mean(alive_steps) / steps_per_month)
```

Use the proxy as a fallback model, not as a replacement for the reference-gated closed form in Task 7B.

- [x] **Step 3: Integrate fair coupon duration**

In `analysis.py`, allow product config to use static `expected_alive_months` or MC-derived alive months when basket path output is available.

- [x] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics
.venv/bin/python -m py_compile src/fcn_wizard/metrics.py src/fcn_wizard/analysis.py
```

Expected: tests pass and compile exits 0.

### Task 7B: Add Reference-Gated Reiner-Rubinstein DIP Function

**Files:**
- Modify: `src/fcn_wizard/analytics/metrics.py`
- Modify: `tests/test_metrics.py`
- Modify: `fcn_framework_reference.md`

- [x] **Step 1: Add invariant tests before formula transcription**

Extend `tests/test_metrics.py`:

```python
from fcn_wizard.metrics import black_scholes_put, down_in_put_rr


def test_down_in_put_rr_is_bounded_by_vanilla_put():
    vanilla = black_scholes_put(spot=100, strike=100, tenor_years=1.0, rate=0.04, vol=0.60)
    dip = down_in_put_rr(spot=100, strike=100, barrier=50, tenor_years=1.0, rate=0.04, vol=0.60)

    assert 0 <= dip <= vanilla


def test_down_in_put_rr_converges_to_vanilla_as_barrier_approaches_spot():
    vanilla = black_scholes_put(spot=100, strike=100, tenor_years=1.0, rate=0.04, vol=0.60)
    dip = down_in_put_rr(spot=100, strike=100, barrier=99.0, tenor_years=1.0, rate=0.04, vol=0.60)

    assert abs(dip - vanilla) < 1.0
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics
```

Expected: fail because `black_scholes_put` and `down_in_put_rr` do not exist.

- [x] **Step 3: Implement Black-Scholes put**

In `src/fcn_wizard/analytics/metrics.py`:

```python
def black_scholes_put(spot: float, strike: float, tenor_years: float, rate: float, vol: float) -> float:
    if tenor_years <= 0:
        return float(max(strike - spot, 0.0))
    sigma_t = vol * np.sqrt(tenor_years)
    d1 = (np.log(spot / strike) + (rate + 0.5 * vol**2) * tenor_years) / sigma_t
    d2 = d1 - sigma_t
    return float(strike * np.exp(-rate * tenor_years) * norm.cdf(-d2) - spot * norm.cdf(-d1))
```

- [x] **Step 4: Implement RR DIP behind invariant tests**

Implement `down_in_put_rr` in `src/fcn_wizard/analytics/metrics.py` using the Haug/Reiner-Rubinstein down-and-in put formula for the FCN case `barrier < spot` and `strike >= barrier`. Function signature:

```python
def down_in_put_rr(
    spot: float,
    strike: float,
    barrier: float,
    tenor_years: float,
    rate: float,
    vol: float,
    dividend_yield: float = 0.0,
) -> float:
    # Implement the FCN case K >= B with the Haug/Reiner-Rubinstein formula.
    # Return a float in currency units.
```

Implementation requirements:

- reject `barrier >= spot` with `ValueError("barrier must be below spot")`
- reject `strike < barrier` with `ValueError("strike must be greater than or equal to barrier for the FCN DIP formula")`
- compute with continuous dividend yield support
- clamp only final tiny numerical noise into `[0, vanilla_put]`; do not clamp large formula errors
- document in the function docstring that this is for the common FCN `K >= B` case

- [x] **Step 5: Add edge-case regression tests before using in scoring**

Add deterministic edge-case tests to `tests/test_metrics.py` before wiring this into fair coupon output:

```python
def test_down_in_put_rr_is_near_zero_for_remote_barrier():
    value = down_in_put_rr(spot=100, strike=100, barrier=1, tenor_years=1.0, rate=0.04, vol=0.30)

    assert value < 0.01


def test_down_in_put_rr_rejects_unsupported_strike_below_barrier():
    try:
        down_in_put_rr(spot=100, strike=40, barrier=50, tenor_years=1.0, rate=0.04, vol=0.30)
    except ValueError as exc:
        assert "strike must be greater than or equal to barrier" in str(exc)
    else:
        raise AssertionError("down_in_put_rr should reject strike below barrier")
```

Do not use `down_in_put_rr` in dashboard or CSV outputs until these edge-case tests pass.

- [x] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_metrics
.venv/bin/python -m py_compile src/fcn_wizard/analytics/metrics.py
```

Expected: tests pass and compile exits 0.

---

## Phase 7: Point-in-Time Historical Replay Backtesting

### Task 8: Replay Screener at Historical t0 and Score Forward KI Outcomes

**Files:**
- Create: `src/fcn_wizard/workflows/backtest.py`
- Modify: `src/fcn_wizard/backtest.py`
- Modify: `src/fcn_wizard/data/market_data.py`
- Create: `tests/test_backtest.py`
- Modify: `README.md`
- Modify: `fcn_framework_reference.md`

- [x] **Step 1: Write point-in-time outcome tests**

Create `tests/test_backtest.py`:

```python
from __future__ import annotations

import unittest

import pandas as pd

from fcn_wizard.workflows.backtest import BacktestResult, forward_ki_outcome, score_ki_rank_correlation


class PointInTimeBacktestTest(unittest.TestCase):
    def test_forward_ki_outcome_flags_barrier_touch_after_t0(self):
        prices = pd.Series(
            [100, 95, 80, 49, 70],
            index=pd.date_range("2024-01-15", periods=5, freq="D"),
        )

        outcome = forward_ki_outcome(prices, initial_spot=100, barrier=0.50)

        self.assertTrue(outcome)

    def test_forward_ki_outcome_false_when_barrier_not_touched(self):
        prices = pd.Series(
            [100, 95, 80, 51, 70],
            index=pd.date_range("2024-01-15", periods=5, freq="D"),
        )

        outcome = forward_ki_outcome(prices, initial_spot=100, barrier=0.50)

        self.assertFalse(outcome)

    def test_score_ki_rank_correlation_returns_negative_when_high_scores_avoid_ki(self):
        result = BacktestResult(
            as_of_date="2024-01-15",
            rows=pd.DataFrame(
                [
                    {"symbol": "SAFE", "score": 9.0, "ki_outcome": False},
                    {"symbol": "RISKY", "score": 1.0, "ki_outcome": True},
                ]
            ),
        )

        corr = score_ki_rank_correlation(result)

        self.assertLess(corr, 0)
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_backtest
```

Expected: fail because `fcn_wizard.workflows.backtest` does not exist.

- [x] **Step 3: Implement pure backtest outcome helpers**

Create `src/fcn_wizard/workflows/backtest.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
```

Create root compatibility facade `src/fcn_wizard/backtest.py`:

```python
from .workflows.backtest import *  # noqa: F401,F403
```

- [x] **Step 4: Add IBKR historical end-date support**

In `src/fcn_wizard/data/market_data.py`, change `fetch_history` signature to:

```python
def fetch_history(
    ib: IB,
    symbol: str,
    days: int,
    what: str = "TRADES",
    end_datetime: str = "",
) -> Optional[pd.DataFrame]:
```

Pass `endDateTime=end_datetime` into `ib.reqHistoricalData`. Use IBKR format like `"20240115 23:59:59 US/Eastern"` when replaying t0.

Add:

```python
def fetch_forward_price_history(
    ib: IB,
    symbol: str,
    as_of_date: str,
    days: int,
) -> Optional[pd.Series]:
    start = pd.Timestamp(as_of_date)
    calendar_days = int(days * 365 / 252) + 14
    end = start + pd.Timedelta(days=calendar_days)
    end_datetime = end.strftime("%Y%m%d 23:59:59 US/Eastern")
    df = fetch_history(ib, symbol, calendar_days + 10, "TRADES", end_datetime=end_datetime)
    if df is None or df.empty:
        return None
    closes = df["close"].copy()
    closes.index = pd.to_datetime(closes.index)
    forward = closes[closes.index > start]
    forward.name = symbol.upper()
    return forward.head(days)
```

Implementation requirement: fetch enough historical bars ending at `as_of_date + days`, then filter rows strictly after `as_of_date`.

- [x] **Step 5: Add CLI script entrypoint**

Add root-level `backtest.py`:

```python
from __future__ import annotations

import argparse

from fcn_wizard.config import ProductConfig, read_universe_file
from fcn_wizard.workflows.backtest import replay_as_of_date, score_ki_rank_correlation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Point-in-time replay backtest for FCN screener scoring.")
    parser.add_argument("--as-of-date", required=True, help="Historical date such as 2024-01-15.")
    parser.add_argument("--universe-file", default="config/default_universe.txt")
    parser.add_argument("--output", default=None)
    parser.add_argument("--skip-skew", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()
```

Wire the CLI to call `replay_as_of_date` with IBKR-backed callbacks. The initial implementation must ignore historical option skew unless an external chain provider is explicitly added, because IBKR historical option chains are incomplete/expensive.

- [x] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_backtest
.venv/bin/python -m py_compile backtest.py src/fcn_wizard/backtest.py src/fcn_wizard/workflows/backtest.py src/fcn_wizard/data/market_data.py
```

Expected: tests pass and compile exits 0.

### Task 8B: Optional Prospective Snapshot Store for Production Monitoring

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Create: `src/fcn_wizard/storage/snapshots.py`
- Create: `tests/test_snapshots.py`

This task is optional and lower priority than point-in-time replay. Use it only for production monitoring, data-quality auditing, and prospective stability checks.

- [x] **Step 1: Add dependency**

Add `duckdb` to `pyproject.toml` and `requirements.txt`.

- [x] **Step 2: Write snapshot tests**

Create `tests/test_snapshots.py`:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fcn_wizard.storage.snapshots import init_snapshot_db, save_candidate_snapshot


class SnapshotStoreTest(unittest.TestCase):
    def test_save_candidate_snapshot_round_trips_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "fcn.duckdb"
            init_snapshot_db(db_path)
            saved = save_candidate_snapshot(
                db_path,
                pd.DataFrame([{"symbol": "NVDA", "score": 7.0, "p_ki": 0.2}]),
                as_of_date="2026-05-07",
                run_id="run-1",
            )
            self.assertEqual(saved, 1)
```

- [x] **Step 3: Implement store**

Create `src/fcn_wizard/storage/snapshots.py` with `init_snapshot_db` and `save_candidate_snapshot`, using a `candidate_snapshots` table with columns:

```text
as_of_date, run_id, symbol, score, p_ki, fair_coupon_proxy
```

- [x] **Step 4: Keep snapshot saving opt-in**

If wired into scripts/dashboard, keep it behind `--save-snapshot/--no-save-snapshot` and a dashboard checkbox. Do not make snapshots required for calibration.

- [x] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_snapshots
.venv/bin/python -m py_compile src/fcn_wizard/storage/snapshots.py
```

Expected: tests pass and compile exits 0.

---

## Phase 8: PB Quote Comparison and Cross-PB Arbitrage

### Task 9: Import Quotes and Compute Dealer Margin Rankings

**Files:**
- Modify: `src/fcn_wizard/quotes/__init__.py`
- Modify: `src/fcn_wizard/quotes/pb_quotes.py`
- Create: `tests/test_quotes.py` additions
- Modify: `app/streamlit_app.py`
- Modify: `README.md`
- Modify: `fcn_framework_reference.md`

- [x] **Step 1: Extend quote tests**

Append to `tests/test_quotes.py`:

```python
from io import StringIO

import pandas as pd

from fcn_wizard.quotes import compare_pb_quotes


def test_compare_pb_quotes_ranks_best_investor_coupon():
    quotes = pd.read_csv(
        StringIO(
            "pb,symbols,quoted_coupon\n"
            "PB_A,NVDA/TSLA,0.22\n"
            "PB_B,NVDA/TSLA,0.25\n"
        )
    )
    fair = pd.DataFrame([{"symbols": "NVDA/TSLA", "fair_coupon_proxy": 0.28}])

    result = compare_pb_quotes(quotes, fair)

    assert result.iloc[0]["pb"] == "PB_A"
    assert result.iloc[0]["dealer_margin"] == 0.06
```

- [x] **Step 2: Implement quotes module**

Extend `src/fcn_wizard/quotes/pb_quotes.py` if Task 2B did not already add `compare_pb_quotes`; otherwise verify this exact implementation remains:

```python
from __future__ import annotations

import pandas as pd


def normalize_symbols(value: str) -> str:
    return "/".join(sorted(part.strip().upper() for part in value.replace(",", "/").split("/") if part.strip()))


def compare_pb_quotes(quotes: pd.DataFrame, fair_values: pd.DataFrame) -> pd.DataFrame:
    left = quotes.copy()
    right = fair_values.copy()
    left["symbols"] = left["symbols"].map(normalize_symbols)
    right["symbols"] = right["symbols"].map(normalize_symbols)
    merged = left.merge(right[["symbols", "fair_coupon_proxy"]], on="symbols", how="left")
    merged["dealer_margin"] = merged["fair_coupon_proxy"] - merged["quoted_coupon"]
    return merged.sort_values(["symbols", "dealer_margin"], ascending=[True, False]).reset_index(drop=True)
```

Verify package export `src/fcn_wizard/quotes/__init__.py`:

```python
from .pb_quotes import *  # noqa: F401,F403
```

- [x] **Step 3: Add dashboard quote uploader**

In `app/streamlit_app.py` add a PB quote upload section:

```python
quote_file = st.file_uploader("PB quote CSV", type=["csv"])
if quote_file is not None:
    quotes = pd.read_csv(quote_file)
    fair_values = build_fair_values_from_session_state()
    quote_comparison = compare_pb_quotes(quotes, fair_values)
    st.dataframe(quote_comparison, use_container_width=True)
```

Define `build_fair_values_from_session_state()` to emit `symbols` and `fair_coupon_proxy` from candidate and pair rows currently loaded.

- [x] **Step 4: Verify**

Run:

```bash
.venv/bin/python -m unittest tests.test_quotes
.venv/bin/python -m py_compile src/fcn_wizard/quotes/__init__.py src/fcn_wizard/quotes/pb_quotes.py app/streamlit_app.py
```

Expected: tests pass and compile exits 0.

---

## Phase 9: Documentation and Final Verification

### Task 10: Update Documents and Run Full Checks

**Files:**
- Modify: `README.md`
- Modify: `fcn_framework_reference.md`
- Modify: tests as needed

- [x] **Step 1: Update README**

Document:

- automatic previous-run bootstrap
- default universe fallback from `config/default_universe.txt`
- quoted coupon, fair coupon, and dealer margin columns
- dealer margin sign convention: `fair_coupon - quoted_coupon`; positive means worse for client / possible PB overcharge
- standalone `fair_coupon.py --quotes-file quotes.csv` workflow
- `--basket-size 3`
- tenor IV caveats and OPRA requirement
- point-in-time replay backtest using historical `endDateTime`
- optional DuckDB snapshot store for prospective production monitoring only
- PB quote CSV schema:

```text
pb,symbols,quoted_coupon
PB_A,NVDA/TSLA,0.22
PB_B,NVDA/TSLA,0.25
```

- [x] **Step 2: Update framework reference**

Move completed items out of future roadmap:

- run history
- fair coupon proxy
- dealer margin
- standalone fair-coupon quote comparison
- 3-name basket screener
- tenor IV selector
- point-in-time replay backtest
- PB quote comparison

Keep caveats explicit:

- historical option-chain/skew replay is limited with IBKR; use simplified no-skew replay or an external historical option-chain provider such as Polygon
- local vol is still an approximation unless SVI/SABR surface fitting is actually implemented
- live tenor IV requires option chain data and OPRA
- exact Reiner-Rubinstein formula should be validated independently before using as booking-grade valuation

- [x] **Step 3: Run Python tests**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Expected: all Python tests pass.

- [x] **Step 4: Run compile checks**

Run:

```bash
.venv/bin/python -m py_compile \
  fcn_screener.py \
  fcn_pair_screener.py \
  app/streamlit_app.py \
  src/fcn_wizard/*.py \
  src/fcn_wizard/analytics/*.py \
  src/fcn_wizard/storage/*.py \
  src/fcn_wizard/data/*.py \
  src/fcn_wizard/workflows/*.py \
  src/fcn_wizard/quotes/*.py
```

Expected: exits 0.

- [x] **Step 5: Run dashboard smoke test**

Start Streamlit:

```bash
.venv/bin/streamlit run app/streamlit_app.py --server.headless true --server.port 8501
```

In a second shell:

```bash
npx playwright test tests/streamlit.spec.ts
```

Expected: dashboard load test passes.

- [ ] **Step 6: Optional live IBKR verification** *(not run in this pass; requires a live IB Gateway/TWS session)*

Only run if IB Gateway/TWS is available:

```bash
.venv/bin/python fcn_screener.py --port 4001 --universe-file config/default_universe.txt --no-fetch-skew --top 5
.venv/bin/python fcn_pair_screener.py --port 4001 --basket-size 2
.venv/bin/python fcn_pair_screener.py --port 4001 --basket-size 3
```

Expected:

- candidate run writes `outputs/runs/RUN_ID/candidates.csv`
- pair run writes `outputs/runs/RUN_ID/pairs.csv`
- `outputs/run_index.csv` has `candidates` and `pairs` rows

---

## Execution Notes

- Do not combine all phases into one commit. Commit after each phase passes its tests.
- Keep generated CSVs, DuckDB files, and Playwright artifacts out of git unless explicitly requested.
- Preserve the Chinese/math style in `fcn_framework_reference.md`.
- Keep scripts runnable as standalone files.
- Treat tenor IV and IV surface work as separate model layers; do not relabel a single tenor IV fetch as local vol.

---

## Plan Self-Review

**Spec coverage:** Covered all items from the current partial/not-done list:

- automatic latest-run load with clear history marking
- no-history fallback that runs `config/default_universe.txt`
- fair coupon, quoted coupon, and client-cost dealer margin for detecting PB overcharge
- standalone fair-coupon quote comparison workflow
- duplicate logic cleanup through shared package modules
- organized subdirectories with compatibility facades
- 3-name basket screener
- tenor IV term structure
- IV surface / downside wing vol adjustment
- DIP value, Reiner-Rubinstein/reference-gated validation, and autocall-aware duration
- point-in-time historical replay backtest
- optional prospective snapshot store for production monitoring
- PB quote comparison and cross-PB ranking
- README and framework reference updates

**Completeness scan:** The plan avoids unresolved filler language. Expected RED failures use absence wording only to describe the intended failing-test condition.

**Type consistency:** Public compatibility imports stay stable:

- `fcn_wizard.metrics`
- `fcn_wizard.scoring`
- `fcn_wizard.analysis`
- `fcn_wizard.market_data`
- `fcn_wizard.run_storage`

New implementation homes are consistent:

- `fcn_wizard.analytics.*`
- `fcn_wizard.storage.*`
- `fcn_wizard.data.*`
- `fcn_wizard.workflows.*`
- `fcn_wizard.quotes.*`

**Scope risks:** Exact booking-grade local vol and Reiner-Rubinstein valuation are model-risk-sensitive. The plan prevents accidental overclaiming by requiring tested SVI/wing-vol and DIP valuation helpers first, and by keeping documentation caveats explicit until exact formulas are validated with reference values.
