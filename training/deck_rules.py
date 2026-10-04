"""The game's numbers, in one place.

Every number the deck's game uses lives here and reaches the phone baked into
/deck/ as the `deck-rules` block (rules_json). deck.js keeps no copies of its
own: there is no JavaScript test runner in this project, so a number written
in both places could drift with nothing to notice.

The phone uses these to stamp a play when he saves it - points, medal, bests,
stored on the play and never worked out again (see Play). So:

* Changing a points value or a medal target changes plays from then on, and
  never takes back one already made.
* A level threshold may be lowered, never raised. Raising one takes a level
  off him. test_deck_rules.py holds the ceilings.

Pure functions that take the date, like progress.py: the tests pin dates.
See docs/chart/deck.md, "Leg 2 decisions", for why each number is what it is.
"""

from collections import defaultdict, namedtuple
from datetime import date, timedelta

from .deck_data import MOVES

# Points for one play. A per-foot card, or a weak-foot-only one, earns the
# weak-foot bonus: the bonus is for doing weak-foot work at all. Each foot
# that beats his best (not a first score) earns the best bonus. The whole
# play doubles when the card is a level of the skill of the week's move.
POINTS = {
    "base": 10,
    "weak_foot": 5,
    "best": 20,
    "skill_multiplier": 2,
}
WEAK_FOOT_CARDS = ["keepy-ups-weak"]  # on top of every per-foot card

# Player levels by total points. Lower a threshold if you like; never raise one.
LEVELS = [
    ("Grassroots", 0),
    ("Academy", 300),
    ("First Team", 1000),
    ("Captain", 2500),
    ("Legend", 5000),
]

# The skill of the week: one move a week, in the order of MOVES (the research
# doc's two four-week blocks), repeating. Every fourth week is test week, and
# its move still counts double.
SKILL_ORDER = [move[0] for move in MOVES]
BLOCKS_START = date(2026, 10, 5)  # a Monday
BLOCK_WEEKS = 4

# A deck session is this many different cards on one day; free play is one
# card like any other. A goal week is GOAL_SESSIONS sessions in a Mon-Sun week.
# deck.js counts sessions too, for the weekly bar - the one rule written in
# both places. Change both.
SESSION_CARDS = 3
GOAL_SESSIONS = 3
FREE_PLAY = "free-play"

# Test week: all six of these played in one test week. Weak foot closer: the
# first card, in a test week, with the weak foot at least this percentage of
# the strong one.
TEST_CARDS = [
    "toe-taps-30",
    "foundations-30",
    "rebounder-two-touch",
    "slalom-race",
    "corners",
    "keepy-ups-best",
]
WEAK_FOOT_CLOSER = ("rebounder-two-touch", 80)

# Weeks of calendar baked into the page. A phone offline for longer than this
# simply shows no skill of the week until it next loads with signal.
CALENDAR_WEEKS = 60


def monday_of(day):
    return day - timedelta(days=day.weekday())


def week_index(day):
    """Weeks since BLOCKS_START, counting from 0. Negative before it."""
    return (monday_of(day) - BLOCKS_START).days // 7


def skill_of_week(day):
    """The move slug that counts double in the week containing `day`.

    None before BLOCKS_START: Python's modulo would happily give a move for
    week -1, and a play stamped double then would stay double for good.
    """
    index = week_index(day)
    if index < 0:
        return None
    return SKILL_ORDER[index % len(SKILL_ORDER)]


def is_test_week(day):
    index = week_index(day)
    return index >= 0 and index % BLOCK_WEEKS == BLOCK_WEEKS - 1


def calendar(from_day, weeks=CALENDAR_WEEKS):
    """One entry per week from the Monday of `from_day`: monday, move, test."""
    start = monday_of(from_day)
    out = []
    for n in range(weeks):
        monday = start + timedelta(weeks=n)
        out.append({
            "monday": monday.isoformat(),
            "move": skill_of_week(monday),
            "test": is_test_week(monday),
        })
    return out


