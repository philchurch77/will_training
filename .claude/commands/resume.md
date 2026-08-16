---
name: resume
description: Re-orient a fresh session from docs/HANDOFF.md (if present), the audit reports, and live git/test state, then propose the next step. Read-only counterpart to /handoff.
allowed-tools: Read, Grep, Glob, Bash
disable-model-invocation: true
---

# Resume

Re-orient yourself in this project as if you have no memory of previous
sessions (you don't). Read, verify, then propose — change nothing.

## Live state

Current branch and status:
!`git status --short --branch`

Recent commits:
!`git log --oneline -8`

Uncommitted diff size:
!`git diff --stat | tail -1; git diff --cached --stat | tail -1`

Test status:
!`python manage.py test 2>&1 | grep -E "^(OK|FAILED|Ran)" | head -3`

## Process

1. Read `docs/HANDOFF.md` **if it exists** — it is written by `/handoff` and
   may legitimately be absent. Treat it as the previous session's claims, not
   as truth: cross-check its one-line status against the live state above. If
   they disagree (test count, dirty files, "done" items), flag the discrepancy
   explicitly; the live state wins. If there is no handoff, say so and lean
   entirely on the audit reports and the live state below.
2. Read the status tables in `docs/audits/**/DEEP_DIVE_*.md` (or whichever
   tracking docs a handoff points at) to see what's in flight. Reports under
   `docs/audits/closed/` are finished — read them for background, not for work.
3. Skim `CLAUDE.md` for any norms relevant to the work in flight.

## Output

Report back, briefly:

- **State**: one line — branch, test status, size of uncommitted work, and
  whether it matches what `docs/HANDOFF.md` claims (or that there is no
  handoff to compare against).
- **In flight**: what was mid-stream, and which of it is written but
  unverified (highest risk — do not build on it until verified).
- **Open decisions**: anything the handoff or the open audit items say is
  blocked on my call.
- **Proposed next step**: the single highest-value action, and whether it is
  decision-free. Wait for my confirmation before doing anything.

Do not modify any files. Use $ARGUMENTS, if given, to focus on a specific
app or task.
