#!/usr/bin/env python3
import argparse
import html
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


OUT_DIR = Path(__file__).resolve().parent / "minor_league_hitter_stars"
FANGRAPHS_MINOR_LEAGUE_API = "https://www.fangraphs.com/api/leaders/minor-league/data"
FANGRAPHS_MINOR_LEAGUE_PAGE = "https://www.fangraphs.com/leaders/minor-league"

AFFILIATED_MINOR_LEAGUE_IDS = [
    2,
    4,
    5,
    6,
    7,
    11,
    14,
    13,
    8,
    9,
    10,
    16,
    17,
    30,
]
LEAGUE_REFERENCE = {
    2: {"League Name": "International League", "League Level": "AAA"},
    4: {"League Name": "Pacific Coast League", "League Level": "AAA"},
    5: {"League Name": "Eastern League", "League Level": "AA"},
    6: {"League Name": "Southern League", "League Level": "AA"},
    7: {"League Name": "Texas League", "League Level": "AA"},
    11: {"League Name": "Midwest League", "League Level": "A+"},
    14: {"League Name": "South Atlantic League", "League Level": "A+"},
    13: {"League Name": "Northwest League", "League Level": "A+"},
    8: {"League Name": "California League", "League Level": "A"},
    9: {"League Name": "Carolina League", "League Level": "A"},
    10: {"League Name": "Florida State League", "League Level": "A"},
    16: {"League Name": "Arizona Complex League", "League Level": "CPX"},
    17: {"League Name": "Florida Complex League", "League Level": "CPX"},
    30: {"League Name": "Dominican Summer League", "League Level": "R"},
}
DEFAULT_HITTING_WEIGHTS = {
    "1B": 2.5,
    "2B": 4.0,
    "3B": 6.0,
    "HR": 8.0,
    "R": 2.0,
    "RBI": 4.0,
    "BB": 2.0,
    "SO": -1.0,
    "SB": 5.0,
    "CS": -2.0,
    "HBP": 1.0,
    "GIDP": -1.0,
    "SH": 2.0,
}

REPORTS = {
    "standard": 0,
    "advanced": 1,
    "batted": 2,
}
REPORT_LABELS = {
    "standard": "Standard",
    "advanced": "Advanced",
    "batted": "Batted Ball",
}

PLAYER_KEY_CANDIDATES = [
    "playerid",
    "PlayerId",
    "player_id",
    "minor_league_player_id",
    "xMLBAMID",
    "MLBAMID",
]
MERGE_CONTEXT_COLUMNS = ["Player Name", "Team", "League", "Source League ID", "Age", "Season"]
REQUESTED_ADVANCED_COLUMNS = ["BB/K", "Spd", "wRC+"]
REQUESTED_BATTED_COLUMNS = ["HR/FB%", "IFFB%", "LD%", "GB%", "FB%"]
FANGRAPHS_POINTS_INPUTS = ["AB", "H", "2B", "3B", "HR", "BB", "HBP", "SB", "CS"]
ANALYTIC_COLUMNS = [
    "FGPts_per_game",
    "Approach_score",
    "Speed_score",
    "LD%",
    "HR_FB_pct",
]
WRC_CORRELATION_METRICS = ANALYTIC_COLUMNS[:]
PAIR_CORRELATIONS = []
PLUS_SCORE_METRICS = [
    "FGPts_per_game",
    "Approach_score",
    "Speed_score",
    "LD%",
    "HR_FB_pct",
]
ROBUST_Z_TRANSFORM_PARAMS = {
    "Age_Plus": {"median": 100.001659, "scale": 7.183389},
    "Approach_score_Plus": {"median": 86.680762, "scale": 43.002009},
    "Speed_score_Plus": {"median": 100.475905, "scale": 35.658575},
    "LD%_Plus": {"median": 99.581673, "scale": 14.380218},
    "HR_FB_pct_Plus": {"median": 88.611564, "scale": 52.365805},
}
ROBUST_Z_COMPOSITE_CAPS = {
    "Approach_score_Plus_RobustZ": 170,
    "LD%_Plus_RobustZ": 160,
    "HR_FB_pct_Plus_RobustZ": 160,
}
CSV_FILE_PATTERNS = [
    "{league}_{report}.csv",
    "{report}_{league}.csv",
    "fangraphs_{league}_{report}.csv",
    "fangraphs_{report}_{league}.csv",
    "{league}-{report}.csv",
    "{report}-{league}.csv",
]


