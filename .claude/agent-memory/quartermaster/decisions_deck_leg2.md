---
name: decisions-deck-leg2
description: Leg 2 of docs/chart/deck.md (game layer) as planned 2026-10-03 - where each rule is computed, per-play stamps, the split into 2a/2b, recommended answers put to the developer
metadata:
  type: project
---

Planned 2026-10-03, on branch `deck-step-2`. Recommendations; check the chart
for what the developer actually accepted before building on them.

**The fork, as recommended:** no JS runner exists (TestDeckScript reads source),
so a rule implemented twice cannot be proved to agree. Therefore:
- Per-play facts are computed ONCE, on the phone, at save time, and stamped on
  the play: `Play.points`, `Play.medal` (0 none..3 gold), `Play.bests` (0..2).
  Null = unstamped (leg-1 / old cached JS), counts as nothing. Server
  validates ranges only, never re-judges. Points/medals/unlocks are then sums
  and maxes of stored facts; changing a rule or a medal target never takes
  anything back.
- Constants (points, level thresholds, session size, goal, test-card slugs,
  skill-of-week calendar for ~60 weeks) live in Python (`training/deck_rules.py`
  proposed) and are baked into /deck/ as a json_script. Phone holds no copies.
- Badges stay server-side: awarded in `api_plays` POST from Play rows; earned
  list and weeks-in-a-row cached on the phone, so they lag offline.
- The one duplicated algorithm: "deck session = 3 distinct cards on one date,
  free play counts as one". Python for badges, JS for the weekly bar; guarded
  by a source test that deck.js reads the baked constants.

**Gotchas found:** `makePlay` whitelists fields, so new stamps vanish through
`wire()`/`restore()` unless added there. Old `award_badges` gives a deck kind
value 0 so it never awards one, but `badge_progress` would show deck badges on
the old Progress page at 0% - filter by a DECK_KINDS set. Trial plays would
earn deck EarnedBadges that outlive `clear_trial_plays` - extend it.
AddField nullable no-default on SQLite is ADD COLUMN (no rebuild);
`Badge.is_active` default True remakes training_badge.

**Split:** 2a = points, levels, medals, unlocks, album, skill of the week
(migration on Play). 2b = weekly goal, weeks in a row, test week, new badges,
Legend tag (migration on Badge), clear_trial_plays extension.

**Recommended answers put to the developer:** base 10, weak-foot +5 on any
per-foot/weak-only card, +20 per foot best, x2 skill of week, free play 10;
first score is not a best; levels 0/300/1000/2500/5000, never raise a
threshold; medal = worse foot of that play; anchor Monday 2026-10-05,
movable to switch-over Monday before his first play; test week = 4th week of
each block; Moves slot in the hand = skill of the week at highest open level;
locked shown not playable; test six = toe-taps-30, foundations-30,
rebounder-two-touch, slalom-race, corners, keepy-ups-best; weak foot closer =
rebounder-two-touch, weak >= 80% strong, strong > 0; Season = 30 goal weeks in
total; old-badge retirement deferred to leg 3 (RETIRED_BADGES empty in leg 2).

See [[decisions-deck]].
