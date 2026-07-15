# healthstack

Personal health tracking + AI briefing system. Pulls from Google Fit (Withings, Pixel Watch, Runna, GOWOD) and Hevy, stores in Supabase, sends a daily briefing via Gmail, and exposes a Claude Skill for interactive review.

Start date: **2026-07-14**. Weight goal: −2.5 lb/wk from 280 lb.

## Architecture

```
Sources → Ingestion → Supabase → Briefing (Claude API) → Gmail
                          ↑
                     Claude Skill (interactive)
```

- **Daily 6:00 AM PT**: GitHub Actions runs `ingest.py` then `briefing.py`
- **Sunday 7:00 AM PT**: `weekly_review.py` runs
- **Anytime**: Open Claude on your phone, invoke the healthstack skill, ask questions

## First-time setup (one pass, ~30 min)

### 1. Supabase
- Create project at supabase.com (done).
- In SQL editor, paste `db/schema.sql` and run.
- Then paste `db/seed_targets.sql` and run.
- Grab from Project Settings → API: **Project URL** and **service_role key** (not anon).

### 2. Google Cloud (OAuth for Fit + Gmail)
- You already have the Fitness API enabled. Go back to the OAuth consent screen and add the scope `https://www.googleapis.com/auth/gmail.send`.
- On the credentials page, download the OAuth client JSON. Save it locally as `credentials.json` (do NOT commit).
- Run once on your laptop:
  ```
  pip install -r requirements.txt
  python scripts/first_time_oauth.py
  ```
  A browser will open. Approve all scopes. This creates `token.json` locally with a refresh token. You will paste its contents into GitHub Secrets.

### 3. Hevy
- hevy.com/settings?developer → copy API key.

### 4. Withings + GOWOD on your phone
- Withings app → Profile → Apps → Health Connect → enable weight sync.
- GOWOD app → settings → confirm Google Fit / Health Connect sync is on.

### 5. GitHub Secrets
In the repo Settings → Secrets and variables → Actions, add:

| Name | Value |
|---|---|
| `SUPABASE_URL` | from step 1 |
| `SUPABASE_KEY` | service_role key from step 1 |
| `GOOGLE_OAUTH_TOKEN` | full contents of `token.json` |
| `GOOGLE_OAUTH_CLIENT` | full contents of `credentials.json` |
| `HEVY_API_KEY` | from step 3 |
| `ANTHROPIC_API_KEY` | from console.anthropic.com |
| `GMAIL_TO` | your email address (where briefings arrive) |
| `GMAIL_FROM` | the Gmail you OAuth'd (usually the same) |

### 6. GitHub Pages (dashboard)
- Repo → Settings → Pages → Source: **Deploy from a branch**
- Branch: **main**, Folder: **/docs**
- Save. Your dashboard will be at `https://payasparab.github.io/healthstack/`
- First view will show empty state until the first daily cron populates `docs/data.json`.

### 7. Push and enable
```
git add .
git commit -m "initial scaffold"
git push
```
Then Actions tab → enable workflows. First run will happen at the next scheduled time, or you can trigger manually.

## Daily flow

Every morning ~6 AM PT:
1. `ingest.py` pulls yesterday's data from Google Fit + Hevy into Supabase.
2. `briefing.py` reads the last 7 days from Supabase, sends it to Claude with the SKILL.md as system prompt, and Claude generates a briefing.
3. Briefing arrives in your inbox with two links at the bottom: `hydration ✓` and `meditation ✓` — one tap to log.

## Interactive mode

On your phone, in Claude:
> "Load my healthstack skill and tell me how I'm tracking this week."

Claude reads the skill, connects to Supabase (via MCP or direct), queries live data, gives you analysis.

## Files

- `db/schema.sql` — Postgres tables
- `db/seed_targets.sql` — your fixed targets + weight schedule
- `src/ingest.py` — pulls from all sources, upserts to Supabase
- `src/briefing.py` — generates daily briefing via Claude API + Gmail
- `src/weekly_review.py` — Sunday review
- `src/export_dashboard.py` — writes docs/data.json for the dashboard
- `src/sources/google_fit.py` — Fit API wrapper (steps, sleep, weight, workouts, hydration, meditation)
- `src/sources/hevy.py` — Hevy API wrapper
- `src/db.py` — Supabase client
- `src/gmail_send.py` — Gmail sender
- `src/config.py` — env vars
- `scripts/first_time_oauth.py` — one-time OAuth flow
- `skill/SKILL.md` — the Claude Skill
- `docs/` — GitHub Pages dashboard (auto-published)

## Notes

- The Google Fit REST API is deprecated end of 2026. This will need migration to Health Connect (on-device, requires an Android companion) before then. That's a v2 problem.
- Nothing here writes back to Google Fit or Hevy. Read-only.
- **Hydration and meditation are pulled automatically from Google Fit** (any hydration entry logged = day met; any meditation session logged = day met). If you want a volume threshold instead, edit `src/sources/google_fit.py`.
- **Nutrition (calories, protein, carbs) is pulled from Google Fit's `com.google.nutrition` type**, populated by Nutrola via Health Connect. If Nutrola only writes daily aggregates rather than per-meal, that's fine — we still get daily totals. Verify Nutrola → Health Connect sync is enabled in the Nutrola app settings.
- The dashboard is a public URL. If you want it private, either use GitHub Pro for private Pages, or don't share the URL. There's a `noindex` meta tag so it won't show up in search results.
# healthstack
