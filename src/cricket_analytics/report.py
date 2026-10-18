"""Create a compact human-readable report from generated summary tables."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def _markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 10) -> str:
    if frame.empty:
        return "_No rows available._"
    available = [column for column in columns if column in frame.columns]
    if not available:
        return "_Requested columns are unavailable._"
    selected = frame[available].head(limit).copy()
    for column in selected.columns:
        selected[column] = selected[column].map(
            lambda value: "" if pd.isna(value) else (f"{value:.2f}" if isinstance(value, float) else value)
        )
    headers = list(selected.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in selected.itertuples(index=False, name=None):
        lines.append("| " + " | ".join("" if pd.isna(value) else str(value) for value in row) + " |")
    return "\n".join(lines)


def build_quick_report(processed_dir: Path) -> Path:
    matches = pd.read_csv(processed_dir / "matches.csv")
    innings = pd.read_csv(processed_dir / "innings_summary.csv")
    batting = pd.read_csv(processed_dir / "batting_summary.csv")
    bowling = pd.read_csv(processed_dir / "bowling_summary.csv")
    phase = pd.read_csv(processed_dir / "phase_summary.csv")
    quality = pd.read_json(processed_dir / "quality_report.json", typ="series")

    batting = batting.sort_values("runs", ascending=False)
    bowling = bowling[bowling["legal_balls"] >= 12].sort_values(
        ["wickets", "economy"], ascending=[False, True]
    )
    is_super = innings.get("is_super_over", pd.Series(False, index=innings.index)).fillna(False).astype(bool)
    ordinary = innings.loc[~is_super]
    team_scores = ordinary.groupby(["gender", "match_type", "batting_team"], dropna=False, as_index=False).agg(
        innings=("match_id", "count"), total_runs=("total_runs", "sum"),
        total_wickets=("wickets", "sum"), legal_balls=("legal_balls", "sum")
    )
    team_scores["runs_per_over"] = 6 * team_scores["total_runs"] / team_scores["legal_balls"].where(team_scores["legal_balls"] > 0)
    team_scores = team_scores.sort_values("runs_per_over", ascending=False)

    dates = pd.to_datetime(matches["date"], errors="coerce") if "date" in matches else pd.Series(dtype="datetime64[ns]")
    date_start = dates.min().date().isoformat() if dates.notna().any() else "unknown"
    date_end = dates.max().date().isoformat() if dates.notna().any() else "unknown"
    source = quality.get("source", "Cricsheet data")

    lines = [
        f"# {source} — quick report",
        "",
        "Contains information from [Cricsheet](https://cricsheet.org/). Review the current [licensing and attribution terms](https://cricsheet.org/licensing/) before redistributing data or derived outputs.",
        "",
        f"- Matches parsed: **{len(matches):,}**",
        f"- Innings parsed: **{len(innings):,}** (including super overs, if present)",
        f"- Recorded delivery events: **{int(quality.get('delivery_events_parsed', 0)):,}**",
        f"- Match date range: **{date_start}** to **{date_end}**",
        f"- Match types found: **{', '.join(map(str, quality.get('match_type_values', [])))}**",
        "",
        "> These are descriptive summaries of the ingested records. They are not adjusted for opposition, venue, or opportunity, and they are not predictions.",
        "",
        "## Leading run scorers (by gender and format)",
        "",
        _markdown_table(batting, ["batter", "gender", "match_type", "innings", "runs", "balls_faced", "average", "strike_rate", "fours", "sixes"]),
        "",
        "## Leading wicket-takers (minimum 12 legal balls)",
        "",
        _markdown_table(bowling, ["bowler", "gender", "match_type", "innings", "overs", "runs_conceded", "wickets", "economy"]),
        "",
        "## Team scoring rate by batting team and format",
        "",
        _markdown_table(team_scores, ["gender", "match_type", "batting_team", "innings", "total_runs", "total_wickets", "runs_per_over"]),
        "",
        "## Phase scoring by season, format and batting team",
        "",
        _markdown_table(phase.sort_values([c for c in ["season", "match_type", "batting_team", "phase"] if c in phase.columns]), ["season", "gender", "match_type", "batting_team", "phase", "runs", "legal_balls", "wickets", "fours", "sixes", "runs_per_legal_ball"], limit=30),
        "",
        "## Data-quality checks",
        "",
        f"- Duplicate match IDs: **{quality.get('duplicate_match_ids', 'unknown')}**",
        f"- Matches missing dates: **{quality.get('missing_match_dates', 'unknown')}**",
        f"- Matches missing venues: **{quality.get('missing_venues', 'unknown')}**",
        f"- Legal-delivery flag check passed: **{quality.get('legal_delivery_flag_check_passed', 'unknown')}**",
        "",
        "## Interpretation cautions",
        "",
        "- Aggregates are grouped by match format and gender to avoid mixing unlike competitions, but player identities and roles are not yet fully normalized.",
        "- Player names are source display names; registry-based cross-dataset entity resolution is a later step.",
        "- Raw team and venue rates are not adjusted for opposition, match state, or conditions.",
        "- Reconcile sample scorecards and inspect `quality_report.json` before using these tables for model training.",
        "",
    ]
    output = processed_dir / "quick_report.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
