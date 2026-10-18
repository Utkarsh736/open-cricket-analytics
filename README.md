# Open Cricket Analytics

A small, end-to-end open-data project for ingesting Cricsheet match data, building clean CSV tables, and exploring descriptive cricket metrics. WPL is the initial dataset, **not a hard-coded limit**: the same parser and analytics functions support any Cricsheet JSON archive whose records conform to the published schema.

The project has deliberately stayed small. It is a single repository with a reusable Python package, scripts, a notebook for exploration, and an optional Streamlit browser. No ML model is trained yet.

## What to use for human-readable exploration

- **Streamlit app:** best for repeatedly browsing matches, scorecards, players, phase scoring, and tables.
- **Jupyter notebook:** best for asking new questions, plotting results, checking assumptions, and writing down your interpretation.
- **CSV/Markdown reports:** best for simple inspection, sharing small extracts, and reviewing outputs in GitHub.

Use the app and notebook together: the pipeline owns repeatable transformation logic; notebooks own exploratory analysis; the app presents the existing outputs without reimplementing cricket rules.

## Requirements and setup (`uv`)

Install `uv` first if it is not already available: <https://docs.astral.sh/uv/getting-started/installation/>.

```bash
# Resolve dependencies and create/update uv.lock
uv lock

# Install the core project, development tools, app and notebook dependencies
uv sync --extra dev --extra app --extra notebooks

# If you only need the data pipeline and tests, use:
# uv sync --extra dev
```

Commit `pyproject.toml` and `uv.lock`; never commit `.venv`, downloaded match JSON, or generated CSV outputs.

## Dataset retrieval and reuse

The downloader has presets for a few Cricsheet archives and also accepts a direct JSON archive URL.

```bash
# Initial focused dataset (recommended)
uv run python scripts/download_data.py --dataset wpl

# Other verified Cricsheet presets
uv run python scripts/download_data.py --dataset ipl
uv run python scripts/download_data.py --dataset t20s_female
uv run python scripts/download_data.py --dataset t20s_male
uv run python scripts/download_data.py --dataset t20s

# Full archive; much larger than the WPL sample
uv run python scripts/download_data.py --dataset all

# Or name a dataset and provide another direct JSON archive URL
uv run python scripts/download_data.py --dataset my-competition --url https://example.org/archive_json.zip
```

The direct URL example is illustrative; replace it with a real, permitted Cricsheet JSON archive URL. Presets and download links are maintained in `scripts/download_data.py`.

Downloaded source files are stored separately under `data/raw/<dataset>/`. Their archive URL, retrieval timestamp and checksum are recorded in `data/raw/<dataset>_source_manifest.json`.

## Build Stage 1 data tables

```bash
# Use the existing WPL data already downloaded; does not re-download
uv run python scripts/build_dataset.py --dataset wpl

# Or run the end-to-end pipeline on already downloaded WPL data
uv run python scripts/run_pipeline.py --dataset wpl

# Explicitly download a fresh snapshot before building
uv run python scripts/run_pipeline.py --dataset wpl --download
```

You can select another downloaded dataset by replacing `wpl` with its dataset key. `--raw-dir` and `--out-dir` are also available in `build_dataset.py` for custom locations.

### Stage 1 output files

All tables are written to `data/processed/<dataset>/`:

| File | Contents |
|---|---|
| `matches.csv` | One row per match, with date, season, format, venue, teams, toss and outcome |
| `innings_summary.csv` | One row per innings, total runs, wickets, legal balls, target and extras |
| `deliveries.csv` | One row per recorded delivery event, with batter, bowler, runs, extras, wickets and phase |
| `batting_innings.csv` | One row per batter per innings |
| `batting_summary.csv` | Batter aggregates, separated by format and gender |
| `bowling_innings.csv` | One row per bowler per innings |
| `bowling_summary.csv` | Bowler aggregates, separated by format and gender |
| `phase_summary.csv` | Runs, wickets and balls by season, format, team and phase |
| `quality_report.json` | Dataset inventory and basic validation signals |
| `quick_report.md` | Human-readable top-level report |

