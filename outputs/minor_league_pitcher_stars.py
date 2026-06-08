#!/usr/bin/env python3
import argparse
import importlib.util
import json
import math
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd


THIS_DIR = Path(__file__).resolve().parent
HITTER_SCRIPT = THIS_DIR / "minor_league_hitter_stars.py"
spec = importlib.util.spec_from_file_location("minor_league_hitter_stars_shared", HITTER_SCRIPT)
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)

OUT_DIR = THIS_DIR / "minor_league_pitcher_stars"
FANGRAPHS_MINOR_LEAGUE_PAGE = "https://www.fangraphs.com/leaders/minor-league"
AFFILIATED_MINOR_LEAGUE_IDS = shared.AFFILIATED_MINOR_LEAGUE_IDS
LEAGUE_REFERENCE = shared.LEAGUE_REFERENCE
REPORTS = shared.REPORTS

DEFAULT_PITCHING_WEIGHTS = {
    "IP": 3.0,
    "W": 8.0,
    "L": -2.0,
    "SV": 12.0,
    "HLD": 6.0,
    "BS": -3.5,
    "ER": -2.0,
    "H": -0.25,
    "BB": -0.25,
    "K": 3.0,
    "BK": -1.0,
    "CG": 2.0,
    "QA3": 8.0,
    "NH": 5.0,
    "PG": 10.0,
}

PLUS_SCORE_METRICS = [
    "FGPts_per_game",
    "K_BB_pct",
    "Weak_Contact",
]
ROBUST_Z_COMPONENT_COLUMNS = [
    "Age_Plus",
    "K_BB_pct_Plus",
    "Weak_Contact_Plus",
]
ROBUST_Z_CAP_COMPONENTS = [
    "K_BB_pct_Plus_RobustZ",
    "Weak_Contact_Plus_RobustZ",
]


def latest_league_info_path():
    return shared.latest_league_info_path()


def scoring_weights_from_league_info(path=None):
    path = path or latest_league_info_path()
    if not path or not Path(path).exists():
        return DEFAULT_PITCHING_WEIGHTS.copy()
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_PITCHING_WEIGHTS.copy()
    weights = {}
    rules = payload.get("scoringSystem", {}).get("scoringCategories", {}).get("PITCHING", {})
    for key, config in rules.items():
        raw = config.get("Default", "") if isinstance(config, dict) else ""
        if isinstance(raw, str) and raw.startswith("points"):
            try:
                weights[key] = float(raw.replace("points", "", 1))
            except ValueError:
                pass
    legacy = payload.get("scoring_categories", {}).get("PITCHING", {})
    for key, config in legacy.items():
        if isinstance(config, dict) and "points" in config:
            try:
                weights.setdefault(key, float(config["points"]))
            except (TypeError, ValueError):
                pass
    weights.setdefault("SO", weights.get("K", DEFAULT_PITCHING_WEIGHTS["K"]))
    return {**DEFAULT_PITCHING_WEIGHTS, **weights}


def parse_leagues(value):
    return shared.parse_leagues(value)


def parse_paths(value):
    return shared.parse_paths(value)


def print_export_urls(year, leagues):
    for league_id in leagues:
        for report_name, report_type in REPORTS.items():
            params = {
                "pos": "all",
                "lg": str(league_id),
                "stats": "pit",
                "qual": "0",
                "type": str(report_type),
                "team": "",
                "season": str(year),
                "seasonEnd": str(year),
                "org": "",
                "ind": "0",
                "splitTeam": "true",
                "players": "",
                "sort": "23,1",
                "page": "1",
                "pageitems": "1000",
            }
            print(f"{league_id} {report_name}: {FANGRAPHS_MINOR_LEAGUE_PAGE}?{urlencode(params)}")


def complete_csv_leagues(csv_dir, leagues):
    return shared.complete_csv_leagues(csv_dir, leagues)


def read_league_report_csv(csv_dir, league_id, report_name):
    return shared.read_league_report_csv(csv_dir, league_id, report_name)


