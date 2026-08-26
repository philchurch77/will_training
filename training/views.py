"""Views.

Function-based throughout, on purpose. This app has one maintainer who will
come back to it in a year, and a flat list of small functions is the easiest
thing to re-read.
"""

import json
from functools import wraps
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import progress, throttle
from .forms import DrillForm, PlanDayForm
from .models import (
    WEEKDAYS,
    Drill,
    PlanDay,
    PlanDrill,
    SessionLog,
    Skill,
    TrainingPlan,
    get_athlete,
)

# There is one profile, and Dad is the only other person who touches this, so
# the coach screens sit behind the same PIN rather than a second account. They
# are simply kept off Will's tab bar.
def coach_required(view):
    """Coach screens: same session, flagged so the chrome can adapt."""

    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        request.in_coach = True
        return view(request, *args, **kwargs)

    return wrapped


def _today():
    """Today's date in the app's timezone."""
    from django.utils import timezone

    return timezone.localdate()


# --- Auth -----------------------------------------------------------------


def login_view(request):
    """Tap a 4-digit PIN. The only typing anywhere in the app.

    One profile, so there is no name to pick - the pad is the whole screen.
    """
    if request.user.is_authenticated:
        return redirect("training:today")

    athlete = get_athlete()
    error = None
    locked_for = throttle.seconds_locked(request)

    if request.method == "POST":
        if locked_for:
            error = throttle.describe(locked_for)
        elif athlete is None:
            error = "No profile yet. Run manage.py seed_drills."
        else:
            pin = request.POST.get("pin", "")
            user = authenticate(request, username=athlete.username, password=pin)
            if user is not None:
                throttle.clear(request)
                auth_login(request, user)
                request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                return redirect("training:today")

            locked_for = throttle.record_failure(request)
            error = throttle.describe(locked_for) or "Wrong code. Try again."

    return render(
        request,
        "training/login.html",
        {
            "athlete_name": athlete.first_name or athlete.username if athlete else "",
            "error": error,
            "locked_for": locked_for,
        },
    )


def logout_view(request):
    auth_logout(request)
    return redirect("training:login")


# --- Child screens --------------------------------------------------------


@login_required
def today(request):
    athlete = request.user
    day = _today()

    summary = progress.today_summary(athlete, day)
    just_done = request.GET.get("done")
    new_badges = request.session.pop("new_badges", [])
    new_record = request.session.pop("new_record", None)

    return render(
        request,
        "training/today.html",
        {
            "summary": summary,
            "today": day,
            "streak": progress.current_streak(athlete, day),
            "just_done": just_done,
            "new_badges": new_badges,
            "new_record": new_record,
            "tab": "today",
        },
    )


@login_required
def drill_detail(request, slug):
    drill = get_object_or_404(Drill.objects.select_related("skill"), slug=slug)
    athlete = request.user
    day = _today()

    already = SessionLog.objects.filter(
        athlete=athlete, date=day, drill=drill, completed=True
    ).exists()

    return render(
        request,
        "training/drill.html",
        {
            "drill": drill,
            "already_done": already,
            "best": progress.personal_best(athlete, drill),
            "tab": "today",
        },
    )


