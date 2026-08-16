---
name: audit-apps
description: Multi-agent, read-only audit that fans out to the review agents (Les, Victor, Tess, Stella) per Django app and writes a ranked impact-vs-effort improvement plan for each app to its own report file.
allowed-tools: Read, Grep, Glob, Bash, Write, Agent
disable-model-invocation: true
---

# Audit Apps

Produce a ranked, impact-vs-effort improvement plan **for each app separately**,
grounded in the review agents' findings plus your own read of the code. This is
recon and planning only — do NOT modify any application code, migrations,
templates, or data. The only files you may write are the per-app report files.

## Scope
Use $ARGUMENTS to choose which apps to audit. If empty, audit all four in order:
`home`, `csat`, `assessments`, `standards`. Do them one app at a time.

## Ground rules for this codebase
- `CLAUDE.md` is the arbiter of intended design. Flag deviations from it, but do
  not treat deliberate, documented decisions as defects — the feature flags,
  archive-not-delete, positional statement identity `(sub_standard, tier, order)`,
  the dormant Executive Summaries feature, PDF-via-print, and the deliberately
  deferred flag-off cleanup are all intentional.
- `docs/csat_data.json` is the single source of truth for CSAT content. Never
  propose hand-editing content in the DB or migrations.
- This is live pupil/school QA data for a real trust. Weight anything touching
  auth, session-school ↔ School-FK isolation, permissions, or PII heavily.

## Process — repeat for each app in scope
1. **Fan out to the review agents in parallel.** In one message, spawn:
   - **Les** — complexity, duplication, oversized views/functions, messy patterns.
   - **Victor** — security, privacy/GDPR, role-based access, PII in logs/AuditLog,
     deployment safety.
   - **Tess** — test-coverage gaps: which permission/ownership/access paths and
     high-risk logic (tier derivation, snapshot immutability, autosave) are untested.
   - **Stella** — UI/UX of templates and CSS. **Only spawn Stella for apps that
     have templates: `home`, `assessments`, `standards`. Skip her for `csat`.**

   Scope each agent tightly to the one app under audit. Tell them it is read-only
   recon feeding a plan — they must not edit anything.

2. **Do your own read** of the app's `views.py`, `services.py`, `permissions.py`,
   `models.py`, middleware and `tests.py` so you can verify and rank the agents'
   findings rather than just collating them. Ground every item in a file you read.

3. **Synthesise** the agents' findings and your own into one ranked plan. Dedupe
   overlaps (Les and Victor will both flag some things), and drop anything that
   contradicts a documented decision in CLAUDE.md.

## Output — one file per app under docs/audits/
Write `docs/audits/DEEP_DIVE_<app>.md` for each app, containing:
- A one-paragraph architecture/risk map for that app.
- Top 8–10 concrete problems, RANKED by impact-to-effort. Each cites the specific
  file and function (`path:line`), names which agent(s) raised it, and gives a
  one-line definition of done.
- Batches: group items that can each be done and tested independently.
- An **Open questions / needs-decision** section — things that need my call. Do
  not paper over these; I may be away when this runs, so capture them for review.

After all apps are done, print a short summary to me: one line per app with its
report path and its single highest-priority item. Remember the agents' own
reports aren't shown to me — surface what matters in that summary.
