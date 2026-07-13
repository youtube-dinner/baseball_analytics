#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


LEAGUE_ID = os.environ.get("FANTRAX_LEAGUE_ID") or "qqll39pvmj90wrl1"
FANTRAX_OLD_UI_TOKEN = os.environ.get("FANTRAX_OLD_UI_TOKEN", "")
FANTRAX_REQ_URL = "https://www.fantrax.com/fxpa/req"
FANTRAX_GENERAL_URL = "https://www.fantrax.com/fxea/general"
OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"
FANTRAX_AUTH_COOKIE_FILE = Path(os.environ.get(
    "FANTRAX_AUTH_COOKIE_FILE",
    OUT_DIR / "fantrax_auth_cookie_latest.txt",
))
CENTRAL = ZoneInfo("America/Chicago")
EASTERN = ZoneInfo("America/New_York")
FANTRAX_DISPLAY_TIMEZONE = ZoneInfo(os.environ.get("FANTRAX_DISPLAY_TIMEZONE", "America/Chicago"))
FANTRAX_DATE_FORMATS = [
    "%a %b %d, %Y, %I:%M%p",
    "%a %b %d, %Y %I:%M%p",
    "%b %d, %Y, %I:%M%p",
    "%b %d, %Y %I:%M%p",
]
ADD_TRANSACTION_CODES = {"ADD", "CLAIM"}
ADD_CLAIM_TYPES = {"FA", "WAIVER", "FREE_AGENT", "FREE AGENT"}
DROP_TYPES = {"DROP", "RELEASE", "REMOVE"}
MINORS_MARKERS = {"MINORS", "MINOR", "MINOR_LEAGUE", "MINOR LEAGUE"}
DEFAULT_MAJOR_ADD_LIMIT_OVERRIDES = {"2026-07-13": 14}


def fantrax_auth_cookie():
    cookie = os.environ.get("FANTRAX_AUTH_COOKIE", "")
    if cookie:
        return cookie
    if FANTRAX_AUTH_COOKIE_FILE.exists():
        return FANTRAX_AUTH_COOKIE_FILE.read_text(encoding="utf-8").strip()
    return ""


