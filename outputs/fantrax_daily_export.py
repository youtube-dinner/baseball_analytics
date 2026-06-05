#!/usr/bin/env python3
import csv
import json
import os
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


LEAGUE_ID = "qqll39pvmj90wrl1"
SPORT = "MLB"
BASE_URL = "https://www.fantrax.com/fxea/general"
UI_BASE_URL = "https://www.fantrax.com/fxpa"
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"
FANTRAX_AUTH_COOKIE = os.environ.get("FANTRAX_AUTH_COOKIE", "")
FANTRAX_OLD_UI_TOKEN = os.environ.get("FANTRAX_OLD_UI_TOKEN", "")
FANTRAX_PROBABLE_MISC_DISPLAY_TYPE = os.environ.get("FANTRAX_PROBABLE_MISC_DISPLAY_TYPE", "7")
FANTRAX_PROBABLE_DATE_PLAYING = os.environ.get("FANTRAX_PROBABLE_DATE_PLAYING", "")
NETWORK_RETRIES = max(1, int(os.environ.get("FANTRAX_NETWORK_RETRIES", "4")))
NETWORK_RETRY_DELAY_SECONDS = max(1.0, float(os.environ.get("FANTRAX_NETWORK_RETRY_DELAY_SECONDS", "5")))
NETWORK_TIMEOUT_SECONDS = max(1, int(os.environ.get("FANTRAX_NETWORK_TIMEOUT_SECONDS", "60")))


def fetch_bytes(req, url_label):
    last_error = None
    for attempt in range(1, NETWORK_RETRIES + 1):
        try:
            with urlopen(req, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == NETWORK_RETRIES:
                raise
            last_error = exc
        except (URLError, OSError) as exc:
            if attempt == NETWORK_RETRIES:
                raise
            last_error = exc
        print(
            f"Retrying {url_label} after attempt {attempt}/{NETWORK_RETRIES} failed: {last_error}",
            flush=True,
        )
        time.sleep(NETWORK_RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError(f"Failed to fetch {url_label}: {last_error}")


def fetch_json(endpoint, **params):
    url = f"{BASE_URL}/{endpoint}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.loads(fetch_bytes(req, url).decode("utf-8"))


def fetch_url_json(url, **params):
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.loads(fetch_bytes(req, url).decode("utf-8"))


def fetch_ui_bytes(endpoint, **params):
    if FANTRAX_OLD_UI_TOKEN:
        params["olduitk"] = FANTRAX_OLD_UI_TOKEN
    url = f"{UI_BASE_URL}/{endpoint}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
    if FANTRAX_AUTH_COOKIE:
        headers["Cookie"] = FANTRAX_AUTH_COOKIE
    req = Request(url, headers=headers)
    raw = fetch_bytes(req, url)
    if raw.strip().startswith(b"{"):
        data = json.loads(raw.decode("utf-8"))
        page_error = data.get("pageError") or data.get("error")
        if page_error:
            code = page_error.get("code") or "Fantrax UI error"
            text = page_error.get("text") or page_error.get("message") or ""
            raise RuntimeError(f"{code}: {text}".strip())
    return raw


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def player_row(fantrax_id, league_player, player_ids):
    player = player_ids.get(fantrax_id, {})
    return {
        "fantrax_id": fantrax_id,
        "name": player.get("name"),
        "mlb_team": player.get("team"),
        "primary_position": player.get("position"),
        "eligible_positions": league_player.get("eligiblePos"),
        "league_status": league_player.get("status"),
        "stats_inc_id": player.get("statsIncId"),
        "rotowire_id": player.get("rotowireId"),
        "sport_radar_id": player.get("sportRadarId"),
    }


def roster_rows(rosters, player_ids):
    rows = []
    for team_id, roster in rosters.get("rosters", {}).items():
        for item in roster.get("rosterItems", []):
            fantrax_id = item.get("id")
            player = player_ids.get(fantrax_id, {})
            rows.append({
                "period": rosters.get("period"),
                "team_id": team_id,
                "team_name": roster.get("teamName"),
                "fantrax_id": fantrax_id,
                "name": player.get("name"),
                "mlb_team": player.get("team"),
                "primary_position": player.get("position"),
                "roster_position": item.get("position"),
                "roster_status": item.get("status"),
                "salary": item.get("salary"),
                "contract": item.get("contract"),
            })
    return rows


def sortable_name(name):
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(char for char in name if not unicodedata.combining(char))
    name = name.lower().replace(".", "").replace("'", "").replace("-", " ")
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        name = f"{first} {last}"
    return " ".join(name.split())


def display_name(fantrax_name):
    if not fantrax_name:
        return ""
    name = str(fantrax_name)
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return f"{first} {last}".strip()
    return name.strip()


def tomorrow_date():
    override = os.environ.get("FANTRAX_PROBABLE_DATE")
    if override:
        return override
    local_today = datetime.now(ZoneInfo("America/Chicago")).date()
    return (local_today + timedelta(days=1)).isoformat()


def probable_starters(date):
    schedule = fetch_url_json(
        MLB_SCHEDULE_URL,
        sportId=1,
        date=date,
        hydrate="probablePitcher",
    )
    starters = {}
    for date_group in schedule.get("dates", []):
        for game in date_group.get("games", []):
            teams = game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})
            away_team = away.get("team", {})
            home_team = home.get("team", {})
            for side, team, opponent, is_home in [
                ("away", away_team, home_team, False),
                ("home", home_team, away_team, True),
            ]:
                pitcher = teams.get(side, {}).get("probablePitcher")
                if not pitcher:
                    continue
                starters[sortable_name(pitcher.get("fullName"))] = {
                    "probable_date": date,
                    "mlb_player_id": pitcher.get("id"),
                    "probable_name": pitcher.get("fullName"),
                    "game_pk": game.get("gamePk"),
                    "game_time_utc": game.get("gameDate"),
                    "home_away": "home" if is_home else "away",
                    "probable_team": team.get("abbreviation") or team.get("teamName") or team.get("name"),
                    "opponent": opponent.get("abbreviation") or opponent.get("teamName") or opponent.get("name"),
                }
    return starters


