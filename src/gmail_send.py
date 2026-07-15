"""Send emails via Gmail API using an OAuth refresh token in GOOGLE_OAUTH_TOKEN."""
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from . import config

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _creds() -> Credentials:
    token_data = config.google_oauth_token_dict()
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Gmail OAuth token is invalid and cannot be refreshed. "
                "Re-run scripts/first_time_oauth.py."
            )
    return creds


def send(subject: str, body_text: str, body_html: str | None = None) -> None:
    service = build("gmail", "v1", credentials=_creds(), cache_discovery=False)

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
