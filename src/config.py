"""Environment config. All secrets come from env vars (GitHub Actions secrets in prod)."""
import os
import json
import re

def _req(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

# Supabase
SUPABASE_URL = _req("SUPABASE_URL")
SUPABASE_KEY = _req("SUPABASE_KEY")

# Health Connect export sheet — required. Accepts either the raw sheet id or a
# full Google Sheets URL; we extract the id.
_raw_sheet = _req("HEALTHSTACK_SHEET_ID")
_m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", _raw_sheet)
HEALTHSTACK_SHEET_ID = _m.group(1) if _m else _raw_sheet

# Gmail OAuth (used only to send briefings; the data path no longer needs it)
GOOGLE_OAUTH_TOKEN = _req("GOOGLE_OAUTH_TOKEN")
GOOGLE_OAUTH_CLIENT = os.environ.get("GOOGLE_OAUTH_CLIENT", "")

# Hevy
HEVY_API_KEY = _req("HEVY_API_KEY")

# Anthropic
ANTHROPIC_API_KEY = _req("ANTHROPIC_API_KEY")

# Gmail routing
GMAIL_TO = _req("GMAIL_TO")
GMAIL_FROM = os.environ.get("GMAIL_FROM", GMAIL_TO)

# Timezone
TIMEZONE = os.environ.get("TIMEZONE", "America/Los_Angeles")

# Dashboard URL (published GitHub Pages)
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://payasparab.github.io/healthstack/")

def google_oauth_token_dict() -> dict:
    return json.loads(GOOGLE_OAUTH_TOKEN)

def google_oauth_client_dict() -> dict:
    return json.loads(GOOGLE_OAUTH_CLIENT) if GOOGLE_OAUTH_CLIENT else {}
