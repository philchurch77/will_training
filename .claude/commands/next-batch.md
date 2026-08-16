---
name: next-batch
description: Pick the next unstarted batch from the DEEP_DIVE audit reports, implement it with tests, teeth-check each fix, and update the report's status so the audits stay the source of truth.
disable-model-invocation: true
---

# Next Batch

Consume the plans that `/audit-apps` and `/deep-dive` produce: implement the
next batch of improvements from `docs/audits/DEEP_DIVE_<app>.md` (finished
reports live in `docs/audits/closed/` and have nothing left to pick up).

## Selecting the batch

Use $ARGUMENTS to pick an app and/or batch (e.g. `assessments`, or
`assessments batch 2`). If empty: read all `docs/audits/**/DEEP_DIVE_*.md`
status tables and propose the highest-impact unstarted batch that is
**decision-free** — never auto-select items sitting in an "Open questions /
needs-decision" section. Present the chosen batch (items, files, definitions
of done) and wait for my confirmation before changing anything.

## Implementing

For each item in the batch:

1. Re-read the cited code first — the audit may be stale. If the finding no
   longer holds, mark it as such in the report rather than "fixing" it.
2. Respect the documented decisions in `CLAUDE.md` (feature flags,
   archive-not-delete, positional statement identity, PDF-via-print, the
   deferred flag-off cleanup). If an item turns out to conflict with one,
   stop and flag it instead of proceeding.
3. Implement against the item's definition of done. Add or extend tests that
   prove it; teeth-check fixes (revert, confirm failure, restore).
4. Run `python manage.py test <app>` after each item; run the full suite at
   the end of the batch.

## Bookkeeping

- Update the status table in the relevant `DEEP_DIVE_<app>.md`: done items
  marked done with a one-line note of what proved them; stale items marked
  stale. The audit reports are the source of truth — keep them true.
- If anything in `CLAUDE.md` is now out of date because of this batch, update
  it too.
- Do not commit unless asked.

## Report

One line per item: done / stale / blocked (with the decision needed), plus
final full-suite status. If any item touched permissions, snapshots, or the
dashboards, remind me to run `/gauntlet` before shipping.