def fetch_fantrax_req(method, data):
    payload = {"msgs": [{"method": method, "data": {"leagueId": LEAGUE_ID, **data}}]}
    params = {"leagueId": LEAGUE_ID}
    if FANTRAX_OLD_UI_TOKEN:
        params["olduitk"] = FANTRAX_OLD_UI_TOKEN
    url = f"{FANTRAX_REQ_URL}?{urlencode(params)}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    cookie = fantrax_auth_cookie()
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_league_scoring_start():
    params = urlencode({"leagueId": LEAGUE_ID})
    req = Request(
        f"{FANTRAX_GENERAL_URL}/getLeagueInfo?{params}",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as response:
            league_info = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not fetch Fantrax league scoring periods: {exc}") from exc
    start_date = league_info.get("startDate")
    try:
        return datetime.fromisoformat(start_date).date()
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Fantrax league start date is invalid: {start_date!r}") from exc


def parse_fantrax_period_date(value):
    return datetime.strptime(value.strip(), "%a %b %d, %Y").date()


def parse_period_date_range(value):
    match = re.search(r"\(([^-]+) - ([^)]+)\)", str(value or ""))
    if not match:
        return None
    return parse_fantrax_period_date(match.group(1)), parse_fantrax_period_date(match.group(2))


def fetch_matchup_period_windows():
    raw = fetch_fantrax_req("getMatchups", {})
    data = response_data(raw)
    windows = []
    for period in data.get("periods") or []:
        parsed = parse_period_date_range(period.get("dateRange"))
        if not parsed:
            continue
        start, end = parsed
        windows.append({
            "number": int_value(period.get("number")),
            "start": start,
            "end": end,
            "date_range": period.get("dateRange", ""),
            "caption": period.get("caption", ""),
        })
    return sorted(windows, key=lambda item: item["start"])


def fetch_fantrax_general(endpoint, **params):
    query = urlencode({"leagueId": LEAGUE_ID, **params})
    req = Request(
        f"{FANTRAX_GENERAL_URL}/{endpoint}?{query}",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def int_value(value):
    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        return 0


def effective_scoring_date(transaction_period, league_start_date):
    if transaction_period <= 0:
        return None
    return league_start_date + timedelta(days=transaction_period - 1)


def matchup_window_for_date(day, matchup_windows):
    for window in matchup_windows:
        if window["start"] <= day <= window["end"]:
            return window
    week_start_date = day - timedelta(days=day.weekday())
    return {
        "number": 0,
        "start": week_start_date,
        "end": week_start_date + timedelta(days=6),
        "date_range": "",
        "caption": "",
    }


def current_pickup_window(matchup_windows):
    today = datetime.now(EASTERN).date()
    window = matchup_window_for_date(today, matchup_windows)
    return (
        datetime.combine(window["start"], time(0), EASTERN),
        datetime.combine(window["end"] + timedelta(days=1), time(0), EASTERN),
        window,
    )


def assign_effective_periods(rows, league_start_date, matchup_windows):
    for row in rows:
        transaction_period = row.get("transaction_period", 0)
        scoring_date = effective_scoring_date(transaction_period, league_start_date)
        if not scoring_date:
            row["effective_scoring_date"] = ""
            row["effective_week_start"] = ""
            row["effective_period_start"] = ""
            row["effective_period_end"] = ""
            row["effective_period_number"] = ""
            continue
        window = matchup_window_for_date(scoring_date, matchup_windows)
        period_start = datetime.combine(window["start"], time(0), EASTERN)
        row["effective_scoring_date"] = scoring_date.isoformat()
        row["effective_week_start"] = period_start.isoformat()
        row["effective_period_start"] = period_start.isoformat()
        row["effective_period_end"] = datetime.combine(window["end"] + timedelta(days=1), time(0), EASTERN).isoformat()
        row["effective_period_number"] = window.get("number", "")
    return rows


def response_data(raw):
    responses = raw.get("responses") or []
    if not responses:
        page_error = raw.get("pageError") or {}
        raise RuntimeError(page_error.get("code") or "Fantrax response did not include responses")
    first = responses[0]
    page_error = first.get("pageError") or raw.get("pageError") or {}
    if page_error:
        code = page_error.get("code") or "Fantrax page error"
        text = page_error.get("text") or page_error.get("message") or ""
        if code == "WARNING_NOT_LOGGED_IN":
            raise RuntimeError(
                "Fantrax requires auth for transaction history. Set FANTRAX_AUTH_COOKIE "
                "to your logged-in browser cookie string, then rerun this audit."
            )
        raise RuntimeError(f"{code}: {text}".strip())
    return first.get("data") or first


def table_rows(data):
    if isinstance(data.get("table"), dict):
        return data["table"].get("rows", [])
    for table in data.get("tableList", []) or []:
        rows = table.get("rows")
        if rows:
            return rows
    return data.get("rows", [])


def parse_fantrax_datetime(value):
    if not value:
        return None
    value = re.sub(r"\s+", " ", str(value).strip())
    for fmt in FANTRAX_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=FANTRAX_DISPLAY_TIMEZONE)
        except ValueError:
            pass
    return None


def cell_content(row, index, key=None):
    cells = row.get("cells") or []
    if key:
        for cell in cells:
            if isinstance(cell, dict) and cell.get("key") == key:
                return cell.get("content") or cell.get("text") or cell.get("value")
    if index < len(cells) and isinstance(cells[index], dict):
        return cells[index].get("content") or cells[index].get("text") or cells[index].get("value")
    return ""


def cell_by_key(row, key):
    for cell in row.get("cells") or []:
        if isinstance(cell, dict) and cell.get("key") == key:
            return cell
    return {}


def player_id_from_scorer(scorer):
    return (
        scorer.get("scorerId")
        or scorer.get("id")
        or scorer.get("playerId")
        or scorer.get("fantraxId")
        or ""
    )


def player_name_from_scorer(scorer):
    return (
        scorer.get("name")
        or scorer.get("fullName")
        or scorer.get("shortName")
        or scorer.get("displayName")
        or ""
    )


def transaction_player_type(row):
    transaction_code = str(row.get("transactionCode") or "").strip().upper()
    claim_type = str(row.get("claimType") or "").strip().upper()
    if transaction_code == "CLAIM" and claim_type:
        return claim_type
    return claim_type or transaction_code


def is_add_transaction(row):
    transaction_code = str(row.get("transactionCode") or "").strip().upper()
    claim_type = str(row.get("claimType") or "").strip().upper()
    if transaction_code in ADD_TRANSACTION_CODES:
        return True
    return claim_type in ADD_CLAIM_TYPES and transaction_code not in DROP_TYPES


def row_has_minors_marker(row):
    text_values = []
    for key in ("toRosterStatus", "rosterStatus", "status", "toPosition", "position", "slot", "claimType"):
        if row.get(key) is not None:
            text_values.append(str(row[key]))
    for cell in row.get("cells") or []:
        if isinstance(cell, dict):
            text_values.extend(str(v) for v in cell.values() if isinstance(v, (str, int, float)))
    haystack = " ".join(text_values).upper()
    return any(marker in haystack for marker in MINORS_MARKERS)


def roster_status_key(period, team_id, fantrax_id):
    return (int_value(period), team_id or "", fantrax_id or "")


def load_current_roster_statuses(path):
    statuses = {}
    if not path.exists():
        return statuses
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fantrax_id = row.get("fantrax_id")
            if fantrax_id:
                statuses[roster_status_key(row.get("period"), row.get("team_id"), fantrax_id)] = row
    return statuses


def fetch_roster_statuses_for_periods(periods, teams, players):
    statuses = {}
    for period in sorted(period for period in periods if period):
        rosters = fetch_fantrax_general("getTeamRosters", period=str(period))
        for team_id, roster in (rosters.get("rosters") or {}).items():
            team_name = teams.get(team_id, team_id)
            for item in roster.get("rosterItems", []) or []:
                fantrax_id = item.get("id")
                if not fantrax_id:
                    continue
                player = players.get(fantrax_id, {})
                statuses[roster_status_key(period, team_id, fantrax_id)] = {
                    "period": str(rosters.get("period") or period),
                    "team_id": team_id,
                    "team_name": team_name,
                    "fantrax_id": fantrax_id,
                    "name": player.get("name", ""),
                    "mlb_team": player.get("mlb_team", ""),
                    "primary_position": player.get("primary_position", ""),
                    "roster_position": item.get("position", ""),
                    "roster_status": item.get("status", ""),
                }
    return statuses


def load_players(path):
    players = {}
    if not path.exists():
        return players
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fantrax_id = row.get("fantrax_id")
            if fantrax_id:
                players[fantrax_id] = row
    return players


def load_teams(path):
    teams = {}
    if not path.exists():
        return teams
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            team_id = row.get("id")
            if team_id:
                teams[team_id] = row.get("name") or team_id
    return teams


def current_week_window():
    now = datetime.now(EASTERN)
    start = datetime.combine(now.date() - timedelta(days=now.weekday()), time(0), EASTERN)
    if now < start:
        start -= timedelta(days=7)
    return start, start + timedelta(days=7)


def add_limit_overrides():
    raw = os.environ.get("FANTRAX_MAJOR_ADD_LIMIT_OVERRIDES", "")
    if not raw:
        return DEFAULT_MAJOR_ADD_LIMIT_OVERRIDES
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"FANTRAX_MAJOR_ADD_LIMIT_OVERRIDES must be JSON: {exc}") from exc
    return {str(key): int_value(value) for key, value in parsed.items() if int_value(value)}


