"""Shared fixtures.

Dates are pinned everywhere. MONDAY is a real Monday, so weekday arithmetic in
the tests lines up with the seeded plan.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model

from training.models import Drill, PlanDay, PlanDrill, Skill, TrainingPlan

MONDAY = date(2026, 8, 10)  # a Monday
TUESDAY = date(2026, 8, 11)
WEDNESDAY = date(2026, 8, 12)
THURSDAY = date(2026, 8, 13)
FRIDAY = date(2026, 8, 14)
SATURDAY = date(2026, 8, 15)
SUNDAY = date(2026, 8, 16)


@pytest.fixture
def will(db):
    user = get_user_model().objects.create(
        username="will", first_name="Will", is_staff=False
    )
    user.set_password("1234")
    user.save()
    return user


@pytest.fixture
def skill(db):
    # get_or_create so this composes with the `seeded` fixture, which also
    # creates the real ball-mastery skill.
    return Skill.objects.get_or_create(
        slug="ball-mastery", defaults={"name": "Ball mastery", "order": 1}
    )[0]


@pytest.fixture
def drill(skill):
    return Drill.objects.create(
        name="Toe taps",
        slug="test-toe-taps",
        skill=skill,
        instructions="Tap the ball.",
        cue="Quick feet",
        duration_minutes=5,
    )


@pytest.fixture
def rep_drill(skill):
    return Drill.objects.create(
        name="Juggling",
        slug="test-juggling",
        skill=skill,
        instructions="Juggle the ball.",
        cue="Toes up",
        target_reps=30,
    )


@pytest.fixture
def plan(db, drill):
    """A plan where Mon-Fri are required, Sat is optional and Sun is rest."""
    plan = TrainingPlan.objects.create(name="Test week", is_active=True)
    for weekday in range(5):
        day = PlanDay.objects.create(
            plan=plan, weekday=weekday, label="Session", target_minutes=25
        )
        PlanDrill.objects.create(plan_day=day, drill=drill, order=1)

    optional = PlanDay.objects.create(
        plan=plan, weekday=5, label="Match day", is_optional=True, target_minutes=10
    )
    PlanDrill.objects.create(plan_day=optional, drill=drill, order=1)

    PlanDay.objects.create(
        plan=plan, weekday=6, label="Rest", is_rest=True, target_minutes=0
    )
    return plan


@pytest.fixture
def seeded(db):
    """The real starter data, as the seed command produces it."""
    from django.core.management import call_command

    call_command("seed_drills", verbosity=0)
    return TrainingPlan.get_active()