def fetch_bytes(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/csv,text/plain,*/*",
            "Referer": FANGRAPHS_MINOR_LEAGUE_PAGE,
        },
    )
    with urlopen(req, timeout=60) as response:
        return response.read()


def fan_graphs_params(year, report_type, page, page_items, leagues, split_team):
    return {
        "pos": "all",
        "lg": ",".join(str(league) for league in leagues),
        "stats": "bat",
        "qual": "0",
        "type": report_type,
        "team": "",
        "season": year,
        "seasonEnd": year,
        "org": "",
        "ind": "0",
        "splitTeam": str(split_team).lower(),
        "players": "",
        "sort": "23,1",
        "page": page,
        "pageitems": page_items,
    }


def extract_rows(payload):
    if isinstance(payload, list):
        return payload, len(payload)
    if not isinstance(payload, dict):
        return [], 0
    for key in ["data", "Data", "leaders", "rows"]:
        rows = payload.get(key)
        if isinstance(rows, list):
            total = payload.get("total") or payload.get("Total") or payload.get("count") or len(rows)
            return rows, int(total)
    for value in payload.values():
        if isinstance(value, list) and (not value or isinstance(value[0], dict)):
            return value, len(value)
    return [], 0


def fetch_fangraphs_report(year, report_name, leagues, split_team=True, page_items=1000):
    frames = []
    page = 1
    total = None
    while True:
        params = fan_graphs_params(year, REPORTS[report_name], page, page_items, leagues, split_team)
        raw = fetch_bytes(f"{FANGRAPHS_MINOR_LEAGUE_API}?{urlencode(params)}")
        payload = json.loads(raw.decode("utf-8"))
        rows, total = extract_rows(payload)
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if total is not None and page * page_items >= total:
            break
        if len(rows) < page_items:
            break
        page += 1
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["Source Report"] = report_name
    if len(leagues) == 1:
        out["Source League ID"] = leagues[0]
    return out


def read_report(path):
    if not path:
        return None
    return pd.read_csv(path)


def latest_league_info_path():
    candidates = sorted((Path(__file__).resolve().parent / "fantrax_export").glob("raw_*/league_info.json"))
    return candidates[-1] if candidates else None


def scoring_weights_from_league_info(path=None):
    path = Path(path) if path else latest_league_info_path()
    if path is None or not path.exists():
        return DEFAULT_HITTING_WEIGHTS.copy()
    try:
        league_info = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_HITTING_WEIGHTS.copy()
    rules = league_info.get("scoringSystem", {}).get("scoringCategories", {}).get("HITTING", {})
    weights = {}
    for short_name, config in rules.items():
        raw = config.get("Default", "")
        if isinstance(raw, str) and raw.startswith("points"):
            try:
                weights[short_name] = float(raw.replace("points", "", 1))
            except ValueError:
                pass
    return {**DEFAULT_HITTING_WEIGHTS, **weights}


def parse_leagues(value):
    return [int(part) for part in str(value).split(",") if part.strip()]


def parse_paths(value):
    if not value:
        return []
    return [Path(part).expanduser() for part in str(value).split(",") if part.strip()]


def find_league_report_csv(csv_dir, league_id, report_name):
    if not csv_dir:
        return None
    for pattern in CSV_FILE_PATTERNS:
        candidate = csv_dir / pattern.format(league=league_id, report=report_name)
        if candidate.exists():
            return candidate
    report_label = REPORT_LABELS[report_name].lower().replace(" ", "_")
    for pattern in CSV_FILE_PATTERNS:
        candidate = csv_dir / pattern.format(league=league_id, report=report_label)
        if candidate.exists():
            return candidate
    return None


def complete_csv_leagues(csv_dir, leagues):
    return [
        league_id
        for league_id in leagues
        if all(find_league_report_csv(csv_dir, league_id, report_name) for report_name in REPORTS)
    ]


def read_league_report_csv(csv_dir, league_id, report_name):
    path = find_league_report_csv(csv_dir, league_id, report_name)
    if path is None:
        return None
    df = pd.read_csv(path)
    df["Source Report"] = report_name
    df["Source League ID"] = league_id
    return df


def fetch_or_read_report(year, report_name, leagues, split_team, csv_dir=None, supplied_csv=None):
    if supplied_csv:
        df = read_report(supplied_csv)
        df["Source Report"] = report_name
        return df
    frames = []
    missing_manual = []
    for league_id in leagues:
        manual = read_league_report_csv(csv_dir, league_id, report_name)
        if manual is not None:
            frames.append(manual)
            continue
        if csv_dir:
            missing_manual.append(league_id)
            continue
        frames.append(fetch_fangraphs_report(year, report_name, [league_id], split_team=split_team))
    if missing_manual:
        raise FileNotFoundError(
            f"Missing {report_name} CSVs for league IDs: {', '.join(str(league) for league in missing_manual)}"
        )
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def infer_year_from_path(path, fallback_year):
    match = re.search(r"(20\d{2})", str(path))
    return int(match.group(1)) if match else fallback_year


def build_players_from_csv_dir(csv_dir, year, leagues, hitting_weights=None, require_all=True):
    csv_dir = Path(csv_dir)
    usable_leagues = leagues if require_all else complete_csv_leagues(csv_dir, leagues)
    if not usable_leagues:
        raise FileNotFoundError(f"No complete per-league Standard/Advanced/Batted CSV sets found in {csv_dir}")
    reports = {
        report_name: fetch_or_read_report(
            year,
            report_name,
            usable_leagues,
            split_team=True,
            csv_dir=csv_dir,
        )
        for report_name in REPORTS
    }
    players = merge_reports(reports["standard"], reports["advanced"], reports["batted"])
    players = add_league_reference_columns(players)
    players = add_standard_analytics(players, hitting_weights=hitting_weights)
    players["Baseline Source Year"] = year
    return players


def print_export_urls(year, leagues):
    for league_id in leagues:
        print(f"League {league_id}")
        for report_name, report_type in REPORTS.items():
            params = fan_graphs_params(year, report_type, 1, 1000, [league_id], True)
            print(f"  {REPORT_LABELS[report_name]}: {FANGRAPHS_MINOR_LEAGUE_PAGE}?{urlencode(params)}")


def strip_html(value):
    if not isinstance(value, str):
        return value
    return re.sub(r"<[^>]+>", "", value).strip()


def clean_column_name(name):
    name = strip_html(str(name)).replace("\xa0", " ").strip()
    name = re.sub(r"\s+", " ", name)
    aliases = {
        "Name": "Player Name",
        "Player": "Player Name",
        "PlayerName": "Player Name",
        "TeamName": "Team",
        "Team Name": "Team",
        "Current Team": "Team",
        "team": "Team",
        "lg": "League",
        "League Name": "League",
        "AgeR": "Age",
        "SeasonMin": "Season",
        "SeasonMax": "Season",
        "HR/FB": "HR/FB%",
        "IFFB": "IFFB%",
        "LD": "LD%",
    }
    return aliases.get(name, name)


def normalize_columns(df):
    df = df.copy()
    df.columns = [clean_column_name(col) for col in df.columns]
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].map(strip_html)
    return df


