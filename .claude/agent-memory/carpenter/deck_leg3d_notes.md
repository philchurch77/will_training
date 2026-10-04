---
name: deck-leg3d-notes
description: Leg 3d (retire fixed plan) review 2026-10-04 - what is left dead, gaps from test deletions, flagged items
metadata:
  type: project
---

Layout after 3d: views.py = login/logout, before_cards, coach_logs (/coach/), coach_log_edit, PWA plumbing. progress.py = history readers + kept_badge_values + award; REST_WEEKDAYS={6} frozen. No forms.py, no templatetags. Plan tables kept with no admin.

Verified by reading: no unused imports in views.py/progress.py/urls.py; old app.js flush() kept failed items in the queue (writeQueue(remaining)), so a 404 on replay does not drop ticks; CLAUDE.md names all resolve (HISTORY_CARDS, FROZEN_MEANINGS, TestDeckScript, runTimedBar, will-deck-* keys, queue/-pending/-clock keys).

Flagged (not yet fixed when written): test-only/dead code - DrillQuerySet.active, Drill.equipment, Drill.target_label (admin column only), TrainingPlan.get_active/save, PlanDay.drills_for_week/is_required, SessionClock.MAX_SECONDS, conftest `plan`/`fortnight` fixtures (`seeded` now returns None); no test for REST_WEEKDAYS (Sunday rest / no-plan streak), the 3 redirects, or SessionLogAdmin guards; coach_logs caps at 200 rows so older counts cannot be edited on screen; _parse_int blanks a count on out-of-range input; best_scores queries once per rep drill; stale comments (models.py SessionLog constraint/SessionClock/deck banner, progress.kept_badge_values, sw.js header and "ticks must reach the server", seed JUGGLING/COMBINATIONS, test_kept_badges header, test_switch_over empty "4-5" heading, 3 unused imports in test_kept_badges and test_progress, trailing blank lines in views.py/progress.py). CLAUDE.md "trial clear-out ... never needed" contradicts chart lines 103-104 unless Phil confirmed the clear ran.

Dead CSS candidates: .tickform .tick-btn .clock .clocknote .clockchip .counter-sm .rate .flame .chips/.chip (drill-row/drill-list/tick/drill-group are live via deck.js).
