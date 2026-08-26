"""Completing a drill.

The idempotency test here is the one that matters: it is what lets a tick made
in the garden with no signal be replayed later without creating a duplicate.
"""

import pytest
from django.urls import reverse

from training.models import EarnedBadge, SessionLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client, will):
    client.force_login(will)
    return client


class TestCompletion:
    def test_completing_creates_a_log(self, logged_in, will, plan, drill):
        response = logged_in.post(reverse("training:drill_complete", args=[drill.slug]))
        assert response.status_code == 302

        log = SessionLog.objects.get(athlete=will, drill=drill)
        assert log.completed

    def test_completing_twice_updates_instead_of_duplicating(
        self, logged_in, will, plan, drill
    ):
        url = reverse("training:drill_complete", args=[drill.slug])
        logged_in.post(url, {"actual_minutes": "4"})
        logged_in.post(url, {"actual_minutes": "9"})

        assert SessionLog.objects.filter(athlete=will, drill=drill).count() == 1
        assert SessionLog.objects.get(athlete=will, drill=drill).actual_minutes == 9

    def test_minutes_are_stored_for_timed_drills(self, logged_in, will, plan, drill):
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"actual_minutes": "7", "actual_reps": "50"},
        )
        log = SessionLog.objects.get(athlete=will, drill=drill)
        assert log.actual_minutes == 7
        assert log.actual_reps is None  # a timed drill has no rep count

    def test_reps_are_stored_for_rep_drills(self, logged_in, will, plan, rep_drill):
        logged_in.post(
            reverse("training:drill_complete", args=[rep_drill.slug]),
            {"actual_reps": "42", "actual_minutes": "7"},
        )
        log = SessionLog.objects.get(athlete=will, drill=rep_drill)
        assert log.actual_reps == 42
        assert log.actual_minutes is None

    def test_rating_is_saved(self, logged_in, will, plan, drill):
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]), {"rating": "4"}
        )
        assert SessionLog.objects.get(athlete=will, drill=drill).rating == 4

    def test_a_nonsense_rating_is_ignored(self, logged_in, will, plan, drill):
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]), {"rating": "99"}
        )
        assert SessionLog.objects.get(athlete=will, drill=drill).rating is None

    def test_get_is_not_allowed(self, logged_in, plan, drill):
        response = logged_in.get(reverse("training:drill_complete", args=[drill.slug]))
        assert response.status_code == 405

    def test_unticking_removes_the_log(self, logged_in, will, plan, drill):
        logged_in.post(reverse("training:drill_complete", args=[drill.slug]))
        logged_in.post(reverse("training:drill_uncomplete", args=[drill.slug]))
        assert not SessionLog.objects.filter(athlete=will, drill=drill).exists()


class TestQueuedOfflineCompletion:
    """A tick made offline arrives later, carrying the date it happened."""

    def test_a_recent_backdated_tick_is_accepted(self, logged_in, will, plan, drill):
        from datetime import timedelta

        from django.utils import timezone

        yesterday = timezone.localdate() - timedelta(days=1)
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"date": yesterday.isoformat()},
        )
        assert SessionLog.objects.get(athlete=will, drill=drill).date == yesterday

    def test_a_future_date_is_ignored(self, logged_in, will, plan, drill):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"date": (today + timedelta(days=3)).isoformat()},
        )
        # Falls back to today rather than writing into the future.
        assert SessionLog.objects.get(athlete=will, drill=drill).date == today

    def test_an_ancient_date_is_ignored(self, logged_in, will, plan, drill):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"date": (today - timedelta(days=400)).isoformat()},
        )
        assert SessionLog.objects.get(athlete=will, drill=drill).date == today

    def test_replaying_the_same_tick_is_harmless(self, logged_in, will, plan, drill):
        url = reverse("training:drill_complete", args=[drill.slug])
        for _ in range(4):
            logged_in.post(url, {"actual_minutes": "5"})
        assert SessionLog.objects.filter(athlete=will, drill=drill).count() == 1

    def test_ajax_completion_returns_json(self, logged_in, plan, drill):
        response = logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True


class TestBadgeAwardOnCompletion:
    def test_finishing_a_drill_awards_the_first_badge(self, client, will, seeded):
        from training.models import Drill

        client.force_login(will)
        drill = Drill.objects.get(slug="toe-taps")
        client.post(reverse("training:drill_complete", args=[drill.slug]))

        assert EarnedBadge.objects.filter(
            athlete=will, badge__code="first-session"
        ).exists()

    def test_badges_are_not_awarded_twice_across_requests(self, client, will, seeded):
        from training.models import Drill

        client.force_login(will)
        drill = Drill.objects.get(slug="toe-taps")
        url = reverse("training:drill_complete", args=[drill.slug])
        client.post(url)
        client.post(url)

        assert EarnedBadge.objects.filter(athlete=will).count() == 1


