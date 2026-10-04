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

**0008_deck (read 2026-10-03)** — two `CreateModel`s, `Card` and `Play`, and
nothing else. `sqlmigrate` is two `CREATE TABLE` + two `CREATE INDEX`: no
table rebuild, no existing table touched. Additive, loses nothing. Committed
in 4914d36 and already on `origin/main`, so treat it as possibly applied on
Render: never edit it, add 0009 instead. `makemigrations --check` clean at 0008.

**0009_play_stamps (read 2026-10-03, uncommitted on deck-step-2)** — three
nullable `PositiveSmallIntegerField` AddFields on Play (`points`, `medal`,
`bests`). `sqlmigrate` is three plain `ALTER TABLE ADD COLUMN ... NULL CHECK
(>=0)`: **no table rebuild** (nullable, no default => SQLite ADD COLUMN, unlike
0007). Existing rows get NULL, which passes the CHECK. Additive, loses nothing.
Applied on dev; `makemigrations --check` clean at 0009.

**0010_badge_retire_and_deck_kinds (read 2026-10-04, uncommitted on deck-step-2b)**
- `AddField Badge.is_active BooleanField(default=True)` + `AlterField Badge.kind`
(choices only). `sqlmigrate`: **table rebuild** of `training_badge` (NOT NULL
with default => remake, like 0007): INSERT SELECT carries `id` explicitly, so
`EarnedBadge.badge_id` still points at the same rows; every row gets
`is_active=1`. AlterField is `-- (no-op)`. Django 5.2.17 schema editor still
does `PRAGMA foreign_keys = OFF` on enter and `check_constraints()` on exit
(re-verified in .venv source). Additive, loses nothing. Applied on dev;
`makemigrations --check` clean. 2a (0009) not yet on Render, so a 2b deploy
carries 0009+0010 in one `migrate` pass.
