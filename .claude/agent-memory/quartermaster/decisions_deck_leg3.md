---
name: decisions-deck-leg3
description: Leg 3 of docs/chart/deck.md (switch-over) as planned 2026-10-04 - cut into 3a-3d, head start computed live from SessionLog, honest drill->card map, why "/" must render not redirect
metadata:
  type: project
---

Planned 2026-10-04 on `deck-step-3`. Recommendations put to the developer;
check the chart for what was accepted.

**Cut:** 3a head start (history -> starting points + starting bests, no
migration, invisible to Will) / 3b badges in one place (kept badges count ticks
+ plays, #badges shows all; deploy only AFTER clear_trial_plays has run) / 3c
switch over ("/" renders deck, tab bar, RETIRED_BADGES, SW CACHE bump, delete
clear_trial_plays, BLOCKS_START to switch Monday) / 3d retire fixed plan code,
CLAUDE.md rules, test_seed plan assertions, tick endpoints after a grace period.

**Head start computed live, nothing written** (`history_for(athlete)` in
deck_rules, baked into rules_json). Why: idempotent by construction, picks up
Today ticks until the switch, no Purser-grade conversion. Recommended 5 pts per
completed SessionLog, cap 1000. Rule may only go UP after hand-over (levels).

**Honest map (facts read from seed_drills/deck_data):** only rep drills carry
actual_reps: juggling-laces, thigh-juggles, weak-foot-juggles, juggle-and-catch,
alternate-foot-juggles, low-juggles, target-passing, corner-placement.
keepy-up-record is MINUTES (no counts). Clean maps: thigh-juggles ->
keepy-ups-thighs, weak-foot-juggles -> keepy-ups-weak, alternate-foot-juggles ->
keepy-ups-alternate. No move/combo drill ever had a score, so there is NO past
gold to stamp: the chart fog item "stamp medals" resolves to nothing to carry.

**Cutover gotchas:** "/" must RENDER the deck (start_url; SW keep() refuses
redirected responses, so a redirect at "/" = no offline launch). Keep
drill_complete/session_time accepting through 3c so a tick queued by an old
cached Today still lands. deck.js seeds bests in `bestsFor` (lines ~220; used
for stamp at ~849 and display at ~932) - the one place.

See [[decisions-deck-leg2b]], [[seeder-runs-on-render]].
