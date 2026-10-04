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

**Leg 3b (reviewed 2026-10-04, no migration):** `Badge.KEPT_KINDS`
(TOTAL_DRILLS, SKILLS_TRIED, WEAK_FOOT, JUGGLING) now count ticks + card-days
via `progress.kept_badge_values`; awarded by both `award_badges` (tick) and
`award_deck_badges` (sync, clear re-award loop). Both add-only, savepoint per
create. `clear_trial_plays` delete still bounded to active DECK_KINDS - kept
badges are never deleted by it (decided, do not ask to widen). Its dry run lists
kept awards with earned_on >= first trial play: noisy (catches real tick
awards too), only a backstop. Deploy order decided by Phil: merge 3a, back up,
clear, then 3b.
SQLite race note: inside drill_complete the SessionLog write takes the write
lock before award_badges reads `already`, so an EarnedBadge IntegrityError
there is effectively unreachable on SQLite (rollback-journal); the savepoint is
defence in depth. What CAN still roll back a tick: any non-IntegrityError from
award_badges (now pulls in deck_rows/play_counts) - api_plays wraps its award
in try/except, drill_complete does not. Gunicorn is 1 worker x 4 threads, DB
timeout 20, no WAL/transaction_mode set.
Open after 3b review: no tests for any 3b guard (grep KEPT_KINDS in tests = 0).
Badge text: longest description 70/120, name 16/40 (measured by ast over BADGES).
