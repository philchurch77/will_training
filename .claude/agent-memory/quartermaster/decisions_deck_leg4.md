---
name: decisions-deck-leg4
description: Leg 4 of docs/chart/deck.md ("His cards" on the coach page) as planned 2026-10-04 - URL swap, read-only, server-only numbers, refused plays not stored anywhere server-side, staff-session sign-in recommendation
metadata:
  type: project
---

Planned 2026-10-04 on `deck-step-4` (off 1189404, 3d unmerged). Recommendations;
check the chart for what Phil accepted.

**URL map:** `/coach/` -> new `views.coach_cards` (name `coach_cards`);
old logs move to `/coach/before/` keeping name `coach_logs` (coach_log_edit
redirects by name, untouched). `/coach/logs/` redirect retargets to
`/coach/before/` (test_retired_plan.py:106 hardcodes "/coach/"). base.html
Coach link -> coach_cards; TestChrome in test_views.py reverses coach_logs.

**Facts found:** refused plays are stored nowhere server-side and not even
logged - reason lives only in localStorage `play.refused` on the phone.
Coach pages are not precached; sw.js is network-first for pages, cache-first
for /static/ (any app.css edit needs CACHE bump, v26 -> v27).
`coach_required` is login_required only, so a staff session can read coach
screens (and api_plays 403s staff, so a staff phone can never file plays).

**Shape:** server shows only what has synced; points = Sum(Play.points) +
history_for(get_athlete()).points; bests per card one aggregate query
(Max for count, Min over >0 for time, Max medal), merged with starting_bests
"(from before)"; goal weeks from one deck_rows read; plays paginated 50.
Level in Python = second writing of levelFor (deck.js) - flagged.

**Risk:** clear_trial_plays is gone (3d). Phil's phone signed in by PIN lands
on "/" and syncs any localStorage plays onto Will's record permanently.

See [[decisions-deck-leg3d]], [[decisions-deck-leg3c]].
