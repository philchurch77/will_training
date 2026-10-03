---
name: deck-review-notes
description: Deck leg 1 review (2026-10-03) - where deck logic lives, what was flagged, what is deliberate
metadata:
  type: project
---

Deck = training/static/training/js/deck.js (ES5 IIFE, ~880 lines), training/deck_views.py (deck, api_plays), Play/Card models, sw.js /api/ bypass, clear_trial_plays command.

Deliberate, do not re-raise: never-shrink savePlays, hash routing, plays marked synced and never removed by server answers, timed bar with no text, MAX_BATCH 500 duplicated in JS and Python (commented).

Flagged 2026-10-03 (see report): sync() does not re-run for a play saved while a post is in flight; savePlays ignores setItem failure; play object shape written in three places (savePlay, wire, restore); weakWins duplicates beats(); clear_trial_plays has no DEBUG-style guard and no test; its docstring says phone resends plays but synced plays are not resent (stale local bests stay).

No shell tool for this agent: review is read-only, nothing run.
