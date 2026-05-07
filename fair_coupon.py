from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

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
