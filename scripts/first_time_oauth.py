"""One-time OAuth flow. Run this on your laptop before deploying.

Prereqs: `credentials.json` in the repo root (downloaded from Google Cloud Console).
Output: `token.json` in the repo root. Copy its contents to the GH secret GOOGLE_OAUTH_TOKEN.
"""
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.location.read",
    "https://www.googleapis.com/auth/gmail.send",
]

def main():
    repo_root = Path(__file__).parent.parent
    creds_path = repo_root / "credentials.json"
    token_path = repo_root / "token.json"

    if not creds_path.exists():
        raise SystemExit(
            f"Missing {creds_path}. Download OAuth client JSON from Google Cloud Console "
            f"and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    token_path.write_text(creds.to_json())
    print(f"\nWrote {token_path}\n")
    print("Next steps:")
    print(f"  1. Copy the ENTIRE contents of {token_path} into GitHub secret GOOGLE_OAUTH_TOKEN")
    print(f"  2. Copy the ENTIRE contents of {creds_path} into GitHub secret GOOGLE_OAUTH_CLIENT")
    print(f"  3. NEVER commit either file. They are gitignored.")

if __name__ == "__main__":
    main()
