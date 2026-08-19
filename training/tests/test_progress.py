"""Streak logic.

The rule that matters most: a scheduled rest day or an academy/match day never
breaks a streak. A 9-year-old should not lose a 20-day run by resting when the
plan told him to rest.
"""

from datetime import date, timedelta

import pytest

from training import progress
from training.models import Badge, PlanDay, PlanDrill, SessionLog

from .conftest import (
    FRIDAY,
    MONDAY,
    SATURDAY,
    SUNDAY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
)

pytestmark = pytest.mark.django_db


def tick(will, drill, day, **kwargs):
    return SessionLog.objects.create(athlete=will, date=day, drill=drill, **kwargs)


class TestCurrentStreak:
    def test_no_sessions_means_no_streak(self, will, plan):
        assert progress.current_streak(will, WEDNESDAY) == 0

    def test_consecutive_days_build_up(self, will, plan, drill):
        tick(will, drill, MONDAY)
        tick(will, drill, TUESDAY)
        tick(will, drill, WEDNESDAY)
        assert progress.current_streak(will, WEDNESDAY) == 3

    def test_one_drill_is_enough_to_count_the_day(self, will, plan, drill, rep_drill):
        # He has four drills scheduled but only did one. The day still counts.
        tick(will, drill, MONDAY)
        assert progress.current_streak(will, MONDAY) == 1

    def test_a_missed_training_day_breaks_it(self, will, plan, drill):
        tick(will, drill, MONDAY)
        # Tuesday missed - it is a required day in the fixture plan.
        tick(will, drill, WEDNESDAY)
        assert progress.current_streak(will, WEDNESDAY) == 1

    def test_a_rest_day_does_not_break_it(self, will, plan, drill):
        """Sunday is a rest day in the fixture plan."""
        tick(will, drill, SATURDAY)
        tick(will, drill, MONDAY + timedelta(days=7))  # the following Monday
        # Sat done, Sun rest (skipped), Mon done -> 2
        assert progress.current_streak(will, MONDAY + timedelta(days=7)) == 2

    def test_an_optional_day_does_not_break_it(self, will, plan, drill):
        """Saturday is optional (match day) in the fixture plan."""
        tick(will, drill, THURSDAY)
        tick(will, drill, date(2026, 8, 14))  # Friday, a required day
        # Sat optional and skipped, Sun rest and skipped, then Monday.
        tick(will, drill, MONDAY + timedelta(days=7))
        assert progress.current_streak(will, MONDAY + timedelta(days=7)) == 3

    def test_today_not_done_yet_keeps_yesterdays_streak(self, will, plan, drill):
        tick(will, drill, MONDAY)
        tick(will, drill, TUESDAY)
        # It is Wednesday morning and he has not trained yet.
        assert progress.current_streak(will, WEDNESDAY) == 2

    def test_a_gap_before_today_still_breaks_it(self, will, plan, drill):
        tick(will, drill, MONDAY)
        # Tuesday missed, and it is now Wednesday with nothing done.
        assert progress.current_streak(will, WEDNESDAY) == 0

    def test_streak_survives_with_no_plan_at_all(self, will, drill):
        """With no active plan nothing is 'required', so nothing breaks."""
        tick(will, drill, MONDAY)
        assert progress.current_streak(will, WEDNESDAY) == 1


class TestLongestStreak:
    def test_finds_the_best_run(self, will, plan, drill):
        for day in (MONDAY, TUESDAY, WEDNESDAY):
            tick(will, drill, day)
        # Thursday and Friday missed, then two more.
        tick(will, drill, MONDAY + timedelta(days=7))
        tick(will, drill, MONDAY + timedelta(days=8))
        assert progress.longest_streak(will) == 3

    def test_zero_when_nothing_logged(self, will, plan):
        assert progress.longest_streak(will) == 0


class TestMonthlyAndTotals:
    def test_sessions_this_month_counts_days_not_drills(
        self, will, plan, drill, rep_drill
    ):
        tick(will, drill, MONDAY)
        tick(will, rep_drill, MONDAY)  # same day, second drill
        tick(will, drill, TUESDAY)
        assert progress.sessions_this_month(will, MONDAY) == 2

    def test_last_month_is_not_counted(self, will, plan, drill):
        tick(will, drill, date(2026, 7, 30))
        tick(will, drill, MONDAY)
        assert progress.sessions_this_month(will, MONDAY) == 1

    def test_total_minutes_uses_actuals_when_present(self, will, plan, drill, rep_drill):
        tick(will, drill, MONDAY, actual_minutes=8)
        tick(will, rep_drill, MONDAY)  # no actual -> 5 minute default
        assert progress.total_minutes(will) == 13

    def test_drills_completed_counts_every_row(self, will, plan, drill, rep_drill):
        tick(will, drill, MONDAY)
        tick(will, rep_drill, MONDAY)
        assert progress.drills_completed(will) == 2


