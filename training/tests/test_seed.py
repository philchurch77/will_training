"""The seed data is the substance of this app, so the coaching brief is
encoded here as assertions. If someone edits seed_drills.py and breaks one of
the principles - a drill that needs a partner, a session that has crept up to
45 minutes, a day with no weak-foot work - these tests say so.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from training import progress
from training.management.commands.seed_drills import (
    COMBINATIONS,
    DRILLS,
    JUGGLING,
    RETIRED,
)
from training.models import (
    Badge,
    Drill,
    PlanDay,
    PlanDrill,
    SessionLog,
    Skill,
    TrainingPlan,
)

pytestmark = pytest.mark.django_db

# Slug is the first column of every DRILLS tuple.
DRILL_SLUGS = {row[0] for row in DRILLS}

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


def sessions(plan):
    """Every session in the fortnight: twelve of them, not six.

    Each day holds two running orders and alternates between them, so a rule
    checked against `day.items` would be checking both weeks jammed together
    and would miss a week B that had drifted. Everything below is asserted
    against each session as Will actually meets it.
    """
    for day in plan.days.all():
        if not day.is_required:
            continue
        for week, letter in ((PlanDrill.WEEK_A, "A"), (PlanDrill.WEEK_B, "B")):
            yield (
                f"{day.get_weekday_display()} week {letter}",
                day,
                day.drills_for_week(week),
            )


class TestSeedShape:
    def test_creates_between_36_and_65_drills(self, seeded):
        """Rows, not active drills.

        Retired drills keep their row so the sessions he logged against them
        still have something to point at, so this bound counts them too.
        """
        assert 36 <= Drill.objects.count() <= 65

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

    def test_combination_drills_tell_him_to_walk_it_through(self, seeded):
        """A three-move sequence at pace is the first thing he does all day.

        Cold feet walk it through slowly first, for the same reason a session
        never opens with a sprint.

        This looks for "walk" and not for "slow", which is what it asked for
        originally. "Slow" passed on a drill whose instructions merely said
        the move would feel "slow and clumsy at first" - a description of how
        it feels, not an instruction to take it steady. The rule is that he is
        told to do something, so the test requires the word that tells him.
        """
        for drill in Drill.objects.filter(is_combination=True):
            assert "walk" in drill.instructions.lower(), (
                f"{drill.slug} never tells him to walk it through before "
                "taking it up to pace"
            )

    def test_difficulty_spans_the_range(self, seeded):
        levels = set(Drill.objects.values_list("difficulty", flat=True))
        assert levels == {1, 2, 3}


class TestWeeklyPlan:
    def test_there_is_exactly_one_active_plan(self, seeded):
        assert TrainingPlan.objects.filter(is_active=True).count() == 1

    def test_it_covers_all_seven_days(self, seeded):
        assert set(seeded.days.values_list("weekday", flat=True)) == set(range(7))

    def test_six_sessions_and_one_day_off(self, seeded):
        """Preseason: no academy and no matches, so six days are full sessions
        and the seventh is a real rest day.

        Seven days out of seven left him nowhere to recover, and the streak -
        which breaks on a missed required day - was pushing him to train
        anyway. A rest day is skipped by the streak walk, so taking it costs
        him nothing.
        """
        required = [d for d in seeded.days.all() if d.is_required]
        rest = [d for d in seeded.days.all() if d.is_rest]
        assert len(required) == 6
        assert len(rest) == 1
        assert rest[0].weekday == 6, "the day off should be Sunday"
        assert not rest[0].items.exists(), "a rest day should carry no drills"

    def test_every_session_is_six_drills(self, seeded):
        for name, _day, drills in sessions(seeded):
            assert len(drills) == 6, f"{name} has {len(drills)}"

    def test_no_session_repeats_a_drill(self, seeded):
        for name, _day, drills in sessions(seeded):
            slugs = [d.slug for d in drills]
            assert len(set(slugs)) == len(slugs), f"{name} repeats a drill"

    def test_no_week_repeats_a_drill_across_its_days(self, seeded):
        """Thirty-six slots, thirty-six different drills, in each week.

        The one above only looks inside a single session, so a drill could sit
        on Thursday and again on Friday and nothing would complain - and
        back-to-back is exactly the repeat he would notice. This is also the
        arithmetic the second week rests on: a week reaches 36 of the 50 drills
        only if it never spends a slot twice.
        """
        for week, letter in ((PlanDrill.WEEK_A, "A"), (PlanDrill.WEEK_B, "B")):
            slugs = [
                d.slug
                for day in seeded.days.all()
                if day.is_required
                for d in day.drills_for_week(week)
            ]
            repeated = sorted({s for s in slugs if slugs.count(s) > 1})
            assert not repeated, f"week {letter} trains {repeated} more than once"

    def test_the_fortnight_uses_the_whole_library(self, seeded):
        """The reason there are two weeks at all: one week can only reach 36 of
        the 50 drills, so the rest sat in the library never being trained."""
        used = {d.slug for _n, _day, drills in sessions(seeded) for d in drills}
        unused = set(Drill.objects.active().values_list("slug", flat=True)) - used
        assert not unused, f"never trained: {sorted(unused)}"

    def test_the_two_weeks_are_not_the_same_session(self, seeded):
        for day in seeded.days.all():
            if not day.is_required:
                continue
            a = [d.slug for d in day.drills_for_week(PlanDrill.WEEK_A)]
            b = [d.slug for d in day.drills_for_week(PlanDrill.WEEK_B)]
            assert a != b, f"{day.get_weekday_display()} is identical both weeks"

    def test_every_session_lands_between_25_and_30_minutes(self, seeded):
        for name, _day, drills in sessions(seeded):
            total = sum(d.estimated_minutes for d in drills)
            assert 25 <= total <= 30, f"{name} is {total} minutes"

    def test_every_training_day_is_the_same_30_minutes(self, seeded):
        """Preseason ask: no light days among the days he does train."""
        for name, _day, drills in sessions(seeded):
            total = sum(d.estimated_minutes for d in drills)
            assert total == 30, f"{name} is {total} minutes"

    def test_the_target_minutes_match_the_drills(self, seeded):
        for name, day, drills in sessions(seeded):
            total = sum(d.estimated_minutes for d in drills)
            assert abs(total - day.target_minutes) <= 5, name

    def test_every_session_includes_weak_foot_work(self, seeded):
        for name, _day, drills in sessions(seeded):
            assert any(d.weak_foot for d in drills), f"{name} has no weak foot work"

    def test_every_session_includes_juggling(self, seeded):
        """The brief: keepy-ups are a fixture, not an extra.

        They are the one thing he will keep doing for the fun of it, and they
        are pure first touch, so every session carries one.
        """
        for name, _day, drills in sessions(seeded):
            assert any(d.is_juggling for d in drills), f"{name} has no juggling"

    def test_no_session_is_mostly_juggling(self, seeded):
        """One block. Juggling is not a substitute for the rest of the session."""
        for name, _day, drills in sessions(seeded):
            count = sum(1 for d in drills if d.is_juggling)
            assert count == 1, f"{name} has {count}"

    def test_every_session_has_shooting_or_dribbling(self, seeded):
        """The two things he loves and would do for the fun of it.

        Mastery and touch work are the priority and they are also the part he
        would skip if a session were nothing but them, so every day he trains
        he meets a shot or a beat-the-cone somewhere in the six.
        """
        for name, _day, drills in sessions(seeded):
            skills = {d.skill.slug for d in drills}
            assert skills & {"shooting", "dribbling"}, (
                f"{name} has neither shooting nor dribbling in it"
            )

    def test_shooting_and_dribbling_both_appear_across_the_fortnight(self, seeded):
        """The rule above, on its own, is satisfied by twelve shooting
        sessions and no dribbling at all - which is not what it is for.

        Both have to keep turning up, so neither can quietly drain out of the
        plan behind a rule that only asks for one of them.
        """
        shooting = 0
        dribbling = 0
        for _name, _day, drills in sessions(seeded):
            skills = {d.skill.slug for d in drills}
            if "shooting" in skills:
                shooting += 1
            if "dribbling" in skills:
                dribbling += 1
        assert shooting >= 5, f"only {shooting} of the 12 sessions shoot at anything"
        assert dribbling >= 5, f"only {dribbling} of the 12 sessions dribble"

    def test_every_session_starts_with_a_warm_up(self, seeded):
        """The first drill is always short ball mastery on the floor."""
        for name, _day, drills in sessions(seeded):
            first = drills[0]
            assert first.skill.slug == "ball-mastery", name
            assert first.estimated_minutes <= 5, name
            assert not first.needs_wall, name

    def test_most_warm_ups_are_combination_work(self, seeded):
        """The first block is where close control is built.

        Single moves on repeat are autopilot by nine on an elite squad, so the
        warm-up is a sequence - rollover, fake, chop - joined into one flow.
        A few simple openers stay, because the moves a combination is made of
        are still worth five minutes of their own.
        """
        combos = [
            name
            for name, _day, drills in sessions(seeded)
            if drills[0].is_combination
        ]
        assert len(combos) >= 8, (
            f"only {len(combos)} of the 12 warm-ups chain moves together"
        )

    def test_the_fortnight_never_repeats_a_warm_up(self, seeded):
        """Twelve sessions, twelve different openings.

        The warm-up is the one slot he meets every single day, so it is the
        one that goes stale first.
        """
        slugs = [drills[0].slug for _name, _day, drills in sessions(seeded)]
        repeated = sorted({s for s in slugs if slugs.count(s) > 1})
        assert not repeated, f"warm-up repeats in the fortnight: {repeated}"

    def test_every_session_ends_with_a_fun_finisher(self, seeded):
        for name, _day, drills in sessions(seeded):
            assert drills[-1].is_fun, f"{name} has no fun finisher"

    def test_every_week_uses_every_skill(self, seeded):
        """Each week on its own, not just the fortnight - a week that never
        shot at anything would be a fortnight of half the shooting practice."""
        for week in (PlanDrill.WEEK_A, PlanDrill.WEEK_B):
            used = {
                d.skill.slug
                for day in seeded.days.all()
                for d in day.drills_for_week(week)
            }
            missing = set(Skill.objects.values_list("slug", flat=True)) - used
            assert not missing, f"week {week}: unused skills {missing}"

    def test_neither_week_is_overloaded(self, seeded):
        """Total required home minutes in a week, sanity bound."""
        for week in (PlanDrill.WEEK_A, PlanDrill.WEEK_B):
            total = sum(
                d.estimated_minutes
                for day in seeded.days.all()
                if day.is_required
                for d in day.drills_for_week(week)
            )
            # Six sessions of thirty, with Sunday off.
            assert 160 <= total <= 190, f"week {week}: {total} minutes a week"


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
        for week in (PlanDrill.WEEK_A, PlanDrill.WEEK_B):
            days = [
                day
                for day in seeded.days.all()
                if any(d.skill.slug == "speed" for d in day.drills_for_week(week))
            ]
            assert len(days) == 3, f"week {week}: speed on {len(days)} days"

    def test_no_session_doubles_up_on_speed(self, seeded):
        for name, _day, drills in sessions(seeded):
            count = sum(1 for d in drills if d.skill.slug == "speed")
            assert count <= 1, f"{name} has {count} speed drills"

    def test_speed_never_replaces_the_warm_up(self, seeded):
        """Cold sprinting is how something gets pulled. Ball mastery comes first."""
        for name, _day, drills in sessions(seeded):
            assert drills[0].skill.slug != "speed", name


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

    def test_reset_rebuilds_cleanly(self, seeded, settings):
        # --reset is refused unless DEBUG is on - see TestResetIsRefused
        # below - so the developer workflow it exists for has to say so.
        settings.DEBUG = True
        call_command("seed_drills", "--reset", verbosity=0)
        assert 36 <= Drill.objects.count() <= 65
        assert TrainingPlan.objects.filter(is_active=True).count() == 1


class TestResetIsRefused:
    """--reset deletes every Drill, and SessionLog.drill is CASCADE.

    On Render the sqlite file on the persistent disk is the only copy of
    Will's history. A --reset there takes every session he has ever logged
    with it - his streak, his lifetime minutes and the counts behind his
    badges - and none of it can be typed back in. The command refuses unless
    DEBUG is on, which is only ever true on this machine.
    """

    # Catches the DEBUG guard being dropped, which puts --reset one typo away
    # from wiping the live database.
    def test_reset_is_refused_when_debug_is_off(self, seeded, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError):
            call_command("seed_drills", "--reset", verbosity=0)

    # Catches the guard being moved below the delete. The message is not the
    # point; the rows still being there afterwards is the point.
    def test_a_refused_reset_deletes_no_history(self, seeded, settings):
        settings.DEBUG = False
        will = get_user_model().objects.get(username="will")
        drill = Drill.objects.get(slug="toe-taps")
        log = SessionLog.objects.create(
            athlete=will, date=date(2026, 8, 10), drill=drill,
            completed=True, rating=4, actual_reps=42,
        )
        drills_before = Drill.objects.count()
        skills_before = Skill.objects.count()

        with pytest.raises(CommandError):
            call_command("seed_drills", "--reset", verbosity=0)

        assert SessionLog.objects.filter(pk=log.pk).exists()
        assert Drill.objects.count() == drills_before
        assert Skill.objects.count() == skills_before
        log.refresh_from_db()
        assert (log.completed, log.rating, log.actual_reps) == (True, 4, 42)

    # Catches the guard being widened into a blanket refusal, which would
    # leave no way to rebuild the drills and the plan from scratch here.
    def test_reset_still_works_in_development(self, seeded, settings):
        settings.DEBUG = True
        call_command("seed_drills", "--reset", verbosity=0)
        assert Drill.objects.filter(slug="toe-taps").exists()


class TestRetirement:
    """A drill that has left the plan is retired, never deleted.

    SessionLog.drill is CASCADE, so removing the row removes every day Will
    logged against it. Retiring sets is_active=False and leaves the drill, its
    text and his history exactly where they are.
    """

    # Catches a retired drill being cut from DRILLS instead of listed in
    # RETIRED - which would take his logged sessions with it.
    def test_retired_drills_still_exist_and_are_inactive(self, seeded):
        for slug in ("figure-eight-legs", "weak-foot-taps"):
            drill = Drill.objects.get(slug=slug)  # raises if it was deleted
            assert drill.is_active is False, slug

    # The most important test here: re-seeding over a retired drill must not
    # touch what he recorded against it.
    def test_re_seeding_keeps_the_history_logged_against_a_retired_drill(
        self, seeded
    ):
        will = get_user_model().objects.get(username="will")
        retired = Drill.objects.get(slug="figure-eight-legs")
        log = SessionLog.objects.create(
            athlete=will, date=date(2026, 8, 10), drill=retired,
            completed=True, rating=5, actual_reps=31,
        )

        call_command("seed_drills", verbosity=0)

        log.refresh_from_db()
        assert (log.completed, log.rating, log.actual_reps) == (True, 5, 31)
        assert log.drill.slug == "figure-eight-legs"

    # Catches retirement that is only idempotent once - a second deploy
    # running the seeder must not start deleting what the first one spared.
    def test_re_seeding_twice_still_keeps_it(self, seeded):
        will = get_user_model().objects.get(username="will")
        retired = Drill.objects.get(slug="weak-foot-taps")
        log = SessionLog.objects.create(
            athlete=will, date=date(2026, 8, 11), drill=retired,
            completed=True, rating=3, actual_reps=18,
        )

        call_command("seed_drills", verbosity=0)
        call_command("seed_drills", verbosity=0)

        log.refresh_from_db()
        assert (log.completed, log.rating, log.actual_reps) == (True, 3, 18)
        assert Drill.objects.get(slug="weak-foot-taps").is_active is False

    # Catches a retired drill still being served to Will. Retiring has to
    # take it out of the plan, not just flag the row.
    def test_a_retired_drill_is_not_in_any_session(self, seeded):
        for label, _day, drills in sessions(seeded):
            on_show = {d.slug for d in drills}
            assert not (on_show & RETIRED), f"{label} still runs a retired drill"


class TestSlugSets:
    """RETIRED, COMBINATIONS and JUGGLING are sets of slugs typed by hand.

    A misspelling in any of them silently does nothing - the drill is never
    retired, never flagged as juggling, never flagged as a combination - and
    every other test here still passes. These fail loudly instead.
    """

    # Catches a typo in RETIRED, which would leave an outgrown drill in the
    # plan while looking as though it had been taken out.
    def test_every_retired_slug_names_a_real_drill(self):
        unknown = RETIRED - DRILL_SLUGS
        assert not unknown, f"RETIRED names slugs that are not in DRILLS: {unknown}"

    # Catches a typo in COMBINATIONS, which would quietly leave a warm-up slot
    # without the combination the plan is counting on.
    def test_every_combination_slug_names_a_real_drill(self):
        unknown = COMBINATIONS - DRILL_SLUGS
        assert not unknown, (
            f"COMBINATIONS names slugs that are not in DRILLS: {unknown}"
        )

    # Catches a typo in JUGGLING, which would leave a session with no juggling
    # block while the flag said otherwise.
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
