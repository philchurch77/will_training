---
name: plan-has-no-history
description: Changing the seeded plan silently re-scores past perfect weeks in will_training, because progress.py reads the plan as it stands today
metadata:
  type: project
---

There is no plan history. `progress.perfect_weeks()` builds its required-drill
sets from `_required_drills_by_weekday()`, which reads the *current*
`PlanDrill` rows, and then subset-tests them against old `SessionLog` rows.

**Why it matters:** any change to `PLAN_DAYS` in `seed_drills.py` retroactively
re-scores every past week. Swap the drill in a slot and a week he genuinely
completed in full stops counting, because the new drill has a new `drill_id` he
never logged against.

**Accepted by the developer** — CLAUDE.md states it explicitly ("Both read the
plan as it stands today, not as it stood back then - there is no plan history
and rebuilding one is not worth it").

**Why it is not data loss:** `award_badges()` only ever creates `EarnedBadge`
rows, never deletes them, so an already-earned `perfect-week` badge survives.
Only the live count on the Progress screen moves. Same applies to the streak —
except the streak reads `completed_dates()` with no plan or `is_active` filter
at all, so the streak is immune to plan changes entirely.

**How to apply:** when a passage changes `PLAN_DAYS`, say plainly that the
displayed perfect-week count may drop and that the badge does not. Do not
escalate it to Critical; do not stay silent about it either.

Also immune to `is_active` (checked, all of these): `total_minutes` /
`_minutes_per_log`, `juggling_sessions`, `weak_foot_sessions`, `skills_tried`,
`completed_dates` / streaks, and `views.drill_detail` (no filter, so a retired
drill's page still renders and old links never 404).
Filtered by `is_active`: `session_for`, `library`, `best_scores`,
`_required_drills_by_weekday`, `_precache_urls`.

**Refinement (checked 2026-09-21): the earned badge is safer than it looks.**
`progress.html:93` renders `{% if row.earned %}earned_on{% else %}value/threshold{% endif %}`
- so for a badge he has already earned, the recomputed `perfect_weeks()` value
is never displayed at all. There is exactly one perfect-week badge and its
threshold is 1 (`seed_drills.py:975`), and `award_badges()` runs inside
`drill_complete`, so the final tick of a genuinely perfect week awards it the
same day. Net effect: a plan change can drive `perfect_weeks()` to 0 for all
of history and **nothing visible to Will changes**. Report it as Low, not
Medium, unless a perfect-weeks badge with threshold > 1 is ever added - then
the progress counter on the *unearned* one goes backwards where he can see it.