## Stage 2: descriptive analytics

Create reusable team, venue, matchup, toss and season summary tables:

```bash
uv run python scripts/build_descriptive_analytics.py --dataset wpl
```

This writes `team_summary.csv`, `venue_summary.csv`, `batter_bowler_matchups.csv`, `toss_summary.csv`, and `season_summary.csv` to the same processed directory.

## Open the interface

```bash
uv run streamlit run apps/explorer.py
```

The app discovers datasets under `data/processed/`, then provides Overview, Players, Teams & Venues, Match Explorer, and Data Tables views. Build Stage 2 tables first to populate all views.

## Explore in a notebook

```bash
uv run jupyter lab
```

Open `notebooks/01_descriptive_analytics.ipynb` and select the `Python (open-cricket-analytics)` kernel. If it is not listed, register the project's kernel once:

```bash
uv run --extra notebooks python -m ipykernel install --user --name cricket-analytics --display-name "Python (open-cricket-analytics)"
```

The notebook loads the processed CSVs; it does not duplicate download or metric code. Use it for deeper experiments and visualizations.

## Metric definitions and important caveats

- The original source JSON is preserved; this repository does not scrape commentary sites.
- A row in `deliveries.csv` is a **recorded delivery event**, not necessarily a legal ball.
- Wides and no-balls are excluded from legal-ball counts; byes and leg-byes are not charged to the bowler. No-balls normally count as balls faced; wides do not.
- Bowler-credited dismissals include bowled, caught, caught and bowled, lbw, stumped and hit wicket. Run-outs and most other dismissal types are not credited to the bowler.
- Overs are stored in cricket notation such as `4.3`; this is not decimal 4.3 overs.
- Phase boundaries are conventional: T20 overs 1–6 / 7–15 / 16 onward; 50-over formats overs 1–10 / 11–40 / 41 onward. Other formats are marked `not_applicable`. The Hundred and multi-day cricket need dedicated phase definitions before such comparisons are interpreted.
- Summary metrics are descriptive, not adjusted for opposition strength, match state, role or conditions. Matchup outputs can be very noisy for small samples.
- Player names are source labels; stable cross-dataset identity resolution using registry IDs is future work.
- The quality report is not a guarantee of complete scorecard correctness. Reconcile sample matches against official scorecards before training models.

## Tests and quality checks

```bash
uv run pytest
uv run ruff check .
```

Tests use small synthetic Cricsheet-like fixtures and do not need internet access or the full archive.

## Source and licensing

- Downloads: <https://cricsheet.org/downloads/>
- JSON format: <https://cricsheet.org/format/json/>
- Coverage: <https://cricsheet.org/coverage/>
- Licensing: <https://cricsheet.org/licensing/>

Cricsheet data is governed by its own license and is not relicensed under this repository's MIT license. Preserve the applicable attribution and check current terms before redistribution or commercial use.

## Git and migration workflow

- [Apply this Stage 2 update to an existing WPL repository](MIGRATE_STAGE2.md).
- [Git/GitHub CLI workflow, commits, remotes and pushing](docs/git-workflow.md).

## Development workflow

1. Add or update logic in `src/cricket_analytics/`, not in notebooks or the Streamlit app.
2. Add a small fixture and tests under `tests/` for edge cases.
3. Run `uv run pytest` and `uv run ruff check .`.
4. Rebuild processed outputs locally; do not commit raw data or generated tables.
5. Document new metric definitions and add provenance when a new source is introduced.

## Current scope and extension points

The ingestion code accepts any named Cricsheet JSON archive selected by the downloader or passed with `--url`; output paths are dataset-scoped. Format and gender are kept as dimensions so summary tables do not quietly combine unlike competitions. Powerplay/middle/death labels are currently defined only for T20 and 50-over formats. Adding a new source with a different schema should be implemented as a separate source adapter that outputs the same canonical tables, rather than mixing source-specific conditionals throughout the analytics functions.
