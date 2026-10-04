---
name: deck-leg4-notes
description: Leg 4 (His cards on /coach/) review 2026-10-04 - where coach logic lives, what agrees with deck.js, what was flagged
metadata:
  type: project
---

Layout: deck_rules.py end of DB section = player_level, coach_summary (4 queries), card_bests (1 query, values+annotate, explicit order_by to dodge Play Meta ordering in GROUP BY). views.coach_cards (/coach/), coach_logs moved to /coach/before/. templatetags/deck_format.py = score, medal filters (MEDAL_WORDS from Play.MEDAL_CHOICES, so only deck.js is a second copy). Partials coach/_switch.html, _signout.html.

Verified by reading (not run): card_bests agrees with deck.js bestsFor/counts/beats on count-0 best, ties with from-before (best <= start), per-foot (history cards never per foot), time Min above 0, unstamped plays (null medal/points ignored like phone); levelFor vs player_level agree; query count fixed.

Flagged: no tests yet for card_bests/coach_summary/player_level/filters (only URL tests); "Level" overloaded in CONTEXT (move level vs player level, glossary has no player-level entry); UI "from before" vs glossary "Head start"; refusal log writes phone-supplied id string (<=64 chars, unvalidated) so newlines can forge log lines; cards.html repeats the Weak/Strong score block twice and hardcodes scoring == "none"; views.py import order (timezone before shortcuts).
