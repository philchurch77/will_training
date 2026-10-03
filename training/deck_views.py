"""The deck: one page that runs on his phone, and the two endpoints behind it.

The page is a shell. Everything he sees on it is drawn by deck.js from what
the phone already holds, so it works the same with no signal as with full
bars. The server's jobs are to hand the phone the cards, to keep a copy of
every play he makes, and to give that copy back if the phone loses its own.

Function-based like views.py, for the same reason.
"""

import json
import uuid
from datetime import datetime, timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Card, Play

# A phone left in a drawer for a month still holds plays worth keeping, so the
# window is generous. It exists to stop a wrong phone clock writing a date
# years out into his history, not to judge how late a sync is.
OLDEST_PLAY_DAYS = 400

# Far above anything he could score, and far below anything that breaks.
MAX_SCORE = 100_000

# Plays per sync. The phone sends everything it has not sent yet; this is a
# ceiling on one request, and the phone simply sends the rest next time.
MAX_BATCH = 500


def api_login_required(view):
    """Like login_required, but a 401 the phone can read, not a redirect.

    A redirect to the PIN pad would be followed by fetch and handed back as a
    200 full of HTML, which the phone would take for a sync that worked.
    """

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "signed out"}, status=401)
        return view(request, *args, **kwargs)

    return wrapped


@login_required
def deck(request):
    """The shell, with every active card baked in.

    The cards ride in the page rather than coming from an endpoint, so the
    copy the service worker keeps is enough to draw the whole deck with no
    signal, and a card changed on the server reaches him the next time the
    page loads with signal.
    """
    cards = [_card_json(card) for card in Card.objects.active()]
    return render(request, "training/deck.html", {"cards": cards, "tab": "deck"})


@api_login_required
@require_http_methods(["GET", "POST"])
def api_plays(request):
    """GET: every play he has made. POST: plays the phone has not sent yet.

    A POST answers with the ids it now holds - new ones and ones it already
    had - and the ones it refused with a reason. The phone marks the first
    lot sent. A refused play stays on the phone; nothing here can make the
    phone throw one away.
    """
    if request.method == "GET":
        plays = Play.objects.filter(athlete=request.user).select_related("card")
        return JsonResponse({"plays": [_play_json(play) for play in plays]})

    try:
        incoming = json.loads(request.body or b"{}").get("plays", [])
    except (ValueError, AttributeError):
        return JsonResponse({"error": "not JSON"}, status=400)
    if not isinstance(incoming, list):
        return JsonResponse({"error": "plays must be a list"}, status=400)

    cards = {card.slug: card for card in Card.objects.all()}
    saved, refused = [], []
    for raw in incoming[:MAX_BATCH]:
        play, reason = _parse_play(raw, request.user, cards)
        if play is None:
            refused.append({"id": _safe_id(raw), "reason": reason})
            continue
        existing = Play.objects.filter(pk=play.pk).first()
        if existing is not None:
            # Already here: a repeat of a sync whose answer never reached the
            # phone. Nothing changes - the first copy is his record.
            if existing.athlete_id == request.user.pk:
                saved.append(str(play.pk))
            else:
                refused.append({"id": str(play.pk), "reason": "id in use"})
            continue
        try:
            with transaction.atomic():
                play.save(force_insert=True)
        except IntegrityError:
            # Two syncs racing with the same play. The other one saved it.
            pass
        saved.append(str(play.pk))

    return JsonResponse({"saved": saved, "refused": refused})


# --- helpers --------------------------------------------------------------


def _card_json(card):
    return {
        "slug": card.slug,
        "name": card.name,
        "pack": card.pack,
        "pack_name": card.get_pack_display(),
        "instructions": card.instructions,
        "cue": card.cue,
        "scoring": card.scoring,
        "score_label": card.score_label,
        "per_foot": card.per_foot,
        "out_of": card.out_of,
        "timer_seconds": card.timer_seconds,
        "medals": [card.bronze, card.silver, card.gold],
        "move": card.move,
        "level": card.level,
        "kit": [
            name
            for name, needed in (
                ("cones", card.needs_cones),
                ("rebounder", card.needs_rebounder),
                ("goal", card.needs_goal),
            )
            if needed
        ],
    }


def _play_json(play):
    return {
        "id": str(play.pk),
        "card": play.card.slug,
        "date": play.date.isoformat(),
        "played_at": play.played_at.isoformat(),
        "score": play.score,
        "weak_score": play.weak_score,
    }


def _safe_id(raw):
    value = raw.get("id") if isinstance(raw, dict) else None
    return value if isinstance(value, str) and len(value) <= 64 else None


def _parse_play(raw, athlete, cards):
    """Turn one play from the phone into an unsaved Play, or say why not."""
    if not isinstance(raw, dict):
        return None, "not a play"
    try:
        play_id = uuid.UUID(str(raw.get("id")))
    except ValueError:
        return None, "bad id"

    card = cards.get(raw.get("card"))
    if card is None:
        return None, "unknown card"

    try:
        played_at = datetime.fromisoformat(str(raw.get("played_at")))
    except ValueError:
        return None, "bad time"
    if timezone.is_naive(played_at):
        played_at = timezone.make_aware(played_at)

    try:
        day = datetime.fromisoformat(str(raw.get("date"))).date()
    except ValueError:
        return None, "bad date"
    today = timezone.localdate()
    # A day of slack forwards: his phone and the server can sit either side
    # of midnight.
    if day > today + timedelta(days=1) or day < today - timedelta(days=OLDEST_PLAY_DAYS):
        return None, "date out of range"

    scores = {}
    for field in ("score", "weak_score"):
        value = raw.get(field)
        if value is None:
            scores[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"bad {field}"
        if not 0 <= value <= MAX_SCORE:
            return None, f"{field} out of range"
        scores[field] = value

    return (
        Play(
            id=play_id,
            athlete=athlete,
            card=card,
            date=day,
            played_at=played_at,
            **scores,
        ),
        None,
    )