@login_required
@require_POST
def drill_complete(request, slug):
    """Mark a drill done for today.

    Idempotent by design: the unique constraint on (athlete, date, drill)
    means replaying a completion that was queued offline updates the existing
    row instead of creating a duplicate.
    """
    drill = get_object_or_404(Drill, slug=slug)
    athlete = request.user

    day = _parse_date(request.POST.get("date")) or _today()
    rating = _parse_int(request.POST.get("rating"), lo=1, hi=5)
    minutes = _parse_int(request.POST.get("actual_minutes"), lo=0, hi=600)
    reps = _parse_int(request.POST.get("actual_reps"), lo=0, hi=10000)

    # Read the old best before the tick overwrites today's row - and count
    # anything already logged today, or ticking the same number twice would
    # claim a second record.
    previous_best = max(
        progress.personal_best(athlete, drill, before=day) or 0,
        SessionLog.objects.filter(athlete=athlete, date=day, drill=drill)
        .values_list("actual_reps", flat=True)
        .first() or 0,
    ) or None

    with transaction.atomic():
        # Every tick carries the session clock with it, so the time is banked
        # even if he never taps Finish.
        progress.record_session_seconds(
            athlete, day, request.POST.get("session_seconds")
        )
        # Only write what this request actually carried. The tick on the
        # Today list posts no count and no rating, and it must not wipe the 30
        # he counted on the drill page ten minutes earlier - which is the
        # number his record is made of.
        defaults = {"completed": True}
        if rating is not None:
            defaults["rating"] = rating
        if drill.is_timed:
            defaults["actual_reps"] = None
            if minutes is not None:
                defaults["actual_minutes"] = minutes
        else:
            defaults["actual_minutes"] = None
            if reps is not None:
                defaults["actual_reps"] = reps

        log, _created = SessionLog.objects.update_or_create(
            athlete=athlete, date=day, drill=drill, defaults=defaults
        )
        new_badges = progress.award_badges(athlete, day)

    record = None
    if reps and not drill.is_timed and (previous_best is None or reps > previous_best):
        record = {"drill": drill.name, "reps": reps, "previous": previous_best}

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "drill": drill.slug,
                "badges": [
                    {"name": b.name, "emoji": b.emoji, "description": b.description}
                    for b in new_badges
                ],
                "record": record,
            }
        )

    if record:
        request.session["new_record"] = record
    if new_badges:
        request.session["new_badges"] = [
            {"name": b.name, "emoji": b.emoji, "description": b.description}
            for b in new_badges
        ]
    return redirect(f"{reverse('training:today')}?done={drill.slug}")


@login_required
@require_POST
def drill_uncomplete(request, slug):
    """Untick a drill - he tapped it by accident."""
    drill = get_object_or_404(Drill, slug=slug)
    athlete = request.user
    SessionLog.objects.filter(athlete=athlete, date=_today(), drill=drill).delete()
    return redirect("training:today")


@login_required
@require_POST
def session_time(request):
    """Bank the session clock.

    Three things post here: the Finish button, a best-effort save when he
    pauses, and the by-hand entry for the evening he forgets to start it at
    all. Separate from ticking a drill because he might train for twenty
    minutes on the one drill he is enjoying and tick nothing until the end.
    """
    day = _parse_date(request.POST.get("date")) or _today()

    # Minutes mean he set it by hand because he forgot to start the clock, so
    # that figure replaces whatever the phone thinks - downwards included.
    minutes = _parse_int(request.POST.get("minutes"), lo=1, hi=180)
    if minutes is not None:
        clock = progress.record_session_seconds(
            request.user, day, minutes * 60, exact=True
        )
    else:
        clock = progress.record_session_seconds(
            request.user, day, request.POST.get("seconds")
        )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "seconds": clock.seconds if clock else 0})
    return redirect("training:today")


@login_required
def progress_view(request):
    athlete = request.user
    day = _today()

    return render(
        request,
        "training/progress.html",
        {
            "streak": progress.current_streak(athlete, day),
            "longest": progress.longest_streak(athlete),
            "month_sessions": progress.sessions_this_month(athlete, day),
            "total_drills": progress.drills_completed(athlete),
            "total_minutes": progress.total_minutes(athlete),
            "skill_rows": progress.minutes_by_skill(athlete),
            "badge_rows": progress.badge_progress(athlete, day),
            "best_rows": progress.best_scores(athlete),
            "tab": "progress",
            "today": day,
        },
    )


@login_required
def library(request, slug=None):
    skills = Skill.objects.all()
    selected = None
    drills = Drill.objects.active().select_related("skill")
    if slug:
        selected = get_object_or_404(Skill, slug=slug)
        drills = drills.filter(skill=selected)

    return render(
        request,
        "training/library.html",
        {"skills": skills, "selected": selected, "drills": drills, "tab": "library"},
    )


# --- Coach screens --------------------------------------------------------


@coach_required
def coach_plan(request):
    plan = TrainingPlan.get_active()
    rows = []
    if plan:
        for day in plan.days.prefetch_related("items__drill__skill").order_by("weekday"):
            rows.append(
                {
                    "day": day,
                    "week_a": len(day.drills_for_week(PlanDrill.WEEK_A)),
                    "week_b": len(day.drills_for_week(PlanDrill.WEEK_B)),
                }
            )
    return render(
        request,
        "training/coach/plan.html",
        {
            "plan": plan,
            "rows": rows,
            "weekdays": WEEKDAYS,
            "this_week": _week_letter(progress.week_of(_today())),
            "tab": "coach",
        },
    )


