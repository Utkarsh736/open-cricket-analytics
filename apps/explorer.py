"""Local Streamlit explorer for processed Cricsheet datasets."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = ROOT / "data" / "processed"
TABLES = [
    "matches", "innings_summary", "deliveries", "batting_innings", "batting_summary",
    "bowling_innings", "bowling_summary", "phase_summary", "team_summary",
    "venue_summary", "batter_bowler_matchups", "toss_summary", "season_summary",
]

st.set_page_config(page_title="Open Cricket Analytics", page_icon="🏏", layout="wide")
st.title("🏏 Open Cricket Analytics")
st.caption("Local explorer for your processed Cricsheet data. Descriptive metrics are not adjusted for match context unless explicitly stated.")


def read_csv_if_present(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, UnicodeDecodeError):
        return pd.DataFrame()


datasets = sorted(
    child.name for child in PROCESSED_ROOT.iterdir()
    if child.is_dir() and (child / "matches.csv").exists()
) if PROCESSED_ROOT.exists() else []

if not datasets:
    st.warning("No processed datasets found. Run `uv run python scripts/run_pipeline.py --dataset wpl` first.")
    st.stop()

selected_dataset = st.sidebar.selectbox("Dataset", datasets)
data_dir = PROCESSED_ROOT / selected_dataset
data = {name: read_csv_if_present(data_dir / f"{name}.csv") for name in TABLES}
matches = data["matches"]
innings = data["innings_summary"]
deliveries = data["deliveries"]
batting = data["batting_summary"]
bowling = data["bowling_summary"]
phase = data["phase_summary"]

# Apply format and gender filters when those dimensions exist in a table.
def options_for(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df:
        return []
    return sorted(str(value) for value in df[column].dropna().unique())

formats = options_for(matches, "match_type")
genders = options_for(matches, "gender")
selected_format = st.sidebar.selectbox("Match type", ["All"] + formats)
selected_gender = st.sidebar.selectbox("Gender", ["All"] + genders)


def filtered(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if selected_format != "All" and "match_type" in result:
        result = result[result["match_type"].astype(str) == selected_format]
    if selected_gender != "All" and "gender" in result:
        result = result[result["gender"].astype(str) == selected_gender]
    return result

filtered_matches = filtered(matches)
filtered_innings = filtered(innings)
filtered_deliveries = filtered(deliveries)
filtered_batting = filtered(batting)
filtered_bowling = filtered(bowling)
filtered_phase = filtered(phase)

first_date = "—"
last_date = "—"
if not filtered_matches.empty and "date" in filtered_matches:
    dates = pd.to_datetime(filtered_matches["date"], errors="coerce")
    if dates.notna().any():
        first_date = dates.min().date().isoformat()
        last_date = dates.max().date().isoformat()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Matches", f"{len(filtered_matches):,}")
m2.metric("Innings records", f"{len(filtered_innings):,}")
m3.metric("Recorded delivery events", f"{len(filtered_deliveries):,}")
m4.metric("Date range", f"{first_date} → {last_date}")

summary_tab, players_tab, teams_tab, match_tab, data_tab = st.tabs(
    ["Overview", "Players", "Teams & venues", "Match explorer", "Data tables"]
)

with summary_tab:
    left, right = st.columns(2)
    with left:
        st.subheader("Leading run scorers")
        if not filtered_batting.empty:
            top = filtered_batting.nlargest(15, "runs").sort_values("runs")
            st.plotly_chart(px.bar(top, x="runs", y="batter", orientation="h", hover_data=[c for c in ["innings", "average", "strike_rate", "fours", "sixes"] if c in top]), use_container_width=True)
        else:
            st.info("No batting summary rows for these filters.")
    with right:
        st.subheader("Leading wicket-takers")
        eligible = filtered_bowling[filtered_bowling.get("legal_balls", pd.Series(dtype=float)) >= 12] if not filtered_bowling.empty else filtered_bowling
        if not eligible.empty:
            top_bowlers = eligible.nlargest(15, "wickets").sort_values("wickets")
            st.plotly_chart(px.bar(top_bowlers, x="wickets", y="bowler", orientation="h", hover_data=[c for c in ["innings", "economy", "overs", "runs_conceded"] if c in top_bowlers]), use_container_width=True)
        else:
            st.info("No eligible bowling summary rows for these filters.")
    st.subheader("Scoring by innings phase")
    if not filtered_phase.empty and "phase" in filtered_phase:
        ordinary_phases = filtered_phase[~filtered_phase["phase"].isin(["super_over", "not_applicable", "other"])]
        if not ordinary_phases.empty:
            phase_plot = ordinary_phases.groupby("phase", as_index=False).agg(
                runs=("runs", "sum"), legal_balls=("legal_balls", "sum"), wickets=("wickets", "sum")
            )
            phase_plot["runs_per_over"] = 6 * phase_plot["runs"] / phase_plot["legal_balls"].where(phase_plot["legal_balls"] > 0)
            st.plotly_chart(px.bar(phase_plot, x="phase", y="runs_per_over", color="phase", hover_data=["runs", "legal_balls", "wickets"]), use_container_width=True)
        else:
            st.info("This format has no configured powerplay/middle/death phases.")
    st.caption("Phase definitions are conventional: six-over powerplay for T20 and ten-over powerplay for 50-over formats. Interpret them within format.")

with players_tab:
    st.subheader("Batter profile")
    if not filtered_batting.empty:
        search = st.text_input("Filter batter name", placeholder="Start typing a player name")
        options = sorted(filtered_batting[filtered_batting["batter"].astype(str).str.contains(search, case=False, na=False)]["batter"].dropna().astype(str).unique())
        if options:
            batter_name = st.selectbox("Batter", options)
            profile = filtered_batting[filtered_batting["batter"].astype(str) == batter_name].sort_values("runs", ascending=False)
            st.dataframe(profile, use_container_width=True, hide_index=True)
        else:
            st.info("No batter matches that search.")
    else:
        st.info("No batting data available.")

    st.subheader("Bowler profile")
    if not filtered_bowling.empty:
        bowl_search = st.text_input("Filter bowler name", placeholder="Start typing a player name", key="bowler_search")
        bowl_options = sorted(filtered_bowling[filtered_bowling["bowler"].astype(str).str.contains(bowl_search, case=False, na=False)]["bowler"].dropna().astype(str).unique())
        if bowl_options:
            bowler_name = st.selectbox("Bowler", bowl_options)
            profile = filtered_bowling[filtered_bowling["bowler"].astype(str) == bowler_name].sort_values("wickets", ascending=False)
            st.dataframe(profile, use_container_width=True, hide_index=True)
        else:
            st.info("No bowler matches that search.")
    else:
        st.info("No bowling data available.")

with teams_tab:
    team_summary = filtered(data["team_summary"])
    venue_summary = filtered(data["venue_summary"])
    if team_summary.empty:
        st.info("Run `uv run python scripts/build_descriptive_analytics.py --dataset <dataset>` to create Stage 2 team and venue tables.")
    else:
        st.subheader("Team summaries")
        st.dataframe(team_summary, use_container_width=True, hide_index=True)
        if "batting_run_rate" in team_summary:
            plot = team_summary.dropna(subset=["batting_run_rate"]).nlargest(15, "batting_run_rate")
            if not plot.empty:
                st.plotly_chart(px.bar(plot, x="team", y="batting_run_rate", color="match_type", hover_data=[c for c in ["matches", "wins", "runs_scored", "wickets_lost"] if c in plot]), use_container_width=True)
    st.subheader("Venue summaries")
    if venue_summary.empty:
        st.info("Venue summary not available yet.")
    else:
        st.dataframe(venue_summary, use_container_width=True, hide_index=True)

with match_tab:
    if filtered_matches.empty:
        st.info("No matches for these filters.")
    else:
        options = filtered_matches.sort_values("date", ascending=False, na_position="last")
        options["display"] = options.apply(
            lambda row: f"{row.get('date', 'unknown')} | {row.get('team_1', '?')} vs {row.get('team_2', '?')} | {row.get('venue', 'unknown')} | {row.get('match_id', '')}", axis=1
        )
        selected = st.selectbox("Choose match", options["display"].tolist())
        match_row = options.loc[options["display"] == selected].iloc[0]
        match_id = match_row["match_id"]
        st.json(match_row.drop(labels=["display"]).where(pd.notna(match_row), None).to_dict())
        match_innings = filtered_innings[filtered_innings["match_id"].astype(str) == str(match_id)]
        st.subheader("Innings")
        st.dataframe(match_innings, use_container_width=True, hide_index=True)
        match_deliveries = filtered_deliveries[filtered_deliveries["match_id"].astype(str) == str(match_id)]
        st.subheader("Delivery events")
        visible = [column for column in ["innings", "over_number", "delivery_sequence_in_over", "batter", "bowler", "batter_runs", "extras_runs", "total_runs", "wicket_kinds", "phase"] if column in match_deliveries]
        st.dataframe(match_deliveries[visible], use_container_width=True, hide_index=True)

with data_tab:
    available_tables = [name for name, frame in data.items() if not frame.empty]
    table_name = st.selectbox("Table", available_tables)
    frame = filtered(data[table_name])
    st.caption(f"{len(frame):,} rows × {len(frame.columns):,} columns · {table_name}.csv")
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button("Download current table as CSV", frame.to_csv(index=False).encode("utf-8"), file_name=f"{selected_dataset}_{table_name}.csv", mime="text/csv")
