---
name: decisions-deck-leg2b
description: Leg 2b of docs/chart/deck.md (goals and badges) as planned 2026-10-04 - stamp trust for Gold medal/Record breaker, trial-play guard, goal_weeks wire shape, migration 0010, tests that will break
metadata:
  type: project
---

Planned 2026-10-04 on `deck-step-2b`. Recommendations; check the chart for what
the developer accepted before building on them.

**Gold medal / Record breaker: trust the stamps, tighten the cross-checks.**
Server recompute rejected: targets change in place (no history), bests depend on
the set of plays the phone held at save time and on phone clocks, and it is the
second implementation in two languages that leg 2 ruled out. Decisive point: the
phone already opened move levels on the same gold stamp - a server that disagreed
would leave a level open with no Gold badge. Tighten `_parse_stamp` with
target-independent checks only (per_foot medal needs both feet; bests <= feet
scored; scoring none => medal 0, bests 0). Gold counts only cards with `move`.

**Trial plays guard:** extend `clear_trial_plays` to delete EVERY deck-kind
EarnedBadge and re-award from the plays left, same atomic block. My 2a plan said
"dated <= --through"; that misses a badge earned later that leaned on trial
plays. A DECK_START cut-off rejected: points/levels/unlocks on the phone would
still count the plays - two notions of his record.

**goal_weeks on the wire:** server sends {monday, before, total_before} (run
ending last week, goal weeks before this one); phone adds 1 if ITS OWN plays make
this week a goal week, only when `monday` matches its own. Keeps the run rule
server-only and the session rule the one duplicate.

**0010:** AlterField kind (choices only, no SQL on SQLite) + AddField
Badge.is_active default True (remakes training_badge; EarnedBadge FK by table
name survives under foreign_keys OFF). Kept is_active over a Python-only
RETIRED_BADGES lookup for consistency with Drill/Card.

**Will break:** `test_every_badge_kind_has_a_metric` (test_seed.py) iterates all
badges against `progress._badge_values`. BadgeAdmin/EarnedBadgeAdmin allow
delete and EarnedBadge.badge is CASCADE - planned NoDeleteMixin on both.

See [[decisions-deck-leg2]], [[decisions-deck]].
