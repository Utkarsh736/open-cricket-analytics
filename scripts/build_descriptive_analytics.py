#!/usr/bin/env python3
"""Create Stage 2 descriptive analytics tables from Stage 1 CSV outputs."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from cricket_analytics.descriptive import build_descriptive_tables

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["matches", "innings_summary", "deliveries"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="wpl", help="Dataset folder under data/processed")
    parser.add_argument("--processed-dir", type=Path, help="Override processed output directory")
    args = parser.parse_args()
    processed_dir = (args.processed_dir or ROOT / "data" / "processed" / args.dataset).resolve()
    missing = [name for name in REQUIRED if not (processed_dir / f"{name}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing {', '.join(missing)} in {processed_dir}. Run scripts/build_dataset.py first."
        )
    tables = {name: pd.read_csv(processed_dir / f"{name}.csv") for name in REQUIRED}
    out = build_descriptive_tables(tables)
    for name, frame in out.items():
        path = processed_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        print(f"{name:24s} {len(frame):>9,} rows -> {path}")
    print("\nStage 2 descriptive tables built. Use notebooks/01_descriptive_analytics.ipynb or apps/explorer.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