class TestMinutesBySkill:
    def test_includes_skills_with_nothing_done(self, will, plan, drill, seeded=None):
        from training.models import Skill

        Skill.objects.create(name="Shooting", slug="shooting", order=2)
        tick(will, drill, MONDAY, actual_minutes=10)

        rows = progress.minutes_by_skill(will)
        by_name = {r["skill"].name: r for r in rows}
        assert by_name["Ball mastery"]["minutes"] == 10
        assert by_name["Shooting"]["minutes"] == 0
        # The busiest skill fills the bar; the neglected one shows empty.
        assert by_name["Ball mastery"]["percent"] == 100
        assert by_name["Shooting"]["percent"] == 0

    def test_all_zero_does_not_divide_by_zero(self, will, plan, drill):
        rows = progress.minutes_by_skill(will)
        assert all(r["percent"] == 0 for r in rows)


class TestBadges:
    def test_awards_when_the_threshold_is_reached(self, will, seeded, drill):
        from training.models import Drill, EarnedBadge

        real = Drill.objects.get(slug="toe-taps")
        tick(will, real, MONDAY)
        earned = progress.award_badges(will, MONDAY)

        codes = {b.code for b in earned}
        assert "first-session" in codes
        assert EarnedBadge.objects.filter(athlete=will, badge__code="first-session").exists()

    def test_never_awards_the_same_badge_twice(self, will, seeded):
        from training.models import Drill, EarnedBadge

        real = Drill.objects.get(slug="toe-taps")
        tick(will, real, MONDAY)
        progress.award_badges(will, MONDAY)
        second = progress.award_badges(will, MONDAY)

        assert second == []
        assert EarnedBadge.objects.filter(athlete=will).count() == 1

    def test_streak_badge_needs_the_streak(self, will, seeded):
        from training.models import Drill

        real = Drill.objects.get(slug="toe-taps")
        for day in (MONDAY, TUESDAY, WEDNESDAY):
            tick(will, real, day)
        earned = progress.award_badges(will, WEDNESDAY)
        assert "streak-3" in {b.code for b in earned}
        assert "streak-7" not in {b.code for b in earned}


class TestTodaySummary:
    def test_marks_what_is_already_done(self, will, plan, drill):
        summary = progress.today_summary(will, MONDAY)
        assert summary["total_count"] == 1
        assert summary["done_count"] == 0
        assert not summary["all_done"]

        tick(will, drill, MONDAY)
        summary = progress.today_summary(will, MONDAY)
        assert summary["done_count"] == 1
        assert summary["all_done"]

    def test_rest_day_has_no_drills(self, will, plan):
        summary = progress.today_summary(will, SUNDAY)
        assert summary["plan_day"].is_rest
        assert summary["rows"] == []


class TestPerfectWeeks:
    """The plan fixture: Mon-Fri required with one drill each, Sat optional,
    Sun rest. So a perfect week is Mon-Fri done in full."""

    WEEKDAYS = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY)

    def test_nothing_done_is_no_weeks(self, will, plan):
        assert progress.perfect_weeks(will, SUNDAY) == 0

    def test_every_required_day_in_full(self, will, plan, drill):
        for day in self.WEEKDAYS:
            tick(will, drill, day)
        assert progress.perfect_weeks(will, SUNDAY) == 1

    def test_the_optional_and_rest_days_are_not_needed(self, will, plan, drill):
        # He trained Mon-Fri and rested Sat and Sun, exactly as asked. That is
        # a perfect week - the same rule that stops a rest day breaking a streak.
        for day in self.WEEKDAYS:
            tick(will, drill, day)
        assert SATURDAY not in progress.completed_dates(will)
        assert progress.perfect_weeks(will, SUNDAY) == 1

    def test_one_missed_day_loses_the_week(self, will, plan, drill):
        for day in self.WEEKDAYS:
            if day != THURSDAY:
                tick(will, drill, day)
        assert progress.perfect_weeks(will, SUNDAY) == 0

    def test_half_a_session_is_not_a_perfect_day(self, will, plan, drill, rep_drill):
        # Two drills on the Monday, only one of them ticked. A streak would
        # survive this; a perfect week must not.
        PlanDrill.objects.create(
            plan_day=PlanDay.objects.get(plan=plan, weekday=0), drill=rep_drill, order=2
        )
        for day in self.WEEKDAYS:
            tick(will, drill, day)
        assert progress.current_streak(will, FRIDAY) == 5
        assert progress.perfect_weeks(will, SUNDAY) == 0

        tick(will, rep_drill, MONDAY)
        assert progress.perfect_weeks(will, SUNDAY) == 1

    def test_weeks_accumulate(self, will, plan, drill):
        for day in self.WEEKDAYS:
            tick(will, drill, day)
            tick(will, drill, day + timedelta(days=7))
        assert progress.perfect_weeks(will, SUNDAY + timedelta(days=7)) == 2

    def test_awards_the_badge(self, will, plan, drill):
        # Its own badge rather than the seeded one: the `seeded` fixture would
        # activate the real plan instead of this fixture's.
        badge = Badge.objects.create(
            code="test-perfect-week",
            name="Perfect week",
            description="Every drill, every training day.",
            kind=Badge.PERFECT_WEEKS,
            threshold=1,
        )
        for day in (MONDAY, TUESDAY, WEDNESDAY):
            tick(will, drill, day)
        assert badge not in progress.award_badges(will, WEDNESDAY)

        for day in (THURSDAY, FRIDAY):
            tick(will, drill, day)
        assert badge in progress.award_badges(will, SUNDAY)
