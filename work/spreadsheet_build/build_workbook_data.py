#!/usr/bin/env python3
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "outputs" / "fantasy_baseball_analytics"
OUT = Path(__file__).resolve().parent / "analytics_workbook_data.json"

SHEETS = [
    ("Streaming Pitchers", "streaming_pitcher_analytics.csv"),
    ("Free Agent Pitchers", "free_agent_pitchers.csv"),
    ("Free Agent Hitters", "free_agent_hitters.csv"),
    ("Current Roster Pitchers", "current_roster_pitchers.csv"),
    ("Current Roster Hitters", "current_roster_hitters.csv"),
    ("All Pitchers", "pitcher_analytics.csv"),
    ("All Hitters", "hitter_analytics.csv"),
]


def sheet_matrix(filename):
    df = pd.read_csv(DATA_DIR / filename).fillna("")
    return [list(df.columns), *df.values.tolist()]


def main():
    payload = {sheet_name: sheet_matrix(filename) for sheet_name, filename in SHEETS}
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
