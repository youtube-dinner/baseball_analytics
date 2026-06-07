#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import smtplib
import ssl
from copy import deepcopy
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


LEAGUE_ID = os.environ.get("FANTRAX_LEAGUE_ID") or "qqll39pvmj90wrl1"
FANTRAX_REQ_URL = "https://www.fantrax.com/fxpa/req"
OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"
FANTRAX_AUTH_COOKIE_FILE = Path(os.environ.get(
    "FANTRAX_AUTH_COOKIE_FILE",
    OUT_DIR / "fantrax_auth_cookie_latest.txt",
))
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"
CENTRAL = ZoneInfo("America/Chicago")
BOLD_UPPER = {chr(ord("A") + index): chr(0x1D400 + index) for index in range(26)}
BOLD_LOWER = {chr(ord("a") + index): chr(0x1D41A + index) for index in range(26)}
BOLD_DIGIT = {chr(ord("0") + index): chr(0x1D7CE + index) for index in range(10)}
BOLD_TRANSLATION = {**BOLD_UPPER, **BOLD_LOWER, **BOLD_DIGIT}
ACTUAL_PARAMS = {
    "view": "STATS",
    "statsType": "2",
    "seasonOrProjection": "SEASON_147_BY_DATE",
    "timeframeTypeCode": "BY_DATE",
}
PROJECTION_PARAMS = {
    "view": "STATS",
    "statsType": "2",
    "seasonOrProjection": "PROJECTION_0_147_EVENT_PROJECTED_WEEKLY",
    "timeframeTypeCode": "PROJECTED_WEEKLY",
}
PRE_WEEK_BASELINE_PARAMS = {
    "view": "STATS",
    "statsType": "2",
    "seasonOrProjection": "SEASON_147_YEAR_TO_DATE",
    "timeframeTypeCode": "YEAR_TO_DATE",
}


def bold_text(value):
    return "".join(BOLD_TRANSLATION.get(char, char) for char in str(value or ""))


def fantrax_auth_cookie():
    cookie = os.environ.get("FANTRAX_AUTH_COOKIE", "")
    if cookie:
        return cookie
    if FANTRAX_AUTH_COOKIE_FILE.exists():
        return FANTRAX_AUTH_COOKIE_FILE.read_text(encoding="utf-8").strip()
    return ""


def fetch_fantrax_req(method, data):
    payload = {"msgs": [{"method": method, "data": {"leagueId": LEAGUE_ID, **data}}]}
    url = f"{FANTRAX_REQ_URL}?{urlencode({'leagueId': LEAGUE_ID})}"
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
        raw = json.loads(response.read().decode("utf-8"))
    responses = raw.get("responses") or []
    if not responses:
        raise RuntimeError("Fantrax response did not include responses")
    first = responses[0]
    page_error = first.get("pageError") or raw.get("pageError") or {}
    if page_error:
        code = page_error.get("code") or "Fantrax page error"
        text = page_error.get("text") or page_error.get("message") or ""
        if code == "WARNING_NOT_LOGGED_IN":
            raise RuntimeError("Fantrax requires auth for weekly matchup recap.")
        raise RuntimeError(f"{code}: {text}".strip())
    return first.get("data") or first


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def load_teams(path):
    rows = read_csv(path)
    if rows:
        return [(row.get("id", ""), row.get("name", "")) for row in rows if row.get("id")]
    data = fetch_fantrax_req("getMatchups", {})
    return [(team.get("id", ""), team.get("name", "")) for team in data.get("fantasyTeams", []) if team.get("id")]


