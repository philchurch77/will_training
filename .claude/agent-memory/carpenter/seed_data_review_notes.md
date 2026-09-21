---
name: seed-data-review-notes
description: How to review seed_drills.py / CLAUDE.md / test_seed.py changes in will_training, and drift already raised once (2026-09-21 ball-mastery passage)
metadata:
  type: project
---

This project has no Bash/shell tool wired up for this agent (Carpenter) —
review of `seed_drills.py` changes is Read-only: read the diff, read
`seed_drills.py` and `test_seed.py` whole, cross-check comment claims against
counted tuples by hand. Cannot RAN anything; say so plainly in the report
(article 10).

**Where drift tends to appear in this file, worth checking every pass:**
- A hand-written prose comment claiming a numeric pattern across a block of
  tuples (e.g. "every one of these is difficulty N bar the two-move pairs")
  is not tested and drifts the moment one row in that block is regraded.
  Verify by counting, don't trust the comment.
- Stale total-drill-count numbers ("50 drills", "fifty tuples") linger in
  prose comments that a bulk-add doesn't touch, even when the same passage
  fixes the number two paragraphs away. Grep for old totals whenever the
  drill count changes.
- Move-naming rulings: the project keeps a strict rule that a move (chop,
  step over, scissor, Cruyff, croqueta...) is described identically wherever
  it recurs. When a new drill reuses a move already taught elsewhere, diff
  the wording — verb swaps like "spin away" vs "turn away" are the kind of
  drift that slips through, because it reads fine, it's just not identical.
- `TestSlugSets` (in `test_seed.py`) only catches typos — a slug in
  COMBINATIONS/RETIRED/JUGGLING that doesn't exist in DRILLS. It does not
  check RETIRED and COMBINATIONS are disjoint, and does not check
  COMBINATIONS matches the warm-up slugs actually used in PLAN_DAYS (a dead
  or stale entry in COMBINATIONS is invisible to every test). In practice
  other tests (test_every_warm_up_is_combination_work,
  test_a_retired_drill_is_not_in_any_session) cover most of the real risk by
  checking the plan as built, not the sets by name — so this is a real but
  minor gap, not a live bug, as of the 2026-09-21 pass.

**2026-09-21 ball-mastery combination-warm-ups passage — already flagged to
developer, do not re-raise unless it recurs or grows:**
- `seed_drills.py` comment "Every one of these is difficulty 3 bar the
  two-move pairs" (near the `rollover-chop` block) contradicts the data added
  in the same change — 6 of 6 new two-move-pair combos are difficulty 3, and
  `croqueta-chop` was regraded 2→3 in the same diff. Flagged High.
- `cruyff-turn` says "...and spin away"; `step-over-cruyff` and `feint-cruyff`
  both say "...and turn away" for the identical Cruyff finish. Flagged
  Medium.
- CLAUDE.md line ~275 ("breaks the fortnight-uses-all-50 rule") and
  seed_drills.py line ~784 ("thirteenth column on fifty tuples") are both
  stale — library is 66 rows now, was already 58 before this passage, never
  50. Pre-existing, not introduced by this passage, flagged Low.
- Already accepted and NOT to be re-raised: slug `sole-roll-scissor` is
  named "Sole roll into a step over" (slug says scissor, name says step
  over) — this is the quartermaster's documented "latent wart, deliberately
  left" (see quartermaster memory `decisions_seed_data.md`), renaming would
  orphan history.
- `croqueta-burst` reuses `croqueta-chop`'s jab description verbatim; new
  `scissor-outside-push` and standalone `scissors` describe the scissor
  identically (near-verbatim, only punctuation differs). Both checked clean,
  no finding.
- The difficulty regrade (croqueta-chop, sole-roll-scissor: 2→3) is not
  fragile against `test_difficulty_spans_the_range`'s {1,2,3} requirement —
  counted ~9 active difficulty-1 rows and ~25 difficulty-2 rows remaining
  even before counting retired rows (which still count towards the test).
