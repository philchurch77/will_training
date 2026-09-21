---
name: migrations-read
description: Every migration in will_training/training/migrations read by the Purser, what each does, and which are destructive
metadata:
  type: project
---

Read and assessed. None of 0001-0007 is destructive.

- `0001_initial` — creates the whole schema.
- `0002_alter_skill_colour` — field alteration on Skill.colour.
- `0003_alter_badge_kind` — choices change on Badge.kind.
- `0004_plan_day_target_thirty` — PlanDay target minutes.
- `0005_drill_is_juggling_alter_badge_kind_sessionclock` — adds `Drill.is_juggling`, adds the `SessionClock` model.
- `0006_alter_plandrill_options_plandrill_week` — adds `PlanDrill.week`, the fortnight rotation.
- `0007_drill_is_combination` — single `AddField(BooleanField, default=False)` on Drill. Additive, loses nothing.

**The thing to remember about 0007 and every future AddField on this project.**
The database is SQLite, so Django does not emit `ALTER TABLE ADD COLUMN` for a
`NOT NULL` field. It emits a full table remake:
`CREATE TABLE new__training_drill` / `INSERT ... SELECT` / `DROP TABLE
training_drill` / `RENAME`. Verified with `manage.py sqlmigrate training 0007`.

That `DROP TABLE` does **not** cascade to `SessionLog`, because Django's SQLite
schema editor (`django/db/backends/sqlite3/schema.py`, `__enter__`) calls
`disable_constraint_checking()` which issues `PRAGMA foreign_keys = OFF` for the
duration, then runs `PRAGMA foreign_key_check` on exit. Verified in the
installed Django source, not assumed. Do not re-derive this next time — but do
re-check it if the project ever moves off SQLite or upgrades Django major.

Read-only commands that are safe to run here: `showmigrations`, `sqlmigrate`,
`makemigrations --check --dry-run`. All three were clean at 0007.

See [[cascades]] and [[deploy-data-safety]].

Re-confirmed 2026-09-21: `showmigrations training` shows 0001-0007 all applied
and 0007 still the head; `makemigrations --check --dry-run` returns
"No changes detected". Nothing has been added since this note was written.
