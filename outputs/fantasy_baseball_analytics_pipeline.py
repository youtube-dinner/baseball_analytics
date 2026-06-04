#!/usr/bin/env python3
import csv
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


LEAGUE_ID = os.environ.get("FANTRAX_LEAGUE_ID", "qqll39pvmj90wrl1")
MY_FANTASY_TEAM = os.environ.get("FANTRAX_TEAM_NAME", "Bobby and the NitWitts")
CURRENT_YEAR = int(os.environ.get("FANTASY_BASEBALL_YEAR", "2026"))
PREVIOUS_YEAR = int(os.environ.get("FANTASY_BASEBALL_PREVIOUS_YEAR", str(CURRENT_YEAR - 1)))
OUT_DIR = Path(os.environ.get("FANTASY_BASEBALL_OUTPUT_DIR", Path(__file__).resolve().parent / "fantasy_baseball_analytics"))
FANTRAX_BASE_URL = "https://www.fantrax.com/fxea/general"
FANTRAX_UI_BASE_URL = "https://www.fantrax.com/fxpa"
FANTRAX_AUTH_COOKIE = os.environ.get("FANTRAX_AUTH_COOKIE", "")
FANTRAX_OLD_UI_TOKEN = os.environ.get("FANTRAX_OLD_UI_TOKEN", "")
FANTRAX_PROBABLE_MISC_DISPLAY_TYPE = os.environ.get("FANTRAX_PROBABLE_MISC_DISPLAY_TYPE", "7")
FANTRAX_PROBABLE_DATE_PLAYING = os.environ.get("FANTRAX_PROBABLE_DATE_PLAYING", "")
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
STATCAST_SEARCH_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
RECENT_WINDOWS = [7, 14, 30]
MIN_PITCHES_THROWN_BY_WINDOW = {7: 25, 14: 50, 30: 75}
MIN_PITCHES_FACED_BY_WINDOW = {7: 25, 14: 50, 30: 75}
MIN_BATTED_BALLS_BY_WINDOW = {7: 3, 14: 6, 30: 10}
HITTER_AB_MATCH_TOLERANCE = int(os.environ.get("HITTER_AB_MATCH_TOLERANCE", "10"))
PITCHER_GAME_MATCH_TOLERANCE = int(os.environ.get("PITCHER_GAME_MATCH_TOLERANCE", "2"))
TEAM_ABBREV_BY_NAME = {
    "Arizona Diamondbacks": "ARI",
    "Athletics": "ATH",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}


def fetch_bytes(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urlopen(req, timeout=60) as response:
        return response.read()


def fetch_url_bytes(url, params=None, headers=None):
    if params:
        url = f"{url}?{urlencode(params)}"
    req_headers = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
    if headers:
        req_headers.update(headers)
    req = Request(url, headers=req_headers)
    with urlopen(req, timeout=60) as response:
        return response.read()


def fetch_json(url, **params):
    if params:
        url = f"{url}?{urlencode(params)}"
    return json.loads(fetch_bytes(url).decode("utf-8"))


def fetch_fantrax(endpoint, **params):
    return fetch_json(f"{FANTRAX_BASE_URL}/{endpoint}", **params)


def fetch_mlb_stats(group, stats="season", start_date=None, end_date=None):
    params = {
        "stats": stats,
        "group": group,
        "playerPool": "ALL",
        "season": CURRENT_YEAR,
        "sportIds": 1,
        "limit": 10000,
    }
    if start_date and end_date:
        params["startDate"] = start_date
        params["endDate"] = end_date
    try:
        data = fetch_json("https://statsapi.mlb.com/api/v1/stats", **params)
    except Exception:
        return pd.DataFrame()
    rows = []
    for split in data.get("stats", [{}])[0].get("splits", []):
        stat = split.get("stat", {})
        player = split.get("player", {})
        team = split.get("team", {})
        row = {
            "mlb_player_id": player.get("id"),
            "Player": player.get("fullName"),
            "Player_standard": standardize_string(player.get("fullName")),
            "mlb_stats_team": team.get("name"),
            "mlb_team": team.get("abbreviation") or TEAM_ABBREV_BY_NAME.get(team.get("name")),
        }
        row.update(stat)
        rows.append(row)
    return pd.DataFrame(rows)


def load_csv_if_exists(path):
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def fetch_savant_csv(year, player_type):
    if player_type == "pitcher":
        selections = "p_game,p_formatted_ip,ab,bb_percent,p_save,p_era,p_hold,meatball_percent,whiff_percent"
        sort = "p_formatted_ip"
    else:
        selections = "ab,barrel_batted_rate,oz_swing_percent,meatball_swing_percent"
        sort = "ab"
    params = {
        "year": year,
        "type": player_type,
        "filter": "",
        "min": 10,
        "selections": selections,
        "chart": "false",
        "x": "ab",
        "y": "ab",
        "r": "no",
        "chartType": "beeswarm",
        "sort": sort,
        "sortDir": "desc",
        "csv": "true",
    }
    url = "https://baseballsavant.mlb.com/leaderboard/custom?" + urlencode(params)
    from io import BytesIO

    try:
        raw = fetch_bytes(url)
    except Exception:
        candidates = sorted(
            Path(__file__).resolve().parent.glob(f"baseball_savant_custom_{player_type}_leaderboard_*.csv")
        )
        fallback = next((path for path in candidates if path.stem.endswith(str(year))), None)
        if fallback is None and candidates:
            fallback = candidates[-1]
        if fallback is None or not fallback.exists():
            raise
        raw = fallback.read_bytes()
    df = pd.read_csv(BytesIO(raw), encoding="utf-8-sig")
    if "last_name, first_name" in df.columns:
        names = df["last_name, first_name"].astype(str).str.split(",", n=1, expand=True)
        df["last_name"] = names[0].str.strip()
        df["first_name"] = names[1].str.strip()
    return df


def fetch_statcast_range(player_type, start_date, end_date):
    frames = []
    day = start_date
    while day <= end_date:
        cache_dir = OUT_DIR / "statcast_cache" / player_type
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{day.isoformat()}.csv"
        if cache_path.exists() and day < date.today():
            daily = pd.read_csv(cache_path)
            if not daily.empty:
                frames.append(daily)
            day += timedelta(days=1)
            continue

        params = {
            "all": "true",
            "type": "details",
            "player_type": player_type,
            "game_date_gt": day.isoformat(),
            "game_date_lt": day.isoformat(),
            "min_pitches": 0,
            "min_results": 0,
            "group_by": "name",
            "sort_col": "pitches",
            "sort_order": "desc",
            "csv": "true",
        }
        from io import BytesIO

        try:
            raw = fetch_bytes(STATCAST_SEARCH_URL + "?" + urlencode(params))
        except Exception:
            if cache_path.exists():
                daily = pd.read_csv(cache_path)
                if not daily.empty:
                    frames.append(daily)
            day += timedelta(days=1)
            continue
        if raw.strip():
            daily = pd.read_csv(BytesIO(raw), encoding="utf-8-sig")
            if not daily.empty:
                clean_for_csv(daily).to_csv(cache_path, index=False)
                frames.append(daily)
        day += timedelta(days=1)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["game_date"] = pd.to_datetime(out["game_date"], errors="coerce")
    out["player_name_standard"] = out["player_name"].apply(standardize_string)
    return out


SWING_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "foul_bunt",
    "missed_bunt",
    "hit_into_play",
}
WHIFF_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "missed_bunt",
}


