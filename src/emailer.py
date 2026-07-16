"""Send briefings via SendGrid.

Just a POST to /v3/mail/send with an API key — no OAuth, no user mailbox
access, no google-api-python-client. The `from` address has to be verified
in the SendGrid account (single-sender verification is a one-click flow;
domain auth is the more permanent option).
"""
import requests

from . import config


SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def send(subject: str, body_text: str, body_html: str | None = None) -> None:
    payload: dict = {
        "personalizations": [{"to": [{"email": config.EMAIL_TO}]}],
        "from": {"email": config.EMAIL_FROM},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body_text}],
    }
    if body_html:
        payload["content"].append({"type": "text/html", "value": body_html})

    r = requests.post(
        SENDGRID_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {config.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"SendGrid error {r.status_code}: {r.text}")