def merge_key_value(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def normalize_merge_key_types(df):
    out = df.copy()
    for col in shared.PLAYER_KEY_CANDIDATES:
        if col in out.columns:
            out[col] = out[col].map(merge_key_value)
    return out


def merge_pitcher_reports(standard, advanced, batted):
    standard = normalize_merge_key_types(shared.prepare_report(standard))
    advanced = normalize_merge_key_types(shared.prepare_report(advanced))
    batted = normalize_merge_key_types(shared.prepare_report(batted))
    key_cols = shared.merge_key_columns(standard)
    out = standard.copy()
    for report_name, report_df in [("advanced", advanced), ("batted", batted)]:
        usable = report_df.copy()
        report_key = [col for col in key_cols if col in usable.columns]
        if not report_key:
            report_key = shared.merge_key_columns(usable)
        duplicate_context = [
            col for col in shared.MERGE_CONTEXT_COLUMNS if col in usable.columns and col not in report_key
        ]
        stat_cols = [col for col in usable.columns if col not in report_key + duplicate_context]
        usable = usable[report_key + stat_cols].drop_duplicates(report_key)
        out = out.merge(usable, on=report_key, how="left", suffixes=("", f"_{report_name}"))
    return out


def read_reports_from_csv_dir(csv_dir, year, leagues, require_all=True):
    csv_dir = Path(csv_dir)
    usable_leagues = complete_csv_leagues(csv_dir, leagues) if require_all else leagues
    if require_all and not usable_leagues:
        raise FileNotFoundError(f"No leagues in {csv_dir} have all required pitcher report CSVs.")
    frames = []
    for league_id in usable_leagues:
        standard = read_league_report_csv(csv_dir, league_id, "standard")
        advanced = read_league_report_csv(csv_dir, league_id, "advanced")
        batted = read_league_report_csv(csv_dir, league_id, "batted")
        merged = merge_pitcher_reports(standard, advanced, batted)
        merged["Source League ID"] = league_id
        merged["Source Year"] = year
        frames.append(merged)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def add_league_reference_columns(df):
    return shared.add_league_reference_columns(df)


def coerce_numeric(value):
    return shared.coerce_numeric(value)


def normalize_rate_scales(df, literal_percent_cols=None):
    return shared.normalize_rate_scales(df, literal_percent_cols=literal_percent_cols)


def safe_divide(numerator, denominator):
    return shared.safe_divide(numerator, denominator)


def innings_to_float(value):
    if pd.isna(value):
        return math.nan
    text = str(value).strip()
    if not text:
        return math.nan
    try:
        number = float(text)
    except ValueError:
        return math.nan
    whole = int(math.trunc(number))
    frac_digit = int(round((abs(number) - abs(whole)) * 10))
    if frac_digit == 1:
        return whole + (1 / 3)
    if frac_digit == 2:
        return whole + (2 / 3)
    return number


def numeric_series(df, col, default=0.0):
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def first_existing_column(df, candidates):
    return shared.first_existing_column(df, candidates)


def add_fantasy_points_estimate(df, pitching_weights=None):
    out = df.copy()
    pitching_weights = pitching_weights or DEFAULT_PITCHING_WEIGHTS
    if "IP" in out.columns:
        out["IP_float"] = out["IP"].map(innings_to_float)
    scoring_inputs = {
        "IP": "IP_float",
        "W": "W",
        "L": "L",
        "SV": "SV",
        "HLD": first_existing_column(out, ["HLD", "Hold", "Holds"]),
        "BS": first_existing_column(out, ["BS", "Blown Saves"]),
        "ER": "ER",
        "H": "H",
        "BB": "BB",
        "K": first_existing_column(out, ["SO", "K"]),
        "BK": "BK",
        "CG": "CG",
        "QA3": first_existing_column(out, ["QA3", "QS", "Quality Starts"]),
        "NH": first_existing_column(out, ["NH", "No Hitters"]),
        "PG": first_existing_column(out, ["PG", "Perfect Games"]),
    }
    total = pd.Series(0.0, index=out.index)
    for scoring_key, column in scoring_inputs.items():
        if not column or column not in out.columns:
            continue
        total = total + numeric_series(out, column) * pitching_weights.get(scoring_key, 0.0)
    out["FGPts_est"] = total
    out["Fantasy Points Formula"] = "fantrax_pitching_categories"
    return out


def add_standard_analytics(df, pitching_weights=None):
    out = add_fantasy_points_estimate(df, pitching_weights=pitching_weights)
    if "IP" in out.columns and "IP_float" not in out.columns:
        out["IP_float"] = out["IP"].map(innings_to_float)
    if "FGPts_est" in out.columns and "G" in out.columns:
        out["FGPts_per_game"] = safe_divide(out["FGPts_est"], out["G"])
    if {"IP_float", "G"}.issubset(out.columns):
        out["IP_per_game"] = safe_divide(out["IP_float"], out["G"])
    if "K%" in out.columns:
        out["K_pct"] = pd.to_numeric(out["K%"], errors="coerce")
    else:
        so_col = first_existing_column(out, ["SO", "K"])
        if so_col and "TBF" in out.columns:
            out["K_pct"] = safe_divide(out[so_col], out["TBF"])
    if "BB%" in out.columns:
        out["BB_pct"] = pd.to_numeric(out["BB%"], errors="coerce")
    elif {"BB", "TBF"}.issubset(out.columns):
        out["BB_pct"] = safe_divide(out["BB"], out["TBF"])
    if {"BB_pct", "K_pct"}.issubset(out.columns):
        out["BB_K_ratio"] = safe_divide(out["BB_pct"], out["K_pct"])
        in_play_share = 1 - out["BB_pct"] - out["K_pct"]
        out["Approach_score"] = out["BB_K_ratio"] * in_play_share
        out["Approach_score"] = out["Approach_score"].replace([math.inf, -math.inf], math.nan)
        out["K_BB_pct"] = out["K_pct"] - out["BB_pct"]
    if "HR/FB%" in out.columns:
        out["HR_FB_pct"] = pd.to_numeric(out["HR/FB%"], errors="coerce")
    if {"GB%", "FB%", "HR_FB_pct"}.issubset(out.columns):
        gb_pct = pd.to_numeric(out["GB%"], errors="coerce")
        fb_pct = pd.to_numeric(out["FB%"], errors="coerce")
        hr_fb_pct = pd.to_numeric(out["HR_FB_pct"], errors="coerce")
        out["Weak_Contact"] = gb_pct + (fb_pct * (1 - hr_fb_pct))
    if "xFIP" in out.columns:
        out["xFIP"] = pd.to_numeric(out["xFIP"], errors="coerce")
    if "WHIP" not in out.columns and {"BB", "H", "IP_float"}.issubset(out.columns):
        out["WHIP"] = safe_divide(out["BB"] + out["H"], out["IP_float"])
    if "BABIP" not in out.columns and "BABIP_advanced" in out.columns:
        out["BABIP"] = out["BABIP_advanced"]
    if {"TBF", "SO", "BB", "HBP", "HR", "FB%"}.issubset(out.columns):
        estimated_bip = out["TBF"] - out["SO"] - out["BB"] - out["HBP"] - out["HR"]
    elif {"IP_float", "H", "BB", "SO", "HR", "FB%"}.issubset(out.columns):
        estimated_bip = out["IP_float"] * 3 + out["H"] + out["BB"] - out["SO"] - out["HR"]
    else:
        estimated_bip = None
    if estimated_bip is not None:
        out["Estimated BIP"] = estimated_bip.where(estimated_bip > 0)
        out["Estimated FB"] = out["Estimated BIP"] * pd.to_numeric(out["FB%"], errors="coerce")
    return out


def weighted_average(group, value_col, weight_col):
    return shared.weighted_average(group, value_col, weight_col)


def weighted_average_nonzero(group, value_col, weight_col):
    return shared.weighted_average_nonzero(group, value_col, weight_col)


def sum_if_present(group, col):
    return shared.sum_if_present(group, col)


def weight_column(group):
    if "TBF" in group.columns:
        return "TBF"
    if "IP_float" in group.columns:
        return "IP_float"
    return "G"


def build_weighted_baseline_row(group):
    weight_col = weight_column(group)
    row = {
        "Players": len(group),
        "Total G": sum_if_present(group, "G"),
        "Total IP": sum_if_present(group, "IP_float"),
        "Total TBF": sum_if_present(group, "TBF"),
    }
    if "Age" in group.columns and weight_col in group.columns:
        row["Average Age"] = weighted_average(group, "Age", weight_col)
    if {"FGPts_per_game", "G"}.issubset(group.columns):
        row["FGPts_per_game"] = weighted_average_nonzero(group, "FGPts_per_game", "G")
    for metric in ["K_BB_pct", "Weak_Contact"]:
        if metric in group.columns and weight_col in group.columns:
            row[metric] = weighted_average(group, metric, weight_col)
    if "xFIP" in group.columns and weight_col in group.columns:
        row["xFIP"] = weighted_average(group, "xFIP", weight_col)
    if "BB_pct" in group.columns and weight_col in group.columns:
        row["BB_pct"] = weighted_average_nonzero(group, "BB_pct", weight_col)
    return pd.Series(row)


def league_group_columns(players):
    return shared.league_group_columns(players)


def build_weighted_baselines(players, group_cols):
    grouped = players.groupby(group_cols, dropna=False)
    return grouped.apply(build_weighted_baseline_row, include_groups=False).reset_index()


def build_league_age_baselines(players):
    group_cols = league_group_columns(players) + (["Age"] if "Age" in players.columns else [])
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
    group_cols = league_group_columns(out) + ["Team"]
    out["Team League Max G"] = out.groupby(group_cols, dropna=False)["G"].transform("max")
    out["Player Team Game Share"] = safe_divide(out["G"], out["Team League Max G"])
    return out


def plus_score(value, baseline, inverse=False):
    value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    baseline = pd.to_numeric(pd.Series([baseline]), errors="coerce").iloc[0]
    if pd.isna(value) or pd.isna(baseline):
        return math.nan
    if inverse:
        if value == 0:
            return 100
        return baseline / value * 100
    if baseline == 0:
        return 100
    return value / baseline * 100


def robust_z_plus(series, median, scale):
    values = pd.to_numeric(series, errors="coerce")
    if not scale or pd.isna(scale):
        return pd.Series(100.0, index=values.index)
    return 100 + 15 * ((values - median) / scale)


def finite_series(df, col):
    if col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").replace([math.inf, -math.inf], math.nan).dropna()


def robust_scale(values):
    if values.empty:
        return math.nan
    iqr_scale = (values.quantile(0.75) - values.quantile(0.25)) / 1.349
    if pd.notna(iqr_scale) and iqr_scale > 0:
        return iqr_scale
    std_scale = values.std()
    return std_scale if pd.notna(std_scale) and std_scale > 0 else math.nan


def round_nearest_five(value):
    if pd.isna(value):
        return math.nan
    return round(float(value) / 5) * 5


def derive_robust_transform_params(training_compared):
    rows = []
    for col in ROBUST_Z_COMPONENT_COLUMNS:
        values = finite_series(training_compared, col)
        rows.append({
            "Metric": col,
            "Median": values.median() if not values.empty else math.nan,
            "Scale": robust_scale(values),
            "N": len(values),
        })
    return pd.DataFrame(rows)


def apply_robust_transforms(out, params, caps):
    if params is None or params.empty:
        return out
    param_lookup = {
        row["Metric"]: {"median": row["Median"], "scale": row["Scale"]}
        for _, row in params.iterrows()
    }
    for col in ROBUST_Z_COMPONENT_COLUMNS:
        if col not in out.columns or col not in param_lookup:
            continue
        out[f"{col}_RobustZ"] = robust_z_plus(out[col], param_lookup[col]["median"], param_lookup[col]["scale"])
    for col, cap in (caps or {}).items():
        if col in out.columns and pd.notna(cap):
            out[f"{col}_Capped"] = pd.to_numeric(out[col], errors="coerce").clip(upper=cap)
    score_cols = [
        "K_BB_pct_Plus_RobustZ_Capped",
        "Weak_Contact_Plus_RobustZ_Capped",
    ]
    prospect_cols = [
        "Age_Plus_RobustZ",
        *score_cols,
    ]
    if all(col in out.columns for col in score_cols):
        components = out[score_cols].apply(pd.to_numeric, errors="coerce")
        out["Pitching Score"] = components.sum(axis=1, min_count=len(score_cols)) / len(score_cols)
    if all(col in out.columns for col in prospect_cols):
        components = out[prospect_cols].apply(pd.to_numeric, errors="coerce")
        out["Pitcher Prospect Score"] = components.sum(axis=1, min_count=len(prospect_cols)) / len(prospect_cols)
    return out


def derive_robust_caps(training_compared, params):
    transformed = apply_robust_transforms(training_compared.copy(), params, caps={})
    caps = {}
    for col in ROBUST_Z_CAP_COMPONENTS:
        values = finite_series(transformed, col)
        caps[col] = round_nearest_five(values.quantile(0.99)) if not values.empty else math.nan
    return caps


def baseline_lookup_key(row, key_cols):
    return tuple(row.get(col) for col in key_cols)


def build_baseline_lookup(baselines, key_cols):
    value_cols = ["Average Age"] + PLUS_SCORE_METRICS + ["BB_pct", "xFIP"]
    lookup = {}
    for _, row in baselines.iterrows():
        lookup[baseline_lookup_key(row, key_cols)] = {
            col: row.get(col) for col in value_cols if col in baselines.columns
        }
    return lookup


def add_baseline_comparison_columns(players, league_baselines, robust_params=None, robust_caps=None):
    out = team_league_game_columns(players)
    key_cols = ["Source League ID"] if "Source League ID" in out.columns else ["League"]
    lookup = build_baseline_lookup(league_baselines, key_cols)
    baseline_rows = [lookup.get(baseline_lookup_key(row, key_cols), {}) for _, row in out.iterrows()]
    for metric in ["Average Age"] + PLUS_SCORE_METRICS + ["BB_pct", "xFIP"]:
        out[f"Baseline {metric}"] = [baseline.get(metric, math.nan) for baseline in baseline_rows]
    # Pitcher age is its own inverse component: younger than the league baseline scores above 100.
    out["Age_Plus"] = [
        plus_score(age, baseline_age, inverse=True)
        for age, baseline_age in zip(out.get("Age", pd.Series(index=out.index)), out["Baseline Average Age"])
    ]
    for metric in PLUS_SCORE_METRICS:
        if metric not in out.columns:
            continue
        out[f"{metric}_Plus"] = [
            plus_score(value, baseline)
            for value, baseline in zip(out[metric], out[f"Baseline {metric}"])
        ]
        out[f"{metric}_Plus"] = out[f"{metric}_Plus"].fillna(100)
    out = apply_robust_transforms(out, robust_params, robust_caps)
    if "Pitching Score" not in out.columns:
        score_components = ROBUST_Z_COMPONENT_COLUMNS
        if all(col in out.columns for col in score_components):
            components = out[score_components].apply(pd.to_numeric, errors="coerce")
            out["Pitching Score"] = components.sum(axis=1, min_count=len(score_components)) / len(score_components)
    if "Pitcher Prospect Score" not in out.columns:
        prospect_components = ["Age_Plus", "K_BB_pct_Plus", "Weak_Contact_Plus"]
        if all(col in out.columns for col in prospect_components):
            components = out[prospect_components].apply(pd.to_numeric, errors="coerce")
            out["Pitcher Prospect Score"] = components.sum(axis=1, min_count=len(prospect_components)) / len(prospect_components)
    return out


def write_combined_baseline_outputs(players, target_year, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    league_age_baselines = build_league_age_baselines(players)
    league_baselines = build_league_baselines(players)
    league_age_path = out_dir / f"combined_league_age_pitcher_baselines_through_{target_year}.csv"
    league_path = out_dir / f"combined_league_pitcher_baselines_through_{target_year}.csv"
    league_age_baselines.to_csv(league_age_path, index=False)
    league_baselines.to_csv(league_path, index=False)
    return league_age_path, league_path, league_age_baselines, league_baselines


def write_player_comparison_output(players, league_baselines, year, out_dir, robust_params=None, robust_caps=None):
    compared = add_baseline_comparison_columns(players, league_baselines, robust_params, robust_caps)
    sort_cols = [
        col
        for col in [
            "League Level",
            "League Name",
            "Source League ID",
            "Age",
            "Pitcher Prospect Score",
            "Pitching Score",
            "Player Name",
            "Team",
        ]
        if col in compared.columns
    ]
    if sort_cols:
        ascending = [True] * len(sort_cols)
        if "Pitcher Prospect Score" in sort_cols:
            ascending[sort_cols.index("Pitcher Prospect Score")] = False
        if "Pitching Score" in sort_cols:
            ascending[sort_cols.index("Pitching Score")] = False
        compared = compared.sort_values(sort_cols, ascending=ascending, kind="stable")
    path = out_dir / f"minor_league_pitchers_{year}_plus_vs_combined_baseline.csv"
    compared.to_csv(path, index=False)
    return path


def build_players_from_csv_dir(csv_dir, year, leagues, pitching_weights=None, require_all=True):
    players = read_reports_from_csv_dir(csv_dir, year, leagues, require_all=require_all)
    if players.empty:
        return players
    players = add_league_reference_columns(players)
    players = normalize_rate_scales(players)
    players = add_standard_analytics(players, pitching_weights=pitching_weights)
    return players


def write_outputs(players, year, out_dir, pitching_weights=None, combined_baseline_csv_dirs=None, leagues=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    players = add_league_reference_columns(players)
    players = normalize_rate_scales(players)
    players = add_standard_analytics(players, pitching_weights=pitching_weights)
    players = team_league_game_columns(players)
    players_path = out_dir / f"minor_league_pitchers_{year}.csv"
    players.to_csv(players_path, index=False)

    baseline_players = players
    training_players = players
    if combined_baseline_csv_dirs:
        frames = []
        for csv_dir in combined_baseline_csv_dirs:
            inferred_year = shared.infer_year_from_path(csv_dir, year)
            frame = build_players_from_csv_dir(
                csv_dir,
                inferred_year,
                leagues or AFFILIATED_MINOR_LEAGUE_IDS,
                pitching_weights=pitching_weights,
                require_all=False,
            )
            if not frame.empty:
                frames.append(frame)
        if frames:
            baseline_players = pd.concat(frames, ignore_index=True, sort=False)
            training_frames = [
                frame for frame in frames
                if "Source Year" in frame.columns and pd.to_numeric(frame["Source Year"], errors="coerce").eq(2025).any()
            ]
            if training_frames:
                training_players = pd.concat(training_frames, ignore_index=True, sort=False)
    _, _, league_age_baselines, league_baselines = write_combined_baseline_outputs(baseline_players, year, out_dir)
    league_age_path = out_dir / f"league_age_pitcher_baselines_{year}.csv"
    league_path = out_dir / f"league_pitcher_baselines_{year}.csv"
    league_age_baselines.to_csv(league_age_path, index=False)
    league_baselines.to_csv(league_path, index=False)
    training_baselines = build_league_baselines(training_players)
    training_compared = add_baseline_comparison_columns(training_players, training_baselines)
    robust_params = derive_robust_transform_params(training_compared)
    robust_caps = derive_robust_caps(training_compared, robust_params)
    robust_params_path = out_dir / f"pitcher_robust_z_transform_params_{year}.csv"
    robust_caps_path = out_dir / f"pitcher_robust_z_composite_caps_{year}.csv"
    robust_params.to_csv(robust_params_path, index=False)
    pd.DataFrame(
        [{"Metric": metric, "Cap": cap} for metric, cap in robust_caps.items()]
    ).to_csv(robust_caps_path, index=False)
    compared_path = write_player_comparison_output(players, league_baselines, year, out_dir, robust_params, robust_caps)
    return players_path, league_age_path, league_path, compared_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build FanGraphs minor-league pitcher stats and league baselines."
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--leagues", default=",".join(str(league) for league in AFFILIATED_MINOR_LEAGUE_IDS))
    parser.add_argument("--csv-dir", type=Path, help="Directory with per-league pitcher exports named like 2_standard.csv.")
    parser.add_argument("--print-export-urls", action="store_true", help="Print one pitcher leaderboard URL per league/report and exit.")
    parser.add_argument("--league-info-json", type=Path, help="Fantrax league_info.json with scoring weights. Defaults to the latest local Fantrax export.")
    parser.add_argument(
        "--combined-baseline-csv-dirs",
        help="Comma-separated pitcher export folders to combine into baselines, for example exports/2025,exports/2026.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    leagues = parse_leagues(args.leagues)
    if args.print_export_urls:
        print_export_urls(args.year, leagues)
        return 0
    if not args.csv_dir:
        raise SystemExit("Pitcher builds currently expect --csv-dir with per-league FanGraphs browser exports.")
    pitching_weights = scoring_weights_from_league_info(args.league_info_json)
    players = build_players_from_csv_dir(args.csv_dir, args.year, leagues, pitching_weights=pitching_weights)
    baseline_dirs = parse_paths(args.combined_baseline_csv_dirs)
    outputs = write_outputs(
        players,
        args.year,
        args.out_dir,
        pitching_weights=pitching_weights,
        combined_baseline_csv_dirs=baseline_dirs,
        leagues=leagues,
    )
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
