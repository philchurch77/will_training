"""The admin is the one screen in this app that can destroy Will's history.

`Drill.skill` and `SessionLog.drill` are both CASCADE. Deleting one skill in
the admin takes every drill under it and every session he ever logged against
them - his streak, his lifetime minutes and the counts behind his badges -
from a bulk action and a single confirmation page. There is no undo and
nothing to type back in.

Retiring is the supported way to take a drill out of circulation: add its slug
to RETIRED in seed_drills.py, which sets is_active=False and leaves the row.
"""

from datetime import date

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.urls import reverse

from training.models import Badge, Drill, EarnedBadge, Skill

pytestmark = pytest.mark.django_db


@pytest.fixture
def coach(db):
    """Phil, the only staff account. A superuser has every permission there
    is, which is exactly the case the guard has to survive."""
    return get_user_model().objects.create_superuser(
        username="phil-admin", email="phil@example.com", password="not-a-pin"
    )


class TestAdminCannotDeleteDrillsOrSkills:
    # Catches NoDeleteMixin being dropped from DrillAdmin, which would put a
    # Delete button back on every drill and take its logs with it.
    def test_drill_admin_refuses_delete_permission(self, rf, coach):
        request = rf.get("/admin/training/drill/")
        request.user = coach
        assert site._registry[Drill].has_delete_permission(request) is False

    # Catches the same on Skill, which is the worse of the two: deleting one
    # skill cascades through every drill under it before it reaches the logs.
    def test_skill_admin_refuses_delete_permission(self, rf, coach):
        request = rf.get("/admin/training/skill/")
        request.user = coach
        assert site._registry[Skill].has_delete_permission(request) is False

    # Catches a per-object override that lets a specific row through. The
    # object form of the check is the one the change page and the bulk action
    # actually call.
    def test_delete_is_refused_for_a_specific_drill_and_skill(
        self, rf, coach, drill, skill
    ):
        request = rf.get("/admin/")
        request.user = coach
        assert site._registry[Drill].has_delete_permission(request, drill) is False
        assert site._registry[Skill].has_delete_permission(request, skill) is False

    # Catches the "delete selected" bulk action reappearing on the changelist,
    # which is how a whole skill's worth of drills would go at once.
    def test_bulk_delete_action_is_not_offered(self, rf, coach):
        request = rf.get("/admin/training/drill/")
        request.user = coach
        assert "delete_selected" not in site._registry[Drill].get_actions(request)
        assert "delete_selected" not in site._registry[Skill].get_actions(request)

    # The same guard over HTTP, as a logged-in superuser: the drill is still
    # there after the POST that asked for it to go.
    def test_posting_the_delete_url_does_not_delete_the_drill(
        self, client, coach, drill
    ):
        client.force_login(coach)
        url = reverse("admin:training_drill_delete", args=[drill.pk])
        response = client.post(url, {"post": "yes"})
        assert response.status_code == 403
        assert Drill.objects.filter(pk=drill.pk).exists()

    # And on Skill, where the cascade is widest.
    def test_posting_the_delete_url_does_not_delete_the_skill(
        self, client, coach, skill, drill
    ):
        client.force_login(coach)
        url = reverse("admin:training_skill_delete", args=[skill.pk])
        response = client.post(url, {"post": "yes"})
        assert response.status_code == 403
        assert Skill.objects.filter(pk=skill.pk).exists()
        assert Drill.objects.filter(pk=drill.pk).exists()


@pytest.fixture
def earned(db, will):
    """One badge he has earned. EarnedBadge.badge is CASCADE, so deleting the
    badge in the admin would take his award with it."""
    badge = Badge.objects.create(
        code="test-badge", name="Test", description="", emoji="*",
        kind=Badge.FREE_PLAYS, threshold=1,
    )
    return EarnedBadge.objects.create(athlete=will, badge=badge, earned_on=date(2026, 10, 1))


class TestAdminCannotDeleteBadges:
    # Catches NoDeleteMixin being dropped from BadgeAdmin or
    # EarnedBadgeAdmin: a Delete button, or the bulk action, back on screen.
    @pytest.mark.parametrize("model", [Badge, EarnedBadge])
    def test_badge_admins_refuse_delete_and_offer_no_bulk_delete(
        self, rf, coach, earned, model
    ):
        request = rf.get("/admin/")
        request.user = coach
        admin = site._registry[model]
        obj = earned.badge if model is Badge else earned
        assert admin.has_delete_permission(request) is False
        assert admin.has_delete_permission(request, obj) is False
        assert "delete_selected" not in admin.get_actions(request)

    # Over HTTP: deleting the badge would cascade to his award.
    def test_posting_the_delete_url_does_not_delete_a_badge(self, client, coach, earned):
        client.force_login(coach)
        url = reverse("admin:training_badge_delete", args=[earned.badge.pk])
        assert client.post(url, {"post": "yes"}).status_code == 403
        assert Badge.objects.filter(pk=earned.badge.pk).exists()
        assert EarnedBadge.objects.filter(pk=earned.pk).exists()

    # And the award itself: already earned stays earned.
    def test_posting_the_delete_url_does_not_delete_an_earned_badge(
        self, client, coach, earned
    ):
        client.force_login(coach)
        url = reverse("admin:training_earnedbadge_delete", args=[earned.pk])
        assert client.post(url, {"post": "yes"}).status_code == 403
        assert EarnedBadge.objects.filter(pk=earned.pk).exists()
