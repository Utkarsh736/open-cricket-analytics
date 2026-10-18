# Data source notes

## Primary source: Cricsheet

Cricsheet provides downloadable structured match records. JSON is the recommended source format because it preserves the nested delivery events and metadata required by the project.

Official documentation:

- Downloads and current archive coverage: https://cricsheet.org/downloads/
- JSON schema: https://cricsheet.org/format/json/
- Coverage information: https://cricsheet.org/coverage/
- Licensing and attribution: https://cricsheet.org/licensing/

Current presets in `scripts/download_data.py`:

| Key | Archive URL | Scope |
|---|---|---|
| `wpl` | `https://cricsheet.org/downloads/wpl_json.zip` | Women's Premier League |
| `ipl` | `https://cricsheet.org/downloads/ipl_json.zip` | Indian Premier League |
| `all` | `https://cricsheet.org/downloads/all_json.zip` | All matches currently released by Cricsheet |
| `t20s` | `https://cricsheet.org/downloads/t20s_json.zip` | T20 matches |
| `t20s_female` | `https://cricsheet.org/downloads/t20s_female_json.zip` | Women's T20 matches |
| `t20s_male` | `https://cricsheet.org/downloads/t20s_male_json.zip` | Men's T20 matches |

Cricsheet's coverage changes over time; the downloads page remains the source of truth. The all-match archive is much larger and is intentionally not the default.

## Provenance

For each downloaded archive the downloader records:

- Source URL and dataset key.
- Retrieval time in UTC.
- SHA-256 checksum of the downloaded archive.
- Number of JSON match files extracted.
- Link to the current license information.

The manifest is stored as `data/raw/<dataset>_source_manifest.json`. Original match JSON files are kept in `data/raw/<dataset>/`; generated CSVs are kept in `data/processed/<dataset>/`.

## Why no web scraping in this project?

The downloadable match event data is sufficient for these initial descriptive and predictive projects. Scraping commentary at the same time creates additional alignment work, brittle HTML dependencies, and licensing/terms considerations. Add commentary through a separate source adapter only after checking access permissions, rate limits, reuse rights and attribution requirements. Keep annotations separate from original Cricsheet events and record whether each label is directly sourced, manually annotated or model-inferred.
