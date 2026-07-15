"""Google Fit REST API wrapper.

Pulls steps, sleep, weight, and workout sessions for a given date range.
Uses the OAuth refresh token stored in GOOGLE_OAUTH_TOKEN env var.
"""
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from .. import config

SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.location.read",
    "https://www.googleapis.com/auth/gmail.send",
]

# Fit activity type ids we care about
# https://developers.google.com/fit/rest/v1/reference/activity-types
STRENGTH_TYPES = {80, 97}                 # strength training, weightlifting
RUN_TYPES = {8, 56, 57, 58}               # running variants
WALK_TYPES = {7, 93}                      # walking, hiking
MOBILITY_TYPES = {100, 101, 102, 111, 112}  # yoga, pilates, mobility-ish
MEDITATION_TYPES = {45}                   # meditation


def _creds() -> Credentials:
    token_data = config.google_oauth_token_dict()
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError("Google credentials invalid and cannot be refreshed. Re-run first_time_oauth.py.")
    return creds


def _service():
    return build("fitness", "v1", credentials=_creds(), cache_discovery=False)


def _ns(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1e9)


def _day_bounds(day_iso: str) -> tuple[datetime, datetime]:
    d = datetime.fromisoformat(day_iso)
    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1)
    return start, end


def get_steps(day_iso: str) -> int | None:
    """Total steps for a given local date."""
    start, end = _day_bounds(day_iso)
    svc = _service()
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.step_count.delta"}],
        "bucketByTime": {"durationMillis": 86_400_000},
        "startTimeMillis": int(start.timestamp() * 1000),
        "endTimeMillis": int(end.timestamp() * 1000),
    }
    resp = svc.users().dataset().aggregate(userId="me", body=body).execute()
    total = 0
    for bucket in resp.get("bucket", []):
        for ds in bucket.get("dataset", []):
            for pt in ds.get("point", []):
                for v in pt.get("value", []):
                    total += v.get("intVal", 0)
    return total if total > 0 else None


def get_weight_lb(day_iso: str) -> float | None:
    """Most recent weight reading on the given date, converted to lb."""
    start, end = _day_bounds(day_iso)
    svc = _service()
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.weight"}],
        "bucketByTime": {"durationMillis": 86_400_000},
        "startTimeMillis": int(start.timestamp() * 1000),
        "endTimeMillis": int(end.timestamp() * 1000),
    }
    resp = svc.users().dataset().aggregate(userId="me", body=body).execute()
    kg = None
    for bucket in resp.get("bucket", []):
        for ds in bucket.get("dataset", []):
            for pt in ds.get("point", []):
                for v in pt.get("value", []):
                    if "fpVal" in v:
                        kg = v["fpVal"]  # aggregate weight point uses average
    if kg is None:
        return None
    return round(kg * 2.20462, 2)


def get_sleep_hours(day_iso: str) -> float | None:
    """Sleep duration for the night ending on this date.
    Queries the sleep-session data source (com.google.sleep.segment).
    """
    d = datetime.fromisoformat(day_iso)
    start = datetime(d.year, d.month, d.day) - timedelta(hours=18)
    end = datetime(d.year, d.month, d.day) + timedelta(hours=12)

    svc = _service()
    sessions = svc.users().sessions().list(
        userId="me",
        startTime=start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        endTime=end.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        activityType=72,  # sleep
    ).execute()

    total_ms = 0
    for s in sessions.get("session", []):
        try:
            total_ms += int(s["endTimeMillis"]) - int(s["startTimeMillis"])
        except (KeyError, ValueError):
            continue
    if total_ms == 0:
        return None
    return round(total_ms / (1000 * 60 * 60), 2)


def get_hydration_ml(day_iso: str) -> float | None:
    """Total hydration logged on a given date (milliliters)."""
    start, end = _day_bounds(day_iso)
    svc = _service()
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.hydration"}],
        "bucketByTime": {"durationMillis": 86_400_000},
        "startTimeMillis": int(start.timestamp() * 1000),
        "endTimeMillis": int(end.timestamp() * 1000),
    }
    try:
        resp = svc.users().dataset().aggregate(userId="me", body=body).execute()
    except Exception:
        return None
    total_liters = 0.0
    for bucket in resp.get("bucket", []):
        for ds in bucket.get("dataset", []):
            for pt in ds.get("point", []):
                for v in pt.get("value", []):
                    if "fpVal" in v:
                        total_liters += v["fpVal"]  # already liters per Fit spec
    return round(total_liters * 1000, 1) if total_liters > 0 else None