def rules_json(today, history=None):
    """Everything the phone needs to stamp plays and draw the game.

    `history` is history_for(athlete): his head start from the old app.
    Without it, he starts from nothing.
    """
    history = history or {"points": 0, "bests": {}}
    return {
        "points": POINTS,
        "weak_foot_cards": WEAK_FOOT_CARDS,
        "levels": [{"name": name, "points": points} for name, points in LEVELS],
        "session_cards": SESSION_CARDS,
        "goal_sessions": GOAL_SESSIONS,
        "test_cards": TEST_CARDS,
        "free_play": FREE_PLAY,
        # A week back, so a phone whose clock sits either side of midnight on
        # a Monday still finds its week.
        "calendar": calendar(today - timedelta(weeks=1)),
        # His head start from the old app (leg 3a): points for the drills he
        # ticked, and his old best on the cards that are the same exercise.
        "starting_points": history["points"],
        "starting_bests": history["bests"],
    }


# --- the head start: his old app's history ----------------------------------
# Worked out from his SessionLog rows every time the deck loads and written
# nowhere, so it cannot be got wrong and days he trains on Today before the
# switch-over still count. See docs/chart/deck.md, "Leg 3 decisions".

# Points per old drill he ticked, and the most the old app can give him. Once
# he has seen his head start these may go up, never down: lowering either
# could take a level off him. Unticking a drill on Today (drill_uncomplete
# deletes the row) lowers it by 5 below the cap - a same-day undo of his own,
# accepted, and gone when 3d retires the tick endpoints. The same goes for
# his inherited best: a count edited on Coach -> His sessions, or unticked,
# moves the number shown on the card. Stamps already made never change.
STARTING_POINTS_PER_TICK = 5
STARTING_POINTS_CAP = 1000

# The only old drills that are the same exercise as a card, so his old best
# is a fair score to beat. Everything else either has no count, or counts
# something different (laces-only juggling is not "any way you like").
HISTORY_CARDS = {
    "thigh-juggles": "keepy-ups-thighs",
    "weak-foot-juggles": "keepy-ups-weak",
    "alternate-foot-juggles": "keepy-ups-alternate",
}


def starting_points(ticks):
    return min(ticks * STARTING_POINTS_PER_TICK, STARTING_POINTS_CAP)


def starting_bests(drill_bests):
    """{old drill slug: best count} to {card slug: {"score", "weak"}}.

    The three mapped cards are not per foot, so the best is the score. A 0 is
    never a best to beat.
    """
    return {
        HISTORY_CARDS[slug]: {"score": best, "weak": None}
        for slug, best in drill_bests.items()
        if slug in HISTORY_CARDS and best
    }


def history_for(athlete):
    """His head start. Two queries, whatever the size of his history; drills
    since retired still count - they are his sessions all the same."""
    from django.db.models import Max

    from .models import SessionLog

    logs = SessionLog.objects.filter(athlete=athlete, completed=True)
    bests = dict(
        logs.filter(drill__slug__in=HISTORY_CARDS, actual_reps__gt=0)
        .values("drill__slug")
        .annotate(best=Max("actual_reps"))
        .values_list("drill__slug", "best")
    )
    return {"points": starting_points(logs.count()), "bests": starting_bests(bests)}


# --- history: sessions, goal weeks, badges ----------------------------------
# Worked out on the server from his Play rows, for the badges awarded at sync.
# Pure functions over plain rows, so the tests need no database.
#
# The badges trust the stamps (medal, bests) the phone wrote: working them
# out again here would write the medal and best rules a second time, and could
# disagree with levels the same gold has already opened on the phone.
# _parse_stamp in deck_views.py holds the checks that stay true whatever the
# targets become. See docs/chart/deck.md, "Leg 2b decisions".

Row = namedtuple("Row", "date card move score weak_score medal bests")


def session_dates(rows):
    """Days with at least SESSION_CARDS different cards played."""
    cards = defaultdict(set)
    for row in rows:
        cards[row.date].add(row.card)
    return {day for day, slugs in cards.items() if len(slugs) >= SESSION_CARDS}


def goal_mondays(dates):
    """Mondays of weeks with at least GOAL_SESSIONS session days."""
    per_week = defaultdict(int)
    for day in dates:
        per_week[monday_of(day)] += 1
    return {monday for monday, n in per_week.items() if n >= GOAL_SESSIONS}


