"""Streak, stats and badge logic.

Every function takes the reference date explicitly rather than calling
date.today() internally, so the tests can pin a date and the behaviour around
month ends and rest days is provable.
"""

from datetime import timedelta


from .models import Badge, EarnedBadge, SessionLog, Skill, TrainingPlan

# How far back current_streak() will walk before giving up. A 9-year-old is not
# going to beat this, and it stops a pathological loop if data goes strange.
MAX_STREAK_LOOKBACK_DAYS = 800

DONE = "done"
REST = "rest"
MISSED = "missed"


def plan_day_for(day, plan=None):
    """The PlanDay covering a given date, or None if there is no active plan."""
    plan = plan or TrainingPlan.get_active()
    if plan is None:
        return None
    return plan.days.filter(weekday=day.weekday()).first()


def completed_dates(athlete):
    """Set of dates on which the athlete completed at least one drill."""
    return set(
        SessionLog.objects.filter(athlete=athlete, completed=True)
        .values_list("date", flat=True)
        .distinct()
    )


def day_state(day, done_dates, plan=None):
    """Classify a single day as done, rest or missed.

    A day counts as *done* if Will completed any drill at all. That is
    deliberately generous: ticking one drill should keep a streak alive.

    Rest days and optional days (academy, match day) are *rest*: they neither
    extend a streak nor break it. He cannot lose a streak by resting when the
    plan told him to rest.
    """
    if day in done_dates:
        return DONE
    plan_day = plan_day_for(day, plan)
    if plan_day is None or not plan_day.is_required:
        return REST
    return MISSED


def current_streak(athlete, today):
    """Consecutive training days up to today.

    Today not being done yet does not break the streak - otherwise it would
    read zero every morning, which is exactly when he needs to see it.
    """
    done_dates = completed_dates(athlete)
    plan = TrainingPlan.get_active()

    streak = 0
    day = today
    for offset in range(MAX_STREAK_LOOKBACK_DAYS):
        state = day_state(day, done_dates, plan)
        if state == DONE:
            streak += 1
        elif state == MISSED:
            # Today being incomplete is not a miss yet - he still has the
            # rest of the day. Any earlier miss ends the streak.
            if offset > 0:
                break
        day -= timedelta(days=1)
    return streak


def longest_streak(athlete):
    """Best run of training days he has ever put together."""
    done_dates = completed_dates(athlete)
    if not done_dates:
        return 0
    plan = TrainingPlan.get_active()

    best = 0
    run = 0
    day = min(done_dates)
    last = max(done_dates)
    while day <= last:
        state = day_state(day, done_dates, plan)
        if state == DONE:
            run += 1
            best = max(best, run)
        elif state == MISSED:
            run = 0
        day += timedelta(days=1)
    return best


def sessions_this_month(athlete, today):
    """Number of days this calendar month with at least one completed drill."""
    return (
        SessionLog.objects.filter(
            athlete=athlete,
            completed=True,
            date__year=today.year,
            date__month=today.month,
        )
        .values("date")
        .distinct()
        .count()
    )


def drills_completed(athlete):
    return SessionLog.objects.filter(athlete=athlete, completed=True).count()


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


def total_minutes(athlete):
    return sum(
        log.minutes_counted
        for log in SessionLog.objects.filter(
            athlete=athlete, completed=True
        ).select_related("drill")
    )


def minutes_by_skill(athlete, since=None):
    """Minutes trained per skill category, for the Progress bar chart.

    Returns a list of dicts sorted by the skill's own display order, including
    skills with zero minutes - the neglected ones are the whole point of the
    chart.
    """

    logs = SessionLog.objects.filter(athlete=athlete, completed=True)
    if since is not None:
        logs = logs.filter(date__gte=since)

    totals = {}
    for log in logs.select_related("drill", "drill__skill"):
        totals[log.drill.skill_id] = totals.get(log.drill.skill_id, 0) + log.minutes_counted

    rows = []
    for skill in Skill.objects.all():
        rows.append(
            {
                "skill": skill,
                "minutes": totals.get(skill.id, 0),
            }
        )
    peak = max([row["minutes"] for row in rows], default=0)
    for row in rows:
        row["percent"] = round(row["minutes"] / peak * 100) if peak else 0
    return rows


def badge_progress(athlete, today):
    """Every badge, annotated with whether it is earned and how close he is."""
    earned = {
        eb.badge_id: eb for eb in EarnedBadge.objects.filter(athlete=athlete)
    }
    values = _badge_values(athlete, today)

    rows = []
    for badge in Badge.objects.all():
        value = values.get(badge.kind, 0)
        rows.append(
            {
                "badge": badge,
                "earned": badge.id in earned,
                "earned_on": earned[badge.id].earned_on if badge.id in earned else None,
                "value": value,
                "percent": min(100, round(value / badge.threshold * 100))
                if badge.threshold
                else 0,
            }
        )
    return rows


def _badge_values(athlete, today):
    """Current value of each badge metric."""
    return {
        Badge.STREAK: current_streak(athlete, today),
        Badge.TOTAL_DRILLS: drills_completed(athlete),
        Badge.SKILLS_TRIED: skills_tried(athlete),
        Badge.TOTAL_MINUTES: total_minutes(athlete),
        Badge.WEAK_FOOT: weak_foot_sessions(athlete),
    }


def award_badges(athlete, today):
    """Create EarnedBadge rows for anything newly earned.

    Returns the list of badges earned by this call, so the Today screen can pop
    a celebration card. Existing awards are never duplicated or revoked.
    """
    values = _badge_values(athlete, today)
    already = set(
        EarnedBadge.objects.filter(athlete=athlete).values_list("badge_id", flat=True)
    )

    newly = []
    for badge in Badge.objects.all():
        if badge.id in already:
            continue
        if values.get(badge.kind, 0) >= badge.threshold:
            EarnedBadge.objects.create(athlete=athlete, badge=badge, earned_on=today)
            newly.append(badge)
    return newly


def session_for(day, plan=None):
    """The PlanDay and its ordered drills for a given date.

    Returns (plan_day, drills). Both may be empty if no plan is active or the
    day is a rest day.
    """
    plan_day = plan_day_for(day, plan)
    if plan_day is None:
        return None, []
    items = (
        plan_day.items.select_related("drill", "drill__skill")
        .filter(drill__is_active=True)
        .order_by("order", "pk")
    )
    return plan_day, [item.drill for item in items]


def today_summary(athlete, today):
    """Everything the Today screen needs, in one place."""
    plan_day, drills = session_for(today)
    done_slugs = set(
        SessionLog.objects.filter(
            athlete=athlete, date=today, completed=True
        ).values_list("drill__slug", flat=True)
    )
    rows = [
        {"drill": drill, "done": drill.slug in done_slugs} for drill in drills
    ]
    planned_minutes = sum(drill.estimated_minutes for drill in drills)
    return {
        "plan_day": plan_day,
        "rows": rows,
        "drills": drills,
        "done_count": sum(1 for row in rows if row["done"]),
        "total_count": len(rows),
        "all_done": bool(rows) and all(row["done"] for row in rows),
        "planned_minutes": plan_day.target_minutes if plan_day else planned_minutes,
    }
