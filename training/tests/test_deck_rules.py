"""The game's numbers: levels, points, the skill of the week, rules_json.

deck_rules.py is the one home of every number the phone stamps a play with.
A stamp is written once and never worked out again, so the rules that matter
are the ones that would take something back: a level threshold going up, a
points total the server would refuse, a skill of the week before the blocks
start (a play stamped double then stays double for good).
"""

from datetime import date, timedelta

import pytest

from training import deck_data, deck_rules
from training.deck_data import seed_deck
from training.deck_rules import (
    BLOCK_WEEKS,
    BLOCKS_START,
    CALENDAR_WEEKS,
    LEVELS,
    POINTS,
    SKILL_ORDER,
    WEAK_FOOT_CARDS,
    calendar,
    is_test_week,
    rules_json,
    skill_of_week,
)
from training.deck_views import STAMP_CEILINGS
from training.models import Card

# The thresholds as first shipped. A threshold may come down, never go up.
LEVEL_CEILINGS = {
    "Grassroots": 0,
    "Academy": 300,
    "First Team": 1000,
    "Captain": 2500,
    "Legend": 5000,
}


class TestLevels:
    # Catches a level threshold being raised, which takes a level he already
    # holds off him.
    def test_no_level_threshold_goes_above_its_ceiling(self):
        for name, points in LEVELS:
            assert name in LEVEL_CEILINGS, f"new or renamed level {name!r}"
            assert points <= LEVEL_CEILINGS[name], (
                f"{name}: {LEVEL_CEILINGS[name]} -> {points}. a level threshold "
                "went up: that takes a level off him; lower it or leave it"
            )

    # Catches a level being renamed, dropped or reordered: totalPoints and
    # levelFor walk this list in order.
    def test_level_names_and_order_are_unchanged(self):
        assert [name for name, _ in LEVELS] == list(LEVEL_CEILINGS)

    # Catches two levels swapping places by threshold, or a first level he
    # has to earn before he has any level at all.
    def test_thresholds_start_at_zero_and_strictly_increase(self):
        thresholds = [points for _, points in LEVELS]
        assert thresholds[0] == 0
        assert all(a < b for a, b in zip(thresholds, thresholds[1:])), thresholds


class TestPointsFitTheStamp:
    # Catches the points table growing past what the server accepts: every
    # stamp over the ceiling is dropped to None and the play counts nothing.
    def test_the_biggest_play_fits_under_the_server_ceiling(self):
        biggest = (POINTS["base"] + POINTS["weak_foot"] + 2 * POINTS["best"]) * POINTS[
            "skill_multiplier"
        ]
        assert biggest < STAMP_CEILINGS["points"]

    # Catches a fractional multiplier: 1.5x sends a float, which the server
    # reads as a bad stamp and drops.
    def test_every_points_value_is_a_whole_number(self):
        for key, value in POINTS.items():
            assert isinstance(value, int) and not isinstance(value, bool), key


@pytest.mark.django_db
class TestRulesMatchTheCards:
    # Catches SKILL_ORDER drifting from the moves the deck actually has.
    def test_skill_order_is_the_moves_in_order(self):
        assert SKILL_ORDER == [move[0] for move in deck_data.MOVES]

    # Catches a skill of the week with no card to play: deal() would have no
    # double-points card to put in his hand.
    def test_every_skill_of_the_week_has_three_active_levels(self, db):
        seed_deck()
        for move in SKILL_ORDER:
            levels = set(
                Card.objects.active().filter(move=move).values_list("level", flat=True)
            )
            assert levels == {1, 2, 3}, move

    # Catches a weak-foot bonus card that does not exist, or was retired.
    def test_weak_foot_cards_are_active_cards(self, db):
        seed_deck()
        for slug in WEAK_FOOT_CARDS:
            assert Card.objects.active().filter(slug=slug).exists(), slug