def get_meditation_min(day_iso: str) -> float:
    """Total meditation minutes logged on a given date. 0 if none."""
    d = datetime.fromisoformat(day_iso)
    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1)
    svc = _service()
    sessions = svc.users().sessions().list(
        userId="me",
        startTime=start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        endTime=end.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        activityType=45,
    ).execute()
    total_ms = 0
    for s in sessions.get("session", []):
        try:
            total_ms += int(s["endTimeMillis"]) - int(s["startTimeMillis"])
        except (KeyError, ValueError):
            continue
    return round(total_ms / (1000 * 60), 1)


def get_nutrition(day_iso: str) -> dict:
    """Total calories, protein (g), and carbs (g) logged on a given date.

    Reads from com.google.nutrition — populated by whichever nutrition app the
    user has writing to Health Connect (Nutrola, Cronometer, MFP, etc.).
    Returns dict with keys: calories, protein_g, carbs_g. Values may be None.
    """
    start, end = _day_bounds(day_iso)
    svc = _service()
    body = {
        "aggregateBy": [{"dataTypeName": "com.google.nutrition"}],
        "bucketByTime": {"durationMillis": 86_400_000},
        "startTimeMillis": int(start.timestamp() * 1000),
        "endTimeMillis": int(end.timestamp() * 1000),
    }
    try:
        resp = svc.users().dataset().aggregate(userId="me", body=body).execute()
    except Exception as e:
        print(f"[fit] nutrition fetch failed: {e}")
        return {"calories": None, "protein_g": None, "carbs_g": None}

    calories = 0.0
    protein = 0.0
    carbs = 0.0
    found = False
    for bucket in resp.get("bucket", []):
        for ds in bucket.get("dataset", []):
            for pt in ds.get("point", []):
                for v in pt.get("value", []):
                    # Nutrition points come as a mapVal with per-nutrient sub-values
                    if "mapVal" in v:
                        for entry in v["mapVal"]:
                            key = entry.get("key", "")
                            val = entry.get("value", {}).get("fpVal")
                            if val is None:
                                continue
                            found = True
                            if key == "calories":
                                calories += val
                            elif key == "protein":
                                protein += val
                            elif key == "carbs.total":
                                carbs += val
    if not found:
        return {"calories": None, "protein_g": None, "carbs_g": None}
    return {
        "calories": round(calories),
        "protein_g": round(protein, 1),
        "carbs_g": round(carbs, 1),
    }


def get_workout_sessions(day_iso: str) -> list[dict]:
    """Return workout sessions that started on the given local date.

    Returns dicts like:
      { external_id, type, source, duration_min, distance_km, pace_min_per_km, calories, notes, raw }
    """
    d = datetime.fromisoformat(day_iso)
    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1)

    svc = _service()
    sessions = svc.users().sessions().list(
        userId="me",
        startTime=start.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        endTime=end.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
    ).execute()

    out = []
    for s in sessions.get("session", []):
        act = s.get("activityType", 0)
        if act == 72:  # skip sleep, we handle it separately
            continue

        duration_ms = int(s.get("endTimeMillis", 0)) - int(s.get("startTimeMillis", 0))
        duration_min = round(duration_ms / (1000 * 60), 1)

        if act in STRENGTH_TYPES:
            wtype = "strength"
        elif act in RUN_TYPES:
            wtype = "run"
        elif act in WALK_TYPES:
            wtype = "walk"
        elif act in MOBILITY_TYPES:
            wtype = "mobility"
        elif act in MEDITATION_TYPES:
            wtype = "meditation"
        else:
            wtype = "other"

        source = s.get("application", {}).get("packageName", "fit")
        source_hint = _source_hint(source, s.get("name", ""))

        out.append({
            "external_id": s.get("id"),
            "type": wtype,
            "source": source_hint,
            "duration_min": duration_min,
            "notes": s.get("name") or s.get("description"),
            "raw": s,
        })
    return out


def _source_hint(package: str, name: str) -> str:
    p = (package or "").lower()
    n = (name or "").lower()
    if "runna" in p or "runna" in n:
        return "runna"
    if "gowod" in p or "gowod" in n or "mobility" in n:
        return "gowod"
    if "hevy" in p:
        return "hevy"
    return "fit"
