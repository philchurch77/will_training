---
name: deep-dive
description: Read-only deep dive into a module that produces a ranked, impact-vs-effort improvement plan with a definition of done per item, written to a report file. For audits and pre-refactor recon.
allowed-tools: Read, Grep, Glob, Bash, Write
disable-model-invocation: true
---

# Deep Dive

Investigate the target (use $ARGUMENTS to scope, e.g. a single app like
`assessments`, `csat`, `home`, or `standards`; if empty, dive the whole
codebase). Read actual code — never generalise from names or assumptions. Do
NOT modify any application code, migrations, templates, or data. The only file
you may write is the report.

## Ground rules for this codebase
- Treat `CLAUDE.md` as the arbiter of intended design — flag deviations from it,
  but don't "fix" deliberate decisions documented there (feature flags, the
  archive-not-delete rule, the dormant Executive Summaries feature, PDF-via-print,
  the deferred flag-off cleanup).
- `docs/csat_data.json` is the single source of truth for CSAT content. Never
  propose hand-editing content in the DB or migrations.
- Statement identity is positional `(sub_standard, tier, order)` — flag anything
  that reorders within a tier as a data-integrity risk, not a cosmetic change.
- This is pupil/school QA data for a live trust. Weight anything touching auth,
  multi-tenant isolation, or PII heavily.

## Process
1. Map the architecture: entry points, request/data flow, where complexity and
   risk concentrate. Read the key files (`views.py`, `services.py`,
   `permissions.py`, `models.py`, middleware), not just skim structure.
2. Check the safety net: read `tests.py` for the app(s) in scope and note what
   they actually cover. Flag high-risk paths (permissions, tier derivation,
   snapshot immutability, autosave endpoints) that are untested or dangerous to
   change. Where useful, run `python manage.py test <app>` to confirm the current
   state — but change nothing.
3. Audit for: dead code, duplication, oversized views/functions, inconsistent
   patterns, and violations of the conventions in CLAUDE.md.
4. Security & data: check auth, the central checks in
   `assessments/permissions.py`, session-school/School-FK isolation, PII in logs
   (including `AuditLog`), and where sensitive fields flow.

## Output — write to DEEP_DIVE.md
- A short architecture map and where risk concentrates.
- Top 8–10 concrete problems, RANKED by impact-to-effort. Each must cite the
  specific file and function (use `path:line` form), and give a one-line
  definition of done.
- Group items into batches that can each be done and tested independently.
- A section for things you're UNCERTAIN about or that need my decision — do not
  paper over these.

Be critical and honest, including problems I've probably rationalised. Ground
every claim in a file you actually read. Produce a plan, not code.
