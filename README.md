# healthstack

Personal health tracking + AI briefing system. Pulls from a **Health Connect export Google Sheet** (weight, steps, sleep, hydration, meditation, nutrition, workouts) and the **Hevy API** (strength workouts + per-set lifts), stores in Supabase, sends a daily briefing via Gmail, and exposes a Claude Skill for interactive review.

Start date: **2026-07-14**. Weight goal: −2.5 lb/wk from 280 lb.

## Architecture

```
Health Connect Sheet ┐
                     ├─► Ingestion ─► Supabase ─► Briefing (Claude API) ─► Gmail
Hevy API ────────────┘                    ↑
                                     Claude Skill (interactive)
```

- **Daily 6:00 AM PT**: GitHub Actions runs `ingest.py` then `briefing.py`.
- **Sunday 7:00 AM PT**: `weekly_review.py` runs.
- **Anytime**: Open Claude on your phone, invoke the healthstack skill, ask questions.

## First-time setup (~30 min)

### 1. Supabase
- Create project at supabase.com (done).
- In SQL editor, paste `db/schema.sql` and run.
- Then paste `db/seed_targets.sql` and run.
- Grab from Project Settings → API: **Project URL** and **service_role key** (not anon).

### 2. Health Connect export sheet
The ingest pulls daily numbers from a sheet that Google Health / Health Connect exports for you. It has five tabs: **Activity**, **Nutrition**, **Sleep**, **Vitals**, **Body**.

1. Open the export sheet in Google Sheets.
2. **Share → General access → "Anyone with the link" → Viewer**. (No auth is used; the ingest fetches each tab via the public CSV endpoint.)
3. Grab the sheet id from its URL:
   `https://docs.google.com/spreadsheets/d/`**`19HUG_t5_EBwZm2-BJH0rcZPIrWf4iRUMumRcXo_4uGE`**`/edit`
4. That id is the value for the `HEALTHSTACK_SHEET_ID` secret below. (You can also paste the full URL; the config strips it.)

Column names are the Health Connect defaults — the ingest keys on `Date`, `Steps`, `Hydration (ml)`, `Nutrition calories (kcal)`, `Protein (g)`, `Carbs (g)`, `Start Time`/`End Time`/`Light/Deep/REM Sleep (min)`, `Start Date/Time`/`Exercise Name`/`Duration (min)`, and a `Weight (kg)` column on the Body tab.

### 3. Gmail (for the daily briefing email)
- Google Cloud Console → enable the **Gmail API** on your project.
- OAuth consent screen → add scope `https://www.googleapis.com/auth/gmail.send`.
- Credentials page → download the OAuth client JSON. Save it locally as `credentials.json` (do NOT commit).
- Run once on your laptop:
  ```
  pip install -r requirements.txt
  python scripts/first_time_oauth.py
  ```
  A browser will open. Approve the gmail.send scope. This creates `token.json` locally with a refresh token — paste its contents into GitHub Secret `GOOGLE_OAUTH_TOKEN`.

### 4. Hevy
- hevy.com/settings?developer → copy API key → set as GH secret `HEVY_API_KEY`.
- Hevy ingestion is on by default. Every daily run pulls the last three days of workouts and re-syncs per-set lifts.

### 5. Withings + GOWOD on your phone
- Withings app → Profile → Apps → Health Connect → enable weight sync.
- GOWOD app → settings → confirm Health Connect sync is on.
- (Health Connect flows those into the export sheet automatically.)

### 6. GitHub Secrets
Repo → Settings → Secrets and variables → Actions:

| Name | Value |
|---|---|
| `SUPABASE_URL` | from step 1 |
| `SUPABASE_KEY` | service_role key from step 1 |
| `HEALTHSTACK_SHEET_ID` | sheet id (or full URL) from step 2 |
| `GOOGLE_OAUTH_TOKEN` | full contents of `token.json` from step 3 |
| `HEVY_API_KEY` | from step 4 |
| `ANTHROPIC_API_KEY` | from console.anthropic.com |
| `GMAIL_TO` | your email address (where briefings arrive) |
| `GMAIL_FROM` | the Gmail you OAuth'd (usually the same) |

### 7. GitHub Pages (dashboard)
- Repo → Settings → Pages → Source: **Deploy from a branch**
- Branch: **main**, Folder: **/docs**
- Save. Your dashboard will be at `https://payasparab.github.io/healthstack/`.
- First view will show empty state until the first daily cron populates `docs/data.json`.

### 8. Push and enable
```
git add .
git commit -m "initial scaffold"
git push
```
Then Actions tab → enable workflows. First run will happen at the next scheduled time, or you can trigger it manually.

## Daily flow

Every morning ~6 AM PT:
1. `ingest.py` reads yesterday's numbers from the Health Connect sheet and Hevy, upserts into Supabase.
2. `briefing.py` reads the last 14 days from Supabase, sends it to Claude with `SKILL.md` as system prompt, and Claude generates a briefing.
3. Briefing arrives in your inbox with a link to the dashboard.

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
- `src/sources/google_sheet.py` — Health Connect export sheet reader (CSV over HTTPS, no OAuth)
- `src/sources/hevy.py` — Hevy API wrapper
- `src/db.py` — Supabase client
- `src/gmail_send.py` — Gmail sender (only remaining Google OAuth surface)
- `src/config.py` — env vars
- `scripts/first_time_oauth.py` — one-time Gmail OAuth flow
- `skill/SKILL.md` — the Claude Skill
- `docs/` — GitHub Pages dashboard (auto-published)

## Notes

- Data pipeline is read-only. Nothing writes back to Google or Hevy.
- The sheet is fetched fresh on each ingest run. Cache within a single run is in-memory only.
- **Hydration and meditation** are inferred from the Health Connect sheet (any Hydration ml > 0 on a date = hydration_met; any Activity row whose Exercise Name matches meditation/mindful/breath = meditation_met).
- **Nutrition (calories, protein, carbs)** comes from whichever app writes to Health Connect (Cronometer, Nutrola, MFP, …) — those show up in the Nutrition tab.
- **Strength / lifts** — the Activity tab has coarse Hevy session rows; those are skipped and the finer-grained per-set data comes from the Hevy API instead.
- The dashboard is a public URL. If you want it private, either use GitHub Pro for private Pages, or don't share the URL. There's a `noindex` meta tag so it won't show up in search results.
