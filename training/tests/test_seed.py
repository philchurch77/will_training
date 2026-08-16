"""The seed data is the substance of this app, so the coaching brief is
encoded here as assertions. If someone edits seed_drills.py and breaks one of
the principles - a drill that needs a partner, a session that has crept up to
45 minutes, a day with no weak-foot work - these tests say so.
"""

import pytest
from django.core.management import call_command

from training.models import Badge, Drill, PlanDay, Skill, TrainingPlan

pytestmark = pytest.mark.django_db

# Named in the brief as the staples a 9-year-old should be drilling.
REQUIRED_STAPLES = [
    "toe-taps",
    "sole-rolls",
    "foundations",
    "drag-backs",
    "cruyff-turn",
    "step-over",
    "figure-eight-dribble",
    "cone-slalom",
    "wall-pass-one-touch",
    "wall-control-inside",
    "laces-technique",
    "corner-placement",
    "juggling-laces",
]

# Words that would mean he cannot do the drill alone in a garden.
FORBIDDEN_WORDS = [
    "partner",
    "teammate",
    "team mate",
    "friend",
    "goalkeeper",
    "someone to",
]

# Training a 9-year-old should not involve any of this.
BANNED_TRAINING = [
    "sprint repeat",
    "weights",
    "dumbbell",
    "barbell",
    "plyometric",
    "squat jump",
    "burpee",
    "press up",
    "push up",
    "sit up",
    "lap of the park",
    "long run",
]


