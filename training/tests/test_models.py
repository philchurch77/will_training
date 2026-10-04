import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from training.models import Drill, PlanDrill, SessionLog, get_athlete

from .conftest import MONDAY

pytestmark = pytest.mark.django_db


class TestDrillTarget:
    """A drill is measured in minutes or in reps - never both, never neither."""

    def test_minutes_only_is_fine(self, drill):
        assert drill.is_timed
        assert drill.target_label == "5 min"

    def test_reps_only_is_fine(self, rep_drill):
        assert not rep_drill.is_timed
        assert rep_drill.target_label == "30 reps"

    def test_neither_is_rejected_by_the_database(self, skill):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Drill.objects.create(
                    name="Broken", slug="broken", skill=skill,
                    instructions="x", cue="y",
                )

    def test_both_is_rejected_by_the_database(self, skill):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Drill.objects.create(
                    name="Broken", slug="broken2", skill=skill,
                    instructions="x", cue="y",
                    duration_minutes=5, target_reps=20,
                )

    def test_clean_rejects_both(self, skill):
        bad = Drill(
            name="Broken", slug="broken3", skill=skill, instructions="x", cue="y",
            duration_minutes=5, target_reps=20,
        )
        with pytest.raises(ValidationError):
            bad.clean()

    def test_clean_rejects_neither(self, skill):
        bad = Drill(name="Broken", slug="broken4", skill=skill, instructions="x", cue="y")
        with pytest.raises(ValidationError):
            bad.clean()

    def test_rep_drills_count_as_five_minutes(self, rep_drill, drill):
        assert rep_drill.estimated_minutes == 5
        assert drill.estimated_minutes == 5


class TestSessionLog:
    def test_one_log_per_drill_per_day(self, will, drill):
        SessionLog.objects.create(athlete=will, date=MONDAY, drill=drill)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SessionLog.objects.create(athlete=will, date=MONDAY, drill=drill)

    def test_same_drill_on_a_different_day_is_fine(self, will, drill):
        SessionLog.objects.create(athlete=will, date=MONDAY, drill=drill)
        SessionLog.objects.create(athlete=will, date=MONDAY.replace(day=11), drill=drill)
        assert SessionLog.objects.count() == 2

    def test_minutes_counted_falls_back_to_the_drill(self, will, drill):
        log = SessionLog.objects.create(athlete=will, date=MONDAY, drill=drill)
        assert log.minutes_counted == 5

    def test_minutes_counted_prefers_what_he_actually_did(self, will, drill):
        log = SessionLog.objects.create(
            athlete=will, date=MONDAY, drill=drill, actual_minutes=9
        )
        assert log.minutes_counted == 9


class TestGetAthlete:
    def test_finds_the_athlete(self, will):
        assert get_athlete() == will

    def test_returns_none_when_there_is_nobody(self, db):
        assert get_athlete() is None
