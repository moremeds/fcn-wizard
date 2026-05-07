# FCN Wizard

Small IBKR-based toolkit for screening Fixed Coupon Note underlyings.

It currently has two scripts:

- `fcn_screener.py`: screens single stocks and ETFs, then ranks candidates.
- `fcn_pair_screener.py`: takes the top single-name candidates and ranks worst-of pairs.

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

The dashboard lets you query tickers directly, adjust product assumptions, toggle scoring factors, inspect raw metric columns, and run worst-of pair analysis.

## Script Run

Single-name screen:

```bash
.venv/bin/python fcn_screener.py --port 4001 --universe-file config/default_universe.txt --no-fetch-skew
```

Pair screen:

```bash
.venv/bin/python fcn_pair_screener.py
```

## Outputs

The single-name screener writes a dated CSV like:

```text
outputs/fcn_candidates_YYYYMMDD.csv
```

The older pair screener still writes:

```text
fcn_pairs_YYYYMMDD.csv
```

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
- `5Y max drawdown`: historical crash context
- `Correlation`: pair dependency; higher correlation is usually safer for worst-of investors
- `Either KI`: Monte Carlo probability that at least one leg hits the barrier
