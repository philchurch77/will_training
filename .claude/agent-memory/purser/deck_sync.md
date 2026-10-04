---
name: deck-sync
description: How deck plays and their stamps move between phone localStorage and /api/plays/; leg 1 items closed, leg 2a loss paths still open (2026-10-03)
metadata:
  type: project
---

Plays live in localStorage `will-deck-plays-v1`. Play is numbers only; Card
text is seeded. Server rule: first copy of an id wins, a resend changes nothing.
Phone rule in `restore()`: where both hold an id, the phone's copy is kept as is.

**Leg 1 items — all closed by 2026-10-03 (verified in code, do not re-raise):**
restore() now marks a synced play the server lacks as unsent and resends it;
the weak-foot score is drafted to `will-deck-draft-v1`; updatePlays sets
`writeLost` and the warning shows; the IntegrityError branch checks the row
and owner; test_deck.py / test_deck_views.py exist (81 pass); clear_trial_plays
needs `--through DATE` and `--confirm --expect N`.

**Leg 2a stamps (points/medal/bests), open at review 2026-10-03:**
- No test covers any stamp path, and `deck_rules.py` names a
  `test_deck_rules.py` that does not exist (same pattern as leg 1).
- `_parse_play` refuses the whole play (score included) on a bad or
  over-ceiling stamp; ceilings (points 1000, medal 3, bests 2) are not tied to
  POINTS by any test. Recommended: null the stamp, keep the play.
- restore() never fills a null local stamp from a stamped server copy, so an
  old cached deck.js (iPhone home-screen app keeps its own SW/storage) that
  restores stamped plays strips them for good on that device.
- Plays saved by old deck.js in the first load after the 2a deploy are
  unstamped forever (worth nothing). One-time; skipWaiting+claim narrow it.
- Unlocks read only stored `medal` via bestMedal(slug); targets (`card.medals`)
  are read only inside stamp(). A changed card slug or move/level would relock.
- Trial plays (if not cleared) are unstamped but still feed bestsFor(), so
  Phil's scores become Will's personal-best baseline; 2b server badges would
  count them too.

**How to apply:** next deck passage, check each 2a item is fixed or decided,
then rewrite this note to what remains. See [[cascades]], [[migrations-read]].
