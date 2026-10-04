---
name: deck-leg3a-notes
description: Leg 3a head start review (2026-10-04) - where it lives, what was verified, what was flagged
metadata:
  type: project
---

Logic home: deck_rules.py (STARTING_*, HISTORY_CARDS, starting_points, starting_bests, history_for, rules_json history arg); deck_views.deck passes history_for(request.user); deck.js bestsFor seeds from RULES.starting_bests, totalPoints starts from RULES.starting_points. 2b goal weeks/badges read Play rows only, never SessionLog - history not leaking in.

Verified by reading: the three mapped cards take Card defaults (COUNT, per_foot False) so {"score": n, "weak": None} is right; old drills are rep drills (minutes None); seeded start is real so verdict gives "New best!" not "First score", stamp bonus only on beating it; bestLine shows "Your best"; medalFor untouched; page is network-first in sw.js so a cached /deck/ only shows up offline.

Flagged: no tests for history_for/starting_points/starting_bests (only the rules-keys test); drill_uncomplete can lower points by 5 (contradicts "never down" comment, same day only); coach_log_edit can put reps on any log but filter only reads the three slugs, so harmless; head start is frozen at page load within an SPA session.
