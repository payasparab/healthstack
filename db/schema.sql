-- healthstack schema
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS daily (
  date DATE PRIMARY KEY,
  weight_lb NUMERIC,
  steps INT,
  sleep_hours NUMERIC,
  hydration_met BOOLEAN DEFAULT FALSE,
  meditation_met BOOLEAN DEFAULT FALSE,
  calories INT,
  protein_g NUMERIC,
  carbs_g NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workouts (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  type TEXT NOT NULL,          -- 'strength' | 'run' | 'mobility' | 'walk' | 'other'
  source TEXT NOT NULL,        -- 'hevy' | 'runna' | 'gowod' | 'fit'
  external_id TEXT,            -- source's own id, for dedupe
  duration_min NUMERIC,
  distance_km NUMERIC,
  pace_min_per_km NUMERIC,
  calories INT,
  notes TEXT,
  raw JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS workouts_date_idx ON workouts (date DESC);
CREATE INDEX IF NOT EXISTS workouts_type_idx ON workouts (type);

CREATE TABLE IF NOT EXISTS lifts (
  id BIGSERIAL PRIMARY KEY,
  workout_id BIGINT REFERENCES workouts(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  exercise TEXT NOT NULL,
  set_num INT,
  weight_lb NUMERIC,
  reps INT,
  is_working_set BOOLEAN DEFAULT TRUE,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS lifts_date_idx ON lifts (date DESC);
CREATE INDEX IF NOT EXISTS lifts_exercise_idx ON lifts (exercise);

CREATE TABLE IF NOT EXISTS targets (
  key TEXT PRIMARY KEY,
  value NUMERIC NOT NULL,
  unit TEXT,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weight_schedule (
  week_start DATE PRIMARY KEY,       -- Sunday-anchored
  target_lb NUMERIC NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lift_prs (
  exercise TEXT PRIMARY KEY,
  target_lb NUMERIC NOT NULL,
  current_best_lb NUMERIC,
  current_best_date DATE,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS briefings (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  kind TEXT NOT NULL,                -- 'daily' | 'weekly'
  content TEXT NOT NULL,
  input_summary JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS briefings_date_idx ON briefings (date DESC);

-- Manual check-in log so we can trace hydration/meditation taps from emails
CREATE TABLE IF NOT EXISTS checkins (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  kind TEXT NOT NULL,                -- 'hydration' | 'meditation'
  source TEXT DEFAULT 'email_link',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
