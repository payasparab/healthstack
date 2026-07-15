"""Generate the daily briefing via Claude API and email it."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from anthropic import Anthropic

from . import db, config
from .gmail_send import send


def load_skill() -> str:
    p = Path(__file__).parent.parent / "skill" / "SKILL.md"
    return p.read_text()


def gather_context(today: str) -> dict:
    """Assemble the last 14 days of data + targets + schedule for Claude."""
    today_d = date.fromisoformat(today)
    start = (today_d - timedelta(days=14)).isoformat()

    daily = db.get_daily_range(start, today)
    workouts = db.get_workouts_range(start, today)
    lifts = db.get_lifts_range(start, today)
    targets = db.get_targets()
    schedule = db.get_weight_schedule()
    prs = db.get_lift_prs()

    # Find the current week's weight target
    this_week_target = None
    for row in schedule:
        if row["week_start"] <= today:
            this_week_target = row
    return {
        "today": today,
        "daily": daily,
        "workouts": workouts,
        "lifts": lifts,
        "targets": targets,
        "weight_schedule": schedule[-8:],
        "current_week_target": this_week_target,
        "lift_prs": prs,
    }


def build_footer(today: str) -> str:
    """Small footer with the dashboard link."""
    return (
        f'<p style="margin-top:24px;font-size:13px;color:#888">'
        f'Hydration + meditation are pulled from Google Fit automatically. '
        f'<a href="{config.DASHBOARD_URL}" style="color:#888">Full dashboard</a>'
        f'</p>'
    )


def generate_briefing(kind: str, context: dict) -> tuple[str, str]:
    """Return (subject, body_text). Body is markdown that Claude generates."""
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    system = load_skill()

    if kind == "daily":
        instruction = (
            "Generate today's DAILY briefing. Keep it short and scannable — "
            "aim for 8-15 lines of body content. Follow the format in the skill exactly. "
            "Focus on: yesterday's data, this week's progress vs targets, and 1-3 concrete nudges. "
            "Do not include the check-in links, they will be added separately."
        )
    else:
        instruction = (
            "Generate this WEEK'S SUNDAY REVIEW. This is longer than a daily briefing — "
            "cover weight progress vs schedule, strength progression on the 6 target lifts, "
            "cardio (runs completed, pace trend), hydration + meditation completion, "
            "and end with 2-3 recommendations for next week."
        )

    user = (
        f"{instruction}\n\n"
        f"Here is the data (JSON):\n\n"
        f"```json\n{json.dumps(context, default=str, indent=2)}\n```"
    )

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    body = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    today = context["today"]
    subject = (
        f"Healthstack daily — {today}"
        if kind == "daily"
        else f"Healthstack weekly review — week ending {today}"
    )
    return subject, body


def md_to_html(md: str) -> str:
    """Very light markdown-ish → HTML. Just newlines + bold + headers."""
    import re
    html = md
    html = re.sub(r"^### (.*)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.*)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.*)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("\n\n", "</p><p>")
    html = html.replace("\n", "<br>")
    return f'<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.5;max-width:640px"><p>{html}</p></div>'


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) > 1 else "daily"
    today = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()
    print(f"=== briefing kind={kind} today={today} ===")

    context = gather_context(today)
    subject, body = generate_briefing(kind, context)

    html = md_to_html(body) + build_footer(today)
    send(subject, body, body_html=html)

    db.save_briefing(today, kind, body, {"targets_keys": list(context["targets"].keys())})
    print(f"sent: {subject}")


if __name__ == "__main__":
    main()
