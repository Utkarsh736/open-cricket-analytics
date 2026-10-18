from __future__ import annotations

import json
from pathlib import Path

import pytest

from cricket_analytics.pipeline import build_tables, parse_match, quality_report
from cricket_analytics.report import build_quick_report


@pytest.fixture
def sample_match(tmp_path: Path) -> Path:
    match = {
        "meta": {"data_version": "1.3.0"},
        "info": {
            "dates": ["2024-03-01"],
            "season": "2024",
            "gender": "female",
            "match_type": "T20",
            "venue": "Test Ground",
            "teams": ["A", "B"],
            "toss": {"winner": "A", "decision": "bat"},
            "outcome": {"winner": "A"},
            "registry": {"people": {}},
        },
        "innings": [
            {
                "team": "A",
                "overs": [
                    {"over": 0, "deliveries": [
                        {
                            "actual_delivery": "0.1", "batter": "Alice", "bowler": "Bea",
                            "non_striker": "Cara", "runs": {"batter": 4, "extras": 0, "total": 4},
                        },
                        {
                            "actual_delivery": "0.2", "batter": "Alice", "bowler": "Bea",
                            "non_striker": "Cara", "extras": {"wides": 1},
                            "runs": {"batter": 0, "extras": 1, "total": 1},
                        },
                        {
                            "actual_delivery": "0.2", "batter": "Alice", "bowler": "Bea",
                            "non_striker": "Cara", "extras": {"noballs": 1},
                            "runs": {"batter": 1, "extras": 1, "total": 2},
                        },
                        {
                            "actual_delivery": "0.3", "batter": "Alice", "bowler": "Bea",
                            "non_striker": "Cara", "runs": {"batter": 0, "extras": 0, "total": 0},
                            "wickets": [{"kind": "bowled", "player_out": "Alice"}],
                        },
                    ]}
                ],
            },
            {
                "team": "B",
                "target": {"runs": 8, "overs": 20},
                "overs": [{"over": 0, "deliveries": [
                    {
                        "actual_delivery": "0.1", "batter": "Bea", "bowler": "Alice",
                        "non_striker": "Cara", "runs": {"batter": 6, "extras": 0, "total": 6},
                    },
                ]}],
            },
        ],
    }
    path = tmp_path / "test_match.json"
    path.write_text(json.dumps(match), encoding="utf-8")
    return path


def test_parse_counts_legal_balls_and_runs(sample_match: Path) -> None:
    _, innings, deliveries = parse_match(sample_match)
    first_innings = innings[0]
    assert first_innings["runs_from_deliveries"] == 7
    assert first_innings["wickets"] == 1
    assert first_innings["legal_balls"] == 2  # wide and no-ball do not count
    assert len(deliveries) == 5
    assert [row["is_legal_delivery"] for row in deliveries[:4]] == [True, False, False, True]


def test_build_outputs_basic_metrics(sample_match: Path, tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / sample_match.name).write_text(sample_match.read_text(encoding="utf-8"), encoding="utf-8")
    tables = build_tables(raw)

    alice = tables["batting_summary"].set_index("batter").loc["Alice"]
    assert alice["runs"] == 5
    assert alice["balls_faced"] == 3  # wide excluded, no-ball counts as faced
    assert alice["dismissals"] == 1

    bea = tables["bowling_summary"].set_index("bowler").loc["Bea"]
    assert bea["legal_balls"] == 2
    assert bea["runs_conceded"] == 7  # 4 + wide + (1 batter run + 1 no-ball extra)
    assert bea["wickets"] == 1
    assert bea["overs"] == "0.2"


def test_batting_strike_rate_and_boundary_flags(sample_match: Path, tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / sample_match.name).write_text(sample_match.read_text(encoding="utf-8"), encoding="utf-8")
    tables = build_tables(raw)
    alice = tables["batting_summary"].set_index("batter").loc["Alice"]
    assert alice["fours"] == 1
    assert alice["sixes"] == 0
    assert alice["strike_rate"] == pytest.approx(166.6666667)


def test_missing_raw_directory_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_tables(tmp_path / "does-not-exist")


def test_quick_report_is_generated(sample_match: Path, tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / sample_match.name).write_text(sample_match.read_text(encoding="utf-8"), encoding="utf-8")
    tables = build_tables(raw)
    out = tmp_path / "processed"
    out.mkdir()
    for table_name, frame in tables.items():
        frame.to_csv(out / f"{table_name}.csv", index=False)
    (out / "quality_report.json").write_text(
        json.dumps(quality_report(tables, raw)), encoding="utf-8"
    )
    report_path = build_quick_report(out)
    content = report_path.read_text(encoding="utf-8")
    assert "Leading run scorers" in content
    assert "Cricsheet" in content


def test_format_aware_phase_labels() -> None:
    from cricket_analytics.pipeline import _phase

    assert _phase(0, "T20") == "powerplay"
    assert _phase(6, "T20") == "middle"
    assert _phase(15, "T20") == "death"
    assert _phase(9, "ODI") == "powerplay"
    assert _phase(10, "ODI") == "middle"
    assert _phase(40, "ODI") == "death"
    assert _phase(0, "Test") == "not_applicable"
    assert _phase(0, "T20", is_super_over=True) == "super_over"


def test_stage2_descriptive_tables(sample_match: Path, tmp_path: Path) -> None:
    from cricket_analytics.descriptive import build_descriptive_tables

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / sample_match.name).write_text(sample_match.read_text(encoding="utf-8"), encoding="utf-8")
    tables = build_tables(raw)
    outputs = build_descriptive_tables(tables)

    assert set(outputs) == {
        "team_summary", "venue_summary", "batter_bowler_matchups", "toss_summary", "season_summary"
    }
    assert set(outputs["team_summary"]["team"]) == {"A", "B"}
    venue = outputs["venue_summary"].iloc[0]
    assert venue["venue"] == "Test Ground"
    matchup = outputs["batter_bowler_matchups"].query("batter == 'Alice' and bowler == 'Bea'").iloc[0]
    assert matchup["runs"] == 5
    assert matchup["balls_faced"] == 3