def first_existing_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def normalize_player_name(df):
    if "Player Name" not in df.columns:
        player_col = first_existing_column(df, ["playerName", "PlayerNameRoute", "player_name"])
        if player_col:
            df["Player Name"] = df[player_col]
    if "Player Name" in df.columns:
        df["Player Name"] = df["Player Name"].astype(str).map(strip_html)
    return df


def coerce_numeric(value):
    if pd.isna(value):
        return math.nan
    if isinstance(value, (int, float)):
        return value
    cleaned = str(value).strip().replace(",", "")
    if cleaned in {"", "-", "--", "nan", "None"}:
        return math.nan
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        return float(cleaned)
    except ValueError:
        return math.nan


def normalize_numeric_columns(df):
    df = df.copy()
    for col in df.columns:
        if col in {"Player Name", "Team", "League", "Source Report"}:
            continue
        numeric = df[col].map(coerce_numeric)
        non_null_original = df[col].notna().sum()
        non_null_numeric = numeric.notna().sum()
        if non_null_original and non_null_numeric / non_null_original >= 0.7:
            df[col] = numeric
    return df


def percent_string_columns(df):
    cols = set()
    for col in df.columns:
        if not str(col).endswith("%"):
            continue
        values = df[col].dropna().astype(str)
        if values.str.contains("%", regex=False).any():
            cols.add(col)
    return cols


def normalize_rate_scales(df, literal_percent_cols=None):
    df = df.copy()
    literal_percent_cols = literal_percent_cols or set()
    for col in literal_percent_cols:
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        df[col] = df[col] / 100
    return df


def merge_key_columns(df):
    key_cols = [col for col in PLAYER_KEY_CANDIDATES if col in df.columns]
    if key_cols:
        key = key_cols[:1]
        for context_col in ["Source League ID", "League", "Team", "Season"]:
            if context_col in df.columns:
                key.append(context_col)
        return key
    fallback = [col for col in ["Player Name", "Team", "League", "Source League ID", "Age", "Season"] if col in df.columns]
    if "Player Name" not in fallback:
        raise ValueError("Could not identify a player key or Player Name column in FanGraphs data.")
    return fallback


def dedupe_columns(df):
    keep = []
    seen = set()
    for col in df.columns:
        if col in seen:
            continue
        keep.append(col)
        seen.add(col)
    return df[keep]


def prepare_report(df):
    df = normalize_columns(df)
    df = normalize_player_name(df)
    literal_percent_cols = percent_string_columns(df)
    df = normalize_numeric_columns(df)
    df = normalize_rate_scales(df, literal_percent_cols)
    return dedupe_columns(df)


def add_league_reference_columns(df):
    out = df.copy()
    if "Source League ID" not in out.columns:
        return out
    league_ids = pd.to_numeric(out["Source League ID"], errors="coerce")
    out["League Name"] = league_ids.map(
        lambda value: LEAGUE_REFERENCE.get(int(value), {}).get("League Name") if pd.notna(value) else None
    )
    out["League Level"] = league_ids.map(
        lambda value: LEAGUE_REFERENCE.get(int(value), {}).get("League Level") if pd.notna(value) else None
    )
    return out


def columns_for_report(df, report_name):
    if report_name == "standard":
        return list(df.columns)
    return list(df.columns)


def merge_reports(standard, advanced, batted):
    standard = prepare_report(standard)
    advanced = prepare_report(advanced)
    batted = prepare_report(batted)
    key_cols = merge_key_columns(standard)
    out = standard.copy()
    for report_name, report_df in [("advanced", advanced), ("batted", batted)]:
        report_cols = columns_for_report(report_df, report_name)
        usable = report_df[report_cols].copy()
        report_key = [col for col in key_cols if col in usable.columns]
        if not report_key:
            report_key = merge_key_columns(usable)
        duplicate_context = [col for col in MERGE_CONTEXT_COLUMNS if col in usable.columns and col not in report_key]
        if report_name == "advanced":
            rename_cols = {
                col: f"{col}_advanced"
                for col in ["PA", "AVG", "OBP", "OPS"]
                if col in usable.columns and col not in report_key
            }
            usable = usable.rename(columns=rename_cols)
        if report_name == "batted":
            rename_cols = {
                col: f"{col}_batted"
                for col in ["PA", "BABIP"]
                if col in usable.columns and col not in report_key
            }
            usable = usable.rename(columns=rename_cols)
        stat_cols = [col for col in usable.columns if col not in report_key + duplicate_context]
        usable = usable[report_key + stat_cols].drop_duplicates(report_key)
        out = out.merge(usable, on=report_key, how="left", suffixes=("", f"_{report_name}"))
    return out


def add_fantasy_points_estimate(df, hitting_weights=None):
    scoring_inputs = [
        ("1B", "1B"),
        ("2B", "2B"),
        ("3B", "3B"),
        ("HR", "HR"),
        ("R", "R"),
        ("RBI", "RBI"),
        ("BB", "BB"),
        ("SO", "SO"),
        ("SB", "SB"),
        ("CS", "CS"),
        ("HBP", "HBP"),
        ("GDP", "GIDP"),
        ("SH", "SH"),
    ]
    if not all(col in df.columns for col in ["AB", "H", "2B", "3B", "HR"]):
        return df
    hitting_weights = hitting_weights or DEFAULT_HITTING_WEIGHTS
    out = df.copy()
    for col in set([col for col, _ in scoring_inputs] + ["AB", "H"]):
        if col in out.columns:
            out[col] = out[col].map(coerce_numeric)
    out["1B"] = out["H"] - out["2B"] - out["3B"] - out["HR"]
    out["FGPts_est"] = sum(
        (out[col] if col in out.columns else pd.Series(0.0, index=out.index)) * hitting_weights.get(scoring_key, 0.0)
        for col, scoring_key in scoring_inputs
    )
    out["Fantasy Points Formula"] = "fantrax_hitting_categories"
    return out


