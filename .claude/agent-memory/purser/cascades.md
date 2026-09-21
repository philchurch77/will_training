---
name: cascades
description: Every on_delete in will_training/training/models.py, what deleting the parent would destroy, and which cascades are accepted
metadata:
  type: project
---

`grep -n "on_delete" training/models.py`. All CASCADE, no exceptions.

**The two that can destroy his history:**

- `Drill.skill -> Skill` CASCADE, and `SessionLog.drill -> Drill` CASCADE.
  Chained: deleting one Skill deletes every Drill under it, which deletes every
  `SessionLog` logged against them. Django admin is mounted at `/admin/` with a
  plain `SkillAdmin` and `DrillAdmin`, so the "Delete selected" bulk action is
  one screen away.
- `SessionLog.athlete -> User` CASCADE. Deleting Will's user deletes his whole
  history.

**Accepted / benign:**

- `PlanDrill.plan_day`, `PlanDrill.drill`, `PlanDay.plan` — PlanDrill and
  PlanDay hold no history; the seeder rebuilds them every run by design.
- `EarnedBadge.badge -> Badge` CASCADE — deleting a Badge row revokes his
  earned badges. Low risk (badges are seeded, never deleted) but real.
- `SessionClock.athlete` CASCADE.

**Not yet accepted with a stated rule by the developer.** If he states one,
record it here rather than re-raising it every passage.

**Hard deletes in views** (`grep "\.delete()" training/ --include=*.py`):
`views.py` `drill_uncomplete` hard-deletes today's `SessionLog` including any
`actual_reps` on it, with no confirm. That is deliberate per CLAUDE.md
(unticking lives on the drill page so it cannot happen in his pocket), but the
count is unrecoverable. `coach_plan_day` action=remove deletes a PlanDrill —
no history, fine.

See [[deploy-data-safety]].

**Authoritative reverse-relation map** (from Django's own
`model._meta.related_objects`, run 2026-09-21 - beats grepping for FKs):

    Skill        -> Drill.skill [CASCADE]
    Drill        -> PlanDrill.drill [CASCADE], SessionLog.drill [CASCADE]
    TrainingPlan -> PlanDay.plan [CASCADE]
    PlanDay      -> PlanDrill.plan_day [CASCADE]
    PlanDrill    -> NOTHING
    SessionLog   -> NOTHING
    SessionClock -> NOTHING
    Badge        -> EarnedBadge.badge [CASCADE]
    EarnedBadge  -> NOTHING

**PlanDrill has no dependents.** So `_seed_plan`'s `day.items.all().delete()`
is a leaf delete and can never reach a SessionLog, however many plan slots a
change rewrites. Settled - do not re-raise it every time PLAN_DAYS moves.

**Admin delete permissions, re-checked 2026-09-21.** `NoDeleteMixin` is on
`SkillAdmin` and `DrillAdmin` only. `SessionLogAdmin` (admin.py:73) and
`BadgeAdmin` (admin.py:80) both still allow delete: the first is his whole
history behind a bulk action, the second revokes every EarnedBadge by CASCADE.
Both pre-date any current work. Raised repeatedly; if the developer states a
decision, record it here and stop re-raising.
