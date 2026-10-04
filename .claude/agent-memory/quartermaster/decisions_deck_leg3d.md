---
name: decisions-deck-leg3d
description: Leg 3d of docs/chart/deck.md (retire the fixed plan) as planned 2026-10-04 - keep/remove map, longest_streak decoupled from plan rows, no migration, queue left on phone, /coach/ = His sessions, SessionLog admin sealed
metadata:
  type: project
---

Planned 2026-10-04 on `deck-step-3d` (off 33e5525). Recommendations; check the
chart for what Phil accepted.

**Kept server code:** login/logout, deck, api_plays, before_cards, offline,
sw/manifest, coach_logs (moved to `/coach/`, name `coach_logs` kept) +
coach_log_edit. Everything else in views.py goes; forms.py deleted.
**progress.py keeps** only what Before the cards, kept_badge_values, award and
history need. Deleted: week_of, plan_day_for, current_streak,
sessions_this_month, _required_drills_by_weekday, perfect_weeks, _badge_values,
award_badges, record_session_seconds, session_seconds, session_for, today_summary.

**Trap found:** longest_streak -> day_state -> TrainingPlan.get_active(). With no
active plan every missed day is REST, so the best streak inflates to "every
done day joined". Fix: constant REST_WEEKDAYS={6} (exactly the Render plan:
Mon-Sat required, Sunday rest, no optional - _seed_plan reset the flags every
deploy). Gate: /before/ numbers identical before/after deploy.

**Data:** no migration. Plan tables/rows left untouched (drop = fog, own leg,
backup). Drills still seeded from DRILLS, all is_active=False (fresh-DB parity,
history text). JUGGLING set must stay (is_juggling feeds Keepy-up king).
Skill/Drill.get_absolute_url reverse removed URLs -> delete them.
SessionLogAdmin had no NoDeleteMixin - now the only thing that can move his
head start; seal it (no delete, no add).

**coach_log_edit** moves only the 3 HISTORY_CARDS "from before" bests and
Before-the-cards records - never head-start points or kept badges (those count
rows, not reps).

**Queue:** no replay endpoint kept; app.js stops flushing/intercepting but
never deletes `will-training-queue`. Gate: Will's phone opens with signal once
on 3c code before 3d merges. today/ and library/ redirect to "/". CACHE v26.

See [[decisions-deck-leg3c]], [[seeder-runs-on-render]].
