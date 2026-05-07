# FCN Wizard Project Guide

## Project Shape
- This is a standalone Python toolkit for screening Fixed Coupon Note (FCN) underlyings using IBKR market data through `ib_insync`.
- `fcn_screener.py` screens single-name and ETF candidates, then writes `fcn_candidates_YYYYMMDD.csv`.
- `fcn_pair_screener.py` ranks worst-of FCN pairs, preferring the latest `fcn_candidates_*.csv` and writing `fcn_pairs_YYYYMMDD.csv`.
- `fcn_framework_reference.md` is the product, model, risk, and scoring reference. It contains Chinese documentation and math notation; preserve that style when editing it.

## Runtime Assumptions
- IB Gateway or TWS must be running with API access enabled.
- Default IBKR connection settings are `127.0.0.1:7497` for paper trading.
- `fcn_screener.py` uses client id `42`; `fcn_pair_screener.py` uses client id `43`.
- Live option skew requires OPRA/option market data. Set `FETCH_SKEW = False` in `fcn_screener.py` for a faster run or if option data is unavailable.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Common Commands
```bash
python -m py_compile fcn_screener.py fcn_pair_screener.py
python fcn_screener.py
python fcn_pair_screener.py
```

## Development Notes
- Keep scripts runnable as standalone files unless the project is intentionally repackaged.
- Generated CSV outputs are dated and should usually be treated as run artifacts.
- Be careful with IBKR pacing when expanding universes or option-chain requests.
- Prefer small, focused edits. The scoring rules are domain assumptions, so document behavioral changes in `fcn_framework_reference.md` when they materially alter rankings.
