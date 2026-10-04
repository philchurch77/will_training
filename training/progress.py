"""His history from before the cards, and the kept badges' award step.

The fixed plan was retired in leg 3d. What it left - SessionLog, SessionClock
and the drills - no longer grows, and these functions read it for Before the
cards, the head start and the kept badges. Nothing here calls date.today():
the tests pin dates.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max

from . import deck_rules
from .models import Badge, Drill, EarnedBadge, SessionClock, SessionLog, Skill

DONE = "done"
REST = "rest"
MISSED = "missed"

# The plan's rest days as they stood when it was retired: Monday to Saturday
# required, Sunday rest. Frozen here because the streak used to read them from
# the active plan, and with no plan every missed day would read as rest - his
# best streak would quietly join every day he ever trained into one run.
REST_WEEKDAYS = frozenset({6})


def completed_dates(athlete):
    """Set of dates on which the athlete completed at least one drill."""
    return set(
        SessionLog.objects.filter(athlete=athlete, completed=True)
        .values_list("date", flat=True)
        .distinct()
    )


def day_state(day, done_dates):
    """Classify a single day as done, rest or missed.

    A day counts as *done* if Will completed any drill at all. A rest day
    neither extends a streak nor breaks it.
    """
    if day in done_dates:
        return DONE
    if day.weekday() in REST_WEEKDAYS:
        return REST
    return MISSED


def longest_streak(athlete):
    """Best run of training days he has ever put together."""
    done_dates = completed_dates(athlete)
    if not done_dates:
        return 0

    best = 0
    run = 0
    day = min(done_dates)
    last = max(done_dates)
    while day <= last:
        state = day_state(day, done_dates)
        if state == DONE:
            run += 1
            best = max(best, run)
        elif state == MISSED:
            run = 0
        day += timedelta(days=1)
    return best


def drills_completed(athlete):
    return SessionLog.objects.filter(athlete=athlete, completed=True).count()


def personal_best(athlete, drill):
    """His best count on a rep drill, or None if he has never counted one."""
    if drill.is_timed:
        return None
    logs = SessionLog.objects.filter(
        athlete=athlete, drill=drill, completed=True, actual_reps__isnull=False
    )
    return logs.aggregate(best=Max("actual_reps"))["best"]


def best_scores(athlete):
    """Every rep drill he has a score on, best first. His record board.

    Only drills he has actually counted appear - a board of empty rows is not
    a thing to be proud of. Retired drills included: a record is his for good,
    and 3d retires every drill.
    """
    rows = []
    for drill in Drill.objects.filter(target_reps__isnull=False):
        best = personal_best(athlete, drill)
        if best:
            rows.append({"drill": drill, "best": best, "target": drill.target_reps})
    rows.sort(key=lambda row: (-row["best"], row["drill"].name))
    return rows


def juggling_sessions(athlete):
    return SessionLog.objects.filter(
        athlete=athlete, completed=True, drill__is_juggling=True
    ).count()


def weak_foot_sessions(athlete):
    return SessionLog.objects.filter(
        athlete=athlete, completed=True, drill__weak_foot=True
    ).count()


def skills_tried(athlete):
    return (
        SessionLog.objects.filter(athlete=athlete, completed=True)
        .values("drill__skill")
        .distinct()
        .count()
    )


def clocked_minutes(athlete):
    """date -> minutes the session clock actually recorded, for days it ran."""
    return {
        row.date: row.minutes
        for row in SessionClock.objects.filter(athlete=athlete, seconds__gt=0)
    }


def _minutes_per_log(athlete, since=None):
    """Yield (log, minutes) for every completed drill.

    There are two ways a day can be measured, and this is the only place that
    knows the difference:

    * He ran the session clock. The day is worth what the clock says, shared
      out across the drills he ticked in proportion to their planned length.
      The total and the per-skill chart then tell the same story.
    * He did not - which is every day before the clock existed. Each drill is
      worth its planned length, exactly as it always was, so his history keeps
      the totals it has always had.

    Clock time on a day with no ticks counts for nothing. A phone left running
    in the kitchen is not a session.
    """
    logs = SessionLog.objects.filter(athlete=athlete, completed=True)
    if since is not None:
        logs = logs.filter(date__gte=since)
    logs = list(logs.select_related("drill", "drill__skill"))

    clocked = clocked_minutes(athlete)
    planned = {}
    for log in logs:
        planned[log.date] = planned.get(log.date, 0) + log.minutes_counted

    for log in logs:
        actual = clocked.get(log.date)
        if actual and planned[log.date]:
            yield log, actual * log.minutes_counted / planned[log.date]
        else:
            yield log, log.minutes_counted


def total_minutes(athlete):
    return round(sum(minutes for _log, minutes in _minutes_per_log(athlete)))


def minutes_by_skill(athlete, since=None):
    """Minutes trained per skill category, for the Progress bar chart.

    Returns a list of dicts sorted by the skill's own display order, including
    skills with zero minutes - the neglected ones are the whole point of the
    chart.
    """

    totals = {}
    for log, minutes in _minutes_per_log(athlete, since=since):
        totals[log.drill.skill_id] = totals.get(log.drill.skill_id, 0) + minutes

    rows = []
    for skill in Skill.objects.all():
        rows.append(
            {
                "skill": skill,
                "minutes": round(totals.get(skill.id, 0)),
            }
        )
    peak = max([row["minutes"] for row in rows], default=0)
    for row in rows:
        row["percent"] = round(row["minutes"] / peak * 100) if peak else 0
    return rows


def kept_badge_values(athlete, rows=None):
    """The kept old badges' values: old ticks and card plays added together.

    The one place that knows the rule (leg 3b), read by a tick on Today and by
    a deck sync alike, so the two can never disagree. A card-day counts as one
    tick (deck_rules.kept_counts_from_plays). All rounder takes the larger of skills
    tried and packs played, never the sum: they are two lists of the same
    idea. `rows` saves reading his plays twice when the caller has them.
    """
    if rows is None:
        rows = deck_rules.deck_rows(athlete)
    plays = deck_rules.kept_counts_from_plays(rows)
    return {
        Badge.TOTAL_DRILLS: drills_completed(athlete) + plays[Badge.TOTAL_DRILLS],
        Badge.SKILLS_TRIED: max(skills_tried(athlete), plays[Badge.SKILLS_TRIED]),
        Badge.WEAK_FOOT: weak_foot_sessions(athlete) + plays[Badge.WEAK_FOOT],
        Badge.JUGGLING: juggling_sessions(athlete) + plays[Badge.JUGGLING],
    }


def award(athlete, values, kinds, today):
    """Award every active badge of `kinds` whose value has reached its
    threshold and that he does not hold yet. Returns the badges awarded now.

    The one award step, called at sync (deck_rules.award_deck_badges) - since
    leg 3d there is no tick to award from. Never deletes or revokes, and never
    a retired badge. Each award is made in its own savepoint, so two syncs
    racing to the same badge leave one row and no error - the unique
    constraint decides, never a get().
    """
    already = set(
        EarnedBadge.objects.filter(athlete=athlete).values_list("badge_id", flat=True)
    )
    newly = []
    for badge in Badge.objects.filter(is_active=True, kind__in=kinds):
        if badge.id in already or values.get(badge.kind, 0) < badge.threshold:
            continue
        try:
            with transaction.atomic():
                EarnedBadge.objects.create(athlete=athlete, badge=badge, earned_on=today)
        except IntegrityError:
            continue
        newly.append(badge)
    return newly


