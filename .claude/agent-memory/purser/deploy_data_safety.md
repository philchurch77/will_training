---
name: deploy-data-safety
description: What runs automatically on Render for will_training, the now-guarded seed_drills --reset, and the exact SQLite backup command
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

**RESOLVED 2026-09-21: `seed_drills --reset` is now guarded.**
`handle()` raises `CommandError` when `--reset` is passed and
`settings.DEBUG` is False, before any delete runs (`seed_drills.py`, top of
`handle`). `TestResetIsRefused` in `test_seed.py` covers the guard and
`test_a_refused_reset_deletes_no_history` covers the rollback. The
recommendation in the earlier version of this note was taken. Do not re-raise
it as an open finding - verify the guard is still there and move on.

**Backup before any migrate on Render.** Render disk snapshots exist but
restoring is a support round trip, so take one first, from the Render shell:

    python -c "import sqlite3,datetime; s=sqlite3.connect('/var/data/db.sqlite3'); d=sqlite3.connect('/var/data/db-backup-%s.sqlite3'%datetime.date.today().isoformat()); s.backup(d); d.close(); s.close()"

Online backup, safe while gunicorn is serving. Confirm with `ls -l /var/data`
and a row count on the copy. A backup on the same disk does not survive disk
loss — the copy should be pulled off the box for anything risky.

The seeder also does `day.items.all().delete()` on every run, so any plan edit
Phil makes by hand on the coach screens is wiped by the next deploy.

See [[migrations-read]].