def _week_letter(week):
    return "B" if week == PlanDrill.WEEK_B else "A"


@coach_required
def coach_plan_day(request, weekday):
    plan = TrainingPlan.get_active()
    if plan is None:
        return redirect("training:coach_plan")
    day = get_object_or_404(PlanDay, plan=plan, weekday=weekday)

    # One week of the fortnight at a time, defaulting to the one he is
    # actually in, so what is on screen is what Will will see today.
    asked = request.GET.get("week") or request.POST.get("week")
    week = {"A": PlanDrill.WEEK_A, "B": PlanDrill.WEEK_B}.get(
        asked, progress.week_of(_today())
    )
    here = f"{reverse('training:coach_plan_day', args=[weekday])}?week={_week_letter(week)}"

    form = PlanDayForm(instance=day)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "settings":
            form = PlanDayForm(request.POST, instance=day)
            if form.is_valid():
                form.save()
                return redirect(here)
            # Fall through so the invalid form renders with its errors.
        elif action == "add":
            drill = get_object_or_404(Drill, pk=request.POST.get("drill"))
            next_order = (
                day.items.filter(week=week)
                .order_by("-order")
                .values_list("order", flat=True)
                .first()
            )
            PlanDrill.objects.create(
                plan_day=day, drill=drill, order=(next_order or 0) + 1, week=week
            )
            return redirect(here)
        elif action == "remove":
            day.items.filter(pk=request.POST.get("item")).delete()
            return redirect(here)
        elif action in {"up", "down"}:
            _move_item(day, request.POST.get("item"), action, week)
            return redirect(here)

    items = (
        day.items.select_related("drill", "drill__skill")
        .filter(Q(week=PlanDrill.EVERY_WEEK) | Q(week=week))
        .order_by("order", "pk")
    )
    return render(
        request,
        "training/coach/plan_day.html",
        {
            "day": day,
            "form": form,
            "items": items,
            "skills": Skill.objects.prefetch_related("drills"),
            "planned_minutes": sum(i.drill.estimated_minutes for i in items),
            "week": _week_letter(week),
            "every_week": PlanDrill.EVERY_WEEK,
        },
    )


def _move_item(day, item_pk, direction, week):
    """Swap a drill with its neighbour in one week's running order.

    Scoped to the week on screen: the two halves of the fortnight each number
    their drills from one, and reordering across both would interleave them.
    """
    items = list(
        day.items.filter(Q(week=PlanDrill.EVERY_WEEK) | Q(week=week)).order_by(
            "order", "pk"
        )
    )
    index = next((i for i, it in enumerate(items) if str(it.pk) == str(item_pk)), None)
    if index is None:
        return
    target = index - 1 if direction == "up" else index + 1
    if not (0 <= target < len(items)):
        return
    # Rewrite the whole day's ordering so gaps and ties cannot accumulate.
    items[index], items[target] = items[target], items[index]
    for position, item in enumerate(items, start=1):
        if item.order != position:
            item.order = position
            item.save(update_fields=["order"])


@coach_required
def coach_drills(request):
    drills = Drill.objects.select_related("skill").order_by("skill__order", "name")
    return render(request, "training/coach/drills.html", {"drills": drills})


@coach_required
def coach_drill_edit(request, slug=None):
    drill = get_object_or_404(Drill, slug=slug) if slug else None
    if request.method == "POST":
        form = DrillForm(request.POST, instance=drill)
        if form.is_valid():
            form.save()
            return redirect("training:coach_drills")
    else:
        form = DrillForm(instance=drill)
    return render(
        request, "training/coach/drill_form.html", {"form": form, "drill": drill}
    )


@coach_required
@require_POST
def coach_log_edit(request, pk):
    """Correct what a session recorded. Blank the box to rub the number out.

    A count nobody watched him make can end up on his record board for ever,
    so it has to be fixable. Only the number changes: deleting the row would
    say he never did the drill at all, which would move his streak and his
    badges, and a wrong score is not worth rewriting his history over.
    """
    athlete = get_athlete()
    log = get_object_or_404(SessionLog, pk=pk, athlete=athlete)

    # Counts only. Nothing records per-drill minutes any more - the ones on
    # old rows are leftovers from the timer that was removed, kept because his
    # lifetime minutes are still counted from them.
    if not log.drill.is_timed:
        log.actual_reps = _parse_int(request.POST.get("reps"), lo=0, hi=10000)
        log.save(update_fields=["actual_reps"])

    return redirect("training:coach_logs")


