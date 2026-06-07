#!/usr/bin/env python3
import argparse
import csv
import json
import os
import random
import smtplib
import ssl
import unicodedata
from copy import deepcopy
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"
ANALYTICS_DIR = Path(__file__).resolve().parent / "fantasy_baseball_analytics"
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"
CENTRAL = ZoneInfo("America/Chicago")
MINORS_MARKERS = {"MINORS", "MINOR", "MINOR_LEAGUE", "MINOR LEAGUE"}
ACTIVE_MARKERS = {"ACTIVE"}
DEFAULT_MAJOR_ADD_LIMIT = int(os.environ.get("FANTRAX_MAJOR_ADD_LIMIT", "7"))
MINOR_WAIT_DAYS = int(os.environ.get("FANTRAX_MINOR_WAIT_DAYS", "21"))
MINOR_ELIGIBLE_OFFSET_DAYS = int(os.environ.get("FANTRAX_MINOR_ELIGIBLE_OFFSET_DAYS", str(MINOR_WAIT_DAYS + 1)))
BOLD_UPPER = {chr(ord("A") + index): chr(0x1D400 + index) for index in range(26)}
BOLD_LOWER = {chr(ord("a") + index): chr(0x1D41A + index) for index in range(26)}
BOLD_DIGIT = {chr(ord("0") + index): chr(0x1D7CE + index) for index in range(10)}
BOLD_TRANSLATION = {**BOLD_UPPER, **BOLD_LOWER, **BOLD_DIGIT}

NO_MORE_ADD_MESSAGES = [
    "Tread lightly buddy!",
    "Choose your next move with care.",
    "The waiver wire is now a no-fly zone.",
    "That add button needs a rest.",
    "The commissioner is watching closely.",
    "Step away from the claims page.",
    "No more shopping this week.",
    "The cart is closed.",
    "Your waiver budget is now vibes only.",
    "Put the roster moves down.",
    "This is the danger zone.",
    "Proceed with extreme caution.",
    "The add meter is officially empty.",
    "Your weekly leash is gone.",
    "The league office has been notified.",
    "No more tinkering until next week.",
    "The runway is out of pavement.",
    "This is your final form for the week.",
    "Roster discipline starts now.",
    "The add counter says enough.",
    "Your transaction privileges are on thin ice.",
    "The wire is closed for business.",
    "Deep breaths before any clicks.",
    "This is not a drill.",
    "Please admire your roster as-is.",
]

OVER_LIMIT_MESSAGES = [
    "{team} are cheaters! They have gone over the add limits and tarnished the league and the spirit of the game.",
    "{team} have crossed the line and brought shame upon the transaction log.",
    "{team} went over the add limit. The league deserves answers.",
    "{team} have offended the waiver gods and the written rules.",
    "{team} are over the limit and officially under public review.",
    "{team} have exceeded the add cap and stained a once-proud roster page.",
    "{team} pushed past the limit and must answer for this injustice.",
    "{team} have committed a roster crime in broad daylight.",
    "{team} ignored the add cap and disrespected the sanctity of the league.",
    "{team} are over the weekly limit. The group chat record will remember this.",
    "{team} have chosen chaos over compliance.",
    "{team} broke through the add ceiling and left sportsmanship behind.",
    "{team} are beyond the limit and beyond polite society.",
    "{team} have made an illegal extra add. The shame is measurable.",
    "{team} crossed the weekly boundary and brought scandal to the standings.",
    "{team} treated the rulebook like light reading and went over the limit.",
    "{team} are over the cap. The honor system has been wounded.",
    "{team} added too many major leaguers and must face the music.",
    "{team} have violated the weekly add code and disturbed competitive balance.",
    "{team} went past seven. The evidence is right here.",
    "{team} exceeded the limit and put the league's integrity in question.",
    "{team} have gone rogue on the waiver wire.",
    "{team} are over the allowed adds. This is a public accounting.",
    "{team} broke the add limit and the group deserves restitution.",
    "{team} have brought transaction dishonor upon themselves.",
]


