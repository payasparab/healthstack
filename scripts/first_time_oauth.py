"""One-time OAuth flow for Gmail. Run this on your laptop before deploying.

Data ingestion no longer needs OAuth — steps/sleep/weight/etc. come from the
Health Connect export Google Sheet, which just has to be shared as
"Anyone with the link can view". The only remaining Google OAuth is for
sending the daily briefing email via Gmail.

Prereqs: `credentials.json` in the repo root (OAuth client JSON downloaded
from Google Cloud Console).
Output:  `token.json` in the repo root. Paste its contents into the GH
secret GOOGLE_OAUTH_TOKEN.
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main():
    repo_root = Path(__file__).parent.parent
    creds_path = repo_root / "credentials.json"
    token_path = repo_root / "token.json"

    if not creds_path.exists():
        raise SystemExit(
            f"Missing {creds_path}. Download the OAuth client JSON from "
            f"Google Cloud Console and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    token_path.write_text(creds.to_json())
    print(f"\nWrote {token_path}\n")
    print("Next steps:")
    print(f"  1. Copy the ENTIRE contents of {token_path} into GitHub secret GOOGLE_OAUTH_TOKEN")
    print(f"  2. NEVER commit token.json or credentials.json.")


if __name__ == "__main__":
    main()
