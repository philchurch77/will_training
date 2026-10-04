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
    FREE_PLAY,
    GOAL_SESSIONS,
    LEVELS,
    POINTS,
    SKILL_ORDER,
    TEST_CARDS,
    WEAK_FOOT_CARDS,
    WEAK_FOOT_CLOSER,
    Row,
    calendar,
    deck_badge_values,
    history_for,
    goal_mondays,
    goal_weeks_json,
    goal_weeks_run,
    is_test_week,
    longest_run,
    rules_json,
    run_before,
    session_dates,
    skill_of_week,
)
from training.deck_views import STAMP_CEILINGS
from training.models import Badge, Card

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

    # Catches a 2b key the phone reads going missing: the week bar and the
    # test-week screen are drawn from these and nothing else.
    def test_rules_json_carries_the_goal_and_test_week_rules(self):
        rules = rules_json(date(2026, 10, 14))
        assert rules["goal_sessions"] == GOAL_SESSIONS
        assert rules["test_cards"] == TEST_CARDS
        assert rules["free_play"] == FREE_PLAY


# --- leg 2b: sessions, goal weeks and the deck's badges ----------------------

# Week 3 from BLOCKS_START is the first test week; week 7 the second.
TEST_MONDAY = date(2026, 10, 26)
NEXT_TEST_MONDAY = date(2026, 11, 23)


def row(day, card="toe-taps-30", move="", score=None, weak=None, medal=None, bests=None):
    return Row(day, card, move, score, weak, medal, bests)


def mondays(*days):
    return {date.fromisoformat(d) for d in days}


class TestSessionsAndGoalWeeks:
    # Catches free play not counting as one of the three, or the count being
    # plays rather than different cards.
    def test_a_session_is_three_different_cards_free_play_included(self):
        day = date(2026, 10, 12)
        assert session_dates([row(day, "toe-taps-30"), row(day, "corners"), row(day, FREE_PLAY)]) == {day}
        assert session_dates([row(day, "toe-taps-30")] * 3) == set()
        assert session_dates([row(day, "toe-taps-30"), row(day, "corners")]) == set()

    # Catches a goal week counted over a rolling seven days instead of one
    # Mon-Sun week.
    def test_a_goal_week_is_three_session_days_in_one_mon_sun_week(self):
        assert goal_mondays({date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14)}) == {
            date(2026, 10, 12)
        }
        # Sat, Sun, Mon: three days in a row, two weeks.
        assert goal_mondays({date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19)}) == set()

    # Catches the week still going on breaking the run: on Wednesday he has
    # not had the chance to hit this week's goal yet.
    def test_this_week_never_breaks_the_run_and_adds_one_once_hit(self):
        wednesday = date(2026, 10, 28)
        done = mondays("2026-10-12", "2026-10-19")
        assert run_before(done, wednesday) == 2
        assert goal_weeks_run(done, wednesday) == 2
        assert goal_weeks_run(done | {date(2026, 10, 26)}, wednesday) == 3

    # Catches a missed week not breaking the run.
    def test_a_missed_week_breaks_the_run(self):
        wednesday = date(2026, 10, 28)
        assert run_before(mondays("2026-10-05", "2026-10-19"), wednesday) == 1
        assert run_before(mondays("2026-10-05", "2026-10-12"), wednesday) == 0

    # Catches the badge reading the current run, which a gap would lower:
    # weeks-3 is earned by the best run ever.
    def test_longest_run_is_the_best_run_across_a_gap(self):
        assert longest_run(mondays(
            "2026-10-05", "2026-10-12", "2026-10-19", "2026-11-02", "2026-11-09",
        )) == 3
        assert longest_run(set()) == 0

    # Catches the phone's figure counting this week twice: the phone adds
    # this week from its own plays, so `before` and `total_before` stop at
    # last week.
    def test_goal_weeks_json_stops_at_last_week(self):
        done = mondays("2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26")
        assert goal_weeks_json(done, date(2026, 10, 28)) == {
            "monday": "2026-10-26", "before": 3, "total_before": 3,
        }

    # Catches a run that restarts at the turn of the year.
    def test_the_run_carries_over_the_turn_of_the_year(self):
        done = mondays("2026-12-21", "2026-12-28")
        assert run_before(done, date(2027, 1, 6)) == 2
        assert longest_run(done | {date(2027, 1, 4)}) == 3


