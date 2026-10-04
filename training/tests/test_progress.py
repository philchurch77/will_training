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
    def test_total_minutes_uses_actuals_when_present(self, will, plan, drill, rep_drill):
        tick(will, drill, MONDAY, actual_minutes=8)
        tick(will, rep_drill, MONDAY)  # no actual -> 5 minute default
        assert progress.total_minutes(will) == 13

    def test_the_session_clock_decides_what_a_day_was_worth(
        self, will, plan, drill, rep_drill
    ):
        """He trained for 45 minutes on a day the plan called 10. The clock is
        what actually happened, so the clock is what counts."""
        from training.models import SessionClock

        tick(will, drill, MONDAY)
        tick(will, rep_drill, MONDAY)
        SessionClock.objects.create(athlete=will, date=MONDAY, seconds=45 * 60)

        assert progress.total_minutes(will) == 45

    def test_a_day_before_the_clock_existed_keeps_its_old_total(
        self, will, plan, drill, rep_drill
    ):
        """The whole point of the fallback: his history does not move."""
        from training.models import SessionClock

        tick(will, drill, MONDAY, actual_minutes=8)
        tick(will, drill, TUESDAY)
        SessionClock.objects.create(athlete=will, date=TUESDAY, seconds=20 * 60)

        # Monday: 8, as it always was. Tuesday: 20, from the clock.
        assert progress.total_minutes(will) == 28

    def test_clock_time_on_a_day_with_no_ticks_counts_for_nothing(self, will, plan):
        from training.models import SessionClock

        SessionClock.objects.create(athlete=will, date=MONDAY, seconds=60 * 60)
        assert progress.total_minutes(will) == 0

    def test_drills_completed_counts_every_row(self, will, plan, drill, rep_drill):
        tick(will, drill, MONDAY)
        tick(will, rep_drill, MONDAY)
        assert progress.drills_completed(will) == 2


class TestPersonalBests:
    """His own number is the one worth beating.

    The counts were being written to the database and never shown back to him,
    which is the one thing that makes a rep drill worth doing twice.
    """

    def test_the_best_count_wins(self, will, plan, rep_drill):
        tick(will, rep_drill, MONDAY, actual_reps=18)
        tick(will, rep_drill, TUESDAY, actual_reps=31)
        tick(will, rep_drill, WEDNESDAY, actual_reps=24)
        assert progress.personal_best(will, rep_drill) == 31

    def test_no_score_yet_is_none_not_zero(self, will, plan, rep_drill):
        tick(will, rep_drill, MONDAY)  # ticked off without counting
        assert progress.personal_best(will, rep_drill) is None

    def test_a_timed_drill_has_no_best(self, will, plan, drill):
        assert progress.personal_best(will, drill) is None

    def test_the_record_board_skips_drills_he_has_never_counted(
        self, will, plan, drill, rep_drill
    ):
        tick(will, rep_drill, MONDAY, actual_reps=22)
        tick(will, drill, MONDAY, actual_minutes=5)

        rows = progress.best_scores(will)
        assert [r["drill"] for r in rows] == [rep_drill]
        assert rows[0]["best"] == 22

    def test_the_board_leads_with_his_biggest_number(self, will, plan, skill):
        from training.models import Drill

        second = Drill.objects.create(
            name="Thigh juggles", slug="test-thigh", skill=skill,
            instructions="Juggle.", cue="Flat thigh", target_reps=20,
        )
        third = Drill.objects.create(
            name="Low juggles", slug="test-low", skill=skill,
            instructions="Juggle low.", cue="Small touches", target_reps=20,
        )
        tick(will, second, MONDAY, actual_reps=9)
        tick(will, third, MONDAY, actual_reps=44)

        assert [r["best"] for r in progress.best_scores(will)] == [44, 9]


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

    def test_the_chart_and_the_total_tell_the_same_story(
        self, will, plan, drill, rep_drill
    ):
        """A clocked day is shared out across the drills he ticked, so the bars
        add up to the total on the same screen."""
        from training.models import Skill, SessionClock

        other = Skill.objects.create(name="Shooting", slug="shooting", order=2)
        rep_drill.skill = other
        rep_drill.save()

        tick(will, drill, MONDAY)       # 5 planned minutes
        tick(will, rep_drill, MONDAY)   # 5 planned minutes
        SessionClock.objects.create(athlete=will, date=MONDAY, seconds=40 * 60)

        rows = {r["skill"].name: r["minutes"] for r in progress.minutes_by_skill(will)}
        assert rows["Ball mastery"] == 20
        assert rows["Shooting"] == 20
        assert sum(rows.values()) == progress.total_minutes(will)

    def test_all_zero_does_not_divide_by_zero(self, will, plan, drill):
        rows = progress.minutes_by_skill(will)
        assert all(r["percent"] == 0 for r in rows)