def bold_text(value):
    return "".join(BOLD_TRANSLATION.get(char, char) for char in value)


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_metadata(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(path):
    if not path.exists():
        return {
            "schema_version": 1,
            "major_add_alerts": {},
            "daily_summaries": {},
            "minor_windows": {},
            "roster_snapshot": {},
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("schema_version", 1)
    state.setdefault("major_add_alerts", {})
    state.setdefault("daily_summaries", {})
    state.setdefault("minor_windows", {})
    state.setdefault("roster_snapshot", {})
    return state


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def display_name(value):
    if not value:
        return ""
    text = str(value).strip()
    if "," in text:
        last, first = [part.strip() for part in text.split(",", 1)]
        return f"{first} {last}".strip()
    return text


def sortable_name(value):
    name = display_name(value)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(char for char in name if not unicodedata.combining(char))
    return " ".join(
        name.lower()
        .replace(".", "")
        .replace("'", "")
        .replace("-", " ")
        .split()
    )


def int_value(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def float_value(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def central_now():
    return datetime.now(CENTRAL)


def format_date(date_value):
    return date_value.strftime("%A %B %-d, %Y")


def build_report(summary_rows, metadata, major_add_limit):
    ordered_rows = sorted(
        summary_rows,
        key=lambda row: (-(int_value(row.get("major_leaguer_adds") or row.get("counted_adds"))), row.get("team_name", "")),
    )
    lines = [
        "Fantrax Add Tracker",
        central_now().strftime("%Y-%m-%d %I:%M %p"),
    ]
    if metadata.get("period_label"):
        lines.append(f"Period: {metadata['period_label']}")
    lines.append("")
    for index, row in enumerate(ordered_rows):
        if index:
            lines.append("")
        major_adds = int_value(row.get("major_leaguer_adds") or row.get("counted_adds"))
        remaining = max(0, major_add_limit - major_adds)
        lines.extend([
            f"{bold_text(row.get('team_name', ''))}:",
            f"Total Major League Adds: {major_adds}",
            f"Major League Adds Remaining: {remaining}",
        ])
    return "\n".join(lines)


def should_send_daily_summary(state, now, summary_hour, force_summary):
    date_key = now.date().isoformat()
    if force_summary:
        return True
    if now.hour < summary_hour:
        return False
    return not state["daily_summaries"].get(date_key)


def mark_daily_summary_sent(state, now):
    state["daily_summaries"][now.date().isoformat()] = True


def period_key(metadata):
    start = metadata.get("period_start") or ""
    return start[:10] or central_now().date().isoformat()


def build_major_add_alerts(summary_rows, metadata, state, major_add_limit):
    alerts = []
    week_key = period_key(metadata)
    week_state = state["major_add_alerts"].setdefault(week_key, {})
    for row in summary_rows:
        team_id = row.get("team_id") or row.get("team_name", "")
        team_name = row.get("team_name", "")
        team_state = week_state.setdefault(team_id, {"overage_alerted": 0})
        major_adds = int_value(row.get("major_leaguer_adds") or row.get("counted_adds"))
        bold_team = bold_text(team_name)
        if major_adds == major_add_limit - 1 and not team_state.get("one_remaining"):
            alerts.append(f"Hey {bold_team}, you only have one more major league add remaining this week!")
            team_state["one_remaining"] = True
        if major_adds == major_add_limit and not team_state.get("none_remaining"):
            alerts.append(
                f"Hey {bold_team}, you have no more adds remaining this week! "
                f"{random.choice(NO_MORE_ADD_MESSAGES)}"
            )
            team_state["none_remaining"] = True
        overage = max(0, major_adds - major_add_limit)
        already_alerted = int_value(team_state.get("overage_alerted"))
        if overage > already_alerted:
            for _ in range(already_alerted + 1, overage + 1):
                alerts.append(random.choice(OVER_LIMIT_MESSAGES).format(team=bold_team))
            team_state["overage_alerted"] = overage
    return alerts


def roster_key(row):
    return f"{row.get('team_id', '')}:{row.get('fantrax_id', '')}"


def is_minors_status(status):
    return str(status or "").upper() in MINORS_MARKERS


def is_active_status(status):
    return str(status or "").upper() in ACTIVE_MARKERS


def load_current_roster(path):
    roster = {}
    for row in read_csv(path):
        if not row.get("team_id") or not row.get("fantrax_id"):
            continue
        key = roster_key(row)
        roster[key] = {
            "team_id": row.get("team_id", ""),
            "team_name": row.get("team_name", ""),
            "fantrax_id": row.get("fantrax_id", ""),
            "player_name": display_name(row.get("name", "")),
            "roster_status": row.get("roster_status", ""),
            "roster_position": row.get("roster_position", ""),
            "primary_position": row.get("primary_position", ""),
        }
    return roster


def load_games_played(analytics_dir):
    games = {}
    paths = [
        analytics_dir / "current_roster_hitters.csv",
        analytics_dir / "current_roster_pitchers.csv",
        analytics_dir / "hitter_analytics.csv",
        analytics_dir / "pitcher_analytics.csv",
    ]
    for path in paths:
        for row in read_csv(path):
            name_key = sortable_name(row.get("Player", ""))
            if not name_key:
                continue
            value = row.get("GP")
            if value in (None, ""):
                value = row.get("p_game")
            games[name_key] = max(games.get(name_key, 0.0), float_value(value))
    return games


def active_minor_window(window, today):
    try:
        eligible_date = datetime.fromisoformat(window.get("eligible_date")).date()
    except (TypeError, ValueError):
        return False
    return today < eligible_date


def build_minor_roster_alerts(current_roster, games_played, state, now):
    alerts = []
    previous_roster = state.get("roster_snapshot") or {}
    minor_windows = state.setdefault("minor_windows", {})
    today = now.date()
    bootstrap = not previous_roster

    for key, current in current_roster.items():
        previous = previous_roster.get(key)
        previous_status = previous.get("roster_status", "") if previous else ""
        current_status = current.get("roster_status", "")
        current_minors = is_minors_status(current_status)
        previous_minors = is_minors_status(previous_status)
        player_name = current.get("player_name", "")
        team_name = current.get("team_name", "")
        bold_team = bold_text(team_name)
        window = minor_windows.get(key)

        if current_minors and not previous_minors and not bootstrap:
            if not window or not active_minor_window(window, today):
                eligible_date = today + timedelta(days=MINOR_ELIGIBLE_OFFSET_DAYS)
                window = {
                    "team_id": current.get("team_id", ""),
                    "team_name": team_name,
                    "fantrax_id": current.get("fantrax_id", ""),
                    "player_name": player_name,
                    "window_start": today.isoformat(),
                    "eligible_date": eligible_date.isoformat(),
                    "demotion_alert_sent": False,
                    "violation_alert_sent": False,
                }
                minor_windows[key] = window
            games = games_played.get(sortable_name(player_name), 0.0)
            if games > 1 and not window.get("demotion_alert_sent"):
                alerts.append(
                    f"Hey {bold_team}, {player_name} has been added to your minor league roster "
                    f"and cannot be called up until {format_date(datetime.fromisoformat(window['eligible_date']).date())}."
                )
                window["demotion_alert_sent"] = True

        if window and active_minor_window(window, today) and is_active_status(current_status):
            if not window.get("violation_alert_sent"):
                alerts.append(
                    f"Hey {bold_team}! You called up {player_name} before their call up eligibility date of "
                    f"{format_date(datetime.fromisoformat(window['eligible_date']).date())}; "
                    "please send back to the minors or release immediately!"
                )
                window["violation_alert_sent"] = True

    state["roster_snapshot"] = current_roster
    return alerts


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
        if not path.exists():
            continue
        msg.add_attachment(
            path.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=path.name,
        )
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        server.login(username, password)
        server.send_message(msg)


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


def send_groupme(messages):
    bot_id = os.environ.get("GROUPME_BOT_ID", "")
    if not bot_id:
        raise RuntimeError("GroupMe requires GROUPME_BOT_ID")
    for body in messages:
        for chunk in groupme_chunks(body):
            req = Request(
                GROUPME_POST_URL,
                data=json.dumps({"bot_id": bot_id, "text": chunk}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=30) as response:
                response.read()


def main():
    parser = argparse.ArgumentParser(description="Send Fantrax pickup audit report by email and/or GroupMe.")
    parser.add_argument("--summary", type=Path, default=OUT_DIR / "fantrax_pickup_audit_summary_latest.csv")
    parser.add_argument("--details", type=Path, default=OUT_DIR / "fantrax_pickup_audit_details_latest.csv")
    parser.add_argument("--metadata", type=Path, default=OUT_DIR / "fantrax_pickup_audit_metadata_latest.json")
    parser.add_argument("--rosters", type=Path, default=OUT_DIR / "fantrax_rosters_latest.csv")
    parser.add_argument("--state", type=Path, default=OUT_DIR / "fantrax_pickup_alert_state.json")
    parser.add_argument("--analytics-dir", type=Path, default=ANALYTICS_DIR)
    parser.add_argument("--major-add-limit", type=int, default=DEFAULT_MAJOR_ADD_LIMIT)
    parser.add_argument("--daily-summary-hour", type=int, default=int(os.environ.get("FANTRAX_DAILY_SUMMARY_HOUR", "7")))
    parser.add_argument("--force-summary", action="store_true")
    parser.add_argument("--update-state", action="store_true")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--groupme", action="store_true")
    args = parser.parse_args()

    summary_rows = read_csv(args.summary)
    metadata = read_metadata(args.metadata)
    state = load_state(args.state)
    original_state = deepcopy(state)
    now = central_now()
    messages = []

    if should_send_daily_summary(state, now, args.daily_summary_hour, args.force_summary):
        messages.append(build_report(summary_rows, metadata, args.major_add_limit))
        mark_daily_summary_sent(state, now)

    messages.extend(build_major_add_alerts(summary_rows, metadata, state, args.major_add_limit))
    current_roster = load_current_roster(args.rosters)
    games_played = load_games_played(args.analytics_dir)
    messages.extend(build_minor_roster_alerts(current_roster, games_played, state, now))

    if args.email and messages:
        send_email("Fantrax pickup audit", "\n\n".join(messages), [args.summary, args.details])
        print("Sent email report")
    if args.groupme and messages:
        send_groupme(messages)
        print(f"Posted {len(messages)} GroupMe message(s)")
    if not args.email and not args.groupme:
        print("\n\n---\n\n".join(messages) if messages else "No Fantrax pickup messages due.")

    if (args.update_state or args.groupme or args.email) and state != original_state:
        save_state(args.state, state)
        print(f"Updated alert state: {args.state}")


if __name__ == "__main__":
    main()
