---
name: handoff
description: Write a concise handoff document capturing the current state of work — what changed, test status, uncommitted work, open decisions, and what's next — so a future session or teammate can pick up cleanly. Grounded in live git/test state, not memory.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit
disable-model-invocation: true
---

# Handoff

Produce a handoff for whoever picks this work up next — a future session with no
memory of this one, or a teammate. Write it to `docs/HANDOFF.md` (overwrite;
it is a living snapshot, not an append log). Keep it scannable: someone should
be able to resume in five minutes.

**Ground every claim in the live state below and in files you read — never in
recollection. If you cannot verify something, say so rather than guessing.**

## Live state

Current branch and status:
!`git status --short --branch`

Recent commits:
!`git log --oneline -8`

Diff size (uncommitted):
!`git diff --stat | tail -1; git diff --cached --stat | tail -1`

Test status — run the suite and record the real number, do not assume:
!`python manage.py test 2>&1 | grep -E "^(OK|FAILED|Ran)" | head -3`

## What to write

Structure `docs/HANDOFF.md` as:

1. **One-line status** — e.g. "Mid audit-implementation; N tests green; ~M
   uncommitted changes across K files; nothing committed."

2. **⚠️ Uncommitted work** — if the tree is dirty, say so up front and list the
   changed files grouped by theme (security / correctness / docs / tests).
   A large uncommitted diff is the single most important thing a successor needs
   to know. If work is staged but not committed, distinguish that.

3. **What was done this session** — the concrete changes, each with the file it
   touched and whether it was verified (tests run + teeth-checked, i.e. proven
   to fail without the fix). **Explicitly flag anything written but *unverified*
   — that is the highest-risk state to hand off.**

4. **Where the source of truth lives** — point at the status tables in
   `docs/audits/**/DEEP_DIVE_*.md` (or the relevant tracking docs) rather than
   restating them. Note which are current — anything under
   `docs/audits/closed/` is finished and is background, not work in flight.

5. **Open decisions** — anything blocked on a human call, with the trade-off in
   one line each and a recommendation. Do not paper over these.

6. **What's next** — the 2–4 highest-value next steps, ordered, noting which are
   decision-free and which need input. Distinguish "risky, verify carefully"
   from "safe addition".

7. **Project norms to carry forward** — the working discipline a successor must
   keep: run `python manage.py test` after changes; teeth-check every fix
   (revert it, confirm the test fails, restore); keep `CLAUDE.md` and the audit
   reports in step with the code, since `CLAUDE.md` is the arbiter of intended
   design; don't commit unless asked. Mention any repo-specific gotchas hit this
   session (e.g. the Bash safety classifier outage, `git checkout` wiping
   unstaged work — prefer scratchpad backups for teeth-checks).

## Rules

- **Accuracy over completeness.** A short handoff that is entirely true beats a
  thorough one with a wrong test count or an overstated "done".
- **No credit-claiming for work you did not verify**, and no marking something
  done that a test didn't prove.
- Do not commit, push, or change any application code — this command only writes
  `docs/HANDOFF.md`.
- After writing, print the one-line status and the path to the file.
