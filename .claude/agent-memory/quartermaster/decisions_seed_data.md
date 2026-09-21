---
name: decisions-seed-data
description: Design decisions taken for the drill library and weekly plan in will_training - retirement over rewrite, combination warm-ups, warm-up slot structure, move-naming rulings, plan slot arithmetic
metadata:
  type: project
---

Decisions taken when planning the drill library and weekly plan
(`training/management/commands/seed_drills.py`, `training/tests/test_seed.py`).

**A drill leaving the plan is retired, never rewritten and never deleted.**
Its tuple stays in `DRILLS` and its slug goes in `RETIRED`, which the seeder
turns into `is_active=False`.
**Why:** `SessionLog.drill` is `on_delete=CASCADE`, so deleting takes his
history with it; rewriting a slug in place silently changes what his past
`SessionLog` rows *mean*. Keeping the tuple means `--reset` and a plain
re-seed produce the same rows, and the retired drill's detail page still
renders (`views.drill_detail` does not filter `is_active`).
**How to apply:** any future drill swap uses the same mechanism. Never drop a
tuple out of `DRILLS`. Changing `difficulty` on a live drill is *not* a
rewrite - it is a label on the current drill, not a claim about what he did.

**Active ⟺ in the plan.** `test_the_fortnight_uses_the_whole_library` asserts
every `Drill.objects.active()` row has a fortnight slot, so a drill cannot be
kept active and parked. "Take it out of the plan" and "retire it" are the same
act.
**How to apply:** any proposal to drop a drill from a slot must name its
replacement slot or accept retirement.

**The row-count bound is a ratchet.** `test_creates_between_36_and_65_drills`
and `test_reset_rebuilds_cleanly` count *rows*, and rows only ever grow because
retirement never deletes. The upper bound will be hit by design.
**How to apply:** raise it generously when it binds; it guards nothing that the
active count does not guard better.

**Plan slot arithmetic (the numbers any seed change must land on).**
12 sessions x 6 slots = 72. Each week must be 36 *distinct* drills. So
`active drills = 72 - (drills appearing in both weeks)`. Adding N active drills
means converting N doubled appearances to single ones, or freeing N slots.

**Five sessions run on exactly one weak-foot drill** and are the fragile ones
to re-check before any swap: weekday1 weekA (`rollover-chop`), weekday2 weekB
(`weak-foot-finish`), weekday3 weekB (`inside-outside-cuts`), weekday4 weekA
(`inside-outside-cuts`), weekday4 weekB (`weak-foot-combo`). Two of those are
warm-ups, so those two warm-up slots must stay `weak_foot=True`.
(The older note naming "day 3 week A" was wrong; this list is computed.)

**Move-naming rulings (2026-09), to stop him meeting one word for two moves.**
- *Chop* stays one move only: cut back with the **inside of the foot, in front
  of you**. The "Ronaldo chop" (inside of the foot, **behind the standing
  leg**) is not given the word chop - that action already exists in the library
  as the **Cruyff turn** and keeps that name.
- *Scissors* and *step over* are two moves, not synonyms. `step-over` is
  canonical: step over with one foot, push away with the **outside of the
  other**. A scissor circles one foot round the front of the ball and pushes
  away with the **outside of the same foot**. A standalone `scissors` Dribbling
  drill owns the canonical wording.
- A new move needs its own standalone Dribbling drill only if it appears in
  more than one drill, or is worth five minutes on its own. Otherwise describe
  it in place - `test_every_drill_has_readable_instructions` caps a drill at
  four sentences, which is the real limit on how many moves one drill can name.
- Latent wart, deliberately left: slug `sole-roll-scissor` is named "Sole roll
  into a step over". The slug is invisible to Will and renaming it would orphan
  history.

**Which tests filter `is_active` and which do not:**
`test_the_fortnight_uses_the_whole_library` uses `Drill.objects.active()`.
`test_the_named_staples_are_all_present`, the row-count bound,
`test_difficulty_spans_the_range` and `test_there_is_a_proper_spread_of_juggling`
count every row - so retiring a drill cannot break them.
`progress.best_scores()` iterates `Drill.objects.active()`, so retiring a *rep*
drill removes a personal best from the Progress board. Retire minutes-based
drills freely; a rep drill is the developer's call.

**`difficulty` is a 3-point choice field** (`DIFFICULTY_CHOICES` 1/2/3) and
`test_difficulty_spans_the_range` asserts all three are present among rows.
"Make it harder" can never be expressed as a 4 without a model change and a
migration. Retired easy rows keep the 1 alive.

**Rejected:** deactivating by blanket `exclude(slug__in=seeded_slugs)`.
Phil can create drills by hand on the coach screens, and a blanket update
would silently switch those off on the next deploy.

See [[seeder-runs-on-render]].
