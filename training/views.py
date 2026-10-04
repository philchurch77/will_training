"""Views.

Function-based throughout, on purpose. This app has one maintainer who will
come back to it in a year, and a flat list of small functions is the easiest
thing to re-read.
"""

import json
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from . import deck_rules, progress, throttle
from .models import Play, SessionLog, get_athlete

# The coach screens read Will's record through get_athlete() (one profile).
# Dad reads them signed in as staff (leg 4): signed out, they send him to the
# staff sign-in, never to Will's PIN pad - a PIN session on Dad's phone could
# sync that phone's plays onto Will for good.
COACH_SIGN_IN = "/admin/login/"


def coach_required(view):
    """Coach screens: signed in, flagged so the chrome can adapt."""

    @wraps(view)
    @login_required(login_url=COACH_SIGN_IN)
    def wrapped(request, *args, **kwargs):
        request.in_coach = True
        return view(request, *args, **kwargs)

    return wrapped


# --- Auth -----------------------------------------------------------------


def login_view(request):
    """Tap a 4-digit PIN. The only typing anywhere in the app.

    One profile, so there is no name to pick - the pad is the whole screen.
    """
    if request.user.is_authenticated:
        return redirect("training:deck")

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
                return redirect(_safe_next(request) or "training:deck")

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


def _safe_next(request):
    """Where to go after the PIN, if the address asked for somewhere on this site.

    The deck's "Sign in to back it up" sends him back to the cards. Anything
    off-site is ignored, so the pad can never be used to bounce
    someone to another address.
    """
    target = request.GET.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return None


@require_POST
def logout_view(request):
    """POST only: a link or a prefetch must never sign him out.

    Signing out of the coach screens goes back to the staff sign-in, not to
    Will's PIN pad.
    """
    from_coach = request.POST.get("from") == "coach"
    auth_logout(request)
    if from_coach:
        return redirect(f"{COACH_SIGN_IN}?next={reverse('training:coach_cards')}")
    return redirect("training:login")


# --- Child screens --------------------------------------------------------


@login_required
def before_cards(request):
    """Before the cards: what he did on the fixed plan, read-only (leg 3c).

    Only what stays true for good - his best streak, totals, minutes per skill
    and his records. No live streak (it breaks the day he switches, and would
    read as a telling-off), no badges (they are on Progress now), and no link
    to a drill page, which carries the tick and untick forms.
    """
    athlete = request.user
    return render(
        request,
        "training/before_cards.html",
        {
            "longest": progress.longest_streak(athlete),
            "total_drills": progress.drills_completed(athlete),
            "total_minutes": progress.total_minutes(athlete),
            "skill_rows": progress.minutes_by_skill(athlete),
            "best_rows": progress.best_scores(athlete),
            "tab": "progress",
        },
    )


# --- Coach screens --------------------------------------------------------


@coach_required
@require_POST
def coach_log_edit(request, pk):
    """Correct what a session recorded. Blank the box to rub the number out.

    A count nobody watched him make can end up on his record board for ever,
    so it has to be fixable. Only the number changes: deleting the row would
    say he never did the drill at all, which would move his head start and
    his badges. A count moves only his records on Before the cards and the
    three "from before" keepy-up bests - never points or badges, which count
    rows, not reps.
    """
    athlete = get_athlete()
    log = get_object_or_404(SessionLog, pk=pk, athlete=athlete)

    # Counts only. Nothing records per-drill minutes any more - the ones on
    # old rows are leftovers from the timer that was removed, kept because his
    # lifetime minutes are still counted from them.
    if not log.drill.is_timed:
        if "reps" not in request.POST:
            # No count sent at all is not "rub it out": change nothing.
            return redirect("training:coach_logs")
        raw = request.POST["reps"].strip()
        reps = _parse_int(raw, lo=0, hi=10000)
        if raw and reps is None:
            # Not a number he could have made: change nothing, never wipe a count.
            messages.error(request, f"Not saved: {raw!r} is not a count.")
            return redirect("training:coach_logs")
        log.actual_reps = reps
        log.save(update_fields=["actual_reps"])
        shown = log.actual_reps if log.actual_reps is not None else "no count"
        messages.success(request, f"Saved: {log.drill.name}, {log.date:%d %b} - {shown}.")

    return redirect("training:coach_logs")


@coach_required
@require_GET
def coach_cards(request):
    """His cards: what has backed up from his phone, read-only (leg 4).

    The phone's copy wins on the phone, so nothing here edits a play. Read it
    signed in as staff: /api/plays/ refuses staff, so Dad's phone can never
    put a play on Will's record.
    """
    athlete = get_athlete()
    today = timezone.localdate()
    summary, bests, page = None, [], None
    if athlete:
        summary = deck_rules.coach_summary(athlete, today)
        bests = deck_rules.card_bests(athlete, summary["starting_bests"])
        plays = (
            Play.objects.filter(athlete=athlete)
            .select_related("card")
            .order_by("-date", "-played_at")
        )
        page = Paginator(plays, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "training/coach/cards.html",
        {
            "athlete": athlete,
            "summary": summary,
            "bests": bests,
            "page": page,
            "as_of": timezone.localtime(),
            "coach_page": "cards",
        },
    )


@coach_required
def coach_logs(request):
    athlete = get_athlete()
    logs = []
    if athlete:
        logs = (
            SessionLog.objects.filter(athlete=athlete)
            .select_related("drill", "drill__skill")
            .order_by("-date", "-created_at")
        )
    return render(
        request,
        "training/coach/logs.html",
        {"logs": logs, "athlete": athlete, "coach_page": "before"},
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
            "Will's football cards: play any three, chase medals and beat "
            "his own best."
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
                "name": "My cards",
                "short_name": "Cards",
                "url": reverse("training:deck"),
            },
            {
                "name": "My progress",
                "short_name": "Progress",
                "url": reverse("training:deck") + "#progress",
            },
        ],
    }
    return HttpResponse(
        json.dumps(data, indent=2), content_type="application/manifest+json"
    )


def _precache_urls():
    """Pages and assets the service worker should hold for offline use.

    The deck at `/` draws itself from the page and deck.js, so those two are
    the whole app offline. app.js registers this worker and shows the
    connection banner.
    """
    urls = [
        reverse("training:deck"),
        reverse("training:before_cards"),
        reverse("training:offline"),
        static("training/css/app.css"),
        static("training/js/app.js"),
        static("training/js/deck.js"),
        # The manifest and icons too: an installed app that is opened offline
        # still asks for these, and a miss shows the browser's default icon.
        reverse("manifest"),
        static("training/img/icon.svg"),
        static("training/img/icon-192.png"),
        static("training/img/icon-512.png"),
        static("training/img/icon-maskable-512.png"),
        static("training/img/apple-touch-icon.png"),
    ]
    return urls


def offline(request):
    return render(request, "training/offline.html")


# --- helpers --------------------------------------------------------------


def _parse_int(value, lo=None, hi=None):
    """A plain whole number in range, or None. ASCII digits only: int() would
    also take other scripts' digits, which no form here can send."""
    if not isinstance(value, str) or not (value.isascii() and value.isdigit()):
        return None
    number = int(value)
    if lo is not None and number < lo:
        return None
    if hi is not None and number > hi:
        return None
    return number


