---
name: migration-review
description: Read-only safety review of unapplied or newly created Django migrations — data loss, snapshot immutability, positional statement identity, seed_csat interaction, reversibility — before anything is applied.
allowed-tools: Read, Grep, Glob, Bash
disable-model-invocation: true
---

# Migration Review

Review migrations before they are applied or shipped. Read-only: do not
apply, edit, or create migrations, and change no code.

## Scope

Use $ARGUMENTS to name specific migration files or an app. If empty, review
everything unapplied (`python manage.py showmigrations` to find them) plus
any migration files that are uncommitted per `git status`.

## Checks — pass/fail each

1. **Data loss.** Any `RemoveField`, `DeleteModel`, `AlterField` that
   narrows/retypes a column, or destructive `RunPython`? This project's rule
   is archive-not-delete — flag anything that destroys pupil/school QA data.
2. **Snapshot immutability.** Nothing may rewrite `Snapshot.data` or
   reshape frozen JSON. Migrating live content must never touch snapshots —
   they are the historical record.
3. **Statement identity.** Statement identity is positional
   `(sub_standard, tier, order)`. Any migration that reorders, renumbers, or
   re-keys statements within a tier is a data-integrity risk, not cosmetic —
   existing judgements would silently point at different statements.
4. **CSAT content boundary.** `docs/csat_data.json` + `seed_csat` is the
   single source of truth for CSAT content. Flag any data migration that
   hand-edits CSAT content in the DB. Check ordering with startup: will this
   migration break the `migrate` → `seed_csat` sequence, and is seeding still
   idempotent afterwards?
5. **Reversibility.** Does `RunPython` have a real reverse (not
   `RunPython.noop` hiding an irreversible change)? Could we roll back on
   Azure after a bad deploy?
6. **Deploy safety.** Anything that locks large tables, needs a default
   backfill on a big table, or assumes local SQLite behaviour that differs in
   production. Multiple migrations with a merge risk if another branch adds
   one to the same app.
7. **Dry run.** `python manage.py migrate --plan` and
   `python manage.py makemigrations --check --dry-run` — confirm the plan is
   what the files say and no migrations are missing.

## Verdict

Pass/fail per check with `path:line` citations, then one line: **Safe to
apply** or **Do not apply**, with the blocking items. If a migration touches
assessment data or permissions models, note that `/gauntlet` applies to the
feature as a whole.
