"""Supabase client + typed helpers."""
from supabase import create_client, Client
from . import config

_client: Client | None = None

def db() -> Client:
    global _client
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client

def upsert_daily(row: dict) -> None:
    """row must include 'date' as ISO string."""
    db().table("daily").upsert(row, on_conflict="date").execute()

def upsert_workout(row: dict) -> int | None:
    """Idempotent by (source, external_id). Returns id if available."""
    resp = db().table("workouts").upsert(
        row, on_conflict="source,external_id"
    ).execute()
    if resp.data:
        return resp.data[0].get("id")
    return None

def insert_lifts(rows: list[dict]) -> None:
    if not rows:
        return
    db().table("lifts").insert(rows).execute()

def delete_lifts_for_workout(workout_id: int) -> None:
    db().table("lifts").delete().eq("workout_id", workout_id).execute()

def get_daily_range(start: str, end: str) -> list[dict]:
    resp = db().table("daily").select("*").gte("date", start).lte("date", end).order("date").execute()
    return resp.data or []

def get_workouts_range(start: str, end: str) -> list[dict]:
    resp = db().table("workouts").select("*").gte("date", start).lte("date", end).order("date").execute()
    return resp.data or []

def get_lifts_range(start: str, end: str) -> list[dict]:
    resp = db().table("lifts").select("*").gte("date", start).lte("date", end).order("date").execute()
    return resp.data or []

def get_targets() -> dict:
    resp = db().table("targets").select("*").execute()
    return {r["key"]: r for r in (resp.data or [])}

def get_weight_schedule() -> list[dict]:
    resp = db().table("weight_schedule").select("*").order("week_start").execute()
    return resp.data or []

def get_lift_prs() -> list[dict]:
    resp = db().table("lift_prs").select("*").execute()
    return resp.data or []

def update_lift_pr(exercise: str, weight_lb: float, date: str) -> None:
    db().table("lift_prs").update({
        "current_best_lb": weight_lb,
        "current_best_date": date,
    }).eq("exercise", exercise).execute()

def save_briefing(date: str, kind: str, content: str, input_summary: dict) -> None:
    db().table("briefings").insert({
        "date": date, "kind": kind, "content": content, "input_summary": input_summary
    }).execute()


def get_recent_briefings(limit: int = 30) -> list[dict]:
    """Most-recent-first list of the last N briefings. Used to publish the
    archive to the GitHub Pages dashboard."""
    resp = (
        db().table("briefings")
        .select("date,kind,content,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []
