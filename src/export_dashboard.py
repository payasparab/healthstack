"""Export dashboard data to docs/data.json.

Runs after ingest in the daily workflow, then the workflow commits docs/data.json
to the repo. GitHub Pages redeploys automatically.
"""
import json
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

from . import db


TARGET_LIFT_ALIASES = {
    "Bench Press":           ["bench press", "barbell bench"],
    "Tricep Pushdown":       ["tricep pushdown", "triceps pushdown", "cable pushdown"],
    "Concentration Curl":    ["concentration curl"],
    "T-Bar Row":             ["t-bar row", "t bar row", "tbar row"],
    "Leg Press":             ["leg press"],
    "Hack Squat":            ["hack squat"],
}


def match_lift(exercise_name: str) -> str | None:
    en = (exercise_name or "").lower()
    for canonical, aliases in TARGET_LIFT_ALIASES.items():
        if any(a in en for a in aliases):
            return canonical
    return None


def top_working_set(sets: list[dict]) -> dict | None:
    """Pick the working set with the highest weight."""
    working = [s for s in sets if s.get("is_working_set") is not False and s.get("weight_lb")]
    if not working:
        return None
    return max(working, key=lambda s: (s["weight_lb"], s.get("reps") or 0))


def compute_streaks(daily_rows: list[dict]) -> dict:
    """Compute current streaks for hydration, meditation, steps target."""
    today = date.today()
    by_date = {r["date"]: r for r in daily_rows}

    def streak(pred) -> int:
        n = 0
        d = today - timedelta(days=1)  # start from yesterday since today is in progress
        while True:
            row = by_date.get(d.isoformat())
            if row is None or not pred(row):
                break
            n += 1
            d -= timedelta(days=1)
        return n

    steps_target = 12000  # from targets; keep in sync or query
    return {
        "hydration": streak(lambda r: r.get("hydration_met")),
        "meditation": streak(lambda r: r.get("meditation_met")),
        "steps": streak(lambda r: (r.get("steps") or 0) >= steps_target),
    }


def build_payload() -> dict:
    today = date.today()
    start_180 = (today - timedelta(days=180)).isoformat()
    today_iso = today.isoformat()

    daily = db.get_daily_range(start_180, today_iso)
    workouts = db.get_workouts_range(start_180, today_iso)
    lifts = db.get_lifts_range(start_180, today_iso)
    targets = db.get_targets()
    schedule = db.get_weight_schedule()
    prs = db.get_lift_prs()

    # Group lifts by workout+exercise to compute top working set per session
    grouped = defaultdict(list)
    for lift in lifts:
        canonical = match_lift(lift["exercise"])
        if not canonical:
            continue
        key = (lift["date"], canonical)
        grouped[key].append(lift)

    target_lifts = {name: [] for name in TARGET_LIFT_ALIASES}
    for (d, canonical), sets in sorted(grouped.items()):
        top = top_working_set(sets)
        if top:
            target_lifts[canonical].append({
                "date": d,
                "weight_lb": top["weight_lb"],
                "reps": top["reps"],
            })

    # Weekly rollups (Sunday-anchored)
    def sunday_of(d: date) -> date:
        # Sunday-anchored: if Sunday itself, that is week_start
        return d - timedelta(days=(d.weekday() + 1) % 7)

    week_buckets = defaultdict(lambda: {
        "exercise_days": set(), "run_count": 0, "run_km": 0.0, "run_pace_sum": 0.0,
        "run_pace_count": 0, "mobility_min": 0.0, "hydration_days": 0,
        "meditation_days": 0, "steps_days": 0,
    })
    for r in daily:
        d = date.fromisoformat(r["date"])
        w = sunday_of(d).isoformat()
        bucket = week_buckets[w]
        if r.get("hydration_met"):
            bucket["hydration_days"] += 1
        if r.get("meditation_met"):
            bucket["meditation_days"] += 1
        if (r.get("steps") or 0) >= 12000:
            bucket["steps_days"] += 1

    for w in workouts:
        d = date.fromisoformat(w["date"])
        wk = sunday_of(d).isoformat()
        bucket = week_buckets[wk]
        if w["type"] in ("strength", "run", "mobility", "walk"):
            bucket["exercise_days"].add(w["date"])
        if w["type"] == "run":
            bucket["run_count"] += 1
            if w.get("distance_km"):
                bucket["run_km"] += w["distance_km"]
            if w.get("pace_min_per_km"):
                bucket["run_pace_sum"] += w["pace_min_per_km"]
                bucket["run_pace_count"] += 1
        if w["type"] == "mobility":
            bucket["mobility_min"] += w.get("duration_min") or 0

    weekly = []
    for wk in sorted(week_buckets):
        b = week_buckets[wk]
        weekly.append({
            "week_start": wk,
            "exercise_days": len(b["exercise_days"]),
            "run_count": b["run_count"],
            "run_km": round(b["run_km"], 1),
            "avg_pace": round(b["run_pace_sum"] / b["run_pace_count"], 2) if b["run_pace_count"] else None,
            "mobility_min": round(b["mobility_min"], 1),
            "hydration_days": b["hydration_days"],
            "meditation_days": b["meditation_days"],
            "steps_days": b["steps_days"],
        })

    # Current week context
    this_week_start = sunday_of(today).isoformat()
    this_week = next((w for w in weekly if w["week_start"] == this_week_start), {
        "week_start": this_week_start, "exercise_days": 0, "run_count": 0,
        "run_km": 0, "avg_pace": None, "mobility_min": 0,
        "hydration_days": 0, "meditation_days": 0, "steps_days": 0,
    })
    week_target = next(
        (s for s in schedule if s["week_start"] == this_week_start), None
    )

    # Most recent weight for header
    weights = [r for r in daily if r.get("weight_lb") is not None]
    current_weight = weights[-1]["weight_lb"] if weights else None
    current_weight_date = weights[-1]["date"] if weights else None

    # Recent runs (last 20)
    recent_runs = [
        {
            "date": w["date"],
            "distance_km": w.get("distance_km"),
            "duration_min": w.get("duration_min"),
            "pace_min_per_km": w.get("pace_min_per_km"),
        }
        for w in workouts if w["type"] == "run"
    ][-20:]

    # Recent briefings — the dashboard renders the most recent expanded and
    # the rest as a collapsed archive.
    briefings = db.get_recent_briefings(limit=30)
    last_briefing = briefings[0] if briefings else None

    return {
        "generated_at": today_iso,
        "current_weight": current_weight,
        "current_weight_date": current_weight_date,
        "this_week": this_week,
        "this_week_target": week_target,
        "daily": daily,
        "weekly": weekly,
        "weight_schedule": schedule,
        "target_lifts": target_lifts,
        "lift_prs": prs,
        "recent_runs": recent_runs,
        "streaks": compute_streaks(daily),
        "targets": {k: v["value"] for k, v in targets.items()},
        "last_briefing": last_briefing,
        "briefings": briefings,
    }


def main():
    payload = build_payload()
    out = Path(__file__).parent.parent / "docs" / "data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, default=str, indent=2))
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
