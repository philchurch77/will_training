"""The seed, after the fixed plan was retired (leg 3d of docs/chart/deck.md).

The drills are frozen history now: what his SessionLog rows from before the
cards point at. These tests hold that the seed keeps every one of them, keeps
them inactive, never touches the history logged against them, and still makes
the skills, the badges and his profile. The coaching brief now lives in the
cards - see TestDeckContent in test_deck.py.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from training.management.commands.seed_drills import COMBINATIONS, DRILLS, JUGGLING
from training.models import Badge, Drill, SessionLog, Skill

pytestmark = pytest.mark.django_db

# Slug is the first column of every DRILLS tuple.
DRILL_SLUGS = {row[0] for row in DRILLS}


class TestSeedShape:
    def test_creates_between_36_and_80_drills(self, seeded):
        """Rows, all inactive since leg 3d: every one is history his logs
        point at, so the number never goes down."""
        assert 36 <= Drill.objects.count() <= 80

    def test_creates_all_seven_skills(self, seeded):
        assert Skill.objects.count() == 7
        assert set(Skill.objects.values_list("slug", flat=True)) == {
            "ball-mastery", "dribbling", "passing", "shooting",
            "first-touch", "one-v-one", "speed",
        }

    def test_every_skill_has_drills(self, seeded):
        for skill in Skill.objects.all():
            assert skill.drills.count() >= 3, f"{skill.name} is thin"

    def test_ball_mastery_and_first_touch_are_the_priority(self, seeded):
        """The brief: technique first at this age."""
        ball = Skill.objects.get(slug="ball-mastery").drills.count()
        touch = Skill.objects.get(slug="first-touch").drills.count()
        shooting = Skill.objects.get(slug="shooting").drills.count()
        assert ball + touch > shooting * 2

    def test_creates_the_badges(self, seeded):
        assert Badge.objects.count() >= 8
        # Retired, never deleted: an earned one stays as a Legend.
        assert Badge.objects.filter(code="streak-7", is_active=False).exists()

    # Catches an active badge whose kind nothing measures: it could never be
    # earned and would sit at "Not yet" on his Progress tab for ever. Retired
    # badges are never awarded, so they need no measure. (The seed makes Will
    # itself, so no `will` fixture - the two would collide on the username.)
    def test_every_active_badge_kind_has_a_metric(self, seeded):
        from training.deck_rules import deck_badge_values
        from training.models import get_athlete
        from training.progress import kept_badge_values

        values = {**deck_badge_values([]), **kept_badge_values(get_athlete(), [])}
        for badge in Badge.objects.filter(is_active=True):
            assert badge.kind in values, badge.code

    def test_creates_the_single_profile(self, seeded):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        assert User.objects.filter(username="will", is_staff=False).exists()


class TestIdempotency:
    def test_running_it_twice_changes_nothing(self, seeded):
        before = (
            Drill.objects.count(),
            Skill.objects.count(),
            Badge.objects.count(),
        )
        call_command("seed_drills", verbosity=0)
        after = (
            Drill.objects.count(),
            Skill.objects.count(),
            Badge.objects.count(),
        )
        assert before == after

    def test_re_seeding_does_not_reset_a_changed_pin(self, seeded):
        from django.contrib.auth import authenticate, get_user_model

        user = get_user_model().objects.get(username="will")
        user.set_password("4321")
        user.save()

        call_command("seed_drills", verbosity=0)
        assert authenticate(username="will", password="4321") is not None


class TestDrillsAreHistory:
    """Every drill is retired with the plan, never deleted and never rewritten.

    SessionLog.drill is CASCADE, so removing a drill removes every day Will
    logged against it. The seed keeps every row and switches it off.
    """

    # Catches a drill being cut from DRILLS, which would leave his logs on a
    # fresh or restored database pointing at nothing.
    def test_every_seeded_drill_exists_and_is_inactive(self, seeded):
        assert set(Drill.objects.values_list("slug", flat=True)) >= DRILL_SLUGS
        assert not Drill.objects.filter(slug__in=DRILL_SLUGS, is_active=True).exists()

    # The most important test here: re-seeding must not touch what he
    # recorded, however many times a deploy runs it.
    def test_re_seeding_twice_keeps_the_history_logged_against_a_drill(self, seeded):
        will = get_user_model().objects.get(username="will")
        drill = Drill.objects.get(slug="keepy-up-record")
        log = SessionLog.objects.create(
            athlete=will, date=date(2026, 8, 10), drill=drill,
            completed=True, rating=5, actual_reps=31,
        )

        call_command("seed_drills", verbosity=0)
        call_command("seed_drills", verbosity=0)

        log.refresh_from_db()
        assert (log.completed, log.rating, log.actual_reps) == (True, 5, 31)
        assert log.drill.slug == "keepy-up-record"


class TestSlugSets:
    """COMBINATIONS and JUGGLING are sets of slugs typed by hand, and the
    drill flags (and Keepy-up king, through is_juggling) are built from them.
    A misspelling silently does nothing; these fail loudly instead."""

    def test_every_combination_slug_names_a_real_drill(self):
        unknown = COMBINATIONS - DRILL_SLUGS
        assert not unknown, f"COMBINATIONS names slugs that are not in DRILLS: {unknown}"

    def test_every_juggling_slug_names_a_real_drill(self):
        unknown = JUGGLING - DRILL_SLUGS
        assert not unknown, f"JUGGLING names slugs that are not in DRILLS: {unknown}"


class TestSetPin:
    def test_it_changes_the_pin(self, seeded):
        from django.contrib.auth import authenticate

        call_command("set_pin", "will", "4321", verbosity=0)
        assert authenticate(username="will", password="4321") is not None
        assert authenticate(username="will", password="1234") is None

    def test_it_rejects_a_pin_that_is_not_four_digits(self, seeded):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("set_pin", "will", "12", verbosity=0)
        with pytest.raises(CommandError):
            call_command("set_pin", "will", "abcd", verbosity=0)

    def test_it_complains_about_an_unknown_profile(self, seeded):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("set_pin", "nobody", "1234", verbosity=0)
