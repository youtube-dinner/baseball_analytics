#!/usr/bin/env python3
import argparse
import csv
import json
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.request import Request, urlopen


OUT_DIR = Path(__file__).resolve().parent / "fantrax_export"
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_report(summary_rows, detail_rows):
    total_adds = sum(int(row.get("total_adds") or 0) for row in summary_rows)
    total_major = sum(int(row.get("major_leaguer_adds") or 0) for row in summary_rows)
    total_minor = sum(int(row.get("minor_leaguer_adds") or 0) for row in summary_rows)
    total_sp = sum(int(row.get("sp_adds") or 0) for row in summary_rows)
    total_rp = sum(int(row.get("rp_adds") or 0) for row in summary_rows)

    lines = [
        "Fantrax pickup audit",
        datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "",
        f"Total adds: {total_adds} | Major: {total_major} | Minor: {total_minor} | SP: {total_sp} | RP: {total_rp}",
        "",
        "Team | Adds | Major | Minor | SP | RP | Remaining",
    ]
    for row in summary_rows:
        lines.append(
            " | ".join([
                row.get("team_name", ""),
                row.get("total_adds", "0"),
                row.get("major_leaguer_adds", "0"),
                row.get("minor_leaguer_adds", "0"),
                row.get("sp_adds", "0"),
                row.get("rp_adds", "0"),
                row.get("remaining_of_limit", ""),
            ])
        )
    if detail_rows:
        lines.extend(["", "Most recent adds:"])
        for row in detail_rows[:10]:
            lines.append(
                f"{row.get('transaction_date', '')[:16]} - {row.get('team_name', '')}: "
                f"{row.get('player_name', '')} ({row.get('primary_position', '')}, {row.get('major_minor_class', '')})"
            )
    return "\n".join(lines)


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


def send_groupme(body):
    bot_id = os.environ.get("GROUPME_BOT_ID", "")
    if not bot_id:
        raise RuntimeError("GroupMe requires GROUPME_BOT_ID")
    chunks = []
    remaining = body
    while remaining:
        chunks.append(remaining[:950])
        remaining = remaining[950:]
    for chunk in chunks:
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
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--groupme", action="store_true")
    args = parser.parse_args()

    summary_rows = read_csv(args.summary)
    detail_rows = read_csv(args.details)
    body = build_report(summary_rows, detail_rows)
    subject = "Fantrax pickup audit"
    if args.email:
        send_email(subject, body, [args.summary, args.details])
        print("Sent email report")
    if args.groupme:
        send_groupme(body)
        print("Posted GroupMe report")
    if not args.email and not args.groupme:
        print(body)


if __name__ == "__main__":
    main()
