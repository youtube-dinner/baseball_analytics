#!/usr/bin/env python3
import csv
import json
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


LEAGUE_ID = "qqll39pvmj90wrl1"
SPORT = "MLB"
BASE_URL = "https://www.fantrax.com/fxea/general"
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"


def fetch_json(endpoint, **params):
    url = f"{BASE_URL}/{endpoint}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_url_json(url, **params):
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


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
    starters = probable_starters(probable_date)
    rostered_ids = {row.get("fantrax_id") for row in roster_items if row.get("fantrax_id")}
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
