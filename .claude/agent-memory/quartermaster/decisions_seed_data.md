---
name: decisions-seed-data
description: Design decisions taken for the drill library and weekly plan in will_training - retirement over rewrite, combination warm-ups, warm-up slot structure
metadata:
  type: project
---

Decisions taken when planning the ball-mastery combination-warm-up change
(`training/management/commands/seed_drills.py`, `training/tests/test_seed.py`).

**A drill leaving the plan is retired, never rewritten and never deleted.**
Its tuple stays in `DRILLS` and its slug goes in a `RETIRED` set, which the
seeder turns into `is_active=False`.
**Why:** `SessionLog.drill` is `on_delete=CASCADE`, so deleting takes his
history with it; rewriting a slug in place silently changes what his past
`SessionLog` rows *mean*. Keeping the tuple means `--reset` and a plain
re-seed produce the same rows, and the retired drill's detail page still
renders (`views.py` drill detail does not filter `is_active`).
**How to apply:** any future drill swap uses the same mechanism. Never drop a
tuple out of `DRILLS`.

**The warm-up slot (slot 1) is the only slot this change touched.**
Structural fact worth keeping: each week's six warm-ups were six distinct
non-fun ball-mastery drills, so warm-ups can be swapped 1-for-1 with no
knock-on to the 30-minute sum, weak-foot cover, speed spacing or the
fun finisher. Two sessions depend on the warm-up for their *only* weak-foot
drill: weekday 1 week A and weekday 4 week B.
**Why:** it keeps a coaching change to twelve lines of `PLAN_DAYS`.
**How to apply:** before touching a warm-up, re-check those two sessions.

**Which tests filter `is_active` and which do not** (the thing that decides
whether a drill can be retired): `test_the_fortnight_uses_the_whole_library`
uses `Drill.objects.active()` - retired drills are exempt.
`test_the_named_staples_are_all_present`, the 36-55 count bound and
`test_difficulty_spans_the_range` count every row, active or not.

**Rejected:** deactivating by blanket `exclude(slug__in=seeded_slugs)`.
Phil can create drills by hand on the coach screens, and a blanket update
would silently switch those off on the next deploy.

See [[seeder-runs-on-render]].