def run_before(mondays, today):
    """Goal weeks in a row, ending the week before this one."""
    week = monday_of(today) - timedelta(weeks=1)
    run = 0
    while week in mondays:
        run += 1
        week -= timedelta(weeks=1)
    return run


def goal_weeks_run(mondays, today):
    """The run as it stands. This week adds one once it is a goal week, and
    never breaks the run while it is still going on."""
    return run_before(mondays, today) + (1 if monday_of(today) in mondays else 0)


def longest_run(mondays):
    best = run = 0
    previous = None
    for monday in sorted(mondays):
        run = run + 1 if previous and monday - previous == timedelta(weeks=1) else 1
        best = max(best, run)
        previous = monday
    return best


def goal_weeks_json(mondays, today):
    """What the phone needs to show weeks in a row: the run up to last week.
    The phone adds this week itself, from its own plays, so it is right
    offline. `monday` says which week `before` was worked out for."""
    this_monday = monday_of(today)
    return {
        "monday": this_monday.isoformat(),
        "before": run_before(mondays, today),
        "total_before": sum(1 for m in mondays if m < this_monday),
    }


def deck_badge_values(rows):
    """The value of each deck badge kind, from every play he has made."""
    from .models import Badge, Play

    rows = list(rows)
    mondays = goal_mondays(session_dates(rows))
    test_weeks = defaultdict(set)
    closer_card, closer_percent = WEAK_FOOT_CLOSER
    closer = set()  # test weeks in which he closed the gap - one each
    for row in rows:
        if not is_test_week(row.date):
            continue
        test_weeks[monday_of(row.date)].add(row.card)
        if (
            row.card == closer_card
            and row.score
            and row.weak_score is not None
            and row.weak_score * 100 >= closer_percent * row.score
        ):
            closer.add(monday_of(row.date))
    return {
        # The best run ever, because a badge is permanent.
        Badge.GOAL_WEEKS_RUN: longest_run(mondays),
        Badge.GOAL_WEEKS_TOTAL: len(mondays),
        Badge.MOVE_GOLDS: sum(1 for r in rows if r.move and r.medal == Play.GOLD),
        Badge.PERSONAL_BESTS: sum(r.bests or 0 for r in rows),
        Badge.TEST_WEEKS: sum(1 for slugs in test_weeks.values() if set(TEST_CARDS) <= slugs),
        Badge.WEAK_FOOT_CLOSER: len(closer),
        Badge.FREE_PLAYS: sum(1 for r in rows if r.card == FREE_PLAY),
    }


# --- reads and writes the database ------------------------------------------


def deck_rows(athlete):
    """Every play he has made as Rows, retired cards included - a badge
    reads his whole record, and retiring a card must not take one away."""
    from .models import Play

    return [
        Row(*values)
        for values in Play.objects.filter(athlete=athlete).values_list(
            "date", "card__slug", "card__move", "score", "weak_score", "medal", "bests"
        )
    ]


def goal_weeks_for(athlete, today):
    return goal_weeks_json(goal_mondays(session_dates(deck_rows(athlete))), today)


def award_deck_badges(athlete, today):
    """Award any deck badge newly earned. Returns the badges awarded now.

    Never deletes or revokes: already earned stays earned. Each award is made
    in its own savepoint, so two syncs racing to award the same badge leave
    one row and no error - the unique constraint decides, never a get().
    """
    from django.db import IntegrityError, transaction

    from .models import Badge, EarnedBadge

    values = deck_badge_values(deck_rows(athlete))
    already = set(
        EarnedBadge.objects.filter(athlete=athlete).values_list("badge_id", flat=True)
    )
    newly = []
    for badge in Badge.objects.filter(is_active=True, kind__in=Badge.DECK_KINDS):
        if badge.id in already or values.get(badge.kind, 0) < badge.threshold:
            continue
        try:
            with transaction.atomic():
                EarnedBadge.objects.create(athlete=athlete, badge=badge, earned_on=today)
        except IntegrityError:
            continue
        newly.append(badge)
    return newly