def pickup_limit_for_window(start, base_limit):
    overrides = add_limit_overrides()
    return overrides.get(start.date().isoformat(), base_limit)


def normalize_rows(rows, roster_statuses, players, teams):
    normalized = []
    seen = set()
    for row in rows:
        tx_set_id = row.get("txSetId") or row.get("id") or ""
        team_cell = cell_by_key(row, "team")
        date_cell = cell_by_key(row, "date")
        period_cell = cell_by_key(row, "week")
        team_id = row.get("teamId") or team_cell.get("teamId") or team_cell.get("id") or ""
        team_name = row.get("teamName") or team_cell.get("content") or teams.get(team_id, "")
        date_text = row.get("date") or row.get("transactionDate") or date_cell.get("content") or ""
        date = parse_fantrax_datetime(date_text)
        scorer = row.get("scorer") or row.get("player") or {}
        fantrax_id = player_id_from_scorer(scorer)
        transaction_period = int_value(period_cell.get("content"))
        unique_key = (tx_set_id, row.get("transactionCode", ""), fantrax_id)
        if unique_key in seen:
            continue
        seen.add(unique_key)
        current_roster = roster_statuses.get(roster_status_key(transaction_period, team_id, fantrax_id), {})
        player = players.get(fantrax_id, {})
        player_type = transaction_player_type(row)
        current_roster_status = current_roster.get("roster_status", "")
        tx_minors = row_has_minors_marker(row)
        current_minors = current_roster_status.upper() in MINORS_MARKERS
        primary_position = (
            player.get("primary_position")
            or current_roster.get("primary_position", "")
            or str(scorer.get("posShortNames") or "").split(",")[0].strip()
        )
        is_minor_exempt = tx_minors or current_minors
        normalized.append({
            "tx_set_id": tx_set_id,
            "transaction_date": date.isoformat() if date else "",
            "transaction_date_raw": date_text,
            "transaction_period": transaction_period,
            "team_id": team_id,
            "team_name": team_name,
            "fantrax_id": fantrax_id,
            "player_name": player_name_from_scorer(scorer) or player.get("name", ""),
            "primary_position": primary_position,
            "transaction_code": row.get("transactionCode", ""),
            "claim_type": row.get("claimType", ""),
            "player_transaction_type": player_type,
            "is_add": is_add_transaction(row),
            "transaction_row_mentions_minors": tx_minors,
            "current_roster_status": current_roster_status,
            "current_roster_position": current_roster.get("roster_position", ""),
            "current_roster_team": current_roster.get("team_name", ""),
            "current_roster_is_minors": current_minors,
            "is_minor_exempt": is_minor_exempt,
            "major_minor_class": "minor" if is_minor_exempt else "major",
            "is_sp": primary_position == "SP",
            "is_rp": primary_position == "RP",
            "minor_exempt_confidence": "transaction_row" if tx_minors else ("current_roster" if current_minors else ""),
        })
    return normalized


