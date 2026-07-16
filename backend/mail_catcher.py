"""Minimal local SMTP capture server with a web inbox.

Outbound SMTP to the public internet is blocked on some networks, which makes
the alert-email flow impossible to demo against a real provider. This catcher
accepts mail on :1025 and shows it at http://localhost:8025 so the notification
pipeline stays demonstrable end to end. Standard library only.
"""
import asyncore
import html
import json
import smtpd
import threading
from datetime import datetime, timezone, timedelta
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, HTTPServer

TZ_MSK = timezone(timedelta(hours=3))

MESSAGES = []


def _extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else str(msg.get_payload())


class CatchServer(smtpd.SMTPServer):
    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        if isinstance(data, str):
            data = data.encode()
        msg = message_from_bytes(data)
        ts = datetime.now(TZ_MSK).strftime("%d.%m.%Y %H:%M:%S UTC+3")
        MESSAGES.insert(0, {
            "from": mailfrom,
            "to": rcpttos,
            "subject": msg.get("Subject", ""),
            "body": _extract_body(msg),
            "ts": ts,
        })
        print(f"[mailcatcher] captured to={rcpttos} subject={msg.get('Subject', '')!r}", flush=True)


PAGE_STYLE = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
h1{padding:16px 24px;margin:0;background:#1e293b;font-size:18px}
.msg{margin:16px 24px;padding:16px;background:#1e293b;border-radius:8px;border:1px solid #334155}
.subject{font-size:15px;font-weight:600;color:#f8fafc}
.meta{color:#94a3b8;font-size:13px;margin:4px 0 10px}
pre{white-space:pre-wrap;word-break:break-word;margin:0;color:#cbd5e1;font-size:13px}
.empty{margin:24px;color:#94a3b8}
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api"):
            body = json.dumps(MESSAGES).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        rows = ""
        for m in MESSAGES:
            rows += (
                "<div class=msg>"
                f"<div class=subject>{html.escape(m['subject'])}</div>"
                f"<div class=meta>{html.escape(m['ts'])} &nbsp;·&nbsp; from {html.escape(m['from'])} &rarr; {html.escape(', '.join(m['to']))}</div>"
                f"<pre>{html.escape(m['body'])}</pre>"
                "</div>"
            )
        if not rows:
            rows = "<div class=empty>No messages yet. Trigger an alert to see it here.</div>"
        page = (
            "<html><head><meta charset=utf-8><meta http-equiv=refresh content=3>"
            f"<title>Mail Catcher</title><style>{PAGE_STYLE}</style></head>"
            f"<body><h1>Inbox &mdash; {len(MESSAGES)} message(s)</h1>{rows}</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())

    def log_message(self, *args):
        pass


def _run_http():
    HTTPServer(("0.0.0.0", 8025), Handler).serve_forever()


if __name__ == "__main__":
    CatchServer(("0.0.0.0", 1025), None, decode_data=False)
    threading.Thread(target=_run_http, daemon=True).start()
    print("[mailcatcher] SMTP on :1025, web inbox on :8025", flush=True)
    asyncore.loop()