class TestSkillOfTheWeek:
    # Catches Python's modulo handing out a move before the blocks start: a
    # play stamped double then would stay double for good.
    def test_nothing_counts_double_before_the_blocks_start(self):
        saturday = date(2026, 10, 3)
        assert skill_of_week(saturday) is None
        assert is_test_week(saturday) is False
        assert skill_of_week(BLOCKS_START - timedelta(days=1)) is None

    # Catches the anchor or the order slipping by a week.
    def test_the_first_weeks_follow_the_order(self):
        assert BLOCKS_START == date(2026, 10, 5)
        assert skill_of_week(date(2026, 10, 5)) == "chop"
        assert is_test_week(date(2026, 10, 5)) is False
        assert skill_of_week(date(2026, 10, 12)) == "drag-back"
        assert skill_of_week(date(2026, 10, 26)) == "matthews"
        assert is_test_week(date(2026, 10, 26)) is True
        assert skill_of_week(date(2026, 11, 2)) == "outside-hook"
        assert is_test_week(date(2026, 11, 2)) is False

    # Catches the order not repeating after the eighth move.
    def test_eight_weeks_on_wraps_back_to_the_first_move(self):
        start = date(2026, 10, 5) + timedelta(weeks=len(SKILL_ORDER))
        assert skill_of_week(start) == "chop"

    # Catches a week split in two: Sunday and Monday disagreeing would make
    # one play double and the next not, in the same week.
    def test_every_day_of_a_week_gives_the_same_answer(self):
        for monday in (date(2026, 10, 5), date(2026, 10, 26), date(2027, 3, 1)):
            days = [monday + timedelta(days=n) for n in range(7)]
            assert len({skill_of_week(d) for d in days}) == 1, monday
            assert len({is_test_week(d) for d in days}) == 1, monday

    # Catches a week index that restarts with the year.
    def test_the_turn_of_the_year_keeps_counting(self):
        before, after = date(2026, 12, 28), date(2027, 1, 4)
        assert skill_of_week(before) == SKILL_ORDER[12 % len(SKILL_ORDER)]
        assert skill_of_week(after) == SKILL_ORDER[13 % len(SKILL_ORDER)]
        assert skill_of_week(before) != skill_of_week(after)
        assert is_test_week(date(2027, 1, 18)) is (15 % BLOCK_WEEKS == BLOCK_WEEKS - 1)


class TestCalendarAndRulesJson:
    # Catches the baked calendar starting mid-week or skipping a week: the
    # phone looks its week up by the Monday string and would find nothing.
    def test_calendar_is_consecutive_mondays_from_the_monday(self):
        weeks = calendar(date(2026, 10, 8))
        assert len(weeks) == CALENDAR_WEEKS
        mondays = [date.fromisoformat(w["monday"]) for w in weeks]
        assert mondays[0] == date(2026, 10, 5)
        assert all(m.weekday() == 0 for m in mondays)
        assert all(b - a == timedelta(weeks=1) for a, b in zip(mondays, mondays[1:]))
        assert weeks[0]["move"] == "chop"

    # Catches a key the phone reads going missing, or starting points that
    # hand him a level he did not earn.
    def test_rules_json_carries_everything_the_phone_reads(self):
        today = date(2026, 10, 14)
        rules = rules_json(today)
        assert set(rules) >= {
            "points", "weak_foot_cards", "levels", "session_cards",
            "calendar", "starting_points",
        }
        assert rules["starting_points"] == 0
        assert rules["points"] == POINTS
        assert [lvl["name"] for lvl in rules["levels"]] == list(LEVEL_CEILINGS)

    # Catches the calendar starting this week: a phone either side of
    # midnight on a Monday would not find its week.
    def test_rules_json_calendar_covers_last_week(self):
        today = date(2026, 10, 14)
        mondays = [w["monday"] for w in rules_json(today)["calendar"]]
        assert mondays[0] == deck_rules.monday_of(today - timedelta(weeks=1)).isoformat()
        assert deck_rules.monday_of(today).isoformat() in mondays
