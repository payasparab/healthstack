"""Google Sheet source. Reads the Health Connect export sheet via public CSV.

The sheet is a "Health Connect export" with five tabs:
  Activity, Nutrition, Sleep, Vitals, Body

The whole workbook is fetched once per process (four to five short HTTP GETs)
and then queried in-memory. No Google API client, no OAuth — the sheet just
has to be shared as "Anyone with the link can view".

Public interface mirrors the old google_fit module so ingest.py can swap
`from .sources import google_fit` for `google_sheet` with no other changes:
  get_steps, get_weight_lb, get_sleep_hours, get_hydration_ml,
  get_meditation_min, get_nutrition, get_workout_sessions
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta
from functools import lru_cache
from urllib.parse import quote

import requests

from .. import config


TAB_ACTIVITY = "Activity"
TAB_NUTRITION = "Nutrition"
TAB_SLEEP = "Sleep"
TAB_BODY = "Body"

_GVIZ_URL = (
    "https://docs.google.com/spreadsheets/d/{sid}/gviz/tq"
    "?tqx=out:csv&sheet={name}"
)

# Fitbit exercise names in the export come through as "<numeric_id> - <label>",
# e.g. "70 - Strength Training", "79 - Walking". Hevy rows are plain titles.
_STRENGTH_HINT = re.compile(r"strength|weight|hevy|push|pull|legs|upper|lower", re.I)
_RUN_HINT = re.compile(r"\brun|jog|treadmill", re.I)
_WALK_HINT = re.compile(r"walk|hike|hiking", re.I)
_MOBILITY_HINT = re.compile(r"yoga|pilates|mobility|stretch|gowod", re.I)
_MEDITATION_HINT = re.compile(r"meditat|mindful|breath", re.I)


# ------------------------------------------------------------------ fetching

def _fetch_tab(name: str) -> list[dict]:
    url = _GVIZ_URL.format(sid=config.HEALTHSTACK_SHEET_ID, name=quote(name))
    r = requests.get(url, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    text = r.text
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader if any((v or "").strip() for v in row.values())]


@lru_cache(maxsize=None)
def _load(name: str) -> list[dict]:
    try:
        return _fetch_tab(name)
    except requests.HTTPError as e:
        print(f"[sheet] tab {name!r} fetch failed: {e}")
        return []


def _clear_cache() -> None:
    """Test/debug helper — drop the in-process cache so a re-run refetches."""
    _load.cache_clear()


# ------------------------------------------------------------------ helpers

def _rows_for_date(tab: str, day_iso: str) -> list[dict]:
    return [r for r in _load(tab) if (r.get("Date") or "").strip() == day_iso]


def _fnum(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _classify(name: str) -> str:
    n = (name or "").lower()
    if _MEDITATION_HINT.search(n):
        return "meditation"
    if _MOBILITY_HINT.search(n):
        return "mobility"
    if _RUN_HINT.search(n):
        return "run"
    if _WALK_HINT.search(n):
        return "walk"
    if _STRENGTH_HINT.search(n):
        return "strength"
    return "other"


def _source_hint(pkg: str, name: str) -> str:
    p = (pkg or "").lower()
    n = (name or "").lower()
    if "hevy" in p or "hevy" in n:
        return "hevy"
    if "runna" in p or "runna" in n:
        return "runna"
    if "gowod" in p or "gowod" in n or "mobility" in n:
        return "gowod"
    if "fitbit" in p:
        return "fitbit"
    return "sheet"


# ------------------------------------------------------------------ metrics

def get_steps(day_iso: str) -> int | None:
    """Highest step count on this date across sources (Health Connect + Fitbit
    both write step totals; taking the max avoids double-counting and picks
    the source that saw the most)."""
    rows = _rows_for_date(TAB_ACTIVITY, day_iso)
    best = 0
    for r in rows:
        v = _fnum(r.get("Steps"))
        if v is not None and v > best:
            best = v
    return int(best) if best > 0 else None


def get_weight_lb(day_iso: str) -> float | None:
    """Most recent weight reading on this date, converted to lb. Reads from
    the Body tab; falls back to None if the tab or column is absent."""
    rows = _rows_for_date(TAB_BODY, day_iso)
    kg = None
    for r in rows:
        for k, v in r.items():
            if not k:
                continue
            key = k.lower()
            if "weight" in key and "kg" in key:
                n = _fnum(v)
                if n is not None:
                    kg = n
    if kg is None:
        return None
    return round(kg * 2.20462, 2)


def get_sleep_hours(day_iso: str) -> float | None:
    """Total sleep hours for the night ending on this date. The Sleep tab
    stores per-night rows with light/deep/REM/awake minutes and start/end
    timestamps. Prefer End - Start when present; otherwise sum light+deep+REM."""
    rows = _rows_for_date(TAB_SLEEP, day_iso)
    total_min = 0.0
    for r in rows:
        start = _parse_dt(r.get("Start Time"))
        end = _parse_dt(r.get("End Time"))
        if start and end and end > start:
            total_min += (end - start).total_seconds() / 60
            continue
        light = _fnum(r.get("Light Sleep (min)")) or 0
        deep = _fnum(r.get("Deep Sleep (min)")) or 0
        rem = _fnum(r.get("REM Sleep (min)")) or 0
        stage_total = light + deep + rem
        if stage_total > 0:
            total_min += stage_total
    return round(total_min / 60, 2) if total_min > 0 else None


def get_hydration_ml(day_iso: str) -> float | None:
    """Total hydration in ml for the day."""
    rows = _rows_for_date(TAB_NUTRITION, day_iso)
    total = 0.0
    for r in rows:
        v = _fnum(r.get("Hydration (ml)"))
        if v is not None:
            total += v
    return round(total, 1) if total > 0 else None


def get_meditation_min(day_iso: str) -> float:
    """Total meditation minutes on the day (0 if none). Sourced from Activity
    rows whose Exercise Name looks like meditation/mindfulness."""
    rows = _rows_for_date(TAB_ACTIVITY, day_iso)
    total = 0.0
    for r in rows:
        name = r.get("Exercise Name") or ""
        if not name.strip():
            continue
        if _classify(name) == "meditation":
            total += _fnum(r.get("Duration (min)")) or 0
    return round(total, 1)


def get_nutrition(day_iso: str) -> dict:
    """Sum calories, protein, and carbs across the day's nutrition rows.
    Returns {calories, protein_g, carbs_g}, each None if never reported."""
    rows = _rows_for_date(TAB_NUTRITION, day_iso)
    calories = None
    protein = None
    carbs = None
    for r in rows:
        c = _fnum(r.get("Nutrition calories (kcal)"))
        p = _fnum(r.get("Protein (g)"))
        cb = _fnum(r.get("Carbs (g)"))
        if c is not None:
            calories = (calories or 0) + c
        if p is not None:
            protein = (protein or 0) + p
        if cb is not None:
            carbs = (carbs or 0) + cb
    return {
        "calories": round(calories) if calories is not None else None,
        "protein_g": round(protein, 1) if protein is not None else None,
        "carbs_g": round(carbs, 1) if carbs is not None else None,
    }


def get_workout_sessions(day_iso: str) -> list[dict]:
    """Return workout sessions logged on this date.

    Activity rows with a Start Date/Time + Exercise Name are workout entries.
    Rows without those columns are just daily step/calorie aggregates and
    are skipped here. Deduped on (source, start-timestamp, exercise-name)
    so ingest.upsert_workout has a stable key.
    """
    rows = _rows_for_date(TAB_ACTIVITY, day_iso)
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        start_raw = (r.get("Start Date/Time") or "").strip()
        name = (r.get("Exercise Name") or "").strip()
        if not start_raw or not name:
            continue

        source_pkg = r.get("Source(s)") or ""
        source = _source_hint(source_pkg, name)

        dedup_key = (source, start_raw, name)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        wtype = _classify(name)
        # Hevy rows in the Activity tab overlap with the dedicated Hevy API
        # ingest (which supplies set-by-set lifts); skip the coarse Activity
        # row so we don't double-count strength sessions.
        if source == "hevy":
            continue

        duration = _fnum(r.get("Duration (min)"))
        distance_m = _fnum(r.get("Distance (m)"))
        distance_km = round(distance_m / 1000, 3) if distance_m else None
        pace = None
        if wtype == "run" and duration and distance_km:
            pace = round(duration / distance_km, 2)

        external_id = f"sheet:{source}:{start_raw}:{name}"
        out.append({
            "external_id": external_id,
            "type": wtype,
            "source": source,
            "duration_min": duration,
            "distance_km": distance_km,
            "pace_min_per_km": pace,
            "notes": name,
            "raw": r,
        })
    return out


# ------------------------------------------------------------------ util

def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except ValueError:
        return None
