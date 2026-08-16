---
name: cover
description: Spawn Tess to write the missing tests for a given path or app — permissions, tier derivation, snapshot immutability, autosave — then verify every new test has teeth.
disable-model-invocation: true
---

# Cover

Close test-coverage gaps in the scope given by $ARGUMENTS (an app like
`assessments`, or a specific area like "snapshot immutability" or
"csat dashboard permissions"). If empty, ask me what to cover rather than
guessing.

## Process

1. **Spawn Tess** on the scope. Ask her to identify the untested paths, in
   priority order, weighting heaviest: permission/ownership/access checks
   (school leader confinement, Governor read-only, Reviewer moderate-only),
   tier derivation, snapshot immutability, and the autosave endpoints. She
   should return the list with the specific view/function each test must
   exercise.

2. **Write the tests** in the app's `tests.py`, following the existing test
   style. For every access-control test, cover the four states: logged out,
   wrong school, wrong role, correct role. Test views and querysets, not
   templates.

3. **Prove teeth.** A test that cannot fail is worse than no test. For each
   new test, verify it fails when the behaviour it guards is broken — either
   by temporarily breaking the code (scratchpad backup first, never
   `git checkout` over unstaged work) or by reasoning shown explicitly for
   cases where breaking is impractical. Mark each test verified/unverified in
   the report.

4. **Run** `python manage.py test <app>` and then the full suite.

## Rules

- Do not change application code to make a test pass. If a test exposes a
  real bug, leave the test failing, and report the bug — that's a `/fix` job
  and possibly a `/gauntlet` matter, not something to quietly patch here.
- Do not commit unless asked.

## Report

Tests added (grouped by risk area), each marked teeth-verified or not; any
real bugs exposed; final suite status with real numbers.
