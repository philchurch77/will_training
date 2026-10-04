"""The deck: one page that runs on his phone, and the two endpoints behind it.

The page is a shell. Everything he sees on it is drawn by deck.js from what
the phone already holds, so it works the same with no signal as with full
bars. The server's jobs are to hand the phone the cards, to keep a copy of
every play he makes, and to give that copy back if the phone loses its own.

Function-based like views.py, for the same reason.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .deck_rules import award_deck_badges, goal_weeks_for, history_for, rules_json
from .models import Badge, Card, EarnedBadge, Play

# A phone left in a drawer for a month still holds plays worth keeping, so the
# window is generous. It exists to stop a wrong phone clock writing a date
# years out into his history, not to judge how late a sync is.
OLDEST_PLAY_DAYS = 400

# Far above anything he could score, and far below anything that breaks.
MAX_SCORE = 100_000

# Plays per sync. The phone sends everything it has not sent yet; this is a
# ceiling on one request, and the phone simply sends the rest next time.
MAX_BATCH = 500

logger = logging.getLogger(__name__)

# Upper bounds for a play's stamp. Points top out near 110 under today's rules
# and a medal is 0-3, bests 0-2 (one per foot).
STAMP_CEILINGS = {"points": 1000, "medal": Play.GOLD, "bests": 2}


def api_login_required(view):
    """Like login_required, but a 401 the phone can read, not a redirect.

    A redirect to the PIN pad would be followed by fetch and handed back as a
    200 full of HTML, which the phone would take for a sync that worked.
    """

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "signed out"}, status=401)
        # The phone's copy of his plays is one list whoever is signed in. A
        # staff session (the admin, on the same phone) would file plays under
        # the coach and, worse, make restore() think every one of Will's had
        # been lost. Plays are Will's; the coach account gets none of this.
        if request.user.is_staff:
            return JsonResponse({"error": "coach account"}, status=403)
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
    return render(
        request,
        "training/deck.html",
        {
            "cards": cards,
            "rules": rules_json(timezone.localdate(), history_for(request.user)),
            "deck_badges": _deck_badges_json(request.user),
            "tab": "deck",
        },
    )


@api_login_required
@require_http_methods(["GET", "POST"])
def api_plays(request):
    """GET: every play he has made. POST: plays the phone has not sent yet.

    A POST answers with the ids it now holds - new ones and ones it already
    had - and the ones it refused with a reason. The phone marks the first
    lot sent. A refused play stays on the phone; nothing here can make the
    phone throw one away.
    """
    today = timezone.localdate()
    if request.method == "GET":
        plays = Play.objects.filter(athlete=request.user).select_related("card")
        return _no_store(JsonResponse({
            "plays": [_play_json(play) for play in plays],
            "earned": _earned_codes(request.user),
            "goal_weeks": goal_weeks_for(request.user, today),
        }))

    try:
        incoming = json.loads(request.body or b"{}").get("plays", [])
    except (ValueError, AttributeError):
        return JsonResponse({"error": "not JSON"}, status=400)
    if not isinstance(incoming, list):
        return JsonResponse({"error": "plays must be a list"}, status=400)

    # Every card, retired ones included: a play made on a card that has since
    # been retired is still his, and the phone has no other copy to send.
    cards = {card.slug: card for card in Card.objects.all()}
    parsed = [(raw, *_parse_play(raw, request.user, cards)) for raw in incoming[:MAX_BATCH]]
    # One query for the whole batch, not one per play.
    owners = dict(
        Play.objects.filter(
            pk__in=[play.pk for _, play, _ in parsed if play is not None]
        ).values_list("pk", "athlete_id")
    )
    saved, refused = [], []

    for raw, play, reason in parsed:
        if play is None:
            refused.append({"id": _safe_id(raw), "reason": reason})
            continue
        if play.pk in owners:
            # Already here: a repeat of a sync whose answer never reached the
            # phone. Nothing changes - the first copy is his record.
            if owners[play.pk] == request.user.pk:
                saved.append(str(play.pk))
            else:
                refused.append({"id": str(play.pk), "reason": "id in use"})
            continue
        try:
            with transaction.atomic():
                play.save(force_insert=True)

        except IntegrityError:
            # Two syncs racing with the same play: the other one saved it.
            # Only call it saved if a copy is really there and it is his:
            # "saved" makes the phone stop sending it.
            owner = Play.objects.filter(pk=play.pk).values_list("athlete_id", flat=True).first()
            if owner != request.user.pk:
                reason = "not saved" if owner is None else "id in use"
                refused.append({"id": str(play.pk), "reason": reason})
                continue
        owners[play.pk] = request.user.pk
        saved.append(str(play.pk))

    # The phone keeps a refused play and shows a count; this is the one place
    # the reason is written down. The id is the phone's, the reason one of a
    # few fixed words - no score goes in the log.
    for refusal in refused:
        logger.warning("play refused: %r (%s)", refusal["id"], refusal["reason"])

    # Checked on every sync that holds his plays, not only when one is new:
    # a retry after a lost answer, or a badge added or lowered at deploy, would
    # otherwise wait for his next play. Awarded after the plays are saved, and
    # a badge going wrong is logged, never a 500: it must not cost a play.
    new_badges = []
    if saved:
        try:
            with transaction.atomic():
                new_badges = [badge.code for badge in award_deck_badges(request.user, today)]
        except Exception:
            logger.exception("awarding deck badges failed; the plays are saved")

    return _no_store(JsonResponse({
        "saved": saved,
        "refused": refused,
        "badges": new_badges,
        "goal_weeks": goal_weeks_for(request.user, today),
    }))


# --- helpers --------------------------------------------------------------


def _no_store(response):
    """His plays change with every card he plays; no browser keeps a copy."""
    response["Cache-Control"] = "no-store"
    return response


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
        "points": play.points,
        "medal": play.medal,
        "bests": play.bests,
    }


def _deck_badges_json(athlete):
    """The deck's badge screen, every badge he has in one place (leg 3b):
    each active deck or kept badge, earned or not, and any other badge he
    earned - an old streak, or a retired one tagged Legend. An old badge he
    has not earned is left out: the deck cannot award it, so "Not yet" would
    be a promise it cannot keep. Only his own awards."""
    earned = set(
        EarnedBadge.objects.filter(athlete=athlete).values_list("badge_id", flat=True)
    )
    on_deck = Badge.DECK_KINDS | Badge.KEPT_KINDS
    return [
        {
            "code": badge.code,
            "name": badge.name,
            "emoji": badge.emoji,
            "description": badge.description,
            "legend": not badge.is_active,
            "earned": badge.id in earned,
        }
        for badge in Badge.objects.all()
        if badge.id in earned or (badge.is_active and badge.kind in on_deck)
    ]


def _earned_codes(athlete):
    """Every badge he has, so the phone's cache knows them as earned rather
    than news - one already earned (a Legend, or one from before the cards) is
    never celebrated again."""
    return list(
        EarnedBadge.objects.filter(athlete=athlete).values_list("badge__code", flat=True)
    )


def _parse_stamp(raw, scores, card):
    """The play's stamp, or no stamp at all - never a reason to refuse it.

    Optional: a play from before the game layer, or from an old cached page,
    has none and is stored as worth nothing. Anything odd - out of range, not
    a whole number, a medal with no score - drops all three fields and keeps
    the play. A refused play sits on the phone unsent, and a real score must
    never be lost over what it was worth in the game.

    Never checked against today's targets or points: change one and every
    older stamp would fail. The ceilings are loose for the same reason.
    """
    none = {field: None for field in STAMP_CEILINGS}
    stamp = {}
    for field, ceiling in STAMP_CEILINGS.items():
        value = raw.get(field)
        if value is None:
            stamp[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= ceiling:
            return none
        stamp[field] = value
    # Cross-checks that stay true whatever the targets become. The Gold medal
    # and Record breaker badges trust these stamps (docs/chart/deck.md, leg
    # 2b), so a stamp the card could never have earned is dropped.
    medal, bests = stamp.get("medal") or 0, stamp.get("bests") or 0
    if card.scoring == Card.NONE and (medal or bests):
        return none
    # No target ever gives a medal for 0, and a time of 0 never counts.
    if medal and not scores.get("score"):
        return none
    if card.per_foot and medal and not scores.get("weak_score"):
        return none
    feet = (scores.get("score") is not None) + (card.per_foot and scores.get("weak_score") is not None)
    if bests > feet:
        return none
    return stamp


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
    # Only the canonical spelling. The answer echoes str(play_id), and the
    # phone matches it against its own id string to mark the play sent; an
    # uppercase or brace-wrapped id would never match and resend forever.
    if str(play_id) != raw.get("id"):
        return None, "bad id"

    card = cards.get(raw.get("card"))
    if card is None:
        return None, "unknown card"

    # The same window as the date, for the same reason. An extreme time like
    # year 1 or 9999 with an offset overflows when it is converted, and an
    # uncaught error here would 500 the whole batch, every sync, for good.
    now = timezone.now()
    try:
        played_at = datetime.fromisoformat(str(raw.get("played_at")))
        if timezone.is_naive(played_at):
            played_at = timezone.make_aware(played_at)
        in_window = (
            now - timedelta(days=OLDEST_PLAY_DAYS + 1)
            <= played_at
            <= now + timedelta(days=2)
        )
    except (ValueError, OverflowError):
        return None, "bad time"
    if not in_window:
        return None, "bad time"

    try:
        day = datetime.fromisoformat(str(raw.get("date"))).date()
    except (ValueError, OverflowError):
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

    scores.update(_parse_stamp(raw, scores, card))

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
