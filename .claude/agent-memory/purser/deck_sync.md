---
name: deck-sync
description: How deck plays, stamps and deck badges move between phone localStorage and /api/plays/; what is open after leg 2b review (2026-10-04)
metadata:
  type: project
---

Plays live in localStorage `will-deck-plays-v1`. Play is numbers only; Card
text is seeded. Server rule: first copy of an id wins, a resend changes nothing.
Phone rule in `restore()`: where both hold an id, the phone's copy is kept.
Only two writers of the plays key: the unreadable-JSON recovery (copies raw
aside first) and `updatePlays`. Leg 1 items all closed (do not re-raise).

**Leg 2b (reviewed 2026-10-04):** server badges via
`deck_rules.award_deck_badges` - add-only, savepoint per award, run in
`api_plays` POST whenever `saved` is non-empty (new OR resent play, not only
inserts; GET never awards). Exceptions logged, never cost a play. A badge
added/lowered at deploy waits for the next POST carrying a play; earned_on is
the award date. `will-deck-server-v1` is a cache (earned union-only, unseen
consumed when drawn) and never touches the plays key - celebration loss is
cosmetic only.
`clear_trial_plays` now also deletes active deck-kind EarnedBadges for every
athlete and re-awards from remaining plays (Legends kept). Re-award resets
earned_on to today; a badge whose threshold was raised since is not given back.
Decided by Phil (chart, Leg 2b decisions) as acceptable before hand-over.

**Open after 2b review:** no test covers award_deck_badges never revoking,
clear_trial_plays leaving old-app/Legend badges and rolling back, the
Badge/EarnedBadge admin guards, or award_badges/badge_progress skipping
retired/deck kinds. Leg 2a stamp items: `_parse_stamp` now nulls a bad stamp
instead of refusing the play (fixed); re-check the restore()/old-cached-deck.js
items next passage.

Running `clear_trial_plays` even as a dry run is refused by the auto-mode
classifier here; read its source instead. See [[cascades]], [[migrations-read]].
