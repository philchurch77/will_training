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

# A deck session is this many different cards on one day.
SESSION_CARDS = 3

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


def rules_json(today):
    """Everything the phone needs to stamp plays and draw the game."""
    return {
        "points": POINTS,
        "weak_foot_cards": WEAK_FOOT_CARDS,
        "levels": [{"name": name, "points": points} for name, points in LEVELS],
        "session_cards": SESSION_CARDS,
        # A week back, so a phone whose clock sits either side of midnight on
        # a Monday still finds its week.
        "calendar": calendar(today - timedelta(weeks=1)),
        # Where leg 3 puts the points his old history converts into.
        "starting_points": 0,
    }
