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
BOLD_UPPER = {chr(ord("A") + index): chr(0x1D400 + index) for index in range(26)}
BOLD_LOWER = {chr(ord("a") + index): chr(0x1D41A + index) for index in range(26)}
BOLD_DIGIT = {chr(ord("0") + index): chr(0x1D7CE + index) for index in range(10)}
BOLD_TRANSLATION = {**BOLD_UPPER, **BOLD_LOWER, **BOLD_DIGIT}


def bold_text(value):
    return "".join(BOLD_TRANSLATION.get(char, char) for char in value)


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_metadata(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(summary_rows, detail_rows):
    ordered_rows = sorted(
        summary_rows,
        key=lambda row: (-(int(row.get("total_adds") or 0)), row.get("team_name", "")),
    )
    lines = [
        "Fantrax Add Tracker",
        datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "",
    ]
    for index, row in enumerate(ordered_rows):
        if index:
            lines.append("")
        lines.extend([
            bold_text(row.get("team_name", "")),
            f"Total Adds: {row.get('total_adds', '0')}",
            f"Major League SP Adds: {row.get('major_sp_adds', '0')}",
            f"Major League RP Adds: {row.get('major_rp_adds', '0')}",
            f"Minor League Adds: {row.get('minor_leaguer_adds', '0')}",
        ])
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
    parser.add_argument("--metadata", type=Path, default=OUT_DIR / "fantrax_pickup_audit_metadata_latest.json")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--groupme", action="store_true")
    args = parser.parse_args()

    summary_rows = read_csv(args.summary)
    detail_rows = read_csv(args.details)
    metadata = read_metadata(args.metadata)
    body = build_report(summary_rows, detail_rows)
    if metadata.get("period_label"):
        body = body.replace("\n\n", f"\nPeriod: {metadata['period_label']}\n\n", 1)
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