def aggregate_recent_pitching(statcast_df, mlb_pitching, days, end_day):
    start_day = pd.Timestamp(end_day - timedelta(days=days - 1))
    window = statcast_df[statcast_df["game_date"] >= start_day].copy()
    if window.empty:
        return pd.DataFrame(columns=["Player_standard"])

    window["is_swing"] = window["description"].isin(SWING_DESCRIPTIONS)
    window["is_whiff"] = window["description"].isin(WHIFF_DESCRIPTIONS)
    window["is_meatball"] = pd.to_numeric(window["zone"], errors="coerce") == 5
    window["is_pa"] = window["events"].notna()
    window["is_walk"] = window["events"].isin(["walk", "intent_walk"])

    grouped = window.groupby(["pitcher", "player_name_standard"], dropna=False)
    group_index = grouped.size().index
    out = pd.DataFrame({
        "mlb_player_id": [idx[0] for idx in group_index],
        "Player_standard": [idx[1] for idx in group_index],
        f"pitches_thrown_{days}d": grouped.size().values,
        f"swings_{days}d": grouped["is_swing"].sum().values,
        f"whiffs_{days}d": grouped["is_whiff"].sum().values,
        f"meatballs_{days}d": grouped["is_meatball"].sum().values,
        f"plate_appearances_{days}d": grouped["is_pa"].sum().values,
        f"walks_{days}d": grouped["is_walk"].sum().values,
        f"p_game_statcast_{days}d": grouped["game_pk"].nunique().values,
    })
    out[f"whiff_percent_{days}d"] = (
        out[f"whiffs_{days}d"] / out[f"swings_{days}d"].replace(0, np.nan) * 100
    )
    out[f"meatball_percent_{days}d"] = (
        out[f"meatballs_{days}d"] / out[f"pitches_thrown_{days}d"].replace(0, np.nan) * 100
    )
    out[f"bb_percent_{days}d"] = (
        out[f"walks_{days}d"] / out[f"plate_appearances_{days}d"].replace(0, np.nan) * 100
    )

    score_input = out.rename(columns={
        f"whiff_percent_{days}d": "whiff_percent",
        f"meatball_percent_{days}d": "meatball_percent",
        f"bb_percent_{days}d": "bb_percent",
    }).copy()
    standardize_numeric(score_input, ["bb_percent", "meatball_percent", "whiff_percent"])
    score_input = compute_pitching_scores(score_input)
    out[f"command_score_{days}d"] = score_input["command_score"]
    out[f"pitching_score_{days}d"] = score_input["pitching_score"]
    qualified = out[f"pitches_thrown_{days}d"] >= MIN_PITCHES_THROWN_BY_WINDOW.get(days, 0)
    for col in [f"command_score_{days}d", f"pitching_score_{days}d"]:
        out.loc[~qualified, col] = np.nan

    if not mlb_pitching.empty:
        mlb = mlb_pitching.copy()
        mlb[f"p_game_{days}d"] = float_series(mlb, "gamesPitched")
        mlb[f"p_save_{days}d"] = float_series(mlb, "saves")
        mlb[f"p_hold_{days}d"] = float_series(mlb, "holds")
        mlb[f"IP_{days}d"] = innings_to_float(mlb["inningsPitched"]) if "inningsPitched" in mlb.columns else np.nan
        mlb[f"IP_per_Game_{days}d"] = (
            mlb[f"IP_{days}d"] / mlb[f"p_game_{days}d"].replace(0, np.nan)
        )
        out = out.merge(
            mlb[[
                "Player_standard",
                f"p_game_{days}d",
                f"p_save_{days}d",
                f"p_hold_{days}d",
                f"IP_{days}d",
                f"IP_per_Game_{days}d",
            ]],
            on="Player_standard",
            how="left",
        )
    for col in out.columns:
        if col != "Player_standard":
            out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
    return out


def aggregate_recent_hitting(statcast_df, mlb_hitting, days, end_day):
    start_day = pd.Timestamp(end_day - timedelta(days=days - 1))
    window = statcast_df[statcast_df["game_date"] >= start_day].copy()
    if window.empty:
        return pd.DataFrame(columns=["Player_standard"])

    zone = pd.to_numeric(window["zone"], errors="coerce")
    window["is_swing"] = window["description"].isin(SWING_DESCRIPTIONS)
    window["is_ozone"] = zone >= 11
    window["is_ozone_swing"] = window["is_ozone"] & window["is_swing"]
    window["is_meatball"] = zone == 5
    window["is_meatball_swing"] = window["is_meatball"] & window["is_swing"]
    window["is_bbe"] = window["bb_type"].notna() | pd.to_numeric(window["launch_speed_angle"], errors="coerce").notna()
    window["is_barrel"] = pd.to_numeric(window["launch_speed_angle"], errors="coerce") == 6

    grouped = window.groupby(["batter", "player_name_standard"], dropna=False)
    group_index = grouped.size().index
    out = pd.DataFrame({
        "mlb_player_id": [idx[0] for idx in group_index],
        "Player_standard": [idx[1] for idx in group_index],
        f"pitches_faced_{days}d": grouped.size().values,
        f"ozone_pitches_{days}d": grouped["is_ozone"].sum().values,
        f"ozone_swings_{days}d": grouped["is_ozone_swing"].sum().values,
        f"meatballs_seen_{days}d": grouped["is_meatball"].sum().values,
        f"meatball_swings_{days}d": grouped["is_meatball_swing"].sum().values,
        f"batted_balls_{days}d": grouped["is_bbe"].sum().values,
        f"barrels_{days}d": grouped["is_barrel"].sum().values,
    })
    out[f"oz_swing_percent_{days}d"] = (
        out[f"ozone_swings_{days}d"] / out[f"ozone_pitches_{days}d"].replace(0, np.nan) * 100
    )
    out[f"meatball_swing_percent_{days}d"] = (
        out[f"meatball_swings_{days}d"] / out[f"meatballs_seen_{days}d"].replace(0, np.nan) * 100
    )
    out[f"barrel_batted_rate_{days}d"] = (
        out[f"barrels_{days}d"] / out[f"batted_balls_{days}d"].replace(0, np.nan) * 100
    )

    score_input = out.rename(columns={
        f"oz_swing_percent_{days}d": "oz_swing_percent",
        f"meatball_swing_percent_{days}d": "meatball_swing_percent",
        f"barrel_batted_rate_{days}d": "barrel_batted_rate",
    }).copy()
    score_input = compute_hitter_scores(score_input)
    out[f"batters_eye_score_{days}d"] = score_input["batters_eye_score"]
    out[f"hitter_score_{days}d"] = score_input["hitter_score"]
    qualified = (
        (out[f"pitches_faced_{days}d"] >= MIN_PITCHES_FACED_BY_WINDOW.get(days, 0))
        & (out[f"batted_balls_{days}d"] >= MIN_BATTED_BALLS_BY_WINDOW.get(days, 0))
    )
    for col in [f"batters_eye_score_{days}d", f"hitter_score_{days}d"]:
        out.loc[~qualified, col] = np.nan

    if not mlb_hitting.empty:
        mlb = mlb_hitting.copy()
        mlb[f"GP_{days}d"] = float_series(mlb, "gamesPlayed")
        mlb[f"AB_{days}d"] = float_series(mlb, "atBats")
        mlb[f"Runs_{days}d"] = float_series(mlb, "runs")
        mlb[f"AB_per_Game_{days}d"] = (
            mlb[f"AB_{days}d"] / mlb[f"GP_{days}d"].replace(0, np.nan)
        )
        mlb[f"R_per_Game_{days}d"] = (
            mlb[f"Runs_{days}d"] / mlb[f"GP_{days}d"].replace(0, np.nan)
        )
        out = out.merge(
            mlb[[
                "Player_standard",
                f"GP_{days}d",
                f"AB_{days}d",
                f"Runs_{days}d",
                f"AB_per_Game_{days}d",
                f"R_per_Game_{days}d",
            ]],
            on="Player_standard",
            how="left",
        )
    for col in out.columns:
        if col != "Player_standard":
            out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
    return out


