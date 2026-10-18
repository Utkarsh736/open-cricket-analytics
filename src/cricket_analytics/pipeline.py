"""Parse Cricsheet JSON and derive format-aware cricket analytics tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

# A wicket is credited to the bowler for these dismissal types.
BOWLER_CREDITED_DISMISSALS = {
    "bowled",
    "caught",
    "caught and bowled",
    "lbw",
    "stumped",
    "hit wicket",
}

# Retired hurt is recorded as an event in some data, but is not a dismissal
# for the usual batter dismissal count or team wickets-fallen count.
NON_DISMISSAL_EVENTS = {"retired hurt"}


def _first_date(info: dict[str, Any]) -> str | None:
    dates = info.get("dates") or []
    return str(dates[0]) if dates else None


def _season(info: dict[str, Any], date: str | None) -> str | None:
    season = info.get("season")
    if season is not None:
        return str(season)
    return date[:4] if date else None


def _penalty_runs(innings: dict[str, Any]) -> int:
    """Read any pre/post innings penalty runs without assuming one fixed key."""
    penalty = innings.get("penalty_runs") or {}
    if isinstance(penalty, (int, float)):
        return int(penalty)
    if isinstance(penalty, dict):
        return sum(int(value or 0) for value in penalty.values() if isinstance(value, (int, float)))
    return 0


def _phase(over_number: int, match_type: str | None, is_super_over: bool = False) -> str:
    """Assign convention-based phases where they make sense for the format.

    T20 phase boundaries: overs 1-6, 7-15, 16 onward.
    50-over phase boundaries: overs 1-10, 11-40, 41 onward.
    Other formats (including The Hundred and multi-day cricket) are not assigned
    these phases because their rules and interpretations differ.
    """
    if is_super_over:
        return "super_over"
    kind = str(match_type or "").strip().upper()
    if kind in {"T20", "IT20", "WT20", "T20I", "NT20"}:
        phases = ((0, 6, "powerplay"), (6, 15, "middle"), (15, 99, "death"))
    elif kind in {"ODI", "ODM", "OD"}:
        phases = ((0, 10, "powerplay"), (10, 40, "middle"), (40, 99, "death"))
    else:
        return "not_applicable"
    for lower, upper, name in phases:
        if lower <= over_number < upper:
            return name
    return "other"


def _is_legal_delivery(extras: dict[str, Any]) -> bool:
    # Cricsheet represents wides/no-balls as keys in `extras`.
    return int(extras.get("wides", 0) or 0) == 0 and int(extras.get("noballs", 0) or 0) == 0


def _non_boundary(runs: dict[str, Any]) -> bool:
    return bool(runs.get("non_boundary", False))


def parse_match(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return one match row, its innings rows and its delivery rows."""
    with path.open("r", encoding="utf-8") as handle:
        match = json.load(handle)

    info = match.get("info", {})
    match_id = path.stem
    date = _first_date(info)
    teams = list(info.get("teams") or [])
    outcome = info.get("outcome") or {}
    toss = info.get("toss") or {}
    event = info.get("event") or {}
    registry = info.get("registry") or {}

    match_row = {
        "match_id": match_id,
        "date": date,
        "season": _season(info, date),
        "gender": info.get("gender"),
        "match_type": info.get("match_type"),
        "event_name": event.get("name") if isinstance(event, dict) else None,
        "event_stage": event.get("stage") if isinstance(event, dict) else None,
        "venue": info.get("venue"),
        "city": info.get("city"),
        "team_1": teams[0] if len(teams) > 0 else None,
        "team_2": teams[1] if len(teams) > 1 else None,
        "toss_winner": toss.get("winner"),
        "toss_decision": toss.get("decision"),
        "winner": outcome.get("winner"),
        "result": outcome.get("result"),
        "win_method": outcome.get("method"),
        "data_version": (match.get("meta") or {}).get("data_version"),
        "source_file": path.name,
        "player_registry_entries": len((registry.get("people") or {})),
    }

    innings_rows: list[dict[str, Any]] = []
    delivery_rows: list[dict[str, Any]] = []
    innings_list = match.get("innings") or []

    for innings_number, innings in enumerate(innings_list, start=1):
        batting_team = innings.get("team")
        bowling_candidates = [team for team in teams if team != batting_team]
        bowling_team = bowling_candidates[0] if bowling_candidates else None
        runs_from_deliveries = 0
        wickets_fallen = 0
        legal_balls = 0
        delivery_count = 0
        phase_accumulator: dict[str, dict[str, int]] = {
            phase: {"runs": 0, "legal_balls": 0, "wickets": 0, "deliveries": 0}
            for phase in ("powerplay", "middle", "death", "super_over", "not_applicable", "other")
        }

        for over in innings.get("overs") or []:
            over_number = int(over.get("over", 0))
            is_super_over = bool(innings.get("super_over", False))
            phase = _phase(over_number, info.get("match_type"), is_super_over)
            for delivery_sequence, delivery in enumerate(over.get("deliveries") or [], start=1):
                runs = delivery.get("runs") or {}
                extras = delivery.get("extras") or {}
                wickets = delivery.get("wickets") or []
                batter_runs = int(runs.get("batter", 0) or 0)
                extras_runs = int(runs.get("extras", 0) or 0)
                total_runs = int(runs.get("total", batter_runs + extras_runs) or 0)
                legal = _is_legal_delivery(extras)
                credited_wickets = [
                    wicket for wicket in wickets
                    if str(wicket.get("kind", "")).lower() not in NON_DISMISSAL_EVENTS
                ]
                wicket_kinds = [str(wicket.get("kind", "unknown")) for wicket in wickets]
                player_outs = [str(wicket.get("player_out", "")) for wicket in wickets if wicket.get("player_out")]
                dismissal_events = [
                    {"kind": str(wicket.get("kind", "unknown")), "player_out": wicket.get("player_out")}
                    for wicket in wickets
                ]
                striker = delivery.get("batter")
                batter_dismissals_on_delivery = sum(
                    1 for event in dismissal_events
                    if event.get("player_out") == striker
                    and str(event.get("kind", "")).lower() not in NON_DISMISSAL_EVENTS
                )
                bowler_credited_wickets_on_delivery = sum(
                    1 for event in dismissal_events
                    if event.get("player_out") == striker
                    and str(event.get("kind", "")).lower() in BOWLER_CREDITED_DISMISSALS
                )
                is_four = batter_runs == 4 and not _non_boundary(runs)
                is_six = batter_runs == 6 and not _non_boundary(runs)

                delivery_count += 1
                runs_from_deliveries += total_runs
                wickets_fallen += len(credited_wickets)
                if legal:
                    legal_balls += 1

                phase_accumulator[phase]["runs"] += total_runs
                phase_accumulator[phase]["legal_balls"] += int(legal)
                phase_accumulator[phase]["wickets"] += len(credited_wickets)
                phase_accumulator[phase]["deliveries"] += 1

                delivery_rows.append({
                    "match_id": match_id,
                    "date": date,
                    "season": match_row["season"],
                    "gender": match_row["gender"],
                    "match_type": match_row["match_type"],
                    "event_name": match_row["event_name"],
                    "venue": match_row["venue"],
                    "innings": innings_number,
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "over_number": over_number,
                    "delivery_sequence_in_over": delivery_sequence,
                    "actual_delivery": delivery.get("actual_delivery"),
                    "batter": delivery.get("batter"),
                    "non_striker": delivery.get("non_striker"),
                    "bowler": delivery.get("bowler"),
                    "batter_runs": batter_runs,
                    "extras_runs": extras_runs,
                    "total_runs": total_runs,
                    "wides": int(extras.get("wides", 0) or 0),
                    "noballs": int(extras.get("noballs", 0) or 0),
                    "byes": int(extras.get("byes", 0) or 0),
                    "legbyes": int(extras.get("legbyes", 0) or 0),
                    "penalty_extras": int(extras.get("penalty", 0) or 0),
                    "is_legal_delivery": legal,
                    "legal_balls_elapsed": legal_balls,
                    "is_boundary_4": is_four,
                    "is_boundary_6": is_six,
                    "wicket_count": len(credited_wickets),
                    "wicket_kinds": ";".join(wicket_kinds),
                    "players_out": ";".join(player_outs),
                    "batter_dismissals_on_delivery": batter_dismissals_on_delivery,
                    "bowler_credited_wickets_on_delivery": bowler_credited_wickets_on_delivery,
                    "dismissal_events_json": json.dumps(dismissal_events, separators=(",", ":")),
                    "phase": phase,
                    "is_super_over": is_super_over,
                    "source_file": path.name,
                })

        penalties = _penalty_runs(innings)
        innings_total = runs_from_deliveries + penalties
        target_obj = innings.get("target") or {}
        innings_rows.append({
            "match_id": match_id,
            "date": date,
            "season": match_row["season"],
            "gender": match_row["gender"],
            "match_type": match_row["match_type"],
            "event_name": match_row["event_name"],
            "venue": match_row["venue"],
            "innings": innings_number,
            "batting_team": batting_team,
            "bowling_team": bowling_team,
            "runs_from_deliveries": runs_from_deliveries,
            "penalty_runs": penalties,
            "total_runs": innings_total,
            "wickets": wickets_fallen,
            "legal_balls": legal_balls,
            "overs_notation": f"{legal_balls // 6}.{legal_balls % 6}",
            "recorded_deliveries": delivery_count,
            "target_runs": target_obj.get("runs"),
            "target_overs": target_obj.get("overs"),
            "forfeited": bool(innings.get("forfeited", False)),
            "declared": bool(innings.get("declared", False)),
            "is_super_over": bool(innings.get("super_over", False)),
            "phase_metrics_json": json.dumps(phase_accumulator, sort_keys=True),
            "source_file": path.name,
        })

    return match_row, innings_rows, delivery_rows


