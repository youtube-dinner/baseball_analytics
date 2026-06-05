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


LEAGUE_ID = os.environ.get("FANTRAX_LEAGUE_ID", "qqll39pvmj90wrl1")
FANTRAX_OLD_UI_TOKEN = os.environ.get("FANTRAX_OLD_UI_TOKEN", "")
FANTRAX_REQ_URL = "https://www.fantrax.com/fxpa/req"
OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"
FANTRAX_AUTH_COOKIE_FILE = Path(os.environ.get(
    "FANTRAX_AUTH_COOKIE_FILE",
    OUT_DIR / "fantrax_auth_cookie_latest.txt",
))
CENTRAL = ZoneInfo("America/Chicago")
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
            return datetime.strptime(value, fmt).replace(tzinfo=CENTRAL)
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


def load_current_roster_statuses(path):
    statuses = {}
    if not path.exists():
        return statuses
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fantrax_id = row.get("fantrax_id")
            if fantrax_id:
                statuses[fantrax_id] = row
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


def current_week_window(boundary_hour):
    now = datetime.now(CENTRAL)
    days_since_sunday = (now.weekday() + 1) % 7
    most_recent_sunday = now.date() - timedelta(days=days_since_sunday)
    start = datetime.combine(most_recent_sunday, time(boundary_hour), CENTRAL)
    if now < start:
        start -= timedelta(days=7)
    return start, start + timedelta(days=7)


def normalize_rows(rows, roster_statuses, players, teams):
    normalized = []
    seen = set()
    for row in rows:
        tx_set_id = row.get("txSetId") or row.get("id") or ""
        team_cell = cell_by_key(row, "team")
        date_cell = cell_by_key(row, "date")
        team_id = row.get("teamId") or team_cell.get("teamId") or team_cell.get("id") or ""
        team_name = row.get("teamName") or team_cell.get("content") or teams.get(team_id, "")
        date_text = row.get("date") or row.get("transactionDate") or date_cell.get("content") or ""
        date = parse_fantrax_datetime(date_text)
        scorer = row.get("scorer") or row.get("player") or {}
        fantrax_id = player_id_from_scorer(scorer)
        unique_key = (tx_set_id, row.get("transactionCode", ""), fantrax_id)
        if unique_key in seen:
            continue
        seen.add(unique_key)
        current_roster = roster_statuses.get(fantrax_id, {})
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
            "remaining_of_limit": pickup_limit - counted,
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
    parser.add_argument("--start", help="Inclusive Central Time start, e.g. 2026-05-31T23:00")
    parser.add_argument("--end", help="Exclusive Central Time end, e.g. 2026-06-07T23:00")
    parser.add_argument("--boundary-hour", type=int, default=23, help="Sunday Central Time boundary hour. Default: 23.")
    parser.add_argument("--max-results", type=int, default=500, help="Rows per page to request from Fantrax.")
    parser.add_argument("--pages", type=int, default=5, help="Maximum Fantrax transaction pages to fetch.")
    parser.add_argument("--pickup-limit", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.start:
        start = datetime.fromisoformat(args.start).replace(tzinfo=CENTRAL)
        if not args.end:
            raise SystemExit("--end is required when --start is provided")
        end = datetime.fromisoformat(args.end).replace(tzinfo=CENTRAL)
    else:
        start, end = current_week_window(args.boundary_hour)

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

    roster_statuses = load_current_roster_statuses(args.out_dir / "fantrax_rosters_latest.csv")
    players = load_players(args.out_dir / "fantrax_players_latest.csv")
    teams = load_teams(args.out_dir / "fantrax_teams_latest.csv")
    normalized = normalize_rows(rows, roster_statuses, players, teams)
    in_window = [
        row for row in normalized
        if row["transaction_date"]
        and start <= datetime.fromisoformat(row["transaction_date"]) < end
    ]
    add_details = [row for row in in_window if row["is_add"]]
    summaries = summarize_adds(in_window, args.pickup_limit, teams)

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
        "team_id",
    ]
    write_csv(args.out_dir / "fantrax_pickup_audit_details_latest.csv", add_details, detail_fields)
    write_csv(args.out_dir / "fantrax_pickup_audit_summary_latest.csv", summaries, summary_fields)

    print(f"Window Central: {start.isoformat()} to {end.isoformat()} (end exclusive)")
    print(f"Raw Fantrax response: {raw_path}")
    print(f"Fetched transaction player rows: {len(rows)}")
    print(f"Rows in window: {len(in_window)}")
    print(f"Add rows in window: {len(add_details)}")
    print(f"Summary CSV: {args.out_dir / 'fantrax_pickup_audit_summary_latest.csv'}")
    print(f"Details CSV: {args.out_dir / 'fantrax_pickup_audit_details_latest.csv'}")


if __name__ == "__main__":
    main()