@coach_required
def coach_logs(request):
    athlete = get_athlete()
    logs = []
    if athlete:
        logs = (
            SessionLog.objects.filter(athlete=athlete)
            .select_related("drill", "drill__skill")
            .order_by("-date", "-created_at")[:200]
        )
    day = _today()
    return render(
        request,
        "training/coach/logs.html",
        {
            "logs": logs,
            "athlete": athlete,
            "streak": progress.current_streak(athlete, day),
            "month_sessions": progress.sessions_this_month(athlete, day)
            if athlete
            else 0,
        },
    )


# --- PWA plumbing ---------------------------------------------------------


def service_worker(request):
    """Served from the site root so its scope covers the whole app."""
    precache = json.dumps(_precache_urls(), indent=2)
    body = render_to_string("training/sw.js", {"precache": precache})
    response = HttpResponse(body, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def manifest(request):
    """The web app manifest, so the phone can install this to a home screen.

    Icons are listed twice on purpose: `any` icons are drawn as they are, while
    `maskable` ones get cropped to whatever shape the launcher likes, so they
    need their own full-bleed artwork. See the make_icons command.
    """
    data = {
        # A stable identity. Without it the browser derives one from start_url,
        # so changing start_url later would look like a different app and
        # orphan the icon already sitting on his home screen.
        "id": "/",
        "name": "Will's Training",
        "short_name": "Training",
        "description": (
            "Will's daily football session: today's drills, his streak "
            "and his badges."
        ),
        "lang": "en-GB",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f4f6f8",
        # Matches the theme-color meta tag in base.html. Blue here would put a
        # blue bar above the app's white top bar, which just looks broken.
        "theme_color": "#f4f6f8",
        "categories": ["sports", "health", "education"],
        "icons": [
            {
                "src": static("training/img/icon.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": static("training/img/icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": static("training/img/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": static("training/img/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        # Long-press the installed icon to jump straight to a screen.
        "shortcuts": [
            {
                "name": "Today's session",
                "short_name": "Today",
                "url": reverse("training:today"),
            },
            {
                "name": "My progress",
                "short_name": "Progress",
                "url": reverse("training:progress"),
            },
        ],
    }
    return HttpResponse(
        json.dumps(data, indent=2), content_type="application/manifest+json"
    )


def _precache_urls():
    """Pages and assets the service worker should hold for offline use."""
    urls = [
        reverse("training:today"),
        reverse("training:library"),
        reverse("training:progress"),
        reverse("training:offline"),
        static("training/css/app.css"),
        static("training/js/app.js"),
        static("training/js/drill.js"),
        static("training/js/session.js"),
        # The manifest and icons too: an installed app that is opened offline
        # still asks for these, and a miss shows the browser's default icon.
        reverse("manifest"),
        static("training/img/icon.svg"),
        static("training/img/icon-192.png"),
        static("training/img/icon-512.png"),
        static("training/img/icon-maskable-512.png"),
        static("training/img/apple-touch-icon.png"),
    ]
    try:
        urls += [d.get_absolute_url() for d in Drill.objects.active()]
        urls += [s.get_absolute_url() for s in Skill.objects.all()]
    except Exception:
        # Before migrations have run there is nothing to precache; the shell
        # of the app is enough.
        pass
    return urls


def offline(request):
    return render(request, "training/offline.html")


# --- helpers --------------------------------------------------------------


def _parse_int(value, lo=None, hi=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if lo is not None and number < lo:
        return None
    if hi is not None and number > hi:
        return None
    return number


def _parse_date(value):
    """Parse an ISO date sent by the offline queue, ignoring anything odd."""
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    # A queued completion can only ever be from the recent past, never the
    # future. This stops a wrong phone clock writing nonsense into history.
    today_ = _today()
    if parsed > today_ or parsed < today_ - timedelta(days=14):
        return None
    return parsed