def first_present(row, names):
    for name in names:
        if name in row and str(row[name]).strip():
            return row[name]
    return ""


def probable_candidate_params(probable_date):
    base = {
        "leagueId": LEAGUE_ID,
        "positionOrGroup": "BASEBALL_PITCHING",
        "miscDisplayType": FANTRAX_PROBABLE_MISC_DISPLAY_TYPE,
        "maxResultsPerPage": 500,
        "pageNumber": 1,
    }
    if FANTRAX_PROBABLE_DATE_PLAYING:
        return [{**base, "datePlaying": FANTRAX_PROBABLE_DATE_PLAYING}]
    candidates = [{**base, "datePlaying": probable_date}]
    for misc_display_type in ["7", "8"]:
        candidates.append({**base, "miscDisplayType": misc_display_type, "datePlaying": probable_date})
    candidates.append(base)
    unique = []
    seen = set()
    for params in candidates:
        key = tuple(sorted(params.items()))
        if key not in seen:
            seen.add(key)
            unique.append(params)
    return unique


def fantrax_ui_probable_starter_rows(probable_date, player_ids, league_players, rostered_ids):
    if not FANTRAX_AUTH_COOKIE and not FANTRAX_OLD_UI_TOKEN:
        raise RuntimeError("Fantrax UI probable-starter feed requires FANTRAX_AUTH_COOKIE or FANTRAX_OLD_UI_TOKEN")

    import pandas as pd
    from io import BytesIO

    best_df = pd.DataFrame()
    best_params = None
    last_error = None
    for params in probable_candidate_params(probable_date):
        try:
            raw = fetch_ui_bytes("downloadPlayerStats", **params)
            candidate = pd.read_csv(BytesIO(raw), encoding="utf-8-sig")
            candidate = candidate.dropna(how="all").drop(
                columns=[col for col in candidate.columns if str(col).startswith("Unnamed")],
                errors="ignore",
            )
            if candidate.shape[0] > best_df.shape[0]:
                best_df = candidate
                best_params = params
        except Exception as exc:
            last_error = exc
    if best_df.empty:
        raise RuntimeError(f"No Fantrax UI probable starters returned: {last_error}")

    pitchers = {}
    for fantrax_id, player in player_ids.items():
        if player.get("position") not in {"SP", "RP"}:
            continue
        name = display_name(player.get("name"))
        pitchers.setdefault(sortable_name(name), []).append((fantrax_id, player))

    rows = []
    for raw_row in best_df.to_dict("records"):
        raw_name = first_present(raw_row, ["Player", "Name", "Scorer", "player", "name"])
        if not raw_name:
            continue
        name = display_name(raw_name)
        team = first_present(raw_row, ["Team", "MLB Team", "Pro Team", "team", "mlb_team"])
        matches = pitchers.get(sortable_name(name), [])
        if team:
            team_matches = [(fantrax_id, player) for fantrax_id, player in matches if player.get("team") == team]
            if team_matches:
                matches = team_matches
        fantrax_id, player = matches[0] if matches else ("", {})
        league_player = league_players.get(fantrax_id, {})
        rows.append({
            "probable_date": probable_date,
            "game_time_utc": first_present(raw_row, ["Game Time", "Game", "Start Time"]),
            "home_away": first_present(raw_row, ["Home/Away", "H/A"]),
            "probable_team": player.get("team") or team,
            "opponent": first_present(raw_row, ["Opponent", "Opp", "OPP"]),
            "mlb_player_id": "",
            "probable_name": display_name(player.get("name")) or name,
            "fantrax_id": fantrax_id,
            "name": player.get("name") or name,
            "mlb_team": player.get("team") or team,
            "primary_position": player.get("position"),
            "eligible_positions": league_player.get("eligiblePos"),
            "league_status": league_player.get("status"),
            "is_rostered": fantrax_id in rostered_ids if fantrax_id else False,
            "stats_inc_id": player.get("statsIncId"),
            "rotowire_id": player.get("rotowireId"),
            "sport_radar_id": player.get("sportRadarId"),
            "game_pk": "",
            "fantrax_probable_source": "fantrax_ui_downloadPlayerStats",
            "fantrax_probable_params": json.dumps(best_params, sort_keys=True),
        })
    return rows