class TestDeckBadgeValues:
    # Catches a gold on any card counting as a move gold, or a silver
    # counting at all.
    def test_move_golds_count_only_gold_on_move_cards(self):
        day = date(2026, 10, 12)
        values = deck_badge_values([
            row(day, "chop-1", move="chop", medal=3),
            row(day, "chop-1", move="chop", medal=2),
            row(day, "toe-taps-30", medal=3),
        ])
        assert values[Badge.MOVE_GOLDS] == 1

    # Catches bests being counted per play rather than per foot.
    def test_personal_bests_sum_the_bests_on_every_play(self):
        day = date(2026, 10, 12)
        values = deck_badge_values([row(day, bests=2), row(day, bests=1), row(day)])
        assert values[Badge.PERSONAL_BESTS] == 3

    # Catches test week being satisfied by six cards spread over weeks, or by
    # six cards before the blocks start.
    def test_test_week_needs_all_six_cards_inside_one_test_week(self):
        six = [row(TEST_MONDAY + timedelta(days=n % 7), card) for n, card in enumerate(TEST_CARDS)]
        assert deck_badge_values(six)[Badge.TEST_WEEKS] == 1
        five_then_one = [row(TEST_MONDAY, card) for card in TEST_CARDS[:5]] + [
            row(TEST_MONDAY + timedelta(weeks=1), TEST_CARDS[5])
        ]
        assert deck_badge_values(five_then_one)[Badge.TEST_WEEKS] == 0
        early = [row(BLOCKS_START - timedelta(days=7), card) for card in TEST_CARDS]
        assert deck_badge_values(early)[Badge.TEST_WEEKS] == 0

    # Catches the 80% bar sliding, or a missing or zero foot passing it.
    @pytest.mark.parametrize(
        "score, weak, expected",
        [(100, 80, 1), (100, 79, 0), (0, 0, 0), (100, None, 0)],
        ids=["exactly-80", "79", "strong-zero", "weak-missing"],
    )
    def test_weak_foot_closer_needs_the_weak_foot_at_80_percent(self, score, weak, expected):
        card, percent = WEAK_FOOT_CLOSER
        assert percent == 80
        values = deck_badge_values([row(TEST_MONDAY, card, score=score, weak=weak)])
        assert values[Badge.WEAK_FOOT_CLOSER] == expected

    # Catches the closer counting plays rather than test weeks, or counting
    # outside a test week at all.
    def test_weak_foot_closer_counts_test_weeks_not_plays(self):
        card, _ = WEAK_FOOT_CLOSER
        same_week = [row(TEST_MONDAY, card, score=40, weak=40), row(TEST_MONDAY + timedelta(days=2), card, score=40, weak=36)]
        assert deck_badge_values(same_week)[Badge.WEAK_FOOT_CLOSER] == 1
        two_weeks = same_week + [row(NEXT_TEST_MONDAY, card, score=40, weak=40)]
        assert deck_badge_values(two_weeks)[Badge.WEAK_FOOT_CLOSER] == 2
        not_test_week = [row(TEST_MONDAY + timedelta(weeks=1), card, score=40, weak=40)]
        assert deck_badge_values(not_test_week)[Badge.WEAK_FOOT_CLOSER] == 0

    # Catches free play being counted from any unscored play rather than the
    # free-play card.
    def test_free_plays_count_free_play_rows(self):
        day = date(2026, 10, 12)
        values = deck_badge_values([row(day, FREE_PLAY), row(day, FREE_PLAY), row(day)])
        assert values[Badge.FREE_PLAYS] == 2


@pytest.mark.django_db
class TestTestCardsExist:
    # Catches a test card renamed or retired: test week could never be done
    # and the screen would show five cards.
    def test_every_test_card_and_the_closer_card_is_active(self):
        seed_deck()
        active = set(Card.objects.active().values_list("slug", flat=True))
        assert set(TEST_CARDS) <= active
        assert len(set(TEST_CARDS)) == 6
        closer, _ = WEAK_FOOT_CLOSER
        assert closer in TEST_CARDS
        assert Card.objects.get(slug=closer).per_foot is True
        assert FREE_PLAY in active


# --- leg 3a: the head start from his old app ----------------------------------

# The head start as first shipped. Either may go up; neither may come down.
HEAD_START_FLOORS = {"per_tick": 5, "cap": 1000}


def history_drill(skill, slug, is_active=True):
    from training.models import Drill

    return Drill.objects.create(
        name=slug, slug=slug, skill=skill, instructions="Juggle.",
        cue="Toes up", target_reps=30, is_active=is_active,
    )


def logs(athlete, drill, count, start=date(2026, 1, 1), **fields):
    """`count` SessionLog rows, one a day, so the unique constraint holds."""
    from training.models import SessionLog

    SessionLog.objects.bulk_create(
        SessionLog(athlete=athlete, drill=drill, date=start + timedelta(days=n), **fields)
        for n in range(count)
    )


