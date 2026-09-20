---
name: deploy-data-safety
description: What runs automatically on Render for will_training, the unguarded seed_drills --reset, and the exact SQLite backup command
metadata:
  type: project
---

`render.yaml` `startCommand` = `migrate && seed_drills && gunicorn`, one worker.
`build.sh` runs only pip + `collectstatic --no-input`; no migrate, no seed, by
design (the `/var/data` disk is not mounted at build time). There is no
`.github/` and no CI. Verified by grepping every yaml/sh/toml/Procfile/Makefile
in the repo for `reset|flush|loaddata|--fake|--noinput`.

**So: every seeder edit is an unattended production data change, and every
migration applies with nobody watching.**

**The standing hazard: `seed_drills --reset` has no guard.**
`handle()` does `PlanDrill / PlanDay / TrainingPlan / Drill / Skill
.objects.all().delete()` with no confirmation prompt, no `--noinput` gate, and
no refusal when `DEBUG` is False or when `WILL_DB_PATH` points at `/var/data`.
Combined with the CASCADEs in [[cascades]], one `--reset` typed into a Render
shell destroys his entire history, streak and badges. It is documented in
CLAUDE.md as an ordinary developer command, so it is in muscle memory.
Recommended fix, raised but not yet applied: refuse when `settings.DEBUG` is
False unless an explicit `--i-know-what-this-does` flag is passed.

**Backup before any migrate on Render.** Render disk snapshots exist but
restoring is a support round trip, so take one first, from the Render shell:

    python -c "import sqlite3,datetime; s=sqlite3.connect('/var/data/db.sqlite3'); d=sqlite3.connect('/var/data/db-backup-%s.sqlite3'%datetime.date.today().isoformat()); s.backup(d); d.close(); s.close()"

Online backup, safe while gunicorn is serving. Confirm with `ls -l /var/data`
and a row count on the copy. A backup on the same disk does not survive disk
loss — the copy should be pulled off the box for anything risky.

The seeder also does `day.items.all().delete()` on every run, so any plan edit
Phil makes by hand on the coach screens is wiped by the next deploy.

See [[migrations-read]].
