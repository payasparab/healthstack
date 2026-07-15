"""Hevy API wrapper. Pulls workouts and their sets."""
from datetime import datetime, timedelta
import requests
from .. import config

BASE = "https://api.hevyapp.com/v1"

def _headers() -> dict:
    return {"api-key": config.HEVY_API_KEY, "accept": "application/json"}

def get_workouts_since(days_back: int = 3) -> list[dict]:
    """Fetch recent workouts. Hevy returns most-recent-first, paginated."""
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    out = []
    page = 1
    while True:
        r = requests.get(
            f"{BASE}/workouts",
            headers=_headers(),
            params={"page": page, "pageSize": 10},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        workouts = data.get("workouts", [])
        if not workouts:
            break

        stop = False
        for w in workouts:
            start = _parse_ts(w.get("start_time"))
            if start and start < cutoff:
                stop = True
                continue
            out.append(w)
        if stop or page >= data.get("page_count", 1):
            break
        page += 1
    return out

def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None

def normalize_workout(w: dict) -> tuple[dict, list[dict]]:
    """Return (workout_row, [lift_rows])."""
    start = _parse_ts(w.get("start_time"))
    end = _parse_ts(w.get("end_time"))
    date_iso = start.date().isoformat() if start else datetime.utcnow().date().isoformat()
    duration_min = None
    if start and end:
        duration_min = round((end - start).total_seconds() / 60, 1)

    workout_row = {
        "date": date_iso,
        "type": "strength",
        "source": "hevy",
        "external_id": w.get("id"),
        "duration_min": duration_min,
        "notes": w.get("title"),
        "raw": w,
    }

    lift_rows: list[dict] = []
    for ex in w.get("exercises", []):
        exercise_name = ex.get("title") or ex.get("exercise_template_id") or "Unknown"
        for i, s in enumerate(ex.get("sets", []), start=1):
            weight_kg = s.get("weight_kg")
            reps = s.get("reps")
            if weight_kg is None and reps is None:
                continue
            weight_lb = round(weight_kg * 2.20462, 2) if weight_kg is not None else None
            lift_rows.append({
                "date": date_iso,
                "exercise": exercise_name,
                "set_num": i,
                "weight_lb": weight_lb,
                "reps": reps,
                "is_working_set": (s.get("type", "normal") == "normal"),
            })
    return workout_row, lift_rows
