"""Google Sheet source. Reads the Health Connect export sheet via public CSV.

The sheet is a "Health Connect export" with five tabs:
  Activity, Nutrition, Sleep, Vitals, Body

The whole workbook is fetched once per process (four to five short HTTP GETs)
and then queried in-memory. No Google API client, no OAuth — the sheet just
has to be shared as "Anyone with the link can view".

Dedup strategy — the sheet contains overlapping rows for three reasons:

  1. A source re-syncs the same daily row (identical columns end up in the
     export twice).
  2. Fitbit repeats the daily step / calorie totals on every workout-session
     row, so a day with four workouts shows four rows with the same Steps.
  3. Multiple sources report the same metric (Health Connect aggregator +
     Fitbit both write daily step totals; user might run two hydration apps).

To handle all three:
  * `_load()` drops byte-identical duplicate rows.
  * Per-source, we take the MAX for aggregate metrics (steps, hydration,
    calories, protein, carbs) — max is idempotent under duplication and
    picks the row that saw the most.
  * Across sources, we then SUM for genuinely additive metrics (hydration,
    nutrition) and MAX for shared aggregates (steps).
  * Sleep sessions dedupe on (source, start, end); meditation sessions on
    (source, start, name).

Public interface mirrors the old google_fit module:
  get_steps, get_weight_lb, get_sleep_hours, get_hydration_ml,
  get_meditation_min, get_nutrition, get_workout_sessions
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
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
    rows = [row for row in reader if any((v or "").strip() for v in row.values())]
    return _dedupe_identical(rows)


def _dedupe_identical(rows: list[dict]) -> list[dict]:
    """Drop byte-identical duplicate rows (all columns match)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        key = tuple(sorted((k, (v or "").strip()) for k, v in r.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


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


def _max_per_source(rows: list[dict], col: str) -> dict[str, float]:
    """For each source, take the max value of `col`. Handles duplicate rows
    from the same source (max is idempotent) and Fitbit's habit of repeating
    daily totals across multiple session rows."""
    out: dict[str, float] = {}
    for r in rows:
        src = (r.get("Source(s)") or "").strip()
        v = _fnum(r.get(col))
        if v is None:
            continue
        if v > out.get(src, float("-inf")):
            out[src] = v
    return out


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
    """Highest step count on this date across sources. Max is safe under
    both (a) same source repeating a daily total across many rows and
    (b) multiple sources each reporting an independent daily total."""
    rows = _rows_for_date(TAB_ACTIVITY, day_iso)
    per_source = _max_per_source(rows, "Steps")
    if not per_source:
        return None
    best = max(per_source.values())
    return int(best) if best > 0 else None


def get_weight_lb(day_iso: str) -> float | None:
    """Most recent weight reading on this date, converted to lb. Dedupes
    on (source, kg) so a re-synced identical reading doesn't affect
    ordering; returns the last remaining value."""
    rows = _rows_for_date(TAB_BODY, day_iso)
    seen: set[tuple[str, float]] = set()
    kg: float | None = None
    for r in rows:
        src = (r.get("Source(s)") or "").strip()
        for k, v in r.items():
            if not k:
                continue
            key = k.lower()
            if "weight" in key and "kg" in key:
                n = _fnum(v)
                if n is None:
                    continue
                sig = (src, round(n, 4))
                if sig in seen:
                    continue
                seen.add(sig)
                kg = n
    if kg is None:
        return None
    return round(kg * 2.20462, 2)


def get_sleep_hours(day_iso: str) -> float | None:
    """Total sleep hours for the night ending on this date. Sleep rows
    dedupe on (source, Start Time, End Time) so a re-synced night doesn't
    double-count; a same-night row from a second source with the same
    start/end is also treated as a duplicate rather than added."""
    rows = _rows_for_date(TAB_SLEEP, day_iso)
    total_min = 0.0
    seen: set[tuple[str, str]] = set()
    for r in rows:
        start_raw = (r.get("Start Time") or "").strip()
        end_raw = (r.get("End Time") or "").strip()
        key = (start_raw, end_raw)
        if key != ("", "") and key in seen:
            continue
        if key != ("", ""):
            seen.add(key)

        start = _parse_dt(start_raw)
        end = _parse_dt(end_raw)
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
    """Total hydration in ml for the day. Max within a source (idempotent
    against re-syncs of the same daily total), summed across sources."""
    rows = _rows_for_date(TAB_NUTRITION, day_iso)
    per_source = _max_per_source(rows, "Hydration (ml)")
    total = sum(per_source.values())
    return round(total, 1) if total > 0 else None


def get_meditation_min(day_iso: str) -> float:
    """Total meditation minutes on the day. Same session dedup as workouts:
    (source, start-timestamp, exercise-name)."""
    rows = _rows_for_date(TAB_ACTIVITY, day_iso)
    total = 0.0
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        name = (r.get("Exercise Name") or "").strip()
        if not name or _classify(name) != "meditation":
            continue
        start = (r.get("Start Date/Time") or "").strip()
        src = _source_hint(r.get("Source(s)") or "", name)
        key = (src, start, name)
        if key in seen:
            continue
        seen.add(key)
        total += _fnum(r.get("Duration (min)")) or 0
    return round(total, 1)


def get_nutrition(day_iso: str) -> dict:
    """Calories, protein, and carbs for the day. Max per source per column
    (idempotent under re-sync of the daily aggregate), summed across sources."""
    rows = _rows_for_date(TAB_NUTRITION, day_iso)
    cals = _max_per_source(rows, "Nutrition calories (kcal)")
    prot = _max_per_source(rows, "Protein (g)")
    carbs = _max_per_source(rows, "Carbs (g)")
    return {
        "calories": round(sum(cals.values())) if cals else None,
        "protein_g": round(sum(prot.values()), 1) if prot else None,
        "carbs_g": round(sum(carbs.values()), 1) if carbs else None,
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