def _batting_tables(deliveries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if deliveries.empty:
        return pd.DataFrame(), pd.DataFrame()

    keys = ["match_id", "season", "gender", "match_type", "date", "innings", "batting_team", "batter"]
    # Count dismissals from all events in an innings, not only rows where the dismissed
    # player was striker. This handles a non-striker run out on a delivery faced by a teammate.
    dismissal_lookup: dict[tuple[str, str, str], dict[str, int]] = {}
    for inning_key, inning_group in deliveries.groupby(
        ["match_id", "innings", "batting_team"], dropna=False, sort=False
    ):
        counts: dict[str, int] = {}
        for raw_events in inning_group.get("dismissal_events_json", pd.Series("[]", index=inning_group.index)):
            try:
                events = json.loads(raw_events) if isinstance(raw_events, str) else []
            except json.JSONDecodeError:
                events = []
            for event in events:
                player_out = event.get("player_out")
                kind = str(event.get("kind", "")).lower()
                if player_out and kind not in NON_DISMISSAL_EVENTS:
                    counts[player_out] = counts.get(player_out, 0) + 1
        dismissal_lookup[tuple(str(value) for value in inning_key)] = counts

    records: list[dict[str, Any]] = []
    for group_key, group in deliveries.groupby(keys, dropna=False, sort=False):
        match_id, season, gender, match_type, date, innings, team, batter = group_key
        balls_faced = int((group["wides"] == 0).sum())
        runs = int(group["batter_runs"].sum())
        lookup_key = tuple(str(value) for value in (match_id, innings, team))
        dismissals = dismissal_lookup.get(lookup_key, {}).get(str(batter), 0)
        records.append({
            "match_id": match_id, "season": season, "gender": gender,
            "match_type": match_type, "date": date, "innings": innings,
            "team": team, "batter": batter, "runs": runs,
            "balls_faced": balls_faced,
            "fours": int(group["is_boundary_4"].sum()),
            "sixes": int(group["is_boundary_6"].sum()),
            "dismissals": dismissals,
            "strike_rate": (100.0 * runs / balls_faced) if balls_faced else None,
        })

    innings_table = pd.DataFrame.from_records(records)
    overall_keys = ["batter", "gender", "match_type"]
    overall_records = []
    for key, group in innings_table.groupby(overall_keys, dropna=False, sort=False):
        batter, gender, match_type = key
        runs = int(group["runs"].sum())
        balls = int(group["balls_faced"].sum())
        dismissals = int(group["dismissals"].sum())
        innings_count = len(group)
        overall_records.append({
            "batter": batter, "gender": gender, "match_type": match_type,
            "innings": innings_count, "runs": runs, "balls_faced": balls,
            "dismissals": dismissals,
            "not_outs": max(innings_count - dismissals, 0),
            "average": (runs / dismissals) if dismissals else None,
            "strike_rate": (100.0 * runs / balls) if balls else None,
            "fours": int(group["fours"].sum()),
            "sixes": int(group["sixes"].sum()),
        })
    summary = pd.DataFrame.from_records(overall_records)
    if not summary.empty:
        summary = summary.sort_values(["runs", "strike_rate"], ascending=[False, False], na_position="last")
    return innings_table, summary

def _bowling_tables(deliveries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if deliveries.empty:
        empty = pd.DataFrame()
        return empty, empty

    # Runs charged to the bowler: batter runs + wides + no-ball extras.
    enriched = deliveries.copy()
    enriched["bowler_runs_conceded"] = enriched["batter_runs"] + enriched["wides"] + enriched["noballs"]
    enriched["bowler_credited_wickets"] = enriched.apply(
        lambda row: sum(
            1 for kind in str(row["wicket_kinds"]).split(";")
            if kind.lower() in BOWLER_CREDITED_DISMISSALS
        ) if row["wicket_kinds"] else 0,
        axis=1,
    )
    enriched["scoreless_deliveries"] = (enriched["total_runs"] == 0).astype(int)

    keys = ["match_id", "season", "gender", "match_type", "date", "innings", "bowling_team", "bowler"]
    group = enriched.groupby(keys, dropna=False, sort=False)
    bowling_innings = group.agg(
        legal_balls=("is_legal_delivery", "sum"),
        runs_conceded=("bowler_runs_conceded", "sum"),
        wickets=("bowler_credited_wickets", "sum"),
        scoreless_deliveries=("scoreless_deliveries", "sum"),
        wides=("wides", "sum"),
        noballs=("noballs", "sum"),
    ).reset_index().rename(columns={"bowling_team": "team"})
    bowling_innings["overs"] = bowling_innings["legal_balls"].map(
        lambda count: f"{int(count) // 6}.{int(count) % 6}"
    )
    bowling_innings["economy"] = bowling_innings.apply(
        lambda row: (6.0 * row["runs_conceded"] / row["legal_balls"])
        if row["legal_balls"] else None,
        axis=1,
    )

    overall_records = []
    for (bowler, gender, match_type), group in enriched.groupby(["bowler", "gender", "match_type"], dropna=False, sort=False):
        balls = int(group["is_legal_delivery"].sum())
        runs = int(group["bowler_runs_conceded"].sum())
        overall_records.append({
            "bowler": bowler,
            "gender": gender,
            "match_type": match_type,
            "innings": int(group[["match_id", "innings"]].drop_duplicates().shape[0]),
            "legal_balls": balls,
            "overs": f"{balls // 6}.{balls % 6}",
            "runs_conceded": runs,
            "wickets": int(group["bowler_credited_wickets"].sum()),
            "economy": (6.0 * runs / balls) if balls else None,
            "scoreless_deliveries": int(group["scoreless_deliveries"].sum()),
            "wides": int(group["wides"].sum()),
            "noballs": int(group["noballs"].sum()),
        })
    bowling_summary = pd.DataFrame.from_records(overall_records).sort_values(
        ["wickets", "economy"], ascending=[False, True], na_position="last"
    )
    return bowling_innings, bowling_summary


def _phase_table(deliveries: pd.DataFrame) -> pd.DataFrame:
    if deliveries.empty:
        return pd.DataFrame()
    keys = ["season", "gender", "match_type", "batting_team", "phase"]
    phase = deliveries.groupby(keys, dropna=False, sort=False).agg(
        runs=("total_runs", "sum"),
        batter_runs=("batter_runs", "sum"),
        deliveries=("match_id", "size"),
        legal_balls=("is_legal_delivery", "sum"),
        wickets=("wicket_count", "sum"),
        fours=("is_boundary_4", "sum"),
        sixes=("is_boundary_6", "sum"),
    ).reset_index()
    phase["runs_per_legal_ball"] = phase.apply(
        lambda row: row["runs"] / row["legal_balls"] if row["legal_balls"] else None,
        axis=1,
    )
    phase["boundary_runs"] = 4 * phase["fours"] + 6 * phase["sixes"]
    return phase.sort_values(["season", "match_type", "batting_team", "phase"], na_position="last")


def build_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse all JSON matches in raw_dir and return named analytical tables."""
    json_files = sorted(raw_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(
            f"No .json match files found in {raw_dir}. Run scripts/download_data.py first."
        )

    match_rows: list[dict[str, Any]] = []
    innings_rows: list[dict[str, Any]] = []
    delivery_rows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []

    for path in json_files:
        try:
            match_row, match_innings, match_deliveries = parse_match(path)
            match_rows.append(match_row)
            innings_rows.extend(match_innings)
            delivery_rows.extend(match_deliveries)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            parse_errors.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})

    if parse_errors:
        error_text = "\n".join(f"- {item['file']}: {item['error']}" for item in parse_errors[:20])
        raise ValueError(f"Failed to parse {len(parse_errors)} file(s); no outputs written:\n{error_text}")

    matches = pd.DataFrame.from_records(match_rows)
    innings = pd.DataFrame.from_records(innings_rows)
    deliveries = pd.DataFrame.from_records(delivery_rows)

    batting_innings, batting_summary = _batting_tables(deliveries)
    bowling_innings, bowling_summary = _bowling_tables(deliveries)
    phase_summary = _phase_table(deliveries)

    return {
        "matches": matches,
        "innings_summary": innings,
        "deliveries": deliveries,
        "batting_innings": batting_innings,
        "batting_summary": batting_summary,
        "bowling_innings": bowling_innings,
        "bowling_summary": bowling_summary,
        "phase_summary": phase_summary,
    }


def quality_report(tables: dict[str, pd.DataFrame], raw_dir: Path) -> dict[str, Any]:
    """Create a compact inventory and set of basic quality checks."""
    matches = tables["matches"]
    deliveries = tables["deliveries"]
    innings = tables["innings_summary"]
    duplicate_match_ids = int(matches["match_id"].duplicated().sum()) if not matches.empty else 0
    gender_values = sorted(str(value) for value in matches["gender"].dropna().unique())
    type_values = sorted(str(value) for value in matches["match_type"].dropna().unique())
    season_counts = (
        matches.groupby("season", dropna=False).size().sort_index().to_dict()
        if not matches.empty else {}
    )
    legal_delivery_check = bool(
        deliveries.empty or (
            deliveries.loc[deliveries["is_legal_delivery"], "wides"].eq(0).all()
            and deliveries.loc[deliveries["is_legal_delivery"], "noballs"].eq(0).all()
        )
    )
    manifest_candidates = [raw_dir / "manifest.json", raw_dir.parent / f"{raw_dir.name}_source_manifest.json"]
    manifest = {}
    for manifest_path in manifest_candidates:
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                break
            except (OSError, json.JSONDecodeError):
                pass
    dataset_name = raw_dir.name
    return {
        "source": manifest.get("dataset_label", f"Cricsheet {dataset_name} JSON archive"),
        "source_url": manifest.get("source_url"),
        "archive_sha256": manifest.get("archive_sha256"),
        "raw_directory": str(raw_dir),
        "json_files_found": len(list(raw_dir.glob("*.json"))),
        "matches_parsed": int(len(matches)),
        "innings_parsed": int(len(innings)),
        "delivery_events_parsed": int(len(deliveries)),
        "gender_values": gender_values,
        "match_type_values": type_values,
        "matches_by_season": {str(key): int(value) for key, value in season_counts.items()},
        "duplicate_match_ids": duplicate_match_ids,
        "missing_match_dates": int(matches["date"].isna().sum()) if not matches.empty else 0,
        "missing_venues": int(matches["venue"].isna().sum()) if not matches.empty else 0,
        "legal_delivery_flag_check_passed": legal_delivery_check,
        "notes": [
            "Delivery rows represent recorded delivery events, not only legal balls.",
            "Overs are stored in cricket notation (e.g. 4.3), not decimal overs.",
            "No spatial ball-tracking fields are inferred by this pipeline.",
            "Powerplay/middle/death phases use conventional T20 and 50-over boundaries; other formats are marked not_applicable.",
            "Super-over events are labeled separately and excluded from ordinary innings phase analysis.",
            "Season/team/player aggregates are descriptive and are not predictive model outputs.",
        ],
    }
