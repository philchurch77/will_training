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