def build_recent_trend_frames():
    end_day = date.today()
    max_start = end_day - timedelta(days=max(RECENT_WINDOWS) - 1)
    pitcher_statcast = fetch_statcast_range("pitcher", max_start, end_day)
    hitter_statcast = fetch_statcast_range("batter", max_start, end_day)

    pitcher_trends = None
    hitter_trends = None
    for days in RECENT_WINDOWS:
        start = (end_day - timedelta(days=days - 1)).isoformat()
        end = end_day.isoformat()
        mlb_pitching = fetch_mlb_stats("pitching", "byDateRange", start, end)
        mlb_hitting = fetch_mlb_stats("hitting", "byDateRange", start, end)
        pitcher_window = aggregate_recent_pitching(pitcher_statcast, mlb_pitching, days, end_day)
        hitter_window = aggregate_recent_hitting(hitter_statcast, mlb_hitting, days, end_day)
        pitcher_trends = pitcher_window if pitcher_trends is None else pitcher_trends.merge(
            pitcher_window, on=["mlb_player_id", "Player_standard"], how="outer"
        )
        hitter_trends = hitter_window if hitter_trends is None else hitter_trends.merge(
            hitter_window, on=["mlb_player_id", "Player_standard"], how="outer"
        )
    return (
        pitcher_trends if pitcher_trends is not None else pd.DataFrame(columns=["Player_standard"]),
        hitter_trends if hitter_trends is not None else pd.DataFrame(columns=["Player_standard"]),
    )


def standardize_string(value):
    value = "" if pd.isna(value) else str(value)
    if "," in value:
        last, first = [part.strip() for part in value.split(",", 1)]
        value = f"{first} {last}"
    value = re.sub(r"\s+Jr\.?$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+(II|III|IV|V)$", "", value, flags=re.IGNORECASE)
    normalized = unicodedata.normalize("NFKD", value)
    ascii_str = normalized.encode("ASCII", "ignore").decode("utf-8")
    return " ".join(ascii_str.lower().replace(".", "").replace("'", "").replace("-", " ").split())


def display_name(fantrax_name):
    if not fantrax_name or pd.isna(fantrax_name):
        return ""
    name = str(fantrax_name)
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return f"{first} {last}"
    return name


def standardize_numeric(df, columns):
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        std = df[col].std()
        df[col + "_std"] = np.nan if std == 0 or pd.isna(std) else (df[col] - df[col].mean()) / std


