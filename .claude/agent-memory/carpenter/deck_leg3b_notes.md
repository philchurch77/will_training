---
name: deck-leg3b-notes
description: Leg 3b kept badges review (2026-10-04) - where the rule lives, verified, flagged
metadata:
  type: project
---

Logic home: progress.kept_badge_values (sums old SessionLog counts + deck_rules.play_counts); Badge.KEPT_KINDS in models.py; award_badges (progress.py) and award_deck_badges (deck_rules.py) both award from it. Import chain: progress -> deck_rules -> deck_data -> models at top level; deck_rules -> progress is lazy inside award_deck_badges. No cycle today, but a top-level progress import in deck_rules/deck_data would create one.

Verified by reading: savepoint per award is right (EarnedBadge unique athlete+badge, award_badges runs inside drill_complete atomic); clear_trial_plays `first` cannot be None (early return on zero count); all-rounder max, free play once a day, card-day collapse are correct because pack/per_foot belong to the card.

Flagged: the award loop (threshold check, savepoint create, skip IntegrityError) is now written twice; play_counts dict-of-last-row trick (a set of tuples is clearer); Progress stats card uses drills_completed (ticks only, views.py ~307) while the 100-drills bar includes cards; no tests for 3b found in training/tests (grep kept/play_counts); CONTEXT.md lacks card-day and kept badge; Row defaults pack="" hide a forgotten argument; All rounder threshold 7 is not tied by a test to the seven non-free packs; _deck_badges_json filters Badge.objects.all() in Python (tiny table, leave); one extra Play read per Today tick (negligible next to total_minutes, leave).
