---
name: retirement-mechanism
description: How drill retirement works in will_training, why it cannot lose a SessionLog, and which checks are already automated
metadata:
  type: project
---

Retiring a drill is **one line**: `"is_active": slug not in RETIRED` in the
single `Drill.objects.update_or_create()` in `_seed_drills`. No delete, no
second code path, no per-drill special case. There is nothing to audit per
retiree beyond "is the tuple still in DRILLS and is the slug spelled right".

**Already guarded by tests — do not re-derive these by hand:**

- `TestRetirement.test_retired_drills_still_exist_and_are_inactive` — every
  RETIRED slug still resolves to a Drill row.
- `test_re_seeding_keeps_the_history_logged_against_a_retired_drill` and
  `test_re_seeding_twice_still_keeps_it` — a SessionLog against a retired
  drill survives one re-seed and two.
- `TestSlugSets.test_every_retired_slug_names_a_real_drill` — a typo in
  RETIRED would silently retire nothing; this fails instead.
- `TestResetIsRefused` — the `--reset` DEBUG guard, plus
  `test_a_refused_reset_deletes_no_history`.

So the real audit question for a retirement batch is only:
**did any pre-existing tuple's text change?** The cheap way to answer it is to
`ast.literal_eval` the DRILLS/COMBINATIONS/RETIRED/PLAN_DAYS assignments out
of `git show HEAD:...seed_drills.py` and out of the working tree and diff them
per slug. That reads the data rather than the diff hunks, so a moved tuple or
a reflowed string cannot hide in it.

**Every drill retired so far is minutes-based (`target_reps` None).** That is
why `best_scores()` filtering `Drill.objects.active()` has never cost him a
record: `personal_best()` returns None for a timed drill anyway. The first
*rep* drill retired will silently drop its row off the Progress record board.
That is still the one thing to check per batch.

**Field sizing on the drill tuples is comfortable**, checked over all 66 rows:
longest slug 25, name 28, cue 35, all against `max_length=60`; `instructions`
is a `TextField` and the longest is ~302 chars. No non-ASCII, no CR, no tabs
in the seeded text.

See [[free-text-fields]] and [[plan-has-no-history]].
