---
name: decisions-deck
description: Leg 1 of docs/chart/deck.md (the deck on the phone) - storage, hand-dealing rule, sync/CSRF/401 handling, service worker bypass, test layout, open questions put to the developer
metadata:
  type: project
---

Planned 2026-10-03 for leg 1 of `docs/chart/deck.md`. Committed before the plan:
`Card`/`Play` (models.py bottom), migration 0008, `training/deck_data.py`,
`training/deck_views.py`, `templates/training/deck.html`.

**Storage: localStorage, not IndexedDB.** Two keys, versioned:
`will-deck-plays-v1` (array, each play carries `synced` and `refused` reason)
and `will-deck-hand-v1` ({date, slugs}). Writes to plays go through one
function that refuses to shrink the list.
**Why:** ~200 bytes a play, a few a day = well under the 5MB quota for years;
sync API, matches app.js/session.js, and a source-reading test can guard it.
**How to apply:** if quota ever binds, that is fog for a later leg - do not
switch to IndexedDB speculatively.

**Hand rule.** 5 distinct packs: 1 Moves + 1 of (Quick feet | Combos) + 3 from
the remaining packs (the other of QF/Combos allowed). Free play is never dealt;
it is a fixed button under the hand (recommended, put to developer). Same hand
all day keyed by the phone's local date; deal again replaces it. Any move level
dealt in leg 1; level gating is leg 2's unlocks.

**Sync.** CSRF read from the `csrftoken` cookie at send time, `data-csrf` only
as fallback - a cached /deck/ carries a token from before the last login
rotation. 401/403/network/non-JSON all leave plays unsent; nothing on the phone
is ever dropped by a response. GET on every load with signal, merged by id
(union). Phone sends `date` as local Y-M-D, never `toISOString().slice(0,10)`.

**Service worker.** Must skip `/api/` entirely: the network-first page branch
would otherwise cache /api/plays/ JSON or answer it offline with offline.html.

**Card copy.** Level-3 move cards ran to four sentences against the "two or
three" brief; recommended tightening before any play points at them.

**Changing a card's meaning** (scoring, per_foot, timer_seconds, out_of) on a
card with plays = new slug + retire the old, same as drills. Medal targets and
wording may change in place.

**Open to developer at plan time:** Phil's trial plays land on the single
athlete's record (one profile, PROTECT, no admin delete); stepper start value
(recommended 0).

See [[decisions-seed-data]], [[seeder-runs-on-render]].