def compute_pitching_scores(df):
    df = df.copy()
    df["command_score_raw"] = -1 * (df["meatball_percent_std"] + df["bb_percent_std"])
    df["command_score"] = (df["command_score_raw"] - df["command_score_raw"].mean()) / df["command_score_raw"].std()
    df["pitching_score_raw"] = df["command_score"] + df["whiff_percent_std"]
    df["pitching_score"] = (df["pitching_score_raw"] - df["pitching_score_raw"].mean()) / df["pitching_score_raw"].std()
    df.drop(columns=["command_score_raw", "pitching_score_raw"], inplace=True)
    for col in [c for c in df.columns if c.endswith("_std")] + ["command_score", "pitching_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
    return df


def compute_hitter_scores(df):
    df = df.copy()
    df["oz_take"] = 100 - pd.to_numeric(df["oz_swing_percent"], errors="coerce")
    df["oz_take_std"] = (df["oz_take"] - df["oz_take"].mean()) / df["oz_take"].std()
    df["meatball_swing_std"] = (
        pd.to_numeric(df["meatball_swing_percent"], errors="coerce") - pd.to_numeric(df["meatball_swing_percent"], errors="coerce").mean()
    ) / pd.to_numeric(df["meatball_swing_percent"], errors="coerce").std()
    df["batters_eye_score_raw"] = df["oz_take_std"] + df["meatball_swing_std"]
    df["batters_eye_score"] = (df["batters_eye_score_raw"] - df["batters_eye_score_raw"].mean()) / df["batters_eye_score_raw"].std()
    df["barrel_std"] = (
        pd.to_numeric(df["barrel_batted_rate"], errors="coerce") - pd.to_numeric(df["barrel_batted_rate"], errors="coerce").mean()
    ) / pd.to_numeric(df["barrel_batted_rate"], errors="coerce").std()
    df["hitter_score_raw"] = df["batters_eye_score"] + df["barrel_std"]
    df["hitter_score"] = (df["hitter_score_raw"] - df["hitter_score_raw"].mean()) / df["hitter_score_raw"].std()
    df.drop(columns=["batters_eye_score_raw", "hitter_score_raw"], inplace=True)
    for col in [c for c in df.columns if c.endswith("_std")] + ["batters_eye_score", "hitter_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
    return df


def prepare_savant(df, kind):
    df = df.copy()
    threshold = int(os.environ.get("SAVANT_AB_THRESHOLD", "30"))
    df["ab"] = pd.to_numeric(df["ab"], errors="coerce")
    df = df.loc[df["ab"] >= threshold].copy()
    if kind == "pitcher":
        standardize_numeric(df, ["bb_percent", "meatball_percent", "whiff_percent"])
        df = compute_pitching_scores(df)
        df["IP_per_Game"] = (
            pd.to_numeric(df["p_formatted_ip"], errors="coerce") / pd.to_numeric(df["p_game"], errors="coerce")
        ).round(1)
    else:
        for col in ["barrel_batted_rate", "oz_swing_percent", "meatball_swing_percent"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = compute_hitter_scores(df)
    df["player_name"] = df["first_name"].astype(str) + " " + df["last_name"].astype(str)
    df["player_name_standard"] = df["player_name"].apply(standardize_string)
    return df


def tomorrow_iso():
    override = os.environ.get("FANTRAX_PROBABLE_DATE")
    if override:
        return override
    return (datetime.now().date() + timedelta(days=1)).isoformat()


def probable_starters(probable_date):
    schedule = fetch_json(MLB_SCHEDULE_URL, sportId=1, date=probable_date, hydrate="probablePitcher")
    rows = []
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            for side, other_side in [("away", "home"), ("home", "away")]:
                pitcher = teams.get(side, {}).get("probablePitcher")
                if not pitcher:
                    continue
                team = teams.get(side, {}).get("team", {})
                opponent = teams.get(other_side, {}).get("team", {})
                team_name = team.get("name") or team.get("teamName")
                opponent_name = opponent.get("name") or opponent.get("teamName")
                team_abbrev = team.get("abbreviation") or TEAM_ABBREV_BY_NAME.get(team_name) or team.get("teamName")
                opponent_abbrev = (
                    opponent.get("abbreviation")
                    or TEAM_ABBREV_BY_NAME.get(opponent_name)
                    or opponent.get("teamName")
                )
                rows.append({
                    "probable_date": probable_date,
                    "game_time_utc": game.get("gameDate"),
                    "home_away": side,
                    "Team": team_abbrev,
                    "Opponent": opponent_abbrev,
                    "mlb_team": team_abbrev,
                    "mlb_player_id": pitcher.get("id"),
                    "probable_name": pitcher.get("fullName"),
                    "Player_standard": standardize_string(pitcher.get("fullName")),
                    "game_pk": game.get("gamePk"),
                })
    return pd.DataFrame(rows)


def fantrax_ui_headers(accept="*/*"):
    headers = {"Accept": accept}
    if FANTRAX_AUTH_COOKIE:
        headers["Cookie"] = FANTRAX_AUTH_COOKIE
    return headers


def fetch_fantrax_ui_bytes(endpoint, **params):
    if FANTRAX_OLD_UI_TOKEN:
        params["olduitk"] = FANTRAX_OLD_UI_TOKEN
    raw = fetch_url_bytes(
        f"{FANTRAX_UI_BASE_URL}/{endpoint}",
        params=params,
        headers=fantrax_ui_headers(),
    )
    stripped = raw.strip()
    if stripped.startswith(b"{"):
        try:
            data = json.loads(stripped.decode("utf-8"))
        except json.JSONDecodeError:
            data = {}
        page_error = data.get("pageError") or data.get("error")
        if page_error:
            code = page_error.get("code") or "Fantrax UI error"
            text = page_error.get("text") or page_error.get("message") or ""
            raise RuntimeError(f"{code}: {text}".strip())
    return raw


def fantrax_probable_candidate_params():
    base = {
        "leagueId": LEAGUE_ID,
        "positionOrGroup": "BASEBALL_PITCHING",
        "miscDisplayType": FANTRAX_PROBABLE_MISC_DISPLAY_TYPE,
        "maxResultsPerPage": 500,
        "pageNumber": 1,
    }
    if FANTRAX_PROBABLE_DATE_PLAYING:
        return [{**base, "datePlaying": FANTRAX_PROBABLE_DATE_PLAYING}]

    candidates = [base]
    for misc_display_type in ["7", "8"]:
        candidates.append({**base, "miscDisplayType": misc_display_type})
        candidates.append({**base, "miscDisplayType": misc_display_type, "datePlaying": "TOMORROW"})
    unique = []
    seen = set()
    for params in candidates:
        key = tuple(sorted(params.items()))
        if key not in seen:
            seen.add(key)
            unique.append(params)
    return unique


def first_present(row, names):
    for name in names:
        if name in row and not pd.isna(row[name]) and str(row[name]).strip():
            return row[name]
    return np.nan


def fantrax_probable_starters_from_ui(probable_date, player_ids, league_players, rostered_ids):
    if not FANTRAX_AUTH_COOKIE and not FANTRAX_OLD_UI_TOKEN:
        raise RuntimeError("Fantrax UI probable-starter feed requires FANTRAX_AUTH_COOKIE or FANTRAX_OLD_UI_TOKEN")

    last_error = None
    best_df = pd.DataFrame()
    best_params = None
    for params in fantrax_probable_candidate_params():
        try:
            raw = fetch_fantrax_ui_bytes("downloadPlayerStats", **params)
            from io import BytesIO

            candidate = pd.read_csv(BytesIO(raw), encoding="utf-8-sig")
            candidate = candidate.dropna(how="all").drop(columns=[c for c in candidate.columns if str(c).startswith("Unnamed")], errors="ignore")
            if candidate.empty:
                continue
            if candidate.shape[0] > best_df.shape[0]:
                best_df = candidate
                best_params = params
        except Exception as exc:
            last_error = exc

    if best_df.empty:
        raise RuntimeError(f"No Fantrax UI probable starters returned: {last_error}")

    pitcher_lookup = []
    for fantrax_id, player in player_ids.items():
        position = player.get("position")
        if position not in {"SP", "RP"}:
            continue
        league_player = league_players.get(fantrax_id, {})
        name = display_name(player.get("name"))
        pitcher_lookup.append({
            "fantrax_id": fantrax_id,
            "probable_name": name,
            "Player_standard": standardize_string(name),
            "mlb_team": player.get("team"),
            "primary_position": position,
            "eligible_positions": league_player.get("eligiblePos"),
            "league_status": league_player.get("status"),
            "is_rostered": fantrax_id in rostered_ids,
            "stats_inc_id": player.get("statsIncId"),
            "rotowire_id": player.get("rotowireId"),
            "sport_radar_id": player.get("sportRadarId"),
        })
    pitchers = pd.DataFrame(pitcher_lookup)

    rows = []
    for raw_row in best_df.to_dict("records"):
        raw_name = first_present(raw_row, ["Player", "Name", "Scorer", "player", "name"])
        if pd.isna(raw_name):
            continue
        name = display_name(raw_name)
        team = first_present(raw_row, ["Team", "MLB Team", "Pro Team", "team", "mlb_team"])
        player_standard = standardize_string(name)
        matches = pitchers[pitchers["Player_standard"] == player_standard].copy()
        if not pd.isna(team) and str(team).strip():
            team_matches = matches[matches["mlb_team"].astype(str) == str(team).strip()]
            if not team_matches.empty:
                matches = team_matches
        match = matches.iloc[0].to_dict() if not matches.empty else {}
        rows.append({
            "probable_date": probable_date,
            "game_time_utc": first_present(raw_row, ["Game Time", "Game", "Start Time"]),
            "home_away": first_present(raw_row, ["Home/Away", "H/A"]),
            "Team": match.get("mlb_team") or team,
            "Opponent": first_present(raw_row, ["Opponent", "Opp", "OPP"]),
            "mlb_team": match.get("mlb_team") or team,
            "mlb_player_id": np.nan,
            "probable_name": match.get("probable_name") or name,
            "Player_standard": match.get("Player_standard") or player_standard,
            "fantrax_id": match.get("fantrax_id"),
            "primary_position": match.get("primary_position"),
            "eligible_positions": match.get("eligible_positions"),
            "league_status": match.get("league_status"),
            "is_rostered": bool(match.get("is_rostered", False)),
            "stats_inc_id": match.get("stats_inc_id"),
            "rotowire_id": match.get("rotowire_id"),
            "sport_radar_id": match.get("sport_radar_id"),
            "fantrax_probable_source": "fantrax_ui_downloadPlayerStats",
            "fantrax_probable_params": json.dumps(best_params, sort_keys=True),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("Fantrax UI probable-starter CSV did not contain recognizable player rows")
    return out


def build_fantrax_frames():
    fantrax_dir = Path(__file__).resolve().parent / "fantrax_export"
    try:
        player_ids = fetch_fantrax("getPlayerIds", sport="MLB")
        league_info = fetch_fantrax("getLeagueInfo", leagueId=LEAGUE_ID)
        rosters = fetch_fantrax("getTeamRosters", leagueId=LEAGUE_ID)
    except Exception:
        player_ids_df = pd.read_csv(fantrax_dir / "fantrax_players_latest.csv")
        rosters_df = pd.read_csv(fantrax_dir / "fantrax_rosters_latest.csv")
        probable = pd.read_csv(fantrax_dir / "fantrax_probable_starters_unrostered_tomorrow_latest.csv")
        probable["Team"] = probable.get("probable_team", probable.get("mlb_team"))
        probable["Opponent"] = probable.get("opponent")
        probable["Player_standard"] = probable["probable_name"].apply(standardize_string)
        player_ids = {
            row.fantrax_id: {
                "name": row.name,
                "team": row.mlb_team,
                "position": row.primary_position,
                "statsIncId": row.stats_inc_id if not pd.isna(row.stats_inc_id) else None,
                "rotowireId": row.rotowire_id if not pd.isna(row.rotowire_id) else None,
                "sportRadarId": row.sport_radar_id if not pd.isna(row.sport_radar_id) else None,
            }
            for row in player_ids_df.itertuples(index=False)
        }
        league_info = {
            "playerInfo": {
                row.fantrax_id: {
                    "eligiblePos": row.eligible_positions,
                    "status": row.league_status,
                }
                for row in player_ids_df.itertuples(index=False)
            }
        }
        rosters = {
            "rosters": {
                team_id: {
                    "teamName": team_name,
                    "rosterItems": [
                        {"id": r.fantrax_id, "position": r.roster_position, "status": r.roster_status}
                        for r in team_rows.itertuples(index=False)
                    ],
                }
                for team_id, team_rows in rosters_df.groupby("team_id")
                for team_name in [team_rows["team_name"].iloc[0]]
            }
        }
    rostered_ids = {
        item.get("id")
        for roster in rosters.get("rosters", {}).values()
        for item in roster.get("rosterItems", [])
    }
    if "probable" not in locals():
        probable_date = tomorrow_iso()
        try:
            probable = fantrax_probable_starters_from_ui(
                probable_date,
                player_ids,
                league_info.get("playerInfo", {}),
                rostered_ids,
            )
        except Exception:
            probable = probable_starters(probable_date)

    all_rows = []
    for fantrax_id, info in league_info.get("playerInfo", {}).items():
        player = player_ids.get(fantrax_id, {})
        all_rows.append({
            "fantrax_id": fantrax_id,
            "Player": display_name(player.get("name")),
            "Position": player.get("position"),
            "Eligible": info.get("eligiblePos"),
            "Status": info.get("status"),
            "mlb_team": player.get("team"),
            "stats_inc_id": player.get("statsIncId"),
            "rotowire_id": player.get("rotowireId"),
            "sport_radar_id": player.get("sportRadarId"),
            "is_rostered": fantrax_id in rostered_ids,
            "FPts": np.nan,
            "FP/G": np.nan,
        })
    all_players = pd.DataFrame(all_rows)
    all_players["Player_standard"] = all_players["Player"].apply(standardize_string)

    roster_rows = []
    for team_id, roster in rosters.get("rosters", {}).items():
        for item in roster.get("rosterItems", []):
            fantrax_id = item.get("id")
            player = player_ids.get(fantrax_id, {})
            roster_rows.append({
                "team_id": team_id,
                "fantasy_team": roster.get("teamName"),
                "fantrax_id": fantrax_id,
                "Player": display_name(player.get("name")),
                "Eligible": player.get("position"),
                "Roster Position": item.get("position"),
                "Status": item.get("status"),
                "mlb_team": player.get("team"),
                "Fantasy Points": np.nan,
                "Average Fantasy Points per Game": np.nan,
                "GP": np.nan,
            })
    current_roster = pd.DataFrame(roster_rows)
    current_roster["Player_standard"] = current_roster["Player"].apply(standardize_string)

    pitcher_players = all_players[all_players["Position"].isin(["SP", "RP"])].copy()
    streaming_pitchers = merge_by_id_team_name(
        probable,
        pitcher_players.drop(columns=["mlb_player_id"], errors="ignore"),
        "mlb_player_id",
    )
    streaming_pitchers = streaming_pitchers[streaming_pitchers["is_rostered"].fillna(False) == False].copy()
    streaming_pitchers["Player"] = streaming_pitchers["probable_name"]
    streaming_pitchers["Position"] = streaming_pitchers["Position"].fillna("SP")
    streaming_pitchers["Status"] = streaming_pitchers["Status"].fillna("FA")
    return all_players, current_roster, streaming_pitchers, league_info


def scoring_weights(league_info, group):
    group_rules = league_info.get("scoringSystem", {}).get("scoringCategories", {}).get(group, {})
    weights = {}
    for short_name, config in group_rules.items():
        raw = config.get("Default", "")
        if isinstance(raw, str) and raw.startswith("points"):
            try:
                weights[short_name] = float(raw.replace("points", "", 1))
            except ValueError:
                pass
    return weights


def float_series(df, col, default=0.0):
    if col not in df.columns:
        return pd.Series(default, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def innings_to_float(series):
    def convert(value):
        if pd.isna(value):
            return 0.0
        text = str(value)
        if "." not in text:
            return float(text)
        whole, frac = text.split(".", 1)
        outs = int(frac[:1] or 0)
        return float(whole or 0) + outs / 3
    return series.apply(convert)


def add_calculated_fantasy_points(all_players, league_info):
    hitting = fetch_mlb_stats("hitting", "season")
    pitching = fetch_mlb_stats("pitching", "season")
    pitching_adv = fetch_mlb_stats("pitching", "seasonAdvanced")

    if not pitching.empty and not pitching_adv.empty:
        pitching = pitching.merge(
            pitching_adv[["Player_standard", "qualityStarts"]],
            on="Player_standard",
            how="left",
        )

    hit_weights = scoring_weights(league_info, "HITTING")
    pitch_weights = scoring_weights(league_info, "PITCHING")

    if not hitting.empty:
        singles = (
            float_series(hitting, "hits")
            - float_series(hitting, "doubles")
            - float_series(hitting, "triples")
            - float_series(hitting, "homeRuns")
        )
        hitting["calculated_fpts"] = (
            singles * hit_weights.get("1B", 0)
            + float_series(hitting, "doubles") * hit_weights.get("2B", 0)
            + float_series(hitting, "triples") * hit_weights.get("3B", 0)
            + float_series(hitting, "homeRuns") * hit_weights.get("HR", 0)
            + float_series(hitting, "runs") * hit_weights.get("R", 0)
            + float_series(hitting, "rbi") * hit_weights.get("RBI", 0)
            + float_series(hitting, "baseOnBalls") * hit_weights.get("BB", 0)
            + float_series(hitting, "strikeOuts") * hit_weights.get("SO", 0)
            + float_series(hitting, "stolenBases") * hit_weights.get("SB", 0)
            + float_series(hitting, "caughtStealing") * hit_weights.get("CS", 0)
            + float_series(hitting, "hitByPitch") * hit_weights.get("HBP", 0)
            + float_series(hitting, "groundIntoDoublePlay") * hit_weights.get("GIDP", 0)
            + float_series(hitting, "sacBunts") * hit_weights.get("SH", 0)
        ).round(2)
        hitting["calculated_fp_per_game"] = (
            hitting["calculated_fpts"] / float_series(hitting, "gamesPlayed").replace(0, np.nan)
        ).round(2)
        hitting["GP"] = float_series(hitting, "gamesPlayed").round(0)
        hitting["MLB_AB"] = float_series(hitting, "atBats").round(0)
        hitting["Runs"] = float_series(hitting, "runs").round(0)
        hitting["R_per_Game"] = (
            hitting["Runs"] / hitting["GP"].replace(0, np.nan)
        ).round(2)

    if not pitching.empty:
        ip = innings_to_float(pitching["inningsPitched"])
        pitching["calculated_fpts"] = (
            ip * pitch_weights.get("IP", 0)
            + float_series(pitching, "wins") * pitch_weights.get("W", 0)
            + float_series(pitching, "losses") * pitch_weights.get("L", 0)
            + float_series(pitching, "saves") * pitch_weights.get("SV", 0)
            + float_series(pitching, "holds") * pitch_weights.get("HLD", 0)
            + float_series(pitching, "blownSaves") * pitch_weights.get("BS", 0)
            + float_series(pitching, "earnedRuns") * pitch_weights.get("ER", 0)
            + float_series(pitching, "hits") * pitch_weights.get("H", 0)
            + float_series(pitching, "baseOnBalls") * pitch_weights.get("BB", 0)
            + float_series(pitching, "strikeOuts") * pitch_weights.get("K", 0)
            + float_series(pitching, "balks") * pitch_weights.get("BK", 0)
            + float_series(pitching, "completeGames") * pitch_weights.get("CG", 0)
            + float_series(pitching, "qualityStarts") * pitch_weights.get("QA3", 0)
        ).round(2)
        pitching["calculated_fp_per_game"] = (
            pitching["calculated_fpts"] / float_series(pitching, "gamesPitched").replace(0, np.nan)
        ).round(2)
        pitching["Pitching_G"] = float_series(pitching, "gamesPitched").round(0)
        pitching["IP"] = ip.round(1)
        pitching["IP_per_Game_MLB"] = (
            pitching["IP"] / pitching["Pitching_G"].replace(0, np.nan)
        ).round(2)

    stats = pd.concat([
        hitting[[
            "mlb_player_id", "Player_standard", "mlb_team",
            "calculated_fpts", "calculated_fp_per_game", "GP", "MLB_AB", "Runs", "R_per_Game"
        ]]
        if not hitting.empty else pd.DataFrame(columns=[
            "mlb_player_id", "Player_standard", "mlb_team",
            "calculated_fpts", "calculated_fp_per_game", "GP", "MLB_AB", "Runs", "R_per_Game"
        ]),
        pitching[[
            "mlb_player_id", "Player_standard", "mlb_team",
            "calculated_fpts", "calculated_fp_per_game", "Pitching_G", "IP", "IP_per_Game_MLB"
        ]]
        if not pitching.empty else pd.DataFrame(columns=[
            "mlb_player_id", "Player_standard", "mlb_team",
            "calculated_fpts", "calculated_fp_per_game", "Pitching_G", "IP", "IP_per_Game_MLB"
        ]),
    ], ignore_index=True)
    out = merge_by_id_team_name(
        all_players.drop(columns=["FPts", "FP/G", "mlb_player_id"], errors="ignore"),
        stats.sort_values("calculated_fpts", ascending=False),
        "mlb_player_id",
    )
    if "calculated_fpts" not in out.columns:
        out["calculated_fpts"] = np.nan
    if "calculated_fp_per_game" not in out.columns:
        out["calculated_fp_per_game"] = np.nan
    out["FPts"] = out["calculated_fpts"]
    out["FP/G"] = out["calculated_fp_per_game"]
    out["fantasy_points_source"] = "calculated_from_mlb_stats"
    return out


def append_daily_snapshot(filename, df, snapshot_columns):
    path = OUT_DIR / filename
    snapshot_date = date.today().isoformat()
    snapshot = safe_columns(df.copy(), ["Player", "Player_standard"] + snapshot_columns)
    snapshot.insert(0, "snapshot_date", snapshot_date)
    history = load_csv_if_exists(path)
    if not history.empty and "snapshot_date" in history.columns:
        history = history[history["snapshot_date"].astype(str) != snapshot_date]
    combined = pd.concat([history, snapshot], ignore_index=True)
    clean_for_csv(combined).to_csv(path, index=False)
    return combined, path


def add_snapshot_trends(df, history, metric_cols, activity_col, rate_cols, prefix):
    out = df.copy()
    if history.empty or "snapshot_date" not in history.columns:
        return out

    today = pd.Timestamp(date.today())
    history = history.copy()
    history["snapshot_date"] = pd.to_datetime(history["snapshot_date"], errors="coerce")
    history = history.dropna(subset=["snapshot_date", "Player_standard"])

    trend_cols = metric_cols + [activity_col] + rate_cols
    for col in trend_cols:
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors="coerce")

    for days in [7, 14, 30, 90]:
        target = today - pd.Timedelta(days=days)
        snapshot = history[history["snapshot_date"] <= target].copy()
        if snapshot.empty:
            continue
        snapshot = (
            snapshot.sort_values("snapshot_date")
            .groupby("Player_standard")
            .tail(1)
        )
        available = [col for col in trend_cols if col in snapshot.columns]
        snapshot = snapshot[["Player_standard"] + available].rename(
            columns={col: f"{col}_{days}d_ago" for col in available}
        )
        out = out.merge(snapshot, on="Player_standard", how="left")

    for col in out.columns:
        if (
            col.startswith(tuple(metric_cols + rate_cols))
            or col.startswith(activity_col)
            or col.startswith("trend_snapshots")
        ):
            out[col] = pd.to_numeric(out[col], errors="coerce").round(2)
    return out


def clean_for_csv(df):
    return df.replace([np.inf, -np.inf], np.nan).fillna("")


def write_output(name, df):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    clean_for_csv(df).to_csv(path, index=False)
    return path


def safe_columns(df, columns):
    for col in columns:
        if col not in df.columns:
            df[col] = np.nan
    return df[columns].copy()


def dedupe_player_rows(df):
    if "fantrax_id" not in df.columns:
        return df
    df = df.copy()
    score_cols = [
        "FPts",
        "Fantasy Points",
        "pitching_score",
        "hitter_score",
        "p_game",
        "GP",
    ]
    for col in score_cols:
        if col in df.columns:
            df[f"_{col}_sort"] = pd.to_numeric(df[col], errors="coerce").fillna(-1)
    sort_cols = [f"_{col}_sort" for col in score_cols if f"_{col}_sort" in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    df = df.drop_duplicates("fantrax_id", keep="first")
    return df.drop(columns=sort_cols, errors="ignore")


def merge_by_id_team_name(left, right, right_id_col, right_name_col="Player_standard"):
    left = left.copy()
    right = right.copy()
    if right.empty:
        return left

    left["_row_id"] = np.arange(len(left))
    original_left_name_counts = left["Player_standard"].value_counts(dropna=False)
    unmatched = left.copy()
    matched_frames = []

    def stat_compatible(matches):
        if matches.empty:
            return matches
        out = matches.copy()
        compatible = pd.Series(True, index=out.index)
        right_game_col = "p_game_matched" if "p_game_matched" in out.columns else "p_game"
        if "Pitching_G" in out.columns and right_game_col in out.columns:
            left_games = pd.to_numeric(out["Pitching_G"], errors="coerce")
            right_games = pd.to_numeric(out[right_game_col], errors="coerce")
            has_both = left_games.notna() & right_games.notna()
            compatible &= ~has_both | ((left_games - right_games).abs() <= PITCHER_GAME_MATCH_TOLERANCE)
        right_ab_col = "ab_matched" if "ab_matched" in out.columns else "ab"
        if "MLB_AB" in out.columns and right_ab_col in out.columns:
            left_ab = pd.to_numeric(out["MLB_AB"], errors="coerce")
            right_ab = pd.to_numeric(out[right_ab_col], errors="coerce")
            has_both = left_ab.notna() & right_ab.notna()
            compatible &= ~has_both | ((left_ab - right_ab).abs() <= HITTER_AB_MATCH_TOLERANCE)
        return out[compatible].copy()

    if "mlb_player_id" in left.columns and right_id_col in right.columns:
        left_id = unmatched.copy()
        left_id["mlb_player_id"] = pd.to_numeric(left_id["mlb_player_id"], errors="coerce")
        right_id = right.copy()
        right_id[right_id_col] = pd.to_numeric(right_id[right_id_col], errors="coerce")
        id_matches = left_id[left_id["mlb_player_id"].notna()].merge(
            right_id,
            left_on="mlb_player_id",
            right_on=right_id_col,
            how="inner",
            suffixes=("", "_matched"),
        )
        if not id_matches.empty:
            matched_frames.append(id_matches)
            unmatched = unmatched[~unmatched["_row_id"].isin(id_matches["_row_id"])]

    if "mlb_team" in unmatched.columns and "mlb_team" in right.columns:
        team_matches = unmatched.merge(
            right,
            left_on=["Player_standard", "mlb_team"],
            right_on=[right_name_col, "mlb_team"],
            how="inner",
            suffixes=("", "_matched"),
        )
        team_matches = stat_compatible(team_matches)
        if not team_matches.empty:
            matched_frames.append(team_matches)
            unmatched = unmatched[~unmatched["_row_id"].isin(team_matches["_row_id"])]

    right_name_counts = right[right_name_col].value_counts(dropna=False)
    unique_right = right[right[right_name_col].map(right_name_counts) == 1]
    unique_left = unmatched[unmatched["Player_standard"].map(original_left_name_counts) == 1]
    name_matches = unique_left.merge(
        unique_right,
        left_on="Player_standard",
        right_on=right_name_col,
        how="left",
        suffixes=("", "_matched"),
    )
    name_matches = stat_compatible(name_matches)
    matched_frames.append(name_matches)
    leftover = unmatched[~unmatched["_row_id"].isin(name_matches["_row_id"])]
    if not leftover.empty:
        matched_frames.append(leftover)

    merged = pd.concat(matched_frames, ignore_index=True, sort=False)
    merged = merged.sort_values("_row_id").drop(columns=["_row_id"], errors="ignore")
    return merged


def run_pipeline():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pitcher_baseball_savant = prepare_savant(fetch_savant_csv(CURRENT_YEAR, "pitcher"), "pitcher")
    hitter_baseball_savant = prepare_savant(fetch_savant_csv(CURRENT_YEAR, "batter"), "hitter")
    pitcher_previous = prepare_savant(fetch_savant_csv(PREVIOUS_YEAR, "pitcher"), "pitcher")
    hitter_previous = prepare_savant(fetch_savant_csv(PREVIOUS_YEAR, "batter"), "hitter")
    all_players, current_roster, streaming_pitchers, league_info = build_fantrax_frames()
    all_players = add_calculated_fantasy_points(all_players, league_info)
    fantasy_merge_cols = [
        "fantrax_id",
        "FPts",
        "FP/G",
        "fantasy_points_source",
        "GP",
        "MLB_AB",
        "Runs",
        "R_per_Game",
        "Pitching_G",
        "IP",
        "IP_per_Game_MLB",
    ]
    fantasy_merge_cols = [col for col in fantasy_merge_cols if col in all_players.columns]
    current_roster = current_roster.drop(
        columns=[
            "Fantasy Points",
            "Average Fantasy Points per Game",
            "GP",
            "MLB_AB",
            "Runs",
            "R_per_Game",
            "Pitching_G",
            "IP",
            "IP_per_Game_MLB",
        ],
        errors="ignore",
    ).merge(
        all_players[fantasy_merge_cols],
        on="fantrax_id",
        how="left",
    )
    current_roster["Fantasy Points"] = current_roster["FPts"]
    current_roster["Average Fantasy Points per Game"] = current_roster["FP/G"]
    streaming_pitchers = streaming_pitchers.drop(
        columns=["FPts", "FP/G", "fantasy_points_source"],
        errors="ignore",
    ).merge(
        all_players[["fantrax_id", "FPts", "FP/G", "fantasy_points_source"]],
        on="fantrax_id",
        how="left",
    )

    pitcher_previous_subset = pitcher_previous[[
        "player_id",
        "player_name_standard",
        "p_game",
        "pitching_score",
        "command_score",
        "whiff_percent",
        "bb_percent",
        "meatball_percent",
    ]].rename(columns={
        "pitching_score": f"pitching_score_{PREVIOUS_YEAR}",
        "command_score": f"command_score_{PREVIOUS_YEAR}",
        "whiff_percent": f"whiff_percent_{PREVIOUS_YEAR}",
        "bb_percent": f"bb_percent_{PREVIOUS_YEAR}",
        "meatball_percent": f"meatball_percent_{PREVIOUS_YEAR}",
    })
    hitter_previous_subset = hitter_previous[[
        "player_id",
        "player_name_standard",
        "ab",
        "hitter_score",
        "batters_eye_score",
        "barrel_batted_rate",
        "oz_swing_percent",
        "meatball_swing_percent",
    ]].rename(columns={
        "hitter_score": f"hitter_score_{PREVIOUS_YEAR}",
        "batters_eye_score": f"batters_eye_score_{PREVIOUS_YEAR}",
        "barrel_batted_rate": f"barrel_batted_rate_{PREVIOUS_YEAR}",
        "oz_swing_percent": f"oz_swing_percent_{PREVIOUS_YEAR}",
        "meatball_swing_percent": f"meatball_swing_percent_{PREVIOUS_YEAR}",
    })

    current_roster_pitchers = current_roster[current_roster["Eligible"].isin(["SP", "RP"])].copy()
    all_players_pitchers = all_players[all_players["Position"].isin(["SP", "RP"])].copy()
    current_roster_hitters = current_roster[~current_roster["Eligible"].isin(["SP", "RP"])].copy()
    all_players_hitters = all_players[~all_players["Position"].isin(["SP", "RP"])].copy()
    current_roster_pitchers = current_roster_pitchers[
        current_roster_pitchers["fantasy_team"] == MY_FANTASY_TEAM
    ].copy()
    current_roster_hitters = current_roster_hitters[
        current_roster_hitters["fantasy_team"] == MY_FANTASY_TEAM
    ].copy()

    def join_pitchers(df):
        out = merge_by_id_team_name(df, pitcher_baseball_savant, "player_id", "player_name_standard")
        return merge_by_id_team_name(out, pitcher_previous_subset, "player_id", "player_name_standard")

    def join_hitters(df):
        out = merge_by_id_team_name(df, hitter_baseball_savant, "player_id", "player_name_standard")
        return merge_by_id_team_name(out, hitter_previous_subset, "player_id", "player_name_standard")

    current_roster_pitchers_joined = join_pitchers(current_roster_pitchers)
    all_players_pitchers_joined = join_pitchers(all_players_pitchers)
    streaming_pitchers_joined = join_pitchers(streaming_pitchers)
    current_roster_hitters_joined = join_hitters(current_roster_hitters)
    all_players_hitters_joined = join_hitters(all_players_hitters)

    current_roster_hitters_joined["AB_per_Game"] = (
        pd.to_numeric(current_roster_hitters_joined.get("ab"), errors="coerce")
        / pd.to_numeric(current_roster_hitters_joined.get("GP"), errors="coerce")
    )
    all_players_hitters_joined["GP"] = (
        pd.to_numeric(all_players_hitters_joined.get("FPts"), errors="coerce")
        / pd.to_numeric(all_players_hitters_joined.get("FP/G"), errors="coerce")
    )
    all_players_hitters_joined["AB_per_Game"] = (
        pd.to_numeric(all_players_hitters_joined.get("ab"), errors="coerce")
        / pd.to_numeric(all_players_hitters_joined.get("GP"), errors="coerce")
    )
    current_roster_hitters_joined["R_per_Game"] = pd.to_numeric(
        current_roster_hitters_joined.get("R_per_Game"), errors="coerce"
    )
    all_players_hitters_joined["R_per_Game"] = pd.to_numeric(
        all_players_hitters_joined.get("R_per_Game"), errors="coerce"
    )

    recent_pitcher_trends, recent_hitter_trends = build_recent_trend_frames()

    def merge_recent(df, trends):
        return merge_by_id_team_name(df, trends, "mlb_player_id") if not trends.empty else df

    all_players_pitchers_joined = merge_recent(all_players_pitchers_joined, recent_pitcher_trends)
    current_roster_pitchers_joined = merge_recent(current_roster_pitchers_joined, recent_pitcher_trends)
    streaming_pitchers_joined = merge_recent(streaming_pitchers_joined, recent_pitcher_trends)
    all_players_hitters_joined = merge_recent(all_players_hitters_joined, recent_hitter_trends)
    current_roster_hitters_joined = merge_recent(current_roster_hitters_joined, recent_hitter_trends)

    current_roster_pitchers_joined = dedupe_player_rows(current_roster_pitchers_joined)
    all_players_pitchers_joined = dedupe_player_rows(all_players_pitchers_joined)
    streaming_pitchers_joined = dedupe_player_rows(streaming_pitchers_joined)
    current_roster_hitters_joined = dedupe_player_rows(current_roster_hitters_joined)
    all_players_hitters_joined = dedupe_player_rows(all_players_hitters_joined)

    pitcher_trend_metrics = ["pitching_score", "command_score", "whiff_percent"]
    hitter_trend_metrics = ["hitter_score", "batters_eye_score", "barrel_batted_rate"]
    pitcher_history, pitcher_history_path = append_daily_snapshot(
        "pitcher_daily_snapshots.csv",
        all_players_pitchers_joined,
        pitcher_trend_metrics + ["p_game", "IP_per_Game"],
    )
    hitter_history, hitter_history_path = append_daily_snapshot(
        "hitter_daily_snapshots.csv",
        all_players_hitters_joined,
        hitter_trend_metrics + ["GP", "AB_per_Game", "R_per_Game"],
    )
    status_order = {"ACTIVE": 0, "INJURED_RESERVE": 1, "MINORS": 2}
    current_roster_pitchers_joined["_status_order"] = (
        current_roster_pitchers_joined["Status"].map(status_order).fillna(99)
    )
    current_roster_pitchers_joined = current_roster_pitchers_joined.sort_values(
        ["_status_order", "IP_per_Game"],
        ascending=[True, False],
        na_position="last",
    ).drop(columns=["_status_order"])
    current_roster_hitters_joined["_status_order"] = (
        current_roster_hitters_joined["Status"].map(status_order).fillna(99)
    )
    current_roster_hitters_joined = current_roster_hitters_joined.sort_values(
        ["_status_order", "Fantasy Points"],
        ascending=[True, False],
        na_position="last",
    ).drop(columns=["_status_order"])
    streaming_pitchers_joined = streaming_pitchers_joined.sort_values(
        ["pitching_score", "command_score"],
        ascending=[False, False],
        na_position="last",
    )

    pitcher_window_cols = []
    pitcher_window_cols_with_sv_hld = []
    for days in [7, 14, 30]:
        pitcher_window_cols.extend([
            f"pitching_score_{days}d",
            f"command_score_{days}d",
            f"whiff_percent_{days}d",
            f"bb_percent_{days}d",
            f"meatball_percent_{days}d",
            f"p_game_{days}d",
            f"IP_per_Game_{days}d",
        ])
        pitcher_window_cols_with_sv_hld.extend([
            f"pitching_score_{days}d",
            f"command_score_{days}d",
            f"whiff_percent_{days}d",
            f"bb_percent_{days}d",
            f"meatball_percent_{days}d",
            f"p_game_{days}d",
            f"p_save_{days}d",
            f"p_hold_{days}d",
            f"IP_per_Game_{days}d",
        ])
    pitcher_snapshot_cols = []
    pitcher_trend_cols = pitcher_window_cols_with_sv_hld + pitcher_snapshot_cols

    hitter_window_cols = []
    for days in [7, 14, 30]:
        hitter_window_cols.extend([
            f"hitter_score_{days}d",
            f"batters_eye_score_{days}d",
            f"barrel_batted_rate_{days}d",
            f"barrels_{days}d",
            f"oz_swing_percent_{days}d",
            f"meatball_swing_percent_{days}d",
            f"GP_{days}d",
            f"AB_per_Game_{days}d",
            f"Runs_{days}d",
        ])
    hitter_snapshot_cols = []
    hitter_trend_cols = hitter_window_cols + hitter_snapshot_cols

    pitcher_cols = [
        "Player", "Eligible", "Status", "Fantasy Points", "Average Fantasy Points per Game",
        "p_formatted_ip", "p_save", "p_hold", "IP_per_Game", "p_era",
        "pitching_score", "command_score", "whiff_percent", "bb_percent", "meatball_percent",
        *pitcher_window_cols_with_sv_hld,
        f"pitching_score_{PREVIOUS_YEAR}", f"command_score_{PREVIOUS_YEAR}",
        f"whiff_percent_{PREVIOUS_YEAR}", f"bb_percent_{PREVIOUS_YEAR}", f"meatball_percent_{PREVIOUS_YEAR}",
        *pitcher_snapshot_cols,
    ]
    pitcher_analytics_cols = [
        "Player", "Position", "Status", "FPts", "FP/G",
        "p_game", "p_save", "p_hold", "IP_per_Game", "p_era", "pitching_score", "command_score",
        "whiff_percent", "bb_percent", "meatball_percent",
        *pitcher_window_cols_with_sv_hld,
        f"pitching_score_{PREVIOUS_YEAR}", f"command_score_{PREVIOUS_YEAR}",
        f"whiff_percent_{PREVIOUS_YEAR}", f"bb_percent_{PREVIOUS_YEAR}", f"meatball_percent_{PREVIOUS_YEAR}",
        *pitcher_snapshot_cols,
    ]
    streamer_cols = [
        "Player", "Team", "Opponent", "Position", "Status", "FPts", "FP/G",
        "p_game", "IP_per_Game", "p_era", "pitching_score", "command_score",
        "whiff_percent", "bb_percent", "meatball_percent",
        *pitcher_window_cols,
        f"pitching_score_{PREVIOUS_YEAR}", f"command_score_{PREVIOUS_YEAR}",
        f"whiff_percent_{PREVIOUS_YEAR}", f"bb_percent_{PREVIOUS_YEAR}", f"meatball_percent_{PREVIOUS_YEAR}",
        *pitcher_snapshot_cols,
    ]
    hitter_cols = [
        "Player", "Eligible", "Status", "Fantasy Points", "Average Fantasy Points per Game",
        "GP", "AB_per_Game", "hitter_score", "batters_eye_score",
        "barrel_batted_rate", "oz_swing_percent", "meatball_swing_percent",
        *hitter_window_cols,
        f"hitter_score_{PREVIOUS_YEAR}", f"batters_eye_score_{PREVIOUS_YEAR}",
        f"barrel_batted_rate_{PREVIOUS_YEAR}", f"oz_swing_percent_{PREVIOUS_YEAR}", f"meatball_swing_percent_{PREVIOUS_YEAR}",
        *hitter_snapshot_cols,
    ]
    hitter_analytics_cols = [
        "Player", "Position", "Status", "FPts", "FP/G", "GP", "AB_per_Game",
        "hitter_score", "batters_eye_score", "barrel_batted_rate", "oz_swing_percent", "meatball_swing_percent",
        *hitter_window_cols,
        f"hitter_score_{PREVIOUS_YEAR}", f"batters_eye_score_{PREVIOUS_YEAR}",
        f"barrel_batted_rate_{PREVIOUS_YEAR}", f"oz_swing_percent_{PREVIOUS_YEAR}", f"meatball_swing_percent_{PREVIOUS_YEAR}",
        *hitter_snapshot_cols,
    ]

    free_agent_pitchers = safe_columns(all_players_pitchers_joined, pitcher_analytics_cols)
    free_agent_pitchers = free_agent_pitchers[
        (free_agent_pitchers["Status"] == "FA")
        & pd.to_numeric(free_agent_pitchers["FPts"], errors="coerce").notna()
    ].copy()
    free_agent_pitchers = free_agent_pitchers.sort_values(
        ["pitching_score_7d", "command_score_7d", "whiff_percent_7d"],
        ascending=[False, False, False],
        na_position="last",
    )

    free_agent_hitters = safe_columns(all_players_hitters_joined, hitter_analytics_cols)
    free_agent_hitters = free_agent_hitters[
        (free_agent_hitters["Status"] == "FA")
        & pd.to_numeric(free_agent_hitters["FPts"], errors="coerce").notna()
    ].copy()
    free_agent_hitters = free_agent_hitters.sort_values(
        ["hitter_score_7d", "batters_eye_score_7d", "barrel_batted_rate_7d"],
        ascending=[False, False, False],
        na_position="last",
    )

    outputs = {
        "current_roster_pitchers.csv": safe_columns(current_roster_pitchers_joined, pitcher_cols),
        "pitcher_analytics.csv": safe_columns(all_players_pitchers_joined, pitcher_analytics_cols),
        "streaming_pitcher_analytics.csv": safe_columns(streaming_pitchers_joined, streamer_cols),
        "current_roster_hitters.csv": safe_columns(current_roster_hitters_joined, hitter_cols),
        "hitter_analytics.csv": safe_columns(all_players_hitters_joined, hitter_analytics_cols),
        "free_agent_pitchers.csv": free_agent_pitchers,
        "free_agent_hitters.csv": free_agent_hitters,
        "pitcher_baseball_savant.csv": pitcher_baseball_savant,
        "hitter_baseball_savant.csv": hitter_baseball_savant,
    }

    written = {name: str(write_output(name, df)) for name, df in outputs.items()}
    written["pitcher_daily_snapshots.csv"] = str(pitcher_history_path)
    written["hitter_daily_snapshots.csv"] = str(hitter_history_path)

    trend_day = date.today().isoformat()
    for filename, df in [
        ("pitching_trends_baseball_savant.csv", pitcher_baseball_savant),
        ("hitting_trends_baseball_savant.csv", hitter_baseball_savant),
    ]:
        trend_path = OUT_DIR / filename
        trend_df = df.copy()
        trend_df["current_date"] = trend_day
        history = load_csv_if_exists(trend_path)
        if not history.empty and "current_date" in history.columns:
            history = history[history["current_date"].astype(str) != trend_day]
        trend_df = pd.concat([history, trend_df], ignore_index=True)
        clean_for_csv(trend_df).to_csv(trend_path, index=False)
        written[filename] = str(trend_path)

    summary = pd.DataFrame([
        {"output": name, "rows": len(df), "path": written[name]}
        for name, df in outputs.items()
    ])
    written["run_summary.csv"] = str(write_output("run_summary.csv", summary))
    return summary, written


if __name__ == "__main__":
    summary, written = run_pipeline()
    print(summary.to_string(index=False))
    print(f"\nOutput directory: {OUT_DIR}")