def safe_divide(numerator, denominator):
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    result = numerator / denominator
    return result.where(denominator != 0)


def add_standard_analytics(df, hitting_weights=None):
    out = add_fantasy_points_estimate(df, hitting_weights=hitting_weights)
    if "FGPts_est" in out.columns and "G" in out.columns:
        out["FGPts_per_game"] = safe_divide(out["FGPts_est"], out["G"])
    if {"AB", "G"}.issubset(out.columns):
        out["AB_per_game"] = safe_divide(out["AB"], out["G"])
    if {"H", "AB"}.issubset(out.columns):
        out["BA"] = safe_divide(out["H"], out["AB"])
    if {"H", "BB", "HBP", "AB", "SF"}.issubset(out.columns):
        out["OBP"] = safe_divide(out["H"] + out["BB"] + out["HBP"], out["AB"] + out["BB"] + out["HBP"] + out["SF"])
    if {"1B", "2B", "3B", "HR", "AB"}.issubset(out.columns):
        total_bases = out["1B"] + 2 * out["2B"] + 3 * out["3B"] + 4 * out["HR"]
        out["SLP"] = safe_divide(total_bases, out["AB"])
    if {"OBP", "SLP"}.issubset(out.columns):
        out["OPS"] = out["OBP"] + out["SLP"]
    if {"BB", "SO"}.issubset(out.columns):
        out["BB_K_ratio"] = safe_divide(out["BB"], out["SO"])
    if "BB%" in out.columns:
        out["BB_pct"] = pd.to_numeric(out["BB%"], errors="coerce")
    elif {"BB", "PA"}.issubset(out.columns):
        out["BB_pct"] = safe_divide(out["BB"], out["PA"])
    if "K%" in out.columns:
        out["K_pct"] = pd.to_numeric(out["K%"], errors="coerce")
    elif {"SO", "PA"}.issubset(out.columns):
        out["K_pct"] = safe_divide(out["SO"], out["PA"])
    if {"BB_K_ratio", "BB_pct", "K_pct"}.issubset(out.columns):
        in_play_share = 1 - out["BB_pct"] - out["K_pct"]
        out["Approach_score"] = out["BB_K_ratio"] * in_play_share
        out["Approach_score"] = out["Approach_score"].replace([math.inf, -math.inf], math.nan)
    if "Spd" in out.columns:
        out["Speed_score"] = pd.to_numeric(out["Spd"], errors="coerce")
    if "HR/FB%" in out.columns:
        out["HR_FB_pct"] = pd.to_numeric(out["HR/FB%"], errors="coerce")
    if {"AB", "SO", "HR", "SF", "FB%"}.issubset(out.columns):
        estimated_bip = out["AB"] - out["SO"] - out["HR"] + out["SF"]
        out["Estimated BIP"] = estimated_bip.where(estimated_bip > 0)
        out["Estimated FB"] = out["Estimated BIP"] * pd.to_numeric(out["FB%"], errors="coerce")
    return out