def probable_starter_rows(starters, player_ids, league_players, rostered_ids):
    by_name = {sortable_name(player.get("name")): player for player in player_ids.values()}
    rows = []
    for name_key, starter in starters.items():
        player = by_name.get(name_key, {})
        fantrax_id = player.get("fantraxId")
        league_player = league_players.get(fantrax_id, {})
        rows.append({
            **starter,
            "fantrax_id": fantrax_id,
            "name": player.get("name") or starter.get("probable_name"),
            "mlb_team": player.get("team"),
            "primary_position": player.get("position"),
            "eligible_positions": league_player.get("eligiblePos"),
            "league_status": league_player.get("status"),
            "is_rostered": fantrax_id in rostered_ids if fantrax_id else False,
            "stats_inc_id": player.get("statsIncId"),
            "rotowire_id": player.get("rotowireId"),
            "sport_radar_id": player.get("sportRadarId"),
        })
    rows.sort(key=lambda row: (row.get("game_time_utc") or "", row.get("name") or ""))
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    player_ids = fetch_json("getPlayerIds", sport=SPORT)
    league_info = fetch_json("getLeagueInfo", leagueId=LEAGUE_ID)
    rosters = fetch_json("getTeamRosters", leagueId=LEAGUE_ID)
    standings = fetch_json("getStandings", leagueId=LEAGUE_ID)
    draft_results = fetch_json("getDraftResults", leagueId=LEAGUE_ID)
    draft_picks = fetch_json("getDraftPicks", leagueId=LEAGUE_ID)

    raw_dir = OUT_DIR / f"raw_{stamp}"
    raw_dir.mkdir()
    write_json(raw_dir / "player_ids.json", player_ids)
    write_json(raw_dir / "league_info.json", league_info)
    write_json(raw_dir / "team_rosters.json", rosters)
    write_json(raw_dir / "standings.json", standings)
    write_json(raw_dir / "draft_results.json", draft_results)
    write_json(raw_dir / "draft_picks.json", draft_picks)

    players = [
        player_row(fantrax_id, info, player_ids)
        for fantrax_id, info in league_info.get("playerInfo", {}).items()
    ]
    players.sort(key=lambda row: (row.get("name") or "", row["fantrax_id"]))

    teams = sorted(league_info.get("teamInfo", {}).values(), key=lambda row: row.get("name", ""))
    roster_items = roster_rows(rosters, player_ids)
    roster_items.sort(key=lambda row: (row.get("team_name") or "", row.get("name") or ""))
    probable_date = tomorrow_date()
    rostered_ids = {row.get("fantrax_id") for row in roster_items if row.get("fantrax_id")}
    try:
        all_probable_starters = fantrax_ui_probable_starter_rows(
            probable_date,
            player_ids,
            league_info.get("playerInfo", {}),
            rostered_ids,
        )
        starters = {sortable_name(row.get("probable_name")): row for row in all_probable_starters}
    except Exception:
        starters = probable_starters(probable_date)
        all_probable_starters = probable_starter_rows(
            starters,
            player_ids,
            league_info.get("playerInfo", {}),
            rostered_ids,
        )
    unrostered_probable_starters = [
        row for row in all_probable_starters if not row.get("is_rostered")
    ]
    probable_roster_items = []
    for row in roster_items:
        starter = starters.get(sortable_name(row.get("name")))
        if starter:
            probable_roster_items.append({**row, **starter})

    write_csv(
        OUT_DIR / "fantrax_players_latest.csv",
        players,
        [
            "fantrax_id",
            "name",
            "mlb_team",
            "primary_position",
            "eligible_positions",
            "league_status",
            "stats_inc_id",
            "rotowire_id",
            "sport_radar_id",
        ],
    )
    write_csv(OUT_DIR / "fantrax_teams_latest.csv", teams, ["id", "name"])
    write_csv(
        OUT_DIR / "fantrax_rosters_latest.csv",
        roster_items,
        [
            "period",
            "team_id",
            "team_name",
            "fantrax_id",
            "name",
            "mlb_team",
            "primary_position",
            "roster_position",
            "roster_status",
            "salary",
            "contract",
        ],
    )
    write_csv(
        OUT_DIR / "fantrax_rosters_probable_starters_tomorrow_latest.csv",
        probable_roster_items,
        [
            "probable_date",
            "game_time_utc",
            "home_away",
            "probable_team",
            "opponent",
            "mlb_player_id",
            "probable_name",
            "period",
            "team_id",
            "team_name",
            "fantrax_id",
            "name",
            "mlb_team",
            "primary_position",
            "roster_position",
            "roster_status",
            "salary",
            "contract",
            "game_pk",
        ],
    )
    probable_fields = [
        "probable_date",
        "game_time_utc",
        "home_away",
        "probable_team",
        "opponent",
        "mlb_player_id",
        "probable_name",
        "fantrax_id",
        "name",
        "mlb_team",
        "primary_position",
        "eligible_positions",
        "league_status",
        "is_rostered",
        "stats_inc_id",
        "rotowire_id",
        "sport_radar_id",
        "game_pk",
    ]
    write_csv(
        OUT_DIR / "fantrax_probable_starters_all_tomorrow_latest.csv",
        all_probable_starters,
        probable_fields,
    )
    write_csv(
        OUT_DIR / "fantrax_probable_starters_unrostered_tomorrow_latest.csv",
        unrostered_probable_starters,
        probable_fields,
    )
    write_csv(
        OUT_DIR / "fantrax_standings_latest.csv",
        standings,
        ["rank", "teamId", "teamName", "points", "gamesBack", "winPercentage", "totalPointsFor"],
    )

    print(f"Wrote Fantrax export to {OUT_DIR}")
    print(f"Players: {len(players)}")
    print(f"Roster items: {len(roster_items)}")
    print(f"Roster probable starters for {probable_date}: {len(probable_roster_items)}")
    print(f"All probable starters for {probable_date}: {len(all_probable_starters)}")
    print(f"Unrostered probable starters for {probable_date}: {len(unrostered_probable_starters)}")
    print(f"Teams: {len(teams)}")
    print(f"Standings rows: {len(standings)}")


if __name__ == "__main__":
    main()
