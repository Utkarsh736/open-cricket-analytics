#!/usr/bin/env python3
"""Parse one Cricsheet dataset into canonical delivery and statistics tables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cricket_analytics.pipeline import build_tables, quality_report
from cricket_analytics.report import build_quick_report

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="wpl", help="Dataset folder name under data/raw and data/processed")
    parser.add_argument("--raw-dir", type=Path, help="Override input directory (optional)")
    parser.add_argument("--out-dir", type=Path, help="Override output directory (optional)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_dir = (args.raw_dir or ROOT / "data" / "raw" / args.dataset).resolve()
    out_dir = (args.out_dir or ROOT / "data" / "processed" / args.dataset).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = build_tables(raw_dir)

    # Build in memory first. If parsing fails, no new CSVs have been written.
    for table_name, frame in tables.items():
        output_path = out_dir / f"{table_name}.csv"
        frame.to_csv(output_path, index=False)
        print(f"{table_name:20s} {len(frame):>9,} rows -> {output_path}")

    report = quality_report(tables, raw_dir)
    report_path = out_dir / "quality_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    quick_report = build_quick_report(out_dir)
    print(f"\nQuality report: {report_path}")
    print(f"Quick report:   {quick_report}")
    print(json.dumps({key: report[key] for key in [
        "source", "json_files_found", "matches_parsed", "innings_parsed",
        "delivery_events_parsed", "match_type_values", "duplicate_match_ids",
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