def summarize_adds(rows, pickup_limit, teams):
    summaries = {}
    details_by_team = defaultdict(list)
    for row in rows:
        if not row["is_add"]:
            continue
        key = (row["team_id"], row["team_name"])
        details_by_team[key].append(row)

    for key, details in details_by_team.items():
        minor_exempt = [row for row in details if row["is_minor_exempt"]]
        major_adds = [row for row in details if not row["is_minor_exempt"]]
        counted = len(details) - len(minor_exempt)
        summaries[key] = {
            "team_id": key[0],
            "team_name": key[1],
            "counted_adds": counted,
            "major_leaguer_adds": len(major_adds),
            "minor_exempt_adds": len(minor_exempt),
            "minor_leaguer_adds": len(minor_exempt),
            "sp_adds": sum(1 for row in details if row["is_sp"]),
            "rp_adds": sum(1 for row in details if row["is_rp"]),
            "major_sp_adds": sum(1 for row in major_adds if row["is_sp"]),
            "major_rp_adds": sum(1 for row in major_adds if row["is_rp"]),
            "minor_sp_adds": sum(1 for row in minor_exempt if row["is_sp"]),
            "minor_rp_adds": sum(1 for row in minor_exempt if row["is_rp"]),
            "total_adds": len(details),
            "remaining_of_limit": max(0, pickup_limit - counted),
            "over_limit_by": max(0, counted - pickup_limit),
        }
    for team_id, team_name in teams.items():
        key = (team_id, team_name)
        if key not in summaries:
            summaries[key] = {
                "team_id": team_id,
                "team_name": team_name,
                "counted_adds": 0,
                "major_leaguer_adds": 0,
                "minor_exempt_adds": 0,
                "minor_leaguer_adds": 0,
                "sp_adds": 0,
                "rp_adds": 0,
                "major_sp_adds": 0,
                "major_rp_adds": 0,
                "minor_sp_adds": 0,
                "minor_rp_adds": 0,
                "total_adds": 0,
                "remaining_of_limit": pickup_limit,
                "over_limit_by": 0,
            }
    return sorted(summaries.values(), key=lambda row: (-row["counted_adds"], row["team_name"]))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Audit Fantrax player adds by team for a weekly pickup limit.")
    parser.add_argument("--start", help="Inclusive Eastern Time start, e.g. 2026-06-01T00:00")
    parser.add_argument("--end", help="Exclusive Eastern Time end, e.g. 2026-06-08T00:00")
    parser.add_argument("--max-results", type=int, default=500, help="Rows per page to request from Fantrax.")
    parser.add_argument("--pages", type=int, default=5, help="Maximum Fantrax transaction pages to fetch.")
    parser.add_argument("--pickup-limit", type=int, default=int(os.environ.get("FANTRAX_MAJOR_ADD_LIMIT", "10")))
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    matchup_windows = fetch_matchup_period_windows()
    selected_window = None
    if args.start:
        start = datetime.fromisoformat(args.start).replace(tzinfo=EASTERN)
        if not args.end:
            raise SystemExit("--end is required when --start is provided")
        end = datetime.fromisoformat(args.end).replace(tzinfo=EASTERN)
        selected_window = matchup_window_for_date(start.date(), matchup_windows)
    else:
        start, end, selected_window = current_pickup_window(matchup_windows)
    pickup_limit = pickup_limit_for_window(start, args.pickup_limit)

    raw_pages = []
    rows = []
    for page in range(1, args.pages + 1):
        try:
            raw = fetch_fantrax_req(
                "getTransactionDetailsHistory",
                {
                    "maxResultsPerPage": str(args.max_results),
                    "pageNumber": str(page),
                    "view": "CLAIM_DROP",
                    "executedOnly": True,
                    "includeDeleted": False,
                },
            )
        except Exception as exc:
            raise SystemExit(f"Fantrax transaction audit failed: {exc}") from exc
        raw_pages.append(raw)
        try:
            page_rows = table_rows(response_data(raw))
        except Exception as exc:
            raise SystemExit(f"Fantrax transaction audit failed: {exc}") from exc
        rows.extend(page_rows)
        if len(page_rows) < args.max_results:
            break

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.out_dir / f"fantrax_transactions_raw_{stamp}.json"
    raw_path.write_text(json.dumps(raw_pages, indent=2, sort_keys=True), encoding="utf-8")

    players = load_players(args.out_dir / "fantrax_players_latest.csv")
    teams = load_teams(args.out_dir / "fantrax_teams_latest.csv")
    roster_statuses = load_current_roster_statuses(args.out_dir / "fantrax_rosters_latest.csv")
    transaction_periods = {
        int_value(cell_by_key(row, "week").get("content"))
        for row in rows
    }
    try:
        roster_statuses.update(fetch_roster_statuses_for_periods(transaction_periods, teams, players))
    except Exception as exc:
        raise SystemExit(f"Fantrax transaction audit failed: {exc}") from exc
    normalized = normalize_rows(rows, roster_statuses, players, teams)
    try:
        league_start_date = fetch_league_scoring_start()
    except Exception as exc:
        raise SystemExit(f"Fantrax transaction audit failed: {exc}") from exc
    assign_effective_periods(normalized, league_start_date, matchup_windows)
    in_window = [
        row for row in normalized
        if row["effective_period_start"] == start.isoformat()
    ]
    add_details = [row for row in in_window if row["is_add"]]
    summaries = summarize_adds(in_window, pickup_limit, teams)

    detail_fields = [
        "transaction_date",
        "team_name",
        "player_name",
        "primary_position",
        "major_minor_class",
        "player_transaction_type",
        "transaction_code",
        "claim_type",
        "fantrax_id",
        "tx_set_id",
        "transaction_row_mentions_minors",
        "current_roster_status",
        "current_roster_position",
        "current_roster_team",
        "current_roster_is_minors",
        "is_minor_exempt",
        "is_sp",
        "is_rp",
        "minor_exempt_confidence",
        "team_id",
        "transaction_date_raw",
        "transaction_period",
        "effective_scoring_date",
        "effective_week_start",
        "effective_period_start",
        "effective_period_end",
        "effective_period_number",
    ]
    summary_fields = [
        "team_name",
        "counted_adds",
        "major_leaguer_adds",
        "minor_exempt_adds",
        "minor_leaguer_adds",
        "sp_adds",
        "rp_adds",
        "major_sp_adds",
        "major_rp_adds",
        "minor_sp_adds",
        "minor_rp_adds",
        "total_adds",
        "remaining_of_limit",
        "over_limit_by",
        "team_id",
    ]
    write_csv(args.out_dir / "fantrax_pickup_audit_details_latest.csv", add_details, detail_fields)
    write_csv(args.out_dir / "fantrax_pickup_audit_summary_latest.csv", summaries, summary_fields)
    metadata = {
        "period_timezone": "America/New_York",
        "fantrax_display_timezone": str(FANTRAX_DISPLAY_TIMEZONE),
        "fantrax_league_scoring_start": league_start_date.isoformat(),
        "transaction_period_policy": "Fantrax transaction Period determines the effective scoring date; Fantrax matchup date ranges determine the add-limit bucket.",
        "fantrax_matchup_period_number": selected_window.get("number", 0) if selected_window else 0,
        "fantrax_matchup_period_caption": selected_window.get("caption", "") if selected_window else "",
        "fantrax_matchup_period_date_range": selected_window.get("date_range", "") if selected_window else "",
        "major_add_limit": pickup_limit,
        "base_major_add_limit": args.pickup_limit,
        "major_add_limit_override": pickup_limit != args.pickup_limit,
        "period_start": start.isoformat(),
        "period_end_exclusive": end.isoformat(),
        "period_label": f"{start.strftime('%Y-%m-%d')} to {(end - timedelta(days=1)).strftime('%Y-%m-%d')} ET",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetched_transaction_player_rows": len(rows),
        "rows_in_window": len(in_window),
        "add_rows_in_window": len(add_details),
    }
    (args.out_dir / "fantrax_pickup_audit_metadata_latest.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Window Eastern: {start.isoformat()} to {end.isoformat()} (end exclusive)")
    print(f"Raw Fantrax response: {raw_path}")
    print(f"Fetched transaction player rows: {len(rows)}")
    print(f"Rows in window: {len(in_window)}")
    print(f"Add rows in window: {len(add_details)}")
    print(f"Summary CSV: {args.out_dir / 'fantrax_pickup_audit_summary_latest.csv'}")
    print(f"Details CSV: {args.out_dir / 'fantrax_pickup_audit_details_latest.csv'}")


if __name__ == "__main__":
    main()
