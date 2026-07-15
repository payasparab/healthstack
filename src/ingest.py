"""Ingest yesterday's data from all sources into Supabase.

Idempotent by design - safe to re-run any time.

Data sources:
  * Health Connect export sheet (steps, sleep, weight, hydration, meditation,
    nutrition, cardio/walk sessions). See src/sources/google_sheet.py.
  * Hevy API (strength workouts + per-set lifts). See src/sources/hevy.py.
"""
from datetime import timedelta, date
import sys

from . import db
from .sources import google_sheet, hevy


def yesterday_iso(days_back: int = 1) -> str:
    return (date.today() - timedelta(days=days_back)).isoformat()


def ingest_sheet(day: str) -> dict:
    print(f"[sheet] pulling {day}")
    weight = google_sheet.get_weight_lb(day)
    steps = google_sheet.get_steps(day)
    sleep = google_sheet.get_sleep_hours(day)
    hydration_ml = google_sheet.get_hydration_ml(day)
    meditation_min = google_sheet.get_meditation_min(day)
    nutrition = google_sheet.get_nutrition(day)
    sessions = google_sheet.get_workout_sessions(day)

    db.upsert_daily({
        "date": day,
        "weight_lb": weight,
        "steps": steps,
        "sleep_hours": sleep,
        "hydration_met": (hydration_ml or 0) > 0,
        "meditation_met": meditation_min > 0,
        "calories": nutrition.get("calories"),
        "protein_g": nutrition.get("protein_g"),
        "carbs_g": nutrition.get("carbs_g"),
    })

    for s in sessions:
        s["date"] = day
        db.upsert_workout(s)

    return {
        "weight": weight,
        "steps": steps,
        "sleep": sleep,
        "hydration_ml": hydration_ml,
        "meditation_min": meditation_min,
        "nutrition": nutrition,
        "sessions": len(sessions),
    }


def ingest_hevy(days_back: int = 3) -> dict:
    """Pull last few days of Hevy workouts, upsert, and refresh their lifts."""
    print(f"[hevy] pulling last {days_back}d")
    workouts = hevy.get_workouts_since(days_back=days_back)
    n_workouts = 0
    n_lifts = 0
    for w in workouts:
        row, lift_rows = hevy.normalize_workout(w)
        workout_id = db.upsert_workout(row)
        if workout_id and lift_rows:
            db.delete_lifts_for_workout(workout_id)
            for lr in lift_rows:
                lr["workout_id"] = workout_id
            db.insert_lifts(lift_rows)
            n_lifts += len(lift_rows)
        n_workouts += 1
    return {"workouts": n_workouts, "lifts": n_lifts}


def refresh_lift_prs() -> None:
    """Scan all lifts for target exercises, update current_best_lb."""
    prs = db.get_lift_prs()
    for pr in prs:
        exercise = pr["exercise"]
        resp = (
            db.db().table("lifts")
            .select("weight_lb,reps,date")
            .ilike("exercise", f"%{exercise}%")
            .order("weight_lb", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows:
            best = rows[0]
            db.update_lift_pr(exercise, best["weight_lb"], best["date"])


def main() -> None:
    day = sys.argv[1] if len(sys.argv) > 1 else yesterday_iso()
    print(f"=== ingest for {day} ===")
    sheet_summary = ingest_sheet(day)
    hevy_summary = ingest_hevy(days_back=3)
    refresh_lift_prs()
    print(f"sheet: {sheet_summary}")
    print(f"hevy: {hevy_summary}")


if __name__ == "__main__":
    main()
