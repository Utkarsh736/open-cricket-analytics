"""Reusable descriptive aggregates built from canonical Cricsheet-derived tables."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

BOWLER_CREDITED_DISMISSALS = {
    "bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"
}
NON_DISMISSAL_EVENTS = {"retired hurt"}


def _truthy(value: Any) -> bool:
    if pd.isna(value):
        return False
    return bool(value)


def build_team_summary(matches: pd.DataFrame, innings: pd.DataFrame) -> pd.DataFrame:
    """Summarize match outcomes and batting/bowling volume by team/format/gender."""
    if matches.empty:
        return pd.DataFrame()

    match_rows: list[dict[str, Any]] = []
    for row in matches.to_dict("records"):
        teams = [team for team in (row.get("team_1"), row.get("team_2")) if pd.notna(team)]
        winner = row.get("winner")
        result = str(row.get("result") or "").strip().lower()
        if result == "nan":
            result = ""
        for team in dict.fromkeys(teams):
            opponent = next((candidate for candidate in teams if candidate != team), None)
            won = pd.notna(winner) and winner == team
            lost = pd.notna(winner) and winner in teams and winner != team
            tied = not pd.notna(winner) and result in {"tie", "tied"}
            no_result = not pd.notna(winner) and result in {"no result", "abandoned", "cancelled"}
            match_rows.append({
                "match_id": row.get("match_id"), "date": row.get("date"),
                "season": row.get("season"), "gender": row.get("gender"),
                "match_type": row.get("match_type"), "team": team, "opponent": opponent,
                "won": int(won), "lost": int(lost), "tied": int(tied),
                "no_result": int(no_result),
            })
    appearances = pd.DataFrame(match_rows)
    group_keys = ["gender", "match_type", "team"]
    results = appearances.groupby(group_keys, dropna=False, as_index=False).agg(
        matches=("match_id", "nunique"), wins=("won", "sum"), losses=("lost", "sum"),
        ties=("tied", "sum"), no_results=("no_result", "sum"),
    )
    decisive = results["wins"] + results["losses"]
    results["win_pct_decisive"] = (100 * results["wins"] / decisive.where(decisive > 0)).round(2)

    if not innings.empty:
        ordinary = innings.loc[~innings["is_super_over"].map(_truthy)].copy()
        bat = ordinary.groupby(["gender", "match_type", "batting_team"], dropna=False, as_index=False).agg(
            innings_batted=("match_id", "size"), runs_scored=("total_runs", "sum"),
            wickets_lost=("wickets", "sum"), legal_balls_faced=("legal_balls", "sum"),
        ).rename(columns={"batting_team": "team"})
        bat["batting_run_rate"] = (6 * bat["runs_scored"] / bat["legal_balls_faced"].where(bat["legal_balls_faced"] > 0)).round(3)
        bowl = ordinary.groupby(["gender", "match_type", "bowling_team"], dropna=False, as_index=False).agg(
            innings_bowled=("match_id", "size"), runs_conceded=("total_runs", "sum"),
            wickets_taken=("wickets", "sum"), legal_balls_bowled=("legal_balls", "sum"),
        ).rename(columns={"bowling_team": "team"})
        bowl["bowling_economy"] = (6 * bowl["runs_conceded"] / bowl["legal_balls_bowled"].where(bowl["legal_balls_bowled"] > 0)).round(3)
        results = results.merge(bat, on=["gender", "match_type", "team"], how="left")
        results = results.merge(bowl, on=["gender", "match_type", "team"], how="left")
    return results.sort_values(["match_type", "wins", "win_pct_decisive"], ascending=[True, False, False], na_position="last")


def build_venue_summary(innings: pd.DataFrame) -> pd.DataFrame:
    """Summarize score and pace by venue, gender and match type."""
    if innings.empty:
        return pd.DataFrame()
    ordinary = innings.loc[~innings["is_super_over"].map(_truthy)].copy()
    keys = ["gender", "match_type", "venue"]
    venue = ordinary.groupby(keys, dropna=False, as_index=False).agg(
        innings=("match_id", "size"), matches=("match_id", "nunique"),
        average_innings_score=("total_runs", "mean"), median_innings_score=("total_runs", "median"),
        average_wickets=("wickets", "mean"), total_legal_balls=("legal_balls", "sum"),
        total_runs=("total_runs", "sum"),
    )
    venue["runs_per_over"] = (6 * venue["total_runs"] / venue["total_legal_balls"].where(venue["total_legal_balls"] > 0)).round(3)
    venue["average_innings_score"] = venue["average_innings_score"].round(2)
    venue["median_innings_score"] = venue["median_innings_score"].round(2)
    venue["average_wickets"] = venue["average_wickets"].round(2)
    return venue.sort_values(["matches", "average_innings_score"], ascending=[False, False])


def _event_counts(raw_events: Any, batter: Any) -> tuple[int, int]:
    """Return (all batter dismissals, bowler-credited dismissals) on one delivery."""
    if not isinstance(raw_events, str) or not raw_events:
        return 0, 0
    try:
        events = json.loads(raw_events)
    except json.JSONDecodeError:
        return 0, 0
    dismissals = credited = 0
    for event in events:
        if event.get("player_out") != batter:
            continue
        kind = str(event.get("kind", "")).lower()
        if kind in NON_DISMISSAL_EVENTS:
            continue
        dismissals += 1
        credited += int(kind in BOWLER_CREDITED_DISMISSALS)
    return dismissals, credited


def build_batter_bowler_matchups(deliveries: pd.DataFrame) -> pd.DataFrame:
    """Create descriptive batter-vs-bowler splits, with no minimum sample filter."""
    if deliveries.empty:
        return pd.DataFrame()
    enriched = deliveries.copy()
    # These numeric fields are produced by the current parser. Fall back to parsing
    # event JSON for older processed snapshots so Stage 2 is usable before re-ingestion.
    if {"batter_dismissals_on_delivery", "bowler_credited_wickets_on_delivery"}.issubset(enriched.columns):
        enriched["batter_dismissals"] = enriched["batter_dismissals_on_delivery"].fillna(0).astype(int)
        enriched["bowler_credited_dismissals"] = enriched["bowler_credited_wickets_on_delivery"].fillna(0).astype(int)
    else:
        counts = enriched.apply(
            lambda row: _event_counts(row.get("dismissal_events_json"), row.get("batter")), axis=1
        )
        enriched["batter_dismissals"] = [value[0] for value in counts]
        enriched["bowler_credited_dismissals"] = [value[1] for value in counts]
    enriched["balls_faced"] = (enriched["wides"] == 0).astype(int)
    keys = ["gender", "match_type", "batter", "bowler"]
    result = enriched.groupby(keys, dropna=False, as_index=False).agg(
        recorded_events=("match_id", "size"), matches=("match_id", "nunique"),
        balls_faced=("balls_faced", "sum"), runs=("batter_runs", "sum"),
        fours=("is_boundary_4", "sum"), sixes=("is_boundary_6", "sum"),
        dismissals=("batter_dismissals", "sum"), bowler_credited_wickets=("bowler_credited_dismissals", "sum"),
    )
    result["strike_rate"] = (100 * result["runs"] / result["balls_faced"].where(result["balls_faced"] > 0)).round(2)
    result["average"] = (result["runs"] / result["dismissals"].where(result["dismissals"] > 0)).round(2)
    # Mark sample size clearly: this table is exploratory, not a stable matchup ranking.
    return result.sort_values(["runs", "balls_faced"], ascending=[False, False])


def build_toss_summary(matches: pd.DataFrame) -> pd.DataFrame:
    """Summarize toss winner outcomes by toss decision and format."""
    if matches.empty or "toss_decision" not in matches:
        return pd.DataFrame()
    data = matches.copy()
    data["toss_winner_won"] = (data["toss_winner"].notna() & (data["toss_winner"] == data["winner"])).astype(int)
    data["decisive_match"] = (data["winner"].notna() & data["toss_winner"].notna()).astype(int)
    keys = ["gender", "match_type", "toss_decision"]
    result = data.groupby(keys, dropna=False, as_index=False).agg(
        matches=("match_id", "nunique"), toss_winner_won=("toss_winner_won", "sum"),
        decisive_matches=("decisive_match", "sum"),
    )
    result["toss_winner_win_pct"] = (100 * result["toss_winner_won"] / result["decisive_matches"].where(result["decisive_matches"] > 0)).round(2)
    return result.sort_values(["match_type", "toss_decision"], na_position="last")


def build_season_summary(matches: pd.DataFrame, innings: pd.DataFrame) -> pd.DataFrame:
    """Summarize match volume and first-innings scores by season/format."""
    if matches.empty:
        return pd.DataFrame()
    keys = ["gender", "match_type", "season"]
    count = matches.groupby(keys, dropna=False, as_index=False).agg(matches=("match_id", "nunique"))
    if innings.empty:
        return count
    first = innings.loc[(innings["innings"] == 1) & (~innings["is_super_over"].map(_truthy))]
    first = first.groupby(keys, dropna=False, as_index=False).agg(
        first_innings=("match_id", "size"), average_first_innings_score=("total_runs", "mean"),
        highest_first_innings_score=("total_runs", "max"),
    )
    first["average_first_innings_score"] = first["average_first_innings_score"].round(2)
    return count.merge(first, on=keys, how="left").sort_values(keys, na_position="last")


def build_descriptive_tables(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Build the Stage 2 tables from Stage 1 pipeline outputs."""
    return {
        "team_summary": build_team_summary(tables["matches"], tables["innings_summary"]),
        "venue_summary": build_venue_summary(tables["innings_summary"]),
        "batter_bowler_matchups": build_batter_bowler_matchups(tables["deliveries"]),
        "toss_summary": build_toss_summary(tables["matches"]),
        "season_summary": build_season_summary(tables["matches"], tables["innings_summary"]),
    }
