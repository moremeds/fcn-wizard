# FCN Wizard

Small IBKR-based toolkit for screening Fixed Coupon Note underlyings.

It currently has two standalone scripts plus a small package used by the dashboard:

- `fcn_screener.py`: screens single stocks and ETFs, then ranks candidates.
- `fcn_pair_screener.py`: takes the top single-name candidates and ranks worst-of 2- or 3-name baskets.
- `fair_coupon.py`: compares PB quoted coupons with modeled fair coupon for saved pair results.
- `backtest.py`: point-in-time historical replay for calibration against forward KI outcomes.
- `src/fcn_wizard/`: shared metrics, scoring, storage, and dashboard analysis helpers.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

IB Gateway or TWS must be running with API access enabled.

Common IBKR ports:

- TWS paper: `7497`
- TWS live: `7496`
- IB Gateway paper: `4002`
- IB Gateway live: `4001`

Your current working port during the last run was `4001`.

## Universe

The universe is the list of tickers the screener checks. It does not scan the whole market.

The default editable list is:

```text
config/default_universe.txt
```

## Dashboard

```bash
source .venv/bin/activate
pip install -e .
streamlit run app/streamlit_app.py
```

The dashboard auto-loads the latest saved candidate run on startup. If no saved run exists, it runs `config/default_universe.txt` once and marks the table source. It also lets you query tickers directly, adjust product assumptions, toggle scoring factors, inspect raw metric columns, run worst-of basket analysis, and upload PB quote CSVs.

## Script Run

Single-name screen:

```bash
.venv/bin/python fcn_screener.py --port 4001 --universe-file config/default_universe.txt --no-fetch-skew
```

Pair screen:

```bash
.venv/bin/python fcn_pair_screener.py --basket-size 2
.venv/bin/python fcn_pair_screener.py --basket-size 3
```

Fair coupon quote comparison:

```bash
.venv/bin/python fair_coupon.py --quotes-file quotes.csv
```

`quotes.csv` should contain `pb,symbols,quoted_coupon`, for example `PB_A,NVDA/TSLA,0.22`.

Point-in-time replay backtest:

```bash
.venv/bin/python backtest.py --as-of-date 2024-01-15 --universe-file config/default_universe.txt
```

This uses IBKR historical `endDateTime` replay and intentionally skips historical option-chain/skew replay unless you add an external historical chain provider.

## Outputs

The single-name screener writes a dated CSV like:

```text
outputs/fcn_candidates_YYYYMMDD.csv
```

The older pair screener still writes:

```text
fcn_pairs_YYYYMMDD.csv
```

Both the scripts and dashboard also save reloadable run history under:

```text
outputs/runs/RUN_ID/candidates.csv
outputs/runs/RUN_ID/pairs.csv
outputs/runs/RUN_ID/baskets.csv
outputs/run_index.csv
```

Use **Load latest saved run** in the dashboard to reopen the most recent candidate table without reconnecting to IBKR. DuckDB snapshots are available only as an opt-in production-monitoring store, not as a calibration requirement.

## What The Score Means

The score is a heuristic ranking, not a recommendation.

Single-name score rewards:

- high implied volatility rank
- implied volatility above realized volatility
- price above the 200-day moving average
- limited recent drawdown
- strong liquidity
- no 50%+ historical drawdown over the lookback window

Pair score rewards:

- two strong individual candidates
- higher and more stable correlation
- lower estimated probability that either name hits the knock-in barrier

The raw columns matter more than the score. Use the score as a sorting aid, then inspect the actual metrics:

- `IV 30D`: current 30-day implied volatility from IBKR history
- `RV 30D`: realized volatility from recent stock returns
- `VRP`: IV minus RV; positive means options are pricing more vol than the stock recently realized
- `KI probability`: simple GBM estimate of touching the selected barrier during the selected tenor
- `Fair coupon proxy`: rough annualized coupon required to compensate for modeled KI loss
- `Dealer margin`: `fair_coupon - quoted_coupon`; positive means the PB quote underpays the client versus model fair value
- `Tenor IV` / `Surface KI Vol`: optional option-chain driven vol inputs; require OPRA/live option data and are slower than the default historical IV path
- `5Y max drawdown`: historical crash context
- `Correlation`: pair dependency; higher correlation is usually safer for worst-of investors
- `Either KI`: Monte Carlo probability that at least one leg hits the barrier

PB quote CSV schema:

```text
pb,symbols,quoted_coupon
PB_A,NVDA/TSLA,0.22
PB_B,NVDA/TSLA,0.25
```