class TestSessionClock:
    """One clock for the whole session, instead of a countdown per drill.

    The rule that matters here is that the saved value only ever goes up. A
    tick queued in the garden can arrive after the session has run on, and it
    must not rewind the clock it rode in on.
    """

    def test_finishing_a_session_saves_the_time(self, logged_in, will, plan):
        from datetime import date

        from django.utils import timezone

        from training.models import SessionClock

        response = logged_in.post(
            reverse("training:session_time"), {"seconds": "1500"}
        )
        assert response.status_code == 302

        clock = SessionClock.objects.get(athlete=will, date=timezone.localdate())
        assert clock.seconds == 1500
        assert clock.minutes == 25
        assert isinstance(clock.date, date)

    def test_a_tick_carries_the_clock_with_it(self, logged_in, will, plan, drill):
        """He might spend twenty minutes on the drill he is enjoying and tick
        nothing until the end, so every tick banks the time too."""
        from django.utils import timezone

        from training.models import SessionClock

        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"session_seconds": "900"},
        )
        clock = SessionClock.objects.get(athlete=will, date=timezone.localdate())
        assert clock.seconds == 900

    def test_the_clock_only_ever_goes_up(self, logged_in, will, plan):
        from django.utils import timezone

        from training.models import SessionClock

        url = reverse("training:session_time")
        logged_in.post(url, {"seconds": "1800"})
        logged_in.post(url, {"seconds": "300"})  # a stale queued value

        clock = SessionClock.objects.get(athlete=will, date=timezone.localdate())
        assert clock.seconds == 1800

    def test_one_clock_per_day(self, logged_in, will, plan):
        from training.models import SessionClock

        url = reverse("training:session_time")
        logged_in.post(url, {"seconds": "600"})
        logged_in.post(url, {"seconds": "1200"})
        assert SessionClock.objects.filter(athlete=will).count() == 1

    def test_a_forgotten_clock_is_capped(self, logged_in, will, plan):
        """A phone left running on the kitchen table is not a nine hour session."""
        from training.models import SessionClock

        logged_in.post(reverse("training:session_time"), {"seconds": "99999"})
        clock = SessionClock.objects.get(athlete=will)
        assert clock.seconds == SessionClock.MAX_SECONDS

    def test_nonsense_is_ignored_without_losing_the_tick(
        self, logged_in, will, plan, drill
    ):
        from training.models import SessionClock, SessionLog

        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"session_seconds": "banana"},
        )
        assert SessionLog.objects.filter(athlete=will, drill=drill).exists()
        assert not SessionClock.objects.filter(athlete=will).exists()

    def test_a_queued_clock_lands_on_the_day_it_was_made(self, logged_in, will, plan):
        from datetime import timedelta

        from django.utils import timezone

        from training.models import SessionClock

        yesterday = timezone.localdate() - timedelta(days=1)
        logged_in.post(
            reverse("training:session_time"),
            {"seconds": "1200", "date": yesterday.isoformat()},
        )
        assert SessionClock.objects.get(athlete=will).date == yesterday

    def test_he_can_set_the_time_by_hand(self, logged_in, will, plan):
        """The evening he trains for half an hour and never starts the clock."""
        from django.utils import timezone

        from training.models import SessionClock

        logged_in.post(reverse("training:session_time"), {"minutes": "35"})
        clock = SessionClock.objects.get(athlete=will, date=timezone.localdate())
        assert clock.seconds == 35 * 60

    def test_a_number_he_set_himself_can_correct_one_that_is_too_big(
        self, logged_in, will, plan
    ):
        """The one case where the clock is allowed to go down. He knows what he
        did better than a clock he left running does."""
        from training.models import SessionClock

        url = reverse("training:session_time")
        logged_in.post(url, {"seconds": "5400"})  # an hour and a half, left running
        logged_in.post(url, {"minutes": "25"})

        assert SessionClock.objects.get(athlete=will).seconds == 25 * 60

    def test_a_running_clock_still_cannot_be_rewound_by_a_stale_tick(
        self, logged_in, will, plan, drill
    ):
        # Only a by-hand figure may go down; ticks keep the old rule.
        from training.models import SessionClock

        logged_in.post(reverse("training:session_time"), {"minutes": "30"})
        logged_in.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"session_seconds": "60"},
        )
        assert SessionClock.objects.get(athlete=will).seconds == 30 * 60

    def test_a_daft_number_of_minutes_is_ignored(self, logged_in, will, plan):
        from training.models import SessionClock

        url = reverse("training:session_time")
        logged_in.post(url, {"minutes": "600"})   # ten hours
        logged_in.post(url, {"minutes": "0"})
        assert not SessionClock.objects.filter(athlete=will).exists()

    def test_today_offers_the_by_hand_stepper(self, logged_in, plan):
        # No typing anywhere on his screens: it has to be minus and plus.
        body = logged_in.get(reverse("training:today")).content.decode()
        assert "Forgot to start the clock?" in body
        assert 'id="byhandminus"' in body
        assert 'type="text"' not in body

    def test_get_is_not_allowed(self, logged_in, plan):
        assert logged_in.get(reverse("training:session_time")).status_code == 405
