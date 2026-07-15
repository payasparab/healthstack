"""Send emails via Gmail API using the same OAuth creds as Fit."""
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build

from .sources.google_fit import _creds
from . import config

def send(subject: str, body_text: str, body_html: str | None = None) -> None:
    creds = _creds()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))
    else:
        msg = MIMEText(body_text)

    msg["to"] = config.GMAIL_TO
    msg["from"] = config.GMAIL_FROM
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
