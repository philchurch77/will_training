---
name: wheels-up
description: "Wheels Up — full pre-deploy workflow: Les tidy pass, the canonical Azure deployment checklist, then commit message. The checklist lives here; /pre-deploy runs it standalone."
disable-model-invocation: true
---

# Wheels Up — Pre-Deploy

You are running Wheels Up: the pre-deploy check before pushing to Azure.

Work through each stage in order. Stop and surface any failures before continuing.

---

## Stage 1 — Final tidy with Les

Spawn Les on the files changed since the last commit. Ask Les to flag anything obviously messy — oversized views, duplicated logic, or code that will be painful to debug in production. Fix any High findings before moving on.

---

## Stage 2 — Deployment checklist

Check each item and report pass/fail:

1. **requirements.txt** — no Windows-only packages (e.g. `pywin32`, `winreg`) that would break the Linux Azure build; file is still plain UTF-8 (not UTF-16, which pip cannot parse)
2. **SECRET_KEY** — confirm `core_standards/settings.py` reads it from `DJANGO_SECRET_KEY`, not hardcoded
3. **DEBUG** — confirm it defaults to `False` when `DJANGO_DEBUG` is unset
4. **Migrations** — run `python manage.py migrate --check` to confirm no unapplied migrations
5. **CSAT content** — confirm `python manage.py seed_csat` runs after `migrate` on startup (idempotent) and `docs/csat_data.json` is valid UTF-8
6. **Static files** — confirm WhiteNoise is in `MIDDLEWARE` and the `STORAGES` static backend, and `collectstatic` runs clean
7. **ALLOWED_HOSTS** — confirm it is populated from `DJANGO_ALLOWED_HOSTS` and not empty for production
8. **Feature flags** — confirm `CSAT_ASSESSMENT_ENABLED` / `EXECUTIVE_SUMMARIES_ENABLED` are set intentionally as Azure app settings
9. **Open TODOs** — grep `core_standards/`, `assessments/`, `csat/`, `home/`, `standards/` for any `TODO`, `FIXME`, or `HACK` comments

---

## Stage 3 — Commit message

When the checklist passes, confirm with the user that they want to commit, then draft a clean commit message following the project's commit style: present tense, concise, focused on the why rather than the what.

---

## Finish

Final verdict: **Ready to deploy** or **Fix before deploying**, with a list of any failures.
