"""Environment config. All secrets come from env vars (GitHub Actions secrets in prod)."""
import os
import re

def _req(name: str, *fallbacks: str) -> str:
    for n in (name, *fallbacks):
        v = os.environ.get(n)
        if v:
            return v
    raise RuntimeError(f"Missing required env var: {name}")


# Supabase — the ingest writes to protected tables, so we want the
# service-role / secret key. Supabase renamed its keys in 2025: the old
# SUPABASE_KEY (service_role) is now SUPABASE_SECRET_KEY. Accept both,
# preferring the new name.
SUPABASE_URL = _req("SUPABASE_URL")
SUPABASE_KEY = _req("SUPABASE_SECRET_KEY", "SUPABASE_KEY")

# Health Connect export sheet — required. Accepts either the raw sheet id or a
# full Google Sheets URL; we extract the id.
_raw_sheet = _req("HEALTHSTACK_SHEET_ID")
_m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", _raw_sheet)
HEALTHSTACK_SHEET_ID = _m.group(1) if _m else _raw_sheet

# Hevy
HEVY_API_KEY = _req("HEVY_API_KEY")

# Anthropic
ANTHROPIC_API_KEY = _req("ANTHROPIC_API_KEY")

# Email delivery — SendGrid. EMAIL_TO/EMAIL_FROM are the current names;
# GMAIL_TO/GMAIL_FROM are accepted as fallbacks so previously-set secrets keep
# working.
SENDGRID_API_KEY = _req("SENDGRID_API_KEY")
EMAIL_TO = _req("EMAIL_TO", "GMAIL_TO")
EMAIL_FROM = os.environ.get("EMAIL_FROM") or os.environ.get("GMAIL_FROM") or EMAIL_TO

# Timezone
TIMEZONE = os.environ.get("TIMEZONE", "America/Los_Angeles")

# Dashboard URL — set the DASHBOARD_URL secret to whatever your dedicated
# dashboard repo publishes to (e.g. https://<user>.github.io/healthstack-dashboard/).
# The default here is only a placeholder for local runs.
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://payasparab.github.io/healthstack-dashboard/")
