---
name: sunday-test-flake
description: Three will_training view tests fail on Sundays because of a date-dependent fixture, not a regression
metadata:
  type: feedback
---

Before blaming a diff for a failing test, check what day it is.

These three fail whenever the real system date is a Sunday:

- `test_views.py::TestTodayScreen::test_a_drill_can_be_ticked_off_without_opening_it`
- `test_views.py::TestTodayScreen::test_today_carries_the_session_clock`
- `test_sessions.py::TestSessionClock::test_today_offers_the_by_hand_stepper`

**Why:** the `plan` fixture in `training/tests/conftest.py` creates weekday 6
(Sunday) as a rest day with no `PlanDrill` rows, while the views under test
call `_today()` for real. On a Sunday the Today screen correctly renders an
empty session, and the three assertions that look for a tick form or the clock
stepper find nothing.

**How to apply:** if a review turns up exactly these three failures, confirm
the weekday first and report them as a pre-existing fixture flake, with the
evidence, rather than as a regression. The real fix is to freeze the date in
those tests, the way `progress.py` functions already take the date explicitly.
Observed 2026-09-20 with the whole suite otherwise green (`test_seed.py`: 57
passed).