class TestSeedShape:
    def test_creates_between_30_and_40_drills(self, seeded):
        assert 30 <= Drill.objects.count() <= 40

    def test_creates_all_six_skills(self, seeded):
        assert Skill.objects.count() == 6
        assert set(Skill.objects.values_list("slug", flat=True)) == {
            "ball-mastery", "dribbling", "passing", "shooting",
            "first-touch", "one-v-one",
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
        assert Badge.objects.filter(code="streak-7").exists()

    def test_creates_the_single_profile(self, seeded):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        assert User.objects.filter(username="will", is_staff=False).exists()


class TestDrillQuality:
    def test_every_drill_has_readable_instructions(self, seeded):
        for drill in Drill.objects.all():
            assert len(drill.instructions) > 60, f"{drill.slug} is too terse"
            assert drill.instructions.strip().endswith("."), drill.slug
            # Two or three sentences, written for him to read.
            sentences = drill.instructions.count(".")
            assert 2 <= sentences <= 4, f"{drill.slug} has {sentences} sentences"

    def test_every_drill_has_a_coaching_cue(self, seeded):
        for drill in Drill.objects.all():
            assert drill.cue, drill.slug
            assert len(drill.cue) <= 60, drill.slug

    def test_every_drill_is_doable_alone(self, seeded):
        for drill in Drill.objects.all():
            text = drill.instructions.lower()
            for word in FORBIDDEN_WORDS:
                assert word not in text, f"{drill.slug} needs another person: {word}"

    def test_no_strength_or_endurance_work(self, seeded):
        for drill in Drill.objects.all():
            text = (drill.instructions + " " + drill.name).lower()
            for word in BANNED_TRAINING:
                assert word not in text, f"{drill.slug} is not age appropriate: {word}"

    def test_every_drill_needs_only_a_ball_wall_cones_or_space(self, seeded):
        for drill in Drill.objects.all():
            assert drill.needs_ball, f"{drill.slug} should need a ball"
            labels = {label for _e, label in drill.equipment}
            assert labels <= {"Ball", "Wall", "Cones", "Space"}, drill.slug

    def test_every_drill_has_a_duration_or_a_rep_target(self, seeded):
        for drill in Drill.objects.all():
            assert (drill.duration_minutes is None) != (drill.target_reps is None), (
                drill.slug
            )

    def test_no_single_drill_is_longer_than_ten_minutes(self, seeded):
        """Attention span at nine is short - keep every block bite sized."""
        for drill in Drill.objects.filter(duration_minutes__isnull=False):
            assert drill.duration_minutes <= 10, drill.slug

    def test_the_named_staples_are_all_present(self, seeded):
        have = set(Drill.objects.values_list("slug", flat=True))
        missing = [slug for slug in REQUIRED_STAPLES if slug not in have]
        assert not missing, f"missing staples: {missing}"

    def test_there_is_real_weak_foot_work(self, seeded):
        assert Drill.objects.filter(weak_foot=True).count() >= 6

    def test_there_are_fun_finishers(self, seeded):
        assert Drill.objects.filter(is_fun=True).count() >= 4

    def test_difficulty_spans_the_range(self, seeded):
        levels = set(Drill.objects.values_list("difficulty", flat=True))
        assert levels == {1, 2, 3}


class TestWeeklyPlan:
    def test_there_is_exactly_one_active_plan(self, seeded):
        assert TrainingPlan.objects.filter(is_active=True).count() == 1

    def test_it_covers_all_seven_days(self, seeded):
        assert set(seeded.days.values_list("weekday", flat=True)) == set(range(7))

    def test_every_day_carries_required_work(self, seeded):
        """Preseason: no academy and no matches, so all seven days are full."""
        required = [d for d in seeded.days.all() if d.is_required]
        assert len(required) == 7

    def test_every_session_is_three_or_four_drills(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            count = day.items.count()
            assert 3 <= count <= 4, f"{day.get_weekday_display()} has {count}"

    def test_every_session_lands_between_20_and_30_minutes(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            total = sum(item.drill.estimated_minutes for item in day.items.all())
            assert 20 <= total <= 30, (
                f"{day.get_weekday_display()} is {total} minutes"
            )

    def test_the_week_is_balanced_at_25_minutes_a_day(self, seeded):
        """Preseason ask: the same 25 minutes every day, no light days."""
        for day in seeded.days.all():
            total = sum(item.drill.estimated_minutes for item in day.items.all())
            assert total == 25, f"{day.get_weekday_display()} is {total} minutes"

    def test_the_target_minutes_match_the_drills(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            total = sum(item.drill.estimated_minutes for item in day.items.all())
            assert abs(total - day.target_minutes) <= 5, day.get_weekday_display()

    def test_every_session_includes_weak_foot_work(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            assert any(item.drill.weak_foot for item in day.items.all()), (
                f"{day.get_weekday_display()} has no weak foot work"
            )

    def test_every_session_starts_with_a_warm_up(self, seeded):
        """The first drill is always short ball mastery on the floor."""
        for day in seeded.days.all():
            if not day.is_required:
                continue
            first = day.items.order_by("order").first().drill
            assert first.skill.slug == "ball-mastery", day.get_weekday_display()
            assert first.estimated_minutes <= 5, day.get_weekday_display()
            assert not first.needs_wall, day.get_weekday_display()

    def test_every_session_ends_with_a_fun_finisher(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            last = day.items.order_by("order").last().drill
            assert last.is_fun, f"{day.get_weekday_display()} has no fun finisher"

    def test_the_whole_week_uses_every_skill(self, seeded):
        used = set()
        for day in seeded.days.all():
            for item in day.items.all():
                used.add(item.drill.skill.slug)
        assert len(used) == 6, f"unused skills: {set(Skill.objects.values_list('slug', flat=True)) - used}"

    def test_the_week_is_not_overloaded(self, seeded):
        """Total required home minutes across the week, sanity bound."""
        total = sum(
            item.drill.estimated_minutes
            for day in seeded.days.all()
            if day.is_required
            for item in day.items.all()
        )
        assert 150 <= total <= 190, f"{total} minutes of home training a week"


class TestIdempotency:
    def test_running_it_twice_changes_nothing(self, seeded):
        before = (
            Drill.objects.count(),
            Skill.objects.count(),
            PlanDay.objects.count(),
            Badge.objects.count(),
        )
        call_command("seed_drills", verbosity=0)
        after = (
            Drill.objects.count(),
            Skill.objects.count(),
            PlanDay.objects.count(),
            Badge.objects.count(),
        )
        assert before == after

    def test_re_seeding_does_not_duplicate_a_days_drills(self, seeded):
        monday = PlanDay.objects.get(weekday=0)
        before = monday.items.count()
        call_command("seed_drills", verbosity=0)
        assert PlanDay.objects.get(weekday=0).items.count() == before

    def test_re_seeding_does_not_reset_a_changed_pin(self, seeded):
        from django.contrib.auth import authenticate, get_user_model

        user = get_user_model().objects.get(username="will")
        user.set_password("4321")
        user.save()

        call_command("seed_drills", verbosity=0)
        assert authenticate(username="will", password="4321") is not None

    def test_reset_rebuilds_cleanly(self, seeded):
        call_command("seed_drills", "--reset", verbosity=0)
        assert 30 <= Drill.objects.count() <= 40
        assert TrainingPlan.objects.filter(is_active=True).count() == 1


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
