"""The seed data is the substance of this app, so the coaching brief is
encoded here as assertions. If someone edits seed_drills.py and breaks one of
the principles - a drill that needs a partner, a session that has crept up to
45 minutes, a day with no weak-foot work - these tests say so.
"""

from datetime import date

import pytest
from django.core.management import call_command

from training import progress
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
    "keepy-up-record",
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

# Training a 9-year-old should not involve any of this. Short sprints and
# accelerations are in now - see TestSpeedWork - but endurance running and
# anything out of a gym stays out.
BANNED_TRAINING = [
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
    def test_creates_between_36_and_55_drills(self, seeded):
        assert 36 <= Drill.objects.count() <= 55

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
        assert Badge.objects.filter(code="streak-7").exists()

    def test_every_badge_kind_has_a_metric(self, seeded):
        # A badge whose kind progress.py does not measure can never be earned:
        # it would sit at 0 on his Progress screen for ever and nothing would
        # ever say why. (The seed makes Will itself, so no `will` fixture -
        # the two would collide on the username.)
        from training.views import get_athlete

        values = progress._badge_values(get_athlete(), date(2026, 8, 10))
        for badge in Badge.objects.all():
            assert badge.kind in values, badge.code

    def test_there_is_something_left_to_chase_after_a_month(self, seeded):
        # A month of preseason clears the whole original ladder - 30 day
        # streak, 100 drills, 500 minutes. If every badge is reachable that
        # fast the screen goes dead just as the habit is forming, so keep a
        # long one and keep one that cannot be reached by volume at all.
        assert Badge.objects.filter(
            kind=Badge.STREAK, threshold__gte=90
        ).exists(), "no long streak badge left to chase"
        assert Badge.objects.filter(
            kind=Badge.PERFECT_WEEKS
        ).exists(), "nothing rewards finishing a whole session"

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
            # Speed is the one skill where a drill may be ball-free: a
            # standing start is a standing start.
            if drill.skill.slug != "speed":
                assert drill.needs_ball, f"{drill.slug} should need a ball"
            labels = {label for _e, label in drill.equipment}
            assert labels <= {"Ball", "Wall", "Cones", "Space"}, drill.slug

    def test_every_drill_has_a_duration_or_a_rep_target(self, seeded):
        for drill in Drill.objects.all():
            assert (drill.duration_minutes is None) != (drill.target_reps is None), (
                drill.slug
            )

    def test_no_single_drill_is_longer_than_five_minutes(self, seeded):
        """Attention span at nine is short - keep every block bite sized.

        Five is also what keeps the plan arithmetic trivial: a rep-based drill
        counts as five minutes too, so six drills is thirty minutes whatever
        mix a day is built from.
        """
        for drill in Drill.objects.filter(duration_minutes__isnull=False):
            assert drill.duration_minutes <= 5, drill.slug

    def test_the_named_staples_are_all_present(self, seeded):
        have = set(Drill.objects.values_list("slug", flat=True))
        missing = [slug for slug in REQUIRED_STAPLES if slug not in have]
        assert not missing, f"missing staples: {missing}"

    def test_there_is_real_weak_foot_work(self, seeded):
        assert Drill.objects.filter(weak_foot=True).count() >= 6

    def test_there_is_a_proper_spread_of_juggling(self, seeded):
        """Juggling is on every day now, so the library has to carry enough of
        it that he is not doing the same keepy-ups seven days a week."""
        juggling = Drill.objects.filter(is_juggling=True)
        assert juggling.count() >= 7
        assert juggling.filter(difficulty=1).exists(), "nothing easy to start on"
        assert juggling.filter(weak_foot=True).exists(), "no weak foot juggling"

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

    def test_every_session_is_six_drills(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            count = day.items.count()
            assert count == 6, f"{day.get_weekday_display()} has {count}"

    def test_every_session_lands_between_25_and_30_minutes(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            total = sum(item.drill.estimated_minutes for item in day.items.all())
            assert 25 <= total <= 30, (
                f"{day.get_weekday_display()} is {total} minutes"
            )

    def test_the_week_is_balanced_at_30_minutes_a_day(self, seeded):
        """Preseason ask: the same 30 minutes every day, no light days."""
        for day in seeded.days.all():
            total = sum(item.drill.estimated_minutes for item in day.items.all())
            assert total == 30, f"{day.get_weekday_display()} is {total} minutes"

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

    def test_every_session_includes_juggling(self, seeded):
        """The brief: keepy-ups are a fixture, not an extra.

        They are the one thing he will keep doing for the fun of it, and they
        are pure first touch, so every session carries one.
        """
        for day in seeded.days.all():
            if not day.is_required:
                continue
            assert any(item.drill.is_juggling for item in day.items.all()), (
                f"{day.get_weekday_display()} has no juggling"
            )

    def test_no_session_is_mostly_juggling(self, seeded):
        """One block. Juggling is not a substitute for the rest of the session."""
        for day in seeded.days.all():
            count = sum(1 for item in day.items.all() if item.drill.is_juggling)
            assert count == 1, f"{day.get_weekday_display()} has {count}"

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
        assert len(used) == 7, f"unused skills: {set(Skill.objects.values_list('slug', flat=True)) - used}"

    def test_the_week_is_not_overloaded(self, seeded):
        """Total required home minutes across the week, sanity bound."""
        total = sum(
            item.drill.estimated_minutes
            for day in seeded.days.all()
            if day.is_required
            for item in day.items.all()
        )
        assert 190 <= total <= 220, f"{total} minutes of home training a week"


class TestSpeedWork:
    """Speed is the newest part of the brief and the easiest to overdo.

    Sprinting is the one thing in here that tires him rather than teaches him,
    so it is short, it is spaced across the week, and a session never carries
    two of them.
    """

    def test_there_is_a_speed_skill_with_real_drills(self, seeded):
        assert Skill.objects.get(slug="speed").drills.count() >= 5

    def test_most_speed_work_is_done_with_the_ball(self, seeded):
        """Football speed, not athletics. A couple of plain sprints are fine."""
        drills = list(Skill.objects.get(slug="speed").drills.all())
        with_ball = [d for d in drills if d.needs_ball]
        assert len(with_ball) * 2 > len(drills), "too much running, not enough ball"

    def test_every_speed_drill_is_short(self, seeded):
        for drill in Skill.objects.get(slug="speed").drills.all():
            assert drill.estimated_minutes <= 5, drill.slug

    def test_speed_drills_tell_him_to_recover(self, seeded):
        """A nine-year-old going flat out needs telling to stop and breathe."""
        drills = list(Skill.objects.get(slug="speed").drills.all())
        resting = [
            d
            for d in drills
            if any(
                word in d.instructions.lower()
                for word in ("rest", "breath", "walk back", "slow down")
            )
        ]
        assert len(resting) * 2 >= len(drills), "no recovery written into the sprints"

    def test_speed_appears_on_three_days_a_week(self, seeded):
        days = [
            day
            for day in seeded.days.all()
            if any(item.drill.skill.slug == "speed" for item in day.items.all())
        ]
        assert len(days) == 3, f"speed on {len(days)} days"

    def test_no_session_doubles_up_on_speed(self, seeded):
        for day in seeded.days.all():
            count = sum(
                1 for item in day.items.all() if item.drill.skill.slug == "speed"
            )
            assert count <= 1, f"{day.get_weekday_display()} has {count} speed drills"

    def test_speed_never_replaces_the_warm_up(self, seeded):
        """Cold sprinting is how something gets pulled. Ball mastery comes first."""
        for day in seeded.days.all():
            if not day.is_required:
                continue
            first = day.items.order_by("order").first().drill
            assert first.skill.slug != "speed", day.get_weekday_display()


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
        assert 36 <= Drill.objects.count() <= 55
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
