---
name: fix
description: Disciplined bug-fix loop — reproduce with a failing test first, implement the minimal fix, then teeth-check it (revert, confirm the test fails, restore) before declaring done.
disable-model-invocation: true
---

# Fix

Fix the bug described in $ARGUMENTS using the failing-test-first discipline.
No fix counts as done until it has been teeth-checked.

## Process

1. **Understand.** Read the code path involved before theorising. State your
   hypothesis for the root cause in one or two lines, citing `path:line`.

2. **Reproduce with a failing test.** Write the smallest test that fails
   because of this bug, in the affected app's `tests.py`. Run it and confirm
   it fails for the *expected reason* (read the failure output — a test
   failing on a typo or import error proves nothing). If the bug cannot be
   captured in a test, say so explicitly and explain why before proceeding.

3. **Fix minimally.** Change only what the root cause requires. Do not
   refactor surrounding code, rename things, or fix unrelated issues you
   notice — list those at the end instead.

4. **Verify.** Run the failing test (now passing) and the full suite:
   `python manage.py test`. All green or it isn't done.

5. **Teeth-check.** Prove the test has teeth: stash or back up the fix to the
   scratchpad (do NOT use `git checkout` on files with other unstaged work —
   it wipes them), revert the fix, confirm the new test fails, restore the
   fix, confirm the suite is green again.

## Ground rules

- If the bug touches permissions, snapshots, tier derivation, or anything in
  `assessments/permissions.py`, note that `/gauntlet` should run before this
  ships.
- Do not commit unless asked.

## Report

- Root cause (one line, with `path:line`)
- The fix and the test that guards it
- Teeth-check result: test failed on revert — yes/no
- Full suite status (real numbers, not assumed)
- Anything unrelated you noticed but deliberately did not touch
