#!/usr/bin/env python3
"""Download a Cricsheet JSON archive into data/raw/<dataset>/ safely."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw"
# URLs verified against Cricsheet's official download page.
DATASETS: dict[str, tuple[str, str]] = {
    "wpl": ("https://cricsheet.org/downloads/wpl_json.zip", "Women's Premier League"),
    "ipl": ("https://cricsheet.org/downloads/ipl_json.zip", "Indian Premier League"),
    "all": ("https://cricsheet.org/downloads/all_json.zip", "All available Cricsheet matches"),
    "t20s": ("https://cricsheet.org/downloads/t20s_json.zip", "T20 matches"),
    "t20s_female": ("https://cricsheet.org/downloads/t20s_female_json.zip", "Women's T20 matches"),
    "t20s_male": ("https://cricsheet.org/downloads/t20s_male_json.zip", "Men's T20 matches"),
}
USER_AGENT = "open-cricket-analytics/0.2 (research project; respectful download)"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_dataset_name(name: str) -> str:
    slug = name.strip().lower().replace(" ", "-")
    if not slug or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in slug):
        raise ValueError("Dataset name must contain only letters, numbers, hyphens and underscores.")
    return slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="wpl", help=f"Dataset key/name (presets: {', '.join(DATASETS)})")
    parser.add_argument("--url", help="Optional direct URL to a Cricsheet JSON zip archive")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dataset = safe_dataset_name(args.dataset)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.url:
        source_url = args.url
        label = dataset.replace("_", " ").replace("-", " ").title()
    elif dataset in DATASETS:
        source_url, label = DATASETS[dataset]
    else:
        print(f"Unknown preset {dataset!r}. Use one of {', '.join(DATASETS)} or pass --url.", file=sys.stderr)
        return 2

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    target_dir = RAW_ROOT / dataset
    manifest_path = RAW_ROOT / f"{dataset}_source_manifest.json"
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{dataset}-staging-", dir=RAW_ROOT))
    archive_path = temp_dir / "source.zip"
    extract_dir = temp_dir / "matches"
    extract_dir.mkdir()

    request = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT})
    print(f"Downloading {label}: {source_url}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, archive_path.open("wb") as out:
            shutil.copyfileobj(response, out)
        archive_sha256 = sha256_file(archive_path)
        match_files = []
        seen_names: set[str] = set()
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".json"):
                    continue
                filename = Path(member.filename).name
                if not filename or filename in {".", ".."}:
                    continue
                if filename in seen_names:
                    raise ValueError(f"Archive contains duplicate JSON filenames: {filename}")
                seen_names.add(filename)
                content = archive.read(member)
                parsed = json.loads(content.decode("utf-8"))
                if not isinstance(parsed, dict) or not isinstance(parsed.get("info"), dict):
                    raise ValueError(f"JSON file does not look like a Cricsheet match: {filename}")
                (extract_dir / filename).write_bytes(content)
                match_files.append(filename)

        if not match_files:
            raise ValueError("No valid JSON match files were found in the archive.")

        manifest = {
            "dataset": dataset,
            "dataset_label": f"Cricsheet {label} JSON archive",
            "source_url": source_url,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "archive_sha256": archive_sha256,
            "json_files_extracted": len(match_files),
            "license_reference": "https://cricsheet.org/licensing/",
        }
        # Swap in a fully validated snapshot; don't leave a half-extracted dataset behind.
        old_dir = RAW_ROOT / f".{dataset}-previous"
        if old_dir.exists():
            shutil.rmtree(old_dir)
        had_previous = target_dir.exists()
        if had_previous:
            os.replace(target_dir, old_dir)
        try:
            os.replace(extract_dir, target_dir)
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except Exception:
            # Roll back if the final replacement or manifest write fails.
            if target_dir.exists():
                shutil.rmtree(target_dir)
            if had_previous and old_dir.exists():
                os.replace(old_dir, target_dir)
            raise
        if old_dir.exists():
            shutil.rmtree(old_dir)
        print(f"Extracted {len(match_files):,} match JSON files to {target_dir.relative_to(ROOT)}")
        print(f"Archive SHA-256: {archive_sha256}")
        print("Review Cricsheet's current license and attribution terms before redistributing data.")
        return 0
    except Exception as exc:  # network/archive failures vary by platform
        print(f"Download/extraction failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Existing extracted data was left untouched unless the final swap had already begun.", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
