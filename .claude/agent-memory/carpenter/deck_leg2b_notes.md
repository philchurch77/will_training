---
name: deck-leg2b-notes
description: Leg 2b review (2026-10-04) - where badge/goal-week logic lives and what was flagged
metadata:
  type: project
---

Logic home: deck_rules.py bottom half (Row, session_dates, goal_mondays, run_before, longest_run, deck_badge_values, award_deck_badges); deck_views.api_plays awards after the save loop; deck.js weekStatus mirrors session_dates (commented "change both"). Server state on phone = localStorage will-deck-server-v1 (earned union-only, unseen, goal_weeks).

Verified by reading, correct: session rule identical JS/Python (JS caps at today, Python does not - negligible); goal_weeks before/monday handshake; longest_run for "in a row" badges; current week never breaks run; closer arithmetic (score 0 / weak None excluded); test_weeks keyed by Monday, False before anchor; award savepoint race safe; free play counted once as a card.

Flagged: awarding only when inserted>0 means a badge is skipped if the award step 500s or the response is lost (retry inserts 0); old cached page with no deck-badges element drains unseen silently; clear_trial_plays deletes retired (Legend) deck badges too and award skips inactive; closer counts every qualifying play, not first per test week (fine while threshold 1).
