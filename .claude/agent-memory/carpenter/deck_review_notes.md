---
name: deck-review-notes
description: Deck review notes - leg 1 (2026-10-03) and leg 2a stamps (2026-10-03): where logic lives, what is deliberate, what was flagged
metadata:
  type: project
---

Deck = training/static/training/js/deck.js (ES5 IIFE, ~1250 lines after 2a), training/deck_views.py (deck, api_plays), training/deck_rules.py (every number, baked as json_script "deck-rules"), Play/Card models, sw.js /api/ bypass, clear_trial_plays command.

Deliberate, do not re-raise: never-shrink savePlays, hash routing, plays marked synced and never removed by server answers, timed bar with no text, MAX_BATCH 500 duplicated in JS and Python (commented). Leg 2a: stamp once on the phone, never re-judged; null stamp = worth nothing; server ceilings loose on purpose; SESSION_CARDS=3 JS fallback; skill card always in hand at highest open level (Deal again cannot change the Moves card).

Flagged leg 1: sync() not re-run for a play saved mid-flight; savePlays ignores setItem failure; play shape in three places; weakWins duplicates beats(); clear_trial_plays has no guard/test and phone keeps its local plays (restore resends them).

Flagged leg 2a: week_index negative before BLOCKS_START (5 Oct 2026) gives a skill of the week and test week before the agreed start, and stamps double points that never come back; a first score of 0 then any positive earns the +20 best; JS hardcodes gold = 3 and three levels; bestMedal/isOpen loops are O(cards x plays) but fine for years (leave). Verified by reading: points formula, medalFor/worseFoot, levelFor thresholds, thisMonday vs monday_of (TIME_ZONE Europe/London, calendar baked from today-1 week) all correct.

No shell tool for this agent: reviews are read-only, nothing run.