def load_state(path):
    if not path.exists():
        return {"schema_version": 1, "projection_snapshots": {}, "weekly_recaps_sent": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("schema_version", 1)
    state.setdefault("projection_snapshots", {})
    state.setdefault("weekly_recaps_sent", {})
    return state


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def today_central():
    override = os.environ.get("FANTRAX_WEEKLY_RECAP_TODAY")
    if override:
        return date.fromisoformat(override)
    return datetime.now(CENTRAL).date()


def now_central():
    override = os.environ.get("FANTRAX_WEEKLY_RECAP_NOW")
    if override:
        return datetime.fromisoformat(override).replace(tzinfo=CENTRAL)
    return datetime.now(CENTRAL)


def week_start(day):
    return day - timedelta(days=day.weekday())


def week_key(start):
    return start.isoformat()


def previous_week_window(day):
    current_start = week_start(day)
    start = current_start - timedelta(days=7)
    end = current_start - timedelta(days=1)
    return start, end


def current_week_window(day):
    start = week_start(day)
    return start, start + timedelta(days=6)


def html_text(value):
    return re.sub(r"<[^>]+>", " ", str(value or "")).strip()


def float_value(value):
    text = html_text(value).replace(",", "")
    if text in {"", "-", "--"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def cell_value(row, header_cells, key=None, short_name=None):
    cells = row.get("cells") or []
    for index, header in enumerate(header_cells):
        if key and header.get("key") == key and index < len(cells):
            return cells[index].get("content")
        if short_name and header.get("shortName") == short_name and index < len(cells):
            return cells[index].get("content")
    return ""


def roster_rows_for_team(team_id, team_name, params):
    data = fetch_fantrax_req("getTeamRosterInfo", {"teamId": team_id, **params})
    rows = []
    for table in data.get("tables") or []:
        header_cells = (table.get("header") or {}).get("cells") or []
        player_type = table.get("scGroupScorerHeader") or ""
        for row in table.get("rows") or []:
            scorer = row.get("scorer") or {}
            fantrax_id = scorer.get("scorerId") or scorer.get("id") or ""
            if row.get("secondary") or not fantrax_id:
                continue
            games_played = float_value(cell_value(row, header_cells, short_name="GP"))
            fpts = float_value(cell_value(row, header_cells, key="fpts"))
            fpts_per_game = float_value(cell_value(row, header_cells, key="fptsPerGame"))
            at_bats = float_value(cell_value(row, header_cells, short_name="AB"))
            rows.append({
                "team_id": team_id,
                "team_name": team_name,
                "fantrax_id": fantrax_id,
                "player_name": scorer.get("name") or "",
                "player_type": player_type,
                "roster_status_id": row.get("statusId", ""),
                "roster_pos_id": row.get("posId", ""),
                "mlb_team": scorer.get("teamShortName", ""),
                "eligible_positions": scorer.get("posShortNames", ""),
                "actual_points": fpts,
                "actual_fpts_per_game": fpts_per_game,
                "games_played": games_played,
                "at_bats": at_bats,
            })
    return rows


def fetch_actual_week_rows(teams, start, end):
    params = {
        **ACTUAL_PARAMS,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }
    rows = []
    for team_id, team_name in teams:
        rows.extend(roster_rows_for_team(team_id, team_name, params))
    return [
        row for row in rows
        if row["games_played"] > 0 or row["actual_points"] != 0
    ]


def fetch_projection_rows(teams):
    rows = []
    for team_id, team_name in teams:
        rows.extend(roster_rows_for_team(team_id, team_name, PROJECTION_PARAMS))
    return rows


def fetch_pre_week_baseline_rows(teams):
    rows = []
    for team_id, team_name in teams:
        rows.extend(roster_rows_for_team(team_id, team_name, PRE_WEEK_BASELINE_PARAMS))
    return rows


def snapshot_projection_rows(projection_rows, baseline_rows):
    snapshot = {}
    baseline_by_key = {
        f"{row['team_id']}:{row['fantrax_id']}": row
        for row in baseline_rows
    }
    all_keys = {
        f"{row['team_id']}:{row['fantrax_id']}"
        for row in projection_rows
    } | set(baseline_by_key)
    projection_by_key = {
        f"{row['team_id']}:{row['fantrax_id']}": row
        for row in projection_rows
    }
    for key in all_keys:
        row = projection_by_key.get(key) or baseline_by_key[key]
        baseline = baseline_by_key.get(key, {})
        key = f"{row['team_id']}:{row['fantrax_id']}"
        snapshot[key] = {
            "team_id": row["team_id"],
            "team_name": row["team_name"],
            "fantrax_id": row["fantrax_id"],
            "player_name": row["player_name"],
            "projected_fpts_per_game": row["actual_points"],
            "projected_at_bats": row.get("at_bats", 0.0),
            "pre_week_fpts_per_game": baseline.get("actual_fpts_per_game", 0.0),
            "pre_week_ab_per_game": (
                baseline.get("at_bats", 0.0) / baseline.get("games_played", 0.0)
                if baseline.get("games_played", 0.0)
                else 0.0
            ),
        }
    return snapshot


def ensure_current_projection_snapshot(state, teams, today):
    start, end = current_week_window(today)
    key = week_key(start)
    if today.weekday() != 0 or state["projection_snapshots"].get(key):
        return False
    projection_rows = fetch_projection_rows(teams)
    baseline_rows = fetch_pre_week_baseline_rows(teams)
    state["projection_snapshots"][key] = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "captured_at": datetime.now(CENTRAL).isoformat(),
        "projection_type": "fantrax_projected_per_game_with_pre_week_fpg_fallback",
        "players": snapshot_projection_rows(projection_rows, baseline_rows),
    }
    return True


def maybe_live_projection_snapshot(teams):
    projection_rows = fetch_projection_rows(teams)
    baseline_rows = fetch_pre_week_baseline_rows(teams)
    return {
        "projection_type": "fantrax_current_projected_per_game_with_current_fpg_fallback",
        "players": snapshot_projection_rows(projection_rows, baseline_rows),
    }


def enrich_with_projections(actual_rows, snapshot):
    players = snapshot.get("players") or {}
    enriched = []
    for row in actual_rows:
        key = f"{row['team_id']}:{row['fantrax_id']}"
        projection = players.get(key, {})
        raw_projected_per_game = float_value(projection.get("projected_fpts_per_game"))
        projected_per_game = raw_projected_per_game
        projected_at_bats = float_value(projection.get("projected_at_bats"))
        pre_week_ab_per_game = float_value(projection.get("pre_week_ab_per_game"))
        projection_basis = "fantrax_projected_fpg"
        if row["player_type"] == "Hitting" and projected_per_game > 0 and projected_at_bats > 0 and pre_week_ab_per_game > 0:
            projected_per_game = projected_per_game * pre_week_ab_per_game / projected_at_bats
            projection_basis = "fantrax_projected_fpg_ab_normalized"
        if projected_per_game <= 0:
            projected_per_game = float_value(projection.get("pre_week_fpts_per_game"))
            projection_basis = "pre_week_fpg"
        projected_total = projected_per_game * row["games_played"]
        enriched.append({
            **row,
            "raw_projected_fpts_per_game": raw_projected_per_game,
            "projected_fpts_per_game": projected_per_game,
            "projected_at_bats": projected_at_bats,
            "pre_week_ab_per_game": pre_week_ab_per_game,
            "projected_points": projected_total,
            "points_over_projection": row["actual_points"] - projected_total,
            "projection_source": snapshot.get("projection_type", ""),
            "projection_basis": projection_basis,
        })
    return enriched


def rounded(value):
    return f"{float(value):.1f}"


def build_section(title, rows, diff=False):
    lines = [title]
    for index, row in enumerate(rows, start=1):
        if index > 1:
            lines.append("")
        lines.extend([
            f"{index}. {bold_text(row['team_name'])}",
            row["player_name"],
        ])
        if diff:
            lines.extend([
                f"Total Projected Points: {rounded(row['projected_points'])}",
                f"Actual Points: {rounded(row['actual_points'])}",
                f"Points Over Projection: {rounded(row['points_over_projection'])}",
            ])
        else:
            lines.append(f"Total Points: {rounded(row['actual_points'])}")
    return lines


def build_report(rows, start, end, projection_source):
    top = sorted(rows, key=lambda row: (-row["actual_points"], row["team_name"], row["player_name"]))[:10]
    projected_rows = [row for row in rows if row["projected_points"] > 0]
    over = sorted(projected_rows, key=lambda row: (-row["points_over_projection"], row["team_name"], row["player_name"]))[:10]
    under = sorted(projected_rows, key=lambda row: (row["points_over_projection"], row["team_name"], row["player_name"]))[:10]
    lines = [
        "Weekly Fantasy Recap",
        f"Period: {start.isoformat()} to {end.isoformat()}",
        "",
        *build_section("Top Performers", top),
        "",
        *build_section("Biggest Overperformers", over, diff=True),
        "",
        *build_section("Biggest Underperformers", under, diff=True),
    ]
    if projection_source.endswith("_fallback"):
        lines.extend([
            "",
            "Projection note: no stored pre-week snapshot was available, so this used current Fantrax projected per-game values with AB/G normalization and current FP/G fallback.",
        ])
    return "\n".join(lines)


def should_send_recap(state, now, start, force):
    if force:
        return True
    if now.weekday() != 0 or now.hour < int(os.environ.get("FANTRAX_WEEKLY_RECAP_HOUR", "7")):
        return False
    return not state["weekly_recaps_sent"].get(week_key(start))


def mark_recap_sent(state, start):
    state["weekly_recaps_sent"][week_key(start)] = datetime.now(CENTRAL).isoformat()


def groupme_chunks(body):
    chunks = []
    current = []
    current_len = 0
    for line in body.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > 950:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def send_groupme(body):
    bot_id = os.environ.get("GROUPME_BOT_ID", "")
    if not bot_id:
        raise RuntimeError("GroupMe requires GROUPME_BOT_ID")
    for chunk in groupme_chunks(body):
        req = Request(
            GROUPME_POST_URL,
            data=json.dumps({"bot_id": bot_id, "text": chunk}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as response:
            response.read()


def send_email(subject, body, attachments):
    host = os.environ.get("FANTRAX_REPORT_SMTP_HOST", "")
    port = int(os.environ.get("FANTRAX_REPORT_SMTP_PORT", "587"))
    username = os.environ.get("FANTRAX_REPORT_SMTP_USERNAME", "")
    password = os.environ.get("FANTRAX_REPORT_SMTP_PASSWORD", "")
    sender = os.environ.get("FANTRAX_REPORT_EMAIL_FROM", username)
    recipient = os.environ.get("FANTRAX_REPORT_EMAIL_TO", "")
    if not all([host, username, password, sender, recipient]):
        raise RuntimeError("Email requires FANTRAX_REPORT_SMTP_HOST, USERNAME, PASSWORD, EMAIL_FROM, and EMAIL_TO")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)
    for path in attachments:
        if path.exists():
            msg.add_attachment(path.read_bytes(), maintype="text", subtype="csv", filename=path.name)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        server.login(username, password)
        server.send_message(msg)


def main():
    parser = argparse.ArgumentParser(description="Send a weekly Fantrax matchup recap to GroupMe.")
    parser.add_argument("--teams", type=Path, default=OUT_DIR / "fantrax_teams_latest.csv")
    parser.add_argument("--state", type=Path, default=OUT_DIR / "fantrax_weekly_recap_state.json")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--force-report", action="store_true")
    parser.add_argument("--update-state", action="store_true")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--groupme", action="store_true")
    args = parser.parse_args()

    teams = load_teams(args.teams)
    state = load_state(args.state)
    original_state = deepcopy(state)
    now = now_central()
    today = today_central()
    ensure_current_projection_snapshot(state, teams, today)
    start, end = previous_week_window(today)
    messages = []
    latest_rows = []
    projection_source = ""

    if should_send_recap(state, now, start, args.force_report):
        actual_rows = fetch_actual_week_rows(teams, start, end)
        snapshot = state["projection_snapshots"].get(week_key(start))
        if not snapshot:
            snapshot = maybe_live_projection_snapshot(teams)
        projection_source = snapshot.get("projection_type", "")
        latest_rows = enrich_with_projections(actual_rows, snapshot)
        body = build_report(latest_rows, start, end, projection_source)
        messages.append(body)
        mark_recap_sent(state, start)

    fields = [
        "team_name",
        "player_name",
        "fantrax_id",
        "player_type",
        "actual_points",
        "games_played",
        "raw_projected_fpts_per_game",
        "projected_fpts_per_game",
        "projected_at_bats",
        "pre_week_ab_per_game",
        "projected_points",
        "points_over_projection",
        "projection_source",
        "projection_basis",
    ]
    write_csv(args.out_dir / "fantrax_weekly_recap_latest.csv", latest_rows, fields)
    write_json(args.out_dir / "fantrax_weekly_recap_metadata_latest.json", {
        "generated_at": datetime.now(CENTRAL).isoformat(),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "projection_source": projection_source,
        "posted_message_count": len(messages),
        "player_rows": len(latest_rows),
    })

    if args.email and messages:
        send_email(
            "Fantrax weekly recap",
            "\n\n".join(messages),
            [args.out_dir / "fantrax_weekly_recap_latest.csv"],
        )
        print("Sent weekly recap email")
    if args.groupme and messages:
        for message in messages:
            send_groupme(message)
        print(f"Posted {len(messages)} weekly recap GroupMe message(s)")
    if not args.email and not args.groupme:
        print("\n\n---\n\n".join(messages) if messages else "No weekly recap message due.")

    if (args.update_state or args.groupme or args.email) and state != original_state:
        save_state(args.state, state)
        print(f"Updated weekly recap state: {args.state}")


if __name__ == "__main__":
    main()
