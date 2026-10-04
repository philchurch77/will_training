"""His sessions before the cards, on the coach screen.

The fixed plan, its ticks and its session clock were retired in leg 3d. What
is left is correcting a count he made back then.
"""

import pytest
from django.urls import reverse

from .conftest import MONDAY

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client, will):
    client.force_login(will)
    return client


class TestFixingACount:
    """A number nobody watched him make can sit on his record board for ever,
    so the coach screen has to be able to correct it."""

    def test_the_coach_can_change_a_count(self, logged_in, will, plan, rep_drill):
        from training import progress
        from training.models import SessionLog

        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        logged_in.post(reverse("training:coach_log_edit", args=[log.pk]), {"reps": "12"})

        log.refresh_from_db()
        assert log.actual_reps == 12
        assert progress.personal_best(will, rep_drill) == 12

    def test_an_empty_box_rubs_the_count_out(self, logged_in, will, plan, rep_drill):
        from training import progress
        from training.models import SessionLog

        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        logged_in.post(reverse("training:coach_log_edit", args=[log.pk]), {"reps": ""})

        log.refresh_from_db()
        assert log.actual_reps is None
        assert progress.personal_best(will, rep_drill) is None
        assert progress.best_scores(will) == []

    def test_the_session_itself_survives(self, logged_in, will, plan, rep_drill):
        """His head start and badges count rows: a wrong score is not worth losing the row over."""
        from training import progress
        from training.models import SessionLog

        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        logged_in.post(reverse("training:coach_log_edit", args=[log.pk]), {"reps": ""})

        log.refresh_from_db()
        assert log.completed
        assert progress.drills_completed(will) == 1
        assert progress.longest_streak(will) == 1

    def test_a_timed_drill_has_nothing_to_edit(self, logged_in, will, plan, drill):
        """Nothing records per-drill minutes any more. The old numbers stay as
        they are, because his lifetime minutes are counted from them."""
        from training.models import SessionLog

        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=drill, actual_minutes=6
        )
        logged_in.post(
            reverse("training:coach_log_edit", args=[log.pk]), {"minutes": "99"}
        )
        log.refresh_from_db()
        assert log.actual_minutes == 6

        body = logged_in.get(reverse("training:coach_logs")).content.decode()
        assert "6 min" in body

    def test_it_needs_a_post(self, logged_in, will, plan, rep_drill):
        from training.models import SessionLog

        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        assert logged_in.get(
            reverse("training:coach_log_edit", args=[log.pk])
        ).status_code == 405

    def test_the_log_screen_offers_the_box(self, logged_in, will, plan, rep_drill):
        from training.models import SessionLog

        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        body = logged_in.get(reverse("training:coach_logs")).content.decode()
        assert reverse("training:coach_log_edit", args=[log.pk]) in body
        assert 'value="30"' in body
