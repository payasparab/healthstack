-- Seed targets from the planning sheet
-- Start date: 2026-07-14 (Tuesday). Weight schedule is Sunday-anchored weeks.

-- Basic targets
INSERT INTO targets (key, value, unit, notes) VALUES
  ('steps_daily', 12000, 'steps', 'daily average target'),
  ('hydration_days_per_week', 5, 'days', 'of 7'),
  ('meditation_days_per_week', 5, 'days', 'of 7'),
  ('exercise_sessions_per_week', 6, 'sessions', 'of 7'),
  ('running_sessions_per_week', 3, 'sessions', 'of 7'),
  ('stretching_min_per_week', 30, 'minutes', 'total per week'),
  ('calorie_cap_daily', 2500, 'kcal', 'daily max'),
  ('protein_daily', 220, 'grams', 'daily min'),
  ('carbs_daily', 50, 'grams', 'daily max'),
  ('weekly_weight_loss', 2.5, 'lb', 'weight loss per week target'),
  ('starting_weight', 280, 'lb', 'baseline 2026-07-14'),
  ('sleep_hours', 7, 'hours', 'nightly target')
ON CONFLICT (key) DO UPDATE
  SET value = EXCLUDED.value, unit = EXCLUDED.unit, notes = EXCLUDED.notes, updated_at = NOW();

-- Lift PR targets
INSERT INTO lift_prs (exercise, target_lb) VALUES
  ('Bench Press', 315),
  ('Tricep Pushdown', 130),
  ('Concentration Curl', 60),
  ('T-Bar Row', 315),
  ('Leg Press', 675),
  ('Hack Squat', 310)
ON CONFLICT (exercise) DO UPDATE
  SET target_lb = EXCLUDED.target_lb, updated_at = NOW();

-- Weight schedule: -2.5 lb/wk from 280, Sunday-anchored, starting week of 2026-07-12
-- (2026-07-14 is Tuesday, so week 1 starts Sunday 2026-07-12)
INSERT INTO weight_schedule (week_start, target_lb) VALUES
  ('2026-07-12', 280.0),
  ('2026-07-19', 277.5),
  ('2026-07-26', 275.0),
  ('2026-08-02', 272.5),
  ('2026-08-09', 270.0),
  ('2026-08-16', 267.5),
  ('2026-08-23', 265.0),
  ('2026-08-30', 262.5),
  ('2026-09-06', 260.0),
  ('2026-09-13', 257.5),
  ('2026-09-20', 255.0),
  ('2026-09-27', 252.5),
  ('2026-10-04', 250.0),
  ('2026-10-11', 247.5),
  ('2026-10-18', 245.0),
  ('2026-10-25', 242.5),
  ('2026-11-01', 240.0),
  ('2026-11-08', 237.5),
  ('2026-11-15', 235.0),
  ('2026-11-22', 232.5),
  ('2026-11-29', 230.0)
ON CONFLICT (week_start) DO UPDATE
  SET target_lb = EXCLUDED.target_lb, updated_at = NOW();