def weighted_average(group, value_col, weight_col):
    values = pd.to_numeric(group[value_col], errors="coerce")
    weights = pd.to_numeric(group[weight_col], errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return math.nan
    return (values[valid] * weights[valid]).sum() / weights[valid].sum()


def weighted_average_nonzero(group, value_col, weight_col):
    values = pd.to_numeric(group[value_col], errors="coerce")
    weights = pd.to_numeric(group[weight_col], errors="coerce")
    valid = values.notna() & (values != 0) & weights.notna() & (weights > 0)
    if not valid.any():
        return math.nan
    return (values[valid] * weights[valid]).sum() / weights[valid].sum()


def sum_if_present(group, col):
    if col not in group.columns:
        return math.nan
    return pd.to_numeric(group[col], errors="coerce").sum()


def build_weighted_baseline_row(group):
    row = {
        "Players": len(group),
        "Total G": sum_if_present(group, "G"),
        "Total PA": sum_if_present(group, "PA"),
        "Total AB": sum_if_present(group, "AB"),
    }
    if "Age" in group.columns and "PA" in group.columns:
        row["Average Age"] = weighted_average(group, "Age", "PA")
    if {"FGPts_per_game", "G"}.issubset(group.columns):
        row["FGPts_per_game"] = weighted_average_nonzero(group, "FGPts_per_game", "G")
    elif {"FGPts_est", "G"}.issubset(group.columns):
        row["FGPts_per_game"] = sum_if_present(group, "FGPts_est") / row["Total G"] if row["Total G"] else math.nan
    if {"BB_K_ratio", "PA"}.issubset(group.columns):
        row["BB_K_ratio"] = weighted_average_nonzero(group, "BB_K_ratio", "PA")
    elif {"BB", "SO"}.issubset(group.columns):
        total_so = sum_if_present(group, "SO")
        row["BB_K_ratio"] = sum_if_present(group, "BB") / total_so if total_so else math.nan
    if "BB_pct" in group.columns and "PA" in group.columns:
        row["BB_pct"] = weighted_average_nonzero(group, "BB_pct", "PA")
    elif "BB%" in group.columns and "PA" in group.columns:
        row["BB_pct"] = weighted_average_nonzero(group, "BB%", "PA")
    if "K_pct" in group.columns and "PA" in group.columns:
        row["K_pct"] = weighted_average_nonzero(group, "K_pct", "PA")
    elif "K%" in group.columns and "PA" in group.columns:
        row["K_pct"] = weighted_average_nonzero(group, "K%", "PA")
    if "Approach_score" in group.columns and "PA" in group.columns:
        row["Approach_score"] = weighted_average_nonzero(group, "Approach_score", "PA")
    if "Spd" in group.columns and "PA" in group.columns:
        row["Speed_score"] = weighted_average_nonzero(group, "Spd", "PA")
    if "LD%" in group.columns and "PA" in group.columns:
        row["LD%"] = weighted_average_nonzero(group, "LD%", "PA")
    if "HR_FB_pct" in group.columns and "PA" in group.columns:
        row["HR_FB_pct"] = weighted_average_nonzero(group, "HR_FB_pct", "PA")
    elif "HR/FB%" in group.columns and "PA" in group.columns:
        row["HR_FB_pct"] = weighted_average_nonzero(group, "HR/FB%", "PA")
    if "wRC+" in group.columns and "PA" in group.columns:
        row["wRC+"] = weighted_average(group, "wRC+", "PA")
    return pd.Series(row)


def finite_metric_frame(players, metric, target="wRC+"):
    if metric not in players.columns or target not in players.columns:
        return pd.DataFrame(columns=[metric, target])
    frame = players[[metric, target]].apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([math.inf, -math.inf], math.nan).dropna()
    return frame


def finite_pair_frame(players, x_metric, y_metric):
    if x_metric not in players.columns or y_metric not in players.columns:
        return pd.DataFrame(columns=[x_metric, y_metric])
    frame = players[[x_metric, y_metric]].apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([math.inf, -math.inf], math.nan).dropna()
    return frame


def build_wrc_correlations(players):
    rows = []
    for metric in WRC_CORRELATION_METRICS:
        frame = finite_metric_frame(players, metric)
        corr = frame[metric].corr(frame["wRC+"]) if len(frame) >= 2 else math.nan
        rows.append({"Metric": metric, "wRC+ Correlation": corr, "N": len(frame)})
    return pd.DataFrame(rows)


def build_pair_correlations(players):
    rows = []
    for x_metric, y_metric in PAIR_CORRELATIONS:
        frame = finite_pair_frame(players, x_metric, y_metric)
        corr = frame[x_metric].corr(frame[y_metric]) if len(frame) >= 2 else math.nan
        rows.append({"X Metric": x_metric, "Y Metric": y_metric, "Correlation": corr, "N": len(frame)})
    return pd.DataFrame(rows)


def axis_bounds(series):
    series = pd.to_numeric(series, errors="coerce").replace([math.inf, -math.inf], math.nan).dropna()
    if series.empty:
        return 0.0, 1.0
    low = float(series.quantile(0.01))
    high = float(series.quantile(0.99))
    if not math.isfinite(low) or not math.isfinite(high) or low == high:
        low = float(series.min())
        high = float(series.max())
    if low == high:
        low -= 0.5
        high += 0.5
    padding = (high - low) * 0.06
    return low - padding, high + padding


def scale_value(value, low, high, start, end):
    if high == low:
        return (start + end) / 2
    clipped = min(max(value, low), high)
    return start + (clipped - low) / (high - low) * (end - start)


def scatter_panel(players, metric, corr, n):
    frame = finite_metric_frame(players, metric)
    width = 360
    height = 300
    left = 54
    right = 18
    top = 38
    bottom = 46
    plot_w = width - left - right
    plot_h = height - top - bottom
    x_low, x_high = axis_bounds(frame[metric])
    y_low, y_high = axis_bounds(frame["wRC+"])
    points = []
    for _, row in frame.iterrows():
        x = scale_value(row[metric], x_low, x_high, left, left + plot_w)
        y = scale_value(row["wRC+"], y_low, y_high, top + plot_h, top)
        points.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.2" fill="#2563eb" opacity="0.28" />')
    corr_text = "NA" if pd.isna(corr) else f"{corr:.3f}"
    title = html.escape(metric)
    return f"""
<svg class="panel" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title} versus wRC+">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
  <text x="{left}" y="22" font-size="15" font-weight="700" fill="#111827">{title} vs wRC+</text>
  <text x="{width - right}" y="22" text-anchor="end" font-size="12" fill="#4b5563">r={corr_text} | n={n}</text>
  <line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#9ca3af" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#9ca3af" />
  <text x="{left}" y="{height - 16}" font-size="11" fill="#4b5563">{x_low:.2f}</text>
  <text x="{left + plot_w}" y="{height - 16}" text-anchor="end" font-size="11" fill="#4b5563">{x_high:.2f}</text>
  <text x="10" y="{top + plot_h}" font-size="11" fill="#4b5563">{y_low:.0f}</text>
  <text x="10" y="{top + 4}" font-size="11" fill="#4b5563">{y_high:.0f}</text>
  {''.join(points)}
</svg>"""


def pair_scatter_panel(players, x_metric, y_metric, corr, n):
    frame = finite_pair_frame(players, x_metric, y_metric)
    width = 520
    height = 360
    left = 62
    right = 22
    top = 44
    bottom = 54
    plot_w = width - left - right
    plot_h = height - top - bottom
    x_low, x_high = axis_bounds(frame[x_metric])
    y_low, y_high = axis_bounds(frame[y_metric])
    points = []
    for _, row in frame.iterrows():
        x = scale_value(row[x_metric], x_low, x_high, left, left + plot_w)
        y = scale_value(row[y_metric], y_low, y_high, top + plot_h, top)
        points.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" fill="#0f766e" opacity="0.3" />')
    corr_text = "NA" if pd.isna(corr) else f"{corr:.3f}"
    title = f"{x_metric} vs {y_metric}"
    safe_title = html.escape(title)
    return f"""
<svg class="panel" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{safe_title}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
  <text x="{left}" y="26" font-size="16" font-weight="700" fill="#111827">{safe_title}</text>
  <text x="{width - right}" y="26" text-anchor="end" font-size="12" fill="#4b5563">r={corr_text} | n={n}</text>
  <line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#9ca3af" />
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#9ca3af" />
  <text x="{left}" y="{height - 18}" font-size="11" fill="#4b5563">{x_low:.3f}</text>
  <text x="{left + plot_w}" y="{height - 18}" text-anchor="end" font-size="11" fill="#4b5563">{x_high:.3f}</text>
  <text x="{left + plot_w / 2}" y="{height - 10}" text-anchor="middle" font-size="12" fill="#374151">{html.escape(x_metric)}</text>
  <text x="12" y="{top + plot_h}" font-size="11" fill="#4b5563">{y_low:.3f}</text>
  <text x="12" y="{top + 4}" font-size="11" fill="#4b5563">{y_high:.3f}</text>
  <text x="14" y="{top + plot_h / 2}" transform="rotate(-90 14 {top + plot_h / 2})" text-anchor="middle" font-size="12" fill="#374151">{html.escape(y_metric)}</text>
  {''.join(points)}
</svg>"""


def write_wrc_correlation_outputs(players, year, out_dir):
    correlations = build_wrc_correlations(players)
    correlations_path = out_dir / f"wrc_metric_correlations_{year}.csv"
    scatter_path = out_dir / f"wrc_metric_scatterplots_{year}.html"
    correlations.to_csv(correlations_path, index=False)
    panels = []
    for row in correlations.to_dict("records"):
        panels.append(scatter_panel(players, row["Metric"], row["wRC+ Correlation"], row["N"]))
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Minor League Hitter Metrics vs wRC+ ({year})</title>
  <style>
    body {{ margin: 24px; font-family: Arial, sans-serif; color: #111827; background: #f8fafc; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    p {{ margin: 0 0 20px; color: #4b5563; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
    .panel {{ border: 1px solid #d1d5db; background: #fff; }}
  </style>
</head>
<body>
  <h1>Minor League Hitter Metrics vs wRC+ ({year})</h1>
  <p>League-agnostic player-row scatterplots. Axis ranges use the 1st and 99th percentiles for readability; correlations use all finite player rows.</p>
  <div class="grid">
    {''.join(panels)}
  </div>
</body>
</html>
"""
    scatter_path.write_text(html_doc, encoding="utf-8")
    return correlations_path, scatter_path


def write_pair_correlation_outputs(players, year, out_dir):
    correlations = build_pair_correlations(players)
    correlations_path = out_dir / f"metric_pair_correlations_{year}.csv"
    scatter_path = out_dir / f"metric_pair_scatterplots_{year}.html"
    correlations.to_csv(correlations_path, index=False)
    panels = []
    for row in correlations.to_dict("records"):
        panels.append(pair_scatter_panel(players, row["X Metric"], row["Y Metric"], row["Correlation"], row["N"]))
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Minor League Hitter Metric Pair Correlations ({year})</title>
  <style>
    body {{ margin: 24px; font-family: Arial, sans-serif; color: #111827; background: #f8fafc; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    p {{ margin: 0 0 20px; color: #4b5563; }}
    .panel {{ border: 1px solid #d1d5db; background: #fff; }}
  </style>
</head>
<body>
  <h1>Minor League Hitter Metric Pair Correlations ({year})</h1>
  <p>League-agnostic player-row scatterplots. Axis ranges use the 1st and 99th percentiles for readability; correlations use all finite player rows.</p>
  {''.join(panels)}
</body>
</html>
"""
    scatter_path.write_text(html_doc, encoding="utf-8")
    return correlations_path, scatter_path


def league_group_columns(players):
    if "Source League ID" in players.columns:
        group_cols = ["Source League ID"]
        if "League Name" in players.columns:
            group_cols.append("League Name")
        if "League Level" in players.columns:
            group_cols.append("League Level")
        return group_cols
    if "League" in players.columns:
        return ["League"]
    raise ValueError("Need League or Source League ID to build league baselines.")


def league_group_column(players):
    group_cols = league_group_columns(players)
    if not group_cols:
        raise ValueError("Need League or Source League ID to build league baselines.")
    return group_cols[0]


def build_weighted_baselines(players, group_cols):
    grouped = players.groupby(group_cols, dropna=False)
    return grouped.apply(build_weighted_baseline_row, include_groups=False).reset_index()


def build_league_age_baselines(players):
    group_cols = league_group_columns(players) + (["Age"] if "Age" in players.columns else [])
    if "Age" not in group_cols:
        raise ValueError("Need League or Source League ID plus Age to build league-age baselines.")
    baselines = build_weighted_baselines(players, group_cols)
    if "Average Age" in baselines.columns:
        baselines["Average Age"] = baselines["Average Age"].fillna(baselines["Age"])
    else:
        baselines["Average Age"] = baselines["Age"]
    return baselines


def build_league_baselines(players):
    return build_weighted_baselines(players, league_group_columns(players))


def team_league_game_columns(players):
    out = players.copy()
    if "G" not in out.columns or "Team" not in out.columns:
        return out
    league_cols = league_group_columns(out)
    group_cols = league_cols + ["Team"]
    out["Team League Max G"] = out.groupby(group_cols, dropna=False)["G"].transform("max")
    out["Player Team Game Share"] = safe_divide(out["G"], out["Team League Max G"])
    return out


def baseline_lookup_key(row, key_cols, include_age=False):
    values = []
    for col in key_cols:
        values.append(row.get(col))
    if include_age:
        values.append(row.get("Age"))
    return tuple(values)


def baseline_metric_columns():
    return ["Average Age"] + PLUS_SCORE_METRICS + ["wRC+"]


def build_baseline_lookup(baselines, key_cols, include_age=False):
    lookup = {}
    needed = key_cols + (["Age"] if include_age else [])
    value_cols = [col for col in baseline_metric_columns() if col in baselines.columns]
    for _, row in baselines.iterrows():
        key = baseline_lookup_key(row, needed, include_age=False)
        lookup[key] = {col: row.get(col) for col in value_cols}
    return lookup


def plus_score(value, baseline, inverse=False):
    value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    baseline = pd.to_numeric(pd.Series([baseline]), errors="coerce").iloc[0]
    if pd.isna(value) or pd.isna(baseline) or value == 0 and inverse or baseline == 0 and not inverse:
        return math.nan
    if inverse:
        return baseline / value * 100 if value else math.nan
    return value / baseline * 100


def hr_fb_plus_score(value, baseline, home_runs, estimated_fb):
    home_runs = pd.to_numeric(pd.Series([home_runs]), errors="coerce").iloc[0]
    estimated_fb = pd.to_numeric(pd.Series([estimated_fb]), errors="coerce").iloc[0]
    if pd.notna(home_runs) and home_runs == 0:
        if pd.notna(estimated_fb) and estimated_fb > 1:
            return 0
        return 100
    return plus_score(value, baseline)


def robust_z_plus(series, median, scale):
    values = pd.to_numeric(series, errors="coerce")
    if not scale:
        return pd.Series(100, index=values.index, dtype=float)
    return 100 + 15 * ((values - median) / scale)


def add_baseline_comparison_columns(players, league_age_baselines, league_baselines):
    out = team_league_game_columns(players)
    key_cols = ["Source League ID"] if "Source League ID" in out.columns else ["League"]
    league_lookup = build_baseline_lookup(league_baselines, key_cols)

    baseline_rows = []
    for _, row in out.iterrows():
        league_key = baseline_lookup_key(row, key_cols)
        baseline = league_lookup.get(league_key, {})
        scope = "league"
        baseline_rows.append((baseline, scope))

    out["Baseline Scope"] = [scope for _, scope in baseline_rows]
    for metric in baseline_metric_columns():
        out[f"Baseline {metric}"] = [baseline.get(metric, math.nan) for baseline, _ in baseline_rows]

    out["Age_Plus"] = [
        plus_score(player_age, baseline_age, inverse=True)
        for player_age, baseline_age in zip(out.get("Age", pd.Series(index=out.index)), out["Baseline Average Age"])
    ]
    for metric in PLUS_SCORE_METRICS:
        if metric in out.columns:
            if metric == "HR_FB_pct":
                out[f"{metric}_Plus"] = [
                    hr_fb_plus_score(value, baseline, home_runs, estimated_fb)
                    for value, baseline, home_runs, estimated_fb in zip(
                        out[metric],
                        out[f"Baseline {metric}"],
                        out.get("HR", pd.Series(index=out.index)),
                        out.get("Estimated FB", pd.Series(index=out.index)),
                    )
                ]
            elif metric == "K_pct":
                out[f"{metric}_Plus"] = [
                    plus_score(value, baseline, inverse=True)
                    for value, baseline in zip(out[metric], out[f"Baseline {metric}"])
                ]
            else:
                out[f"{metric}_Plus"] = [
                    plus_score(value, baseline)
                    for value, baseline in zip(out[metric], out[f"Baseline {metric}"])
                ]
            out[f"{metric}_Plus"] = out[f"{metric}_Plus"].fillna(100)
    if "wRC+" in out.columns:
        out["wRC+_Score"] = pd.to_numeric(out["wRC+"], errors="coerce")
    for col, params in ROBUST_Z_TRANSFORM_PARAMS.items():
        if col in out.columns:
            out[f"{col}_RobustZ"] = robust_z_plus(out[col], params["median"], params["scale"])
    for col, cap in ROBUST_Z_COMPOSITE_CAPS.items():
        if col in out.columns:
            out[f"{col}_Capped"] = pd.to_numeric(out[col], errors="coerce").clip(upper=cap)
    composite_groups = {
        "5 Tool+": [
            "Age_Plus_RobustZ",
            "Approach_score_Plus_RobustZ_Capped",
            "Speed_score_Plus_RobustZ",
            "LD%_Plus_RobustZ_Capped",
            "HR_FB_pct_Plus_RobustZ_Capped",
        ],
        "Hitter+": [
            "Approach_score_Plus_RobustZ_Capped",
            "LD%_Plus_RobustZ_Capped",
            "HR_FB_pct_Plus_RobustZ_Capped",
        ],
    }
    for score_col, component_cols in composite_groups.items():
        if all(col in out.columns for col in component_cols):
            components = out[component_cols].apply(pd.to_numeric, errors="coerce")
            out[score_col] = components.sum(axis=1, min_count=len(component_cols)) / len(component_cols)
    return out


def write_combined_baseline_outputs(players, target_year, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    league_age_baselines = build_league_age_baselines(players)
    league_baselines = build_league_baselines(players)
    league_age_path = out_dir / f"combined_league_age_hitter_baselines_through_{target_year}.csv"
    league_path = out_dir / f"combined_league_hitter_baselines_through_{target_year}.csv"
    league_age_baselines.to_csv(league_age_path, index=False)
    league_baselines.to_csv(league_path, index=False)
    return league_age_path, league_path, league_age_baselines, league_baselines


def write_player_comparison_output(players, league_age_baselines, league_baselines, year, out_dir):
    compared = add_baseline_comparison_columns(players, league_age_baselines, league_baselines)
    sort_cols = [
        col
        for col in [
            "League Level",
            "League Name",
            "Source League ID",
            "League",
            "Age",
            "wRC+_Score",
            "Player Name",
            "Team",
        ]
        if col in compared.columns
    ]
    if sort_cols:
        ascending = [True] * len(sort_cols)
        if "wRC+_Score" in sort_cols:
            ascending[sort_cols.index("wRC+_Score")] = False
        compared = compared.sort_values(sort_cols, ascending=ascending, kind="stable")
    path = out_dir / f"minor_league_hitters_{year}_plus_vs_combined_baseline.csv"
    compared.to_csv(path, index=False)
    return path


def write_outputs(players, year, out_dir, hitting_weights=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    players = add_league_reference_columns(players)
    players = add_standard_analytics(players, hitting_weights=hitting_weights)
    players = team_league_game_columns(players)
    sort_cols = [col for col in ["League Level", "League Name", "Source League ID", "League", "Age", "Player Name", "Team"] if col in players.columns]
    if sort_cols:
        players = players.sort_values(sort_cols, kind="stable")
    league_age_baselines = build_league_age_baselines(players)
    league_baselines = build_league_baselines(players)
    correlations_path, scatter_path = write_wrc_correlation_outputs(players, year, out_dir)
    pair_correlations_path, pair_scatter_path = write_pair_correlation_outputs(players, year, out_dir)
    players_path = out_dir / f"minor_league_hitters_{year}.csv"
    league_age_baselines_path = out_dir / f"league_age_hitter_baselines_{year}.csv"
    league_baselines_path = out_dir / f"league_hitter_baselines_{year}.csv"
    players.to_csv(players_path, index=False)
    league_age_baselines.to_csv(league_age_baselines_path, index=False)
    league_baselines.to_csv(league_baselines_path, index=False)
    return (
        players_path,
        league_age_baselines_path,
        league_baselines_path,
        correlations_path,
        scatter_path,
        pair_correlations_path,
        pair_scatter_path,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pull FanGraphs minor-league hitter stats and build league-by-age baselines."
    )
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--leagues", default=",".join(str(league) for league in AFFILIATED_MINOR_LEAGUE_IDS))
    parser.add_argument("--combined-teams", action="store_true", help="Aggregate players across teams instead of splitting rows by team.")
    parser.add_argument("--combined-leagues", action="store_true", help="Pull/export all requested leagues as one combined leaderboard. Off by default because it can blend players who changed leagues.")
    parser.add_argument("--csv-dir", type=Path, help="Directory with per-league FanGraphs exports named like 2_standard.csv, standard_2.csv, fangraphs_2_standard.csv, etc.")
    parser.add_argument("--print-export-urls", action="store_true", help="Print one FanGraphs leaderboard URL per league/report and exit.")
    parser.add_argument("--league-info-json", type=Path, help="Fantrax league_info.json with scoring weights. Defaults to the latest local Fantrax export.")
    parser.add_argument("--standard-csv", type=Path, help="Use a downloaded FanGraphs Standard CSV instead of the API.")
    parser.add_argument("--advanced-csv", type=Path, help="Use a downloaded FanGraphs Advanced CSV instead of the API.")
    parser.add_argument("--batted-csv", type=Path, help="Use a downloaded FanGraphs Batted Ball CSV instead of the API.")
    parser.add_argument(
        "--combined-baseline-csv-dirs",
        help=(
            "Comma-separated per-year FanGraphs export folders to combine into current baselines, "
            "for example fangraphs_exports/2025,fangraphs_exports/2026. Incomplete folders use only "
            "leagues with all three report CSVs."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    leagues = parse_leagues(args.leagues)
    if args.print_export_urls:
        print_export_urls(args.year, leagues)
        return 0
    supplied = {
        "standard": args.standard_csv,
        "advanced": args.advanced_csv,
        "batted": args.batted_csv,
    }
    reports = {}
    try:
        for report_name in REPORTS:
            if args.combined_leagues and not args.csv_dir:
                if supplied[report_name]:
                    reports[report_name] = read_report(supplied[report_name])
                    reports[report_name]["Source Report"] = report_name
                else:
                    reports[report_name] = fetch_fangraphs_report(
                        args.year,
                        report_name,
                        leagues,
                        split_team=not args.combined_teams,
                    )
            else:
                reports[report_name] = fetch_or_read_report(
                    args.year,
                    report_name,
                    leagues,
                    not args.combined_teams,
                    csv_dir=args.csv_dir,
                    supplied_csv=supplied[report_name],
                )
    except Exception as exc:
        print(
            "FanGraphs data pull failed. If this is a 403, download separate FanGraphs minor-league "
            "CSV reports for each league/report and rerun with --csv-dir.",
            file=sys.stderr,
        )
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    players = merge_reports(reports["standard"], reports["advanced"], reports["batted"])
    hitting_weights = scoring_weights_from_league_info(args.league_info_json)
    (
        players_path,
        league_age_baselines_path,
        league_baselines_path,
        correlations_path,
        scatter_path,
        pair_correlations_path,
        pair_scatter_path,
    ) = write_outputs(players, args.year, args.out_dir, hitting_weights=hitting_weights)
    print(f"Wrote {players_path}")
    print(f"Wrote {league_age_baselines_path}")
    print(f"Wrote {league_baselines_path}")
    print(f"Wrote {correlations_path}")
    print(f"Wrote {scatter_path}")
    print(f"Wrote {pair_correlations_path}")
    print(f"Wrote {pair_scatter_path}")
    baseline_csv_dirs = parse_paths(args.combined_baseline_csv_dirs)
    if baseline_csv_dirs:
        baseline_frames = []
        for csv_dir in baseline_csv_dirs:
            baseline_year = infer_year_from_path(csv_dir, args.year)
            baseline_players = build_players_from_csv_dir(
                csv_dir,
                baseline_year,
                leagues,
                hitting_weights=hitting_weights,
                require_all=False,
            )
            baseline_frames.append(baseline_players)
        combined_players = pd.concat(baseline_frames, ignore_index=True)
        (
            combined_league_age_path,
            combined_league_path,
            combined_league_age_baselines,
            combined_league_baselines,
        ) = write_combined_baseline_outputs(combined_players, args.year, args.out_dir)
        current_players = add_league_reference_columns(players)
        current_players = add_standard_analytics(current_players, hitting_weights=hitting_weights)
        current_players["Baseline Source Year"] = args.year
        player_comparison_path = write_player_comparison_output(
            current_players,
            combined_league_age_baselines,
            combined_league_baselines,
            args.year,
            args.out_dir,
        )
        print(f"Wrote {combined_league_age_path}")
        print(f"Wrote {combined_league_path}")
        print(f"Wrote {player_comparison_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