class TestHeadStartPure:
    # Catches the per-tick rate or the cap being applied wrongly: no ticks
    # must be no points, and the cap must hold however long his history.
    @pytest.mark.parametrize(
        "ticks, expected", [(0, 0), (3, 15), (200, 1000), (201, 1000), (10_000, 1000)]
    )
    def test_starting_points_is_five_a_tick_up_to_the_cap(self, ticks, expected):
        assert deck_rules.starting_points(ticks) == expected

    # Catches an old drill with a different count (laces-only) becoming a
    # best on a card, or a 0 becoming a best that any score then "beats".
    def test_starting_bests_drops_unmapped_drills_and_zeros(self):
        assert deck_rules.starting_bests({
            "thigh-juggles": 14,
            "weak-foot-juggles": 0,
            "alternate-foot-juggles": None,
            "juggling-laces": 50,
        }) == {"keepy-ups-thighs": {"score": 14, "weak": None}}

    # Catches the head start being lowered after he has seen it: a lower
    # rate or cap can take a level off him.
    def test_the_head_start_numbers_never_go_down(self):
        assert deck_rules.STARTING_POINTS_PER_TICK >= HEAD_START_FLOORS["per_tick"], (
            "lowering the head start takes points off him"
        )
        assert deck_rules.STARTING_POINTS_CAP >= HEAD_START_FLOORS["cap"], (
            "lowering the head start takes points off him"
        )

    # Catches the existing callers of rules_json() (no history) handing the
    # phone a missing key or a head start nobody earned.
    def test_rules_json_without_history_starts_from_nothing(self):
        rules = rules_json(date(2026, 10, 14))
        assert rules["starting_points"] == 0
        assert rules["starting_bests"] == {}


@pytest.mark.django_db
class TestHistoryFor:
    # Catches unticked rows (completed=False) earning points, or the rate
    # drifting from five a tick.
    def test_only_completed_ticks_earn_points(self, will, drill):
        logs(will, drill, 5)
        logs(will, drill, 3, start=date(2025, 1, 1), completed=False)
        assert history_for(will)["points"] == 25

    # Catches the cap not holding against a long history.
    def test_points_stop_at_the_cap(self, will, drill):
        logs(will, drill, 300)
        assert history_for(will)["points"] == 1000

    # Catches the best being the latest or the first count instead of the
    # highest, a 0 being a best, or an unticked row's count being his best.
    def test_the_best_is_his_highest_ticked_count(self, will, skill):
        thighs = history_drill(skill, "thigh-juggles")
        weak = history_drill(skill, "weak-foot-juggles")
        logs(will, thighs, 1, start=date(2026, 3, 1), actual_reps=12)
        logs(will, thighs, 1, start=date(2026, 3, 2), actual_reps=31)
        logs(will, thighs, 1, start=date(2026, 3, 3), actual_reps=20)
        logs(will, thighs, 1, start=date(2026, 3, 4), actual_reps=99, completed=False)
        logs(will, weak, 2, start=date(2026, 3, 1), actual_reps=0)
        assert history_for(will)["bests"] == {
            "keepy-ups-thighs": {"score": 31, "weak": None}
        }

    # Catches an old drill that counts something else (laces only) setting a
    # best on a card it is not the same exercise as.
    def test_an_unmapped_rep_drill_gives_no_best(self, will, skill, rep_drill):
        laces = history_drill(skill, "juggling-laces")
        logs(will, laces, 1, actual_reps=60)
        logs(will, rep_drill, 1, actual_reps=60)
        history = history_for(will)
        assert history["bests"] == {}
        assert history["points"] == 10

    # Catches retiring a drill silently taking his history with it: the
    # rows are his sessions all the same.
    def test_a_retired_mapped_drill_still_counts(self, will, skill):
        retired = history_drill(skill, "alternate-foot-juggles", is_active=False)
        logs(will, retired, 2, actual_reps=17)
        assert history_for(will) == {
            "points": 10,
            "bests": {"keepy-ups-alternate": {"score": 17, "weak": None}},
        }

    # Catches a query per log creeping in: the deck page loads this on
    # every visit, and his history only grows.
    @pytest.mark.parametrize("count", [1, 50])
    def test_the_query_count_does_not_grow_with_his_history(
        self, will, skill, count, django_assert_num_queries
    ):
        thighs = history_drill(skill, "thigh-juggles")
        logs(will, thighs, count, actual_reps=5)
        with django_assert_num_queries(2):
            history_for(will)


@pytest.mark.django_db
class TestHistoryCardsMatchTheData:
    # Catches a mapped old drill being renamed or turned into a minutes
    # drill (no count, so no best), or a mapped card retired, made per foot
    # (a single score would land on the wrong foot), or scored by time (a
    # count compared as tenths of a second).
    def test_every_mapping_is_a_seeded_rep_drill_onto_a_single_count_card(self, seeded):
        from training.models import Drill

        for drill_slug, card_slug in deck_rules.HISTORY_CARDS.items():
            old = Drill.objects.get(slug=drill_slug)
            assert old.target_reps is not None and old.duration_minutes is None, drill_slug
            card = Card.objects.active().get(slug=card_slug)
            assert card.per_foot is False, card_slug
            assert card.scoring == Card.COUNT, card_slug
