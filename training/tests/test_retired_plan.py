"""Leg 3d: the fixed plan is retired, and what he logged on it is kept.

Since this leg nothing outside the coach count box writes a SessionLog. Each
row is worth head-start points and a step toward a kept badge, so the tests
here guard the doors that could add, remove or rewrite one: the coach edit,
the admin, the old tick URLs, the seed command and the old offline queue.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from training import progress
from training.models import Drill, PlanDay, PlanDrill, SessionLog, TrainingPlan

from .conftest import MONDAY, SATURDAY, SUNDAY, TUESDAY, WEDNESDAY

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client, will):
    client.force_login(will)
    return client


@pytest.fixture
def coach(db):
    """A superuser has every permission there is - the case the guard must survive."""
    return get_user_model().objects.create_superuser(
        username="phil-admin", email="phil@example.com", password="not-a-pin"
    )


class TestCoachEditAccess:
    # Catches coach_required being dropped from coach_log_edit, which would let
    # anyone on the internet rewrite his record counts with a bare POST.
    def test_anonymous_cannot_change_a_count(self, client, will, rep_drill):
        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        response = client.post(
            reverse("training:coach_log_edit", args=[log.pk]), {"reps": "0"}
        )
        assert response.status_code == 302
        assert reverse("training:login") in response["Location"]
        log.refresh_from_db()
        assert log.actual_reps == 30


class TestSessionLogAdminIsReadOnly:
    # Catches NoDeleteMixin being dropped from SessionLogAdmin: a delete there
    # takes a tick away, and with it head-start points and badge progress.
    def test_session_log_admin_refuses_delete(self, rf, coach, will, drill):
        log = SessionLog.objects.create(athlete=will, date=MONDAY, drill=drill)
        request = rf.get("/admin/training/sessionlog/")
        request.user = coach
        admin = site._registry[SessionLog]
        assert admin.has_delete_permission(request) is False
        assert admin.has_delete_permission(request, log) is False

    # Catches the Add button coming back: a tick written through the back door
    # would be worth points he never earned.
    def test_session_log_admin_refuses_add(self, rf, coach):
        request = rf.get("/admin/training/sessionlog/")
        request.user = coach
        assert site._registry[SessionLog].has_add_permission(request) is False

    # Catches a field dropping out of readonly_fields, which would let the
    # change form move a tick to another day or drill.
    @pytest.mark.parametrize(
        "field",
        ["athlete", "date", "drill", "completed", "actual_minutes", "rating"],
    )
    def test_what_he_did_cannot_be_rewritten_in_the_admin(
        self, rf, coach, will, drill, field
    ):
        log = SessionLog.objects.create(athlete=will, date=MONDAY, drill=drill)
        request = rf.get("/admin/")
        request.user = coach
        assert field in site._registry[SessionLog].get_readonly_fields(request, log)


class TestTheOldTickDoorsAreShut:
    # Catches the drill_complete route coming back: a replayed offline tick
    # from an old cached page would write a row nothing else can remove.
    def test_an_old_tick_post_writes_nothing(self, logged_in, drill):
        response = logged_in.post(f"/drill/{drill.slug}/done/", {"session_seconds": "60"})
        assert response.status_code == 404
        assert not SessionLog.objects.exists()

    # Catches the session_time endpoint coming back.
    def test_the_session_clock_endpoint_is_gone(self, logged_in):
        response = logged_in.post("/session/time/", {"seconds": "600"})
        assert response.status_code == 404

    # Catches an old bookmark or home-screen shortcut landing on a 404.
    @pytest.mark.parametrize(
        "old, new",
        [("/today/", "/"), ("/library/", "/"), ("/coach/logs/", "/coach/before/")],
    )
    def test_old_addresses_go_somewhere_real(self, logged_in, old, new):
        response = logged_in.get(old)
        assert response.status_code == 302
        assert response["Location"] == new


class TestStreakWithNoPlan:
    """day_state no longer reads the plan: Sunday is rest, every other day counts."""

    def _done(self, will, drill, *days):
        for day in days:
            SessionLog.objects.create(athlete=will, date=day, drill=drill)

    # Catches the streak breaking on Sunday now there is no PlanDay to say
    # Sunday is rest - his best run before the cards would shrink.
    def test_sunday_off_does_not_break_his_best_run(self, will, drill):
        week = [MONDAY + timedelta(days=i) for i in range(6)]  # Mon-Sat
        self._done(will, drill, *week, SUNDAY + timedelta(days=1))
        assert not PlanDay.objects.exists()
        assert progress.longest_streak(will) == 7

    # Catches every day without a plan row being treated as rest, which would
    # turn Mon + Wed into a run of two.
    def test_a_missed_weekday_breaks_the_run(self, will, drill):
        self._done(will, drill, MONDAY, WEDNESDAY)
        assert progress.longest_streak(will) == 1

    # Catches a Sunday he did train on being skipped rather than counted.
    def test_a_sunday_he_trained_counts(self, will, drill):
        self._done(will, drill, SATURDAY, SUNDAY)
        assert progress.longest_streak(will) == 2


class TestCoachEditRejectsBadCounts:
    # Catches a POST with no count field at all being read as "rub it out":
    # only an explicit empty box may blank a count (found by the Lookout, 3d).
    def test_a_post_without_the_count_field_changes_nothing(self, logged_in, will, rep_drill):
        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        logged_in.post(reverse("training:coach_log_edit", args=[log.pk]), {})
        log.refresh_from_db()
        assert log.actual_reps == 30

    # Catches a typo or tampered value wiping (or overwriting) a real count -
    # _parse_int returns None for these, which used to blank the row.
    @pytest.mark.parametrize("raw", ["abc", "20000", "-1", "1.5", "३"])
    def test_a_count_he_could_not_have_made_changes_nothing(
        self, logged_in, will, rep_drill, raw
    ):
        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        response = logged_in.post(
            reverse("training:coach_log_edit", args=[log.pk]),
            {"reps": raw},
            follow=True,
        )
        log.refresh_from_db()
        assert log.actual_reps == 30
        assert "Not saved" in response.content.decode()

    # Catches the upper bound being off by one and refusing a real maximum.
    def test_the_top_of_the_range_saves(self, logged_in, will, rep_drill):
        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=rep_drill, actual_reps=30
        )
        logged_in.post(
            reverse("training:coach_log_edit", args=[log.pk]), {"reps": "10000"}
        )
        log.refresh_from_db()
        assert log.actual_reps == 10000


class TestSignOut:
    # Catches logout going back to accepting GET, where a prefetch or a stray
    # link tap signs him out on the pitch with no signal to sign back in.
    def test_a_get_does_not_sign_him_out(self, logged_in):
        assert logged_in.get(reverse("training:logout")).status_code == 405
        assert logged_in.get(reverse("training:coach_logs")).status_code == 200

    # Catches the POST no longer clearing the session.
    def test_a_post_signs_him_out(self, logged_in):
        logged_in.post(reverse("training:logout"))
        response = logged_in.get(reverse("training:coach_logs"))
        assert response.status_code == 302
        assert reverse("training:login") in response["Location"]


class TestCoachScreen:
    # Catches the Sign out button reverting to a GET link, which now 405s.
    def test_sign_out_is_a_post_form_and_home_is_linked(self, logged_in, will):
        body = logged_in.get(reverse("training:coach_logs")).content.decode()
        assert f'method="post" action="{reverse("training:logout")}"' in body
        assert 'href="/"' in body

    # Catches the old 200-row cap returning: a count past it could never be
    # corrected, because its edit box would not be on the page.
    def test_every_row_is_listed_not_just_the_newest_200(
        self, logged_in, will, rep_drill
    ):
        SessionLog.objects.bulk_create(
            SessionLog(
                athlete=will, date=MONDAY - timedelta(days=i), drill=rep_drill,
                actual_reps=i,
            )
            for i in range(201)
        )
        oldest = SessionLog.objects.get(date=MONDAY - timedelta(days=200))
        body = logged_in.get(reverse("training:coach_logs")).content.decode()
        assert reverse("training:coach_log_edit", args=[oldest.pk]) in body


class TestSeedLeavesThePlanAlone:
    # Catches seed_drills going back to rebuilding the plan on every deploy:
    # the plan tables are history now, and nothing should rewrite them.
    def test_seeding_twice_leaves_plan_rows_untouched(self, plan):
        def snapshot():
            return (
                TrainingPlan.objects.count(),
                list(PlanDay.objects.order_by("pk").values()),
                list(PlanDrill.objects.order_by("pk").values()),
            )

        before = snapshot()
        call_command("seed_drills", verbosity=0)
        call_command("seed_drills", verbosity=0)
        assert snapshot() == before

    # Catches a seeded drill being switched back on, which would put the old
    # library back in front of him.
    def test_every_seeded_drill_stays_retired(self, db):
        call_command("seed_drills", verbosity=0)
        call_command("seed_drills", verbosity=0)
        assert Drill.objects.exists()
        assert not Drill.objects.filter(is_active=True).exists()


class TestOldQueueIsNeverTouched:
    """The old offline tick queue stays on his phone as a readable record.

    Nothing may read it (and replay it at a URL that now 404s) or remove it.
    """

    SOURCE = (
        Path(settings.BASE_DIR) / "training" / "static" / "training" / "js" / "app.js"
    ).read_text(encoding="utf-8")

    # Catches the replay loop coming back and reading the queue.
    @pytest.mark.parametrize("call", ["getItem", "setItem", "removeItem"])
    def test_app_js_never_touches_the_queue_keys(self, call):
        assert f"{call}('will-training" not in self.SOURCE
        assert f'{call}("will-training' not in self.SOURCE
        assert call not in self.SOURCE

    # Catches app.js sending anything at all - plays are deck.js's job.
    def test_app_js_sends_nothing(self):
        assert "fetch(" not in self.SOURCE
        assert "method: 'POST'" not in self.SOURCE
        assert 'method: "POST"' not in self.SOURCE
