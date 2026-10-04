---
name: decisions-deck-leg3c
description: Leg 3c of docs/chart/deck.md (switch over) as planned 2026-10-04 - URL map ("/" = deck, Today at /today/ keeping its name), Progress as a deck.js hash route, Before the cards at /before/, six retired badge codes, precache shrink, no migration
metadata:
  type: project
---

Planned 2026-10-04 on `deck-step-3c` (off 8e98977). Recommendations; check the
chart for what Phil accepted.

**URL map:** `""` -> deck_views.deck, name `deck`; `today/` -> views.today keeps
name `today` (so ~40 test reverses and drill_complete/session_time redirects
need no change). `/deck/` and `/progress/` become plain redirects (to `/` and
`/#progress`). Drill/tick URLs never move: the offline queue (app.js,
`will-training-queue`) replays to stored `/drill/<slug>/done/` URLs.
**Trap:** app.js offline submit hardcodes `'/?done='` -> must be `/today/`.
login_view has two hardcoded `redirect("training:today")` plus LOGIN_REDIRECT_URL.

**Progress tab = `/#progress`, drawn by deck.js** (level/points from stamps live
only on the phone; a server page would disagree with unsynced plays). `#badges`
stays as an alias. Tab highlight toggled by deck.js on route.

**Before the cards** at `before/` (name `before_cards`), request.user, read-only:
drop current streak hero, sessions this month, badges section, record links to
drill pages ("Beat one today"). best_scores should read all drills, not
`.active()`, because 3d retires them all.

**RETIRED_BADGES** = streak-3, streak-7, streak-30, perfect-week, minutes-500,
streak-100 (chart says "streak" = all day-streaks). `award()` already filters
is_active. Breaks test_progress streak-3 test and test_seed long-game test.

**BLOCKS_START 2026-10-05**: no-op if 3c lands by Sun 11 Oct. Later: set to the
Monday of the deploy week, same deploy, only while no real play exists.

**Lookout on Render must not save a play or tick** once clear_trial_plays is
gone - nothing can take it off his record.

See [[decisions-deck-leg3]], [[decisions-deck-leg3b]].