def make_badge(code, kind, threshold=0, is_active=True):
    # Threshold 0: anything that looks at the badge at all would award it.
    return Badge.objects.create(
        code=code, name=code, description="", emoji="*",
        kind=kind, threshold=threshold, is_active=is_active,
    )


class TestBadgesAfterTheDeck:
    """Deck badges are worked out from plays, at sync; the old award must
    leave them alone. A retired badge is never awarded, and one he earned
    stays on his record as a Legend."""

    # Catches retiring a badge taking it off his record: one he earned stays,
    # tagged Legend, in the badge list his Progress tab draws.
    def test_a_retired_badge_he_earned_stays_as_a_legend(self, client, will, plan):
        from training.models import EarnedBadge

        from .test_deck_views import deck_badges_in

        retired = make_badge("test-retired", Badge.TOTAL_DRILLS, is_active=False)
        client.force_login(will)
        assert "test-retired" not in {r["code"] for r in deck_badges_in(client.get("/"))}

        EarnedBadge.objects.create(athlete=will, badge=retired, earned_on=MONDAY)
        [shown] = [r for r in deck_badges_in(client.get("/")) if r["code"] == "test-retired"]
        assert shown["legend"] is True and shown["earned"] is True


class TestRetiringADrillDoesNotMoveHisHistory:
    """Retirement flips is_active=False and deletes nothing. Every number on
    the Progress screen must read exactly the same the day after a deploy as
    it did the day before.

    The failure this catches is a later change making a streak, a minutes
    total or the skill chart filter on `Drill.objects.active()`. Nothing would
    error and no row would be lost - his past would simply be smaller, which
    is the version of losing his history that nobody notices.
    """

    def retire(self, *drills):
        from training.models import Drill

        Drill.objects.filter(pk__in=[d.pk for d in drills]).update(is_active=False)

    # Catches a streak or a lifetime total starting to filter on is_active.
    def test_the_streaks_and_the_total_minutes_are_identical_after_retirement(
        self, will, plan, drill, rep_drill
    ):
        for day in (MONDAY, TUESDAY, WEDNESDAY, THURSDAY):
            tick(will, drill, day)
            tick(will, rep_drill, day)

        before = (
            progress.longest_streak(will),
            progress.total_minutes(will),
            progress.drills_completed(will),
        )
        # Guard the guard: an all-zero "before" would pass whatever happened.
        assert before == (4, 40, 8)

        self.retire(drill, rep_drill)

        after = (
            progress.longest_streak(will),
            progress.total_minutes(will),
            progress.drills_completed(will),
        )
        assert after == before

    # Catches the skill chart, and the clock-shared minutes behind it, losing
    # a day because the drill he did it on is no longer in the library.
    def test_a_clocked_day_is_worth_the_same_after_the_drill_is_retired(
        self, will, plan, drill, rep_drill
    ):
        from training.models import SessionClock

        tick(will, drill, MONDAY)
        tick(will, rep_drill, MONDAY)
        SessionClock.objects.create(athlete=will, date=MONDAY, seconds=45 * 60)

        before = [(row["skill"].slug, row["minutes"]) for row in
                  progress.minutes_by_skill(will)]
        assert progress.total_minutes(will) == 45
        assert sum(minutes for _slug, minutes in before) == 45

        self.retire(drill, rep_drill)

        after = [(row["skill"].slug, row["minutes"]) for row in
                 progress.minutes_by_skill(will)]
        assert after == before
        assert progress.total_minutes(will) == 45

    # Catches completed_dates or day_state starting to filter on is_active,
    # which would turn a day he trained into a missed day - and break a streak
    # he has already earned.
    def test_a_day_he_trained_is_still_a_day_he_trained(
        self, will, plan, drill
    ):
        tick(will, drill, MONDAY)
        tick(will, drill, TUESDAY)

        before = progress.completed_dates(will)
        assert before == {MONDAY, TUESDAY}

        self.retire(drill)

        assert progress.completed_dates(will) == before
        done = progress.completed_dates(will)
        assert progress.day_state(MONDAY, done) == progress.DONE
        assert progress.day_state(TUESDAY, done) == progress.DONE
