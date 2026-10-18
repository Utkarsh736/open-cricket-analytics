#!/usr/bin/env python3
"""Build analytics for an already downloaded dataset; optionally refresh it."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="wpl")
    parser.add_argument("--download", action="store_true", help="Download a fresh archive before processing")
    parser.add_argument("--url", help="Optional direct archive URL; used only with --download")
    args = parser.parse_args()

    if args.download:
        command = [sys.executable, str(ROOT / "scripts" / "download_data.py"), "--dataset", args.dataset]
        if args.url:
            command.extend(["--url", args.url])
        subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_dataset.py"), "--dataset", args.dataset],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_descriptive_analytics.py"), "--dataset", args.dataset],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
