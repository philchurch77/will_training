"""Leg 3b: the kept old badges, counted from old ticks and card plays together.

Four of the old badges (Badge.KEPT_KINDS) now read his SessionLog rows and
his Play rows. Two paths award them - a tick on Today and a deck sync - and
both go through progress.award. The things that can go wrong, in order:
another account's ticks, plays or awards leaking into his; the one command
that deletes plays reaching an award he earned from real ticks; a badge error
costing a tick; and the counting rules drifting so a badge is handed out
early or stranded.

Tick dates are pinned well back from today so nothing here depends on the
weekday the suite runs on. Plays sent through /api/plays/ must sit inside its
date window, so those are dated from today.
"""

import json
import uuid
from datetime import date, timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from training import deck_rules, progress
from training.deck_data import seed_deck
from training.models import Badge, Card, Drill, EarnedBadge, Play, SessionLog, Skill

from .test_deck_views import deck_badges_in

pytestmark = pytest.mark.django_db

URL = "/api/plays/"
LONG_AGO = date(2026, 1, 5)  # a Monday, nowhere near any day the suite runs


# --- fixtures and helpers ----------------------------------------------------


@pytest.fixture
def deck(db):
    seed_deck()


@pytest.fixture
def all_badges(db):
    """Every badge exactly as seed_drills ships it, old and deck alike."""
    from training.management.commands.seed_drills import BADGES

    for code, name, description, emoji, kind, threshold, order in BADGES:
        Badge.objects.create(
            code=code, name=name, description=description, emoji=emoji,
            kind=kind, threshold=threshold, order=order,
        )


@pytest.fixture
def other(db):
    """A second account, standing in for anyone who is not Will."""
    return get_user_model().objects.create_user(username="other", password="x")


def ticks(athlete, drill, count, start=LONG_AGO):
    """`count` ticks on `drill`, one a day from `start`."""
    for n in range(count):
        SessionLog.objects.create(athlete=athlete, drill=drill, date=start + timedelta(days=n))


def make_play(athlete, slug, day, score=10, weak_score=None):
    return Play.objects.create(
        id=uuid.uuid4(), athlete=athlete, card=Card.objects.get(slug=slug),
        date=day, played_at=timezone.now(), score=score, weak_score=weak_score,
    )


def api_play(card, day=None, score=10, weak_score=None):
    return {
        "id": str(uuid.uuid4()),
        "card": card,
        "date": (day or timezone.localdate()).isoformat(),
        "played_at": timezone.now().isoformat(),
        "score": None if card == "free-play" else score,
        "weak_score": weak_score,
    }


def post(client, plays):
    return client.post(URL, data=json.dumps({"plays": plays}), content_type="application/json")


def earn(athlete, code, on=LONG_AGO):
    return EarnedBadge.objects.create(
        athlete=athlete, badge=Badge.objects.get(code=code), earned_on=on
    )


def codes_of(athlete):
    return set(EarnedBadge.objects.filter(athlete=athlete).values_list("badge__code", flat=True))


# --- 1. one user's own --------------------------------------------------------


class TestKeptBadgeIsolation:
    # Catches _earned_codes losing its athlete filter: since 3b it returns
    # every badge, old ones included, so another account's streak and kept
    # badge would land in Will's phone cache as his.
    def test_another_users_streak_and_kept_badge_are_not_in_wills_get(
        self, client, deck, all_badges, will, other
    ):
        earn(other, "streak-3")
        earn(other, "drills-10")
        client.force_login(will)
        assert client.get(URL).json()["earned"] == []

    # Catches _deck_badges_json reading anyone's awards: another account's
    # kept badge would show earned on Will's screen, and their old streak
    # badge would appear on it at all.
    def test_wills_deck_page_shows_nothing_earned_from_another_users_awards(
        self, client, deck, all_badges, will, other
    ):
        earn(other, "streak-3")
        earn(other, "drills-10")
        client.force_login(will)
        rows = deck_badges_in(client.get(reverse("training:deck")))
        by_code = {row["code"]: row for row in rows}
        assert "drills-10" in by_code, "the kept badges are not on the deck screen"
        assert not any(row["earned"] for row in rows)
        assert "streak-3" not in by_code

    # Catches kept_badge_values, or deck_rows under it, counting every
    # account's ticks or plays rather than the one asked about.
    def test_kept_values_count_only_the_athletes_own_ticks_and_plays(
        self, deck, will, other, drill
    ):
        ticks(will, drill, 1)
        make_play(will, "toe-taps-30", LONG_AGO)
        ticks(other, drill, 9)
        for slug in ("free-play", "keepy-ups-weak", "keepy-ups-best"):
            make_play(other, slug, LONG_AGO)
        values = progress.kept_badge_values(will)
        assert values[Badge.TOTAL_DRILLS] == 2
        assert values[Badge.WEAK_FOOT] == 0
        assert values[Badge.JUGGLING] == 0
        assert values[Badge.SKILLS_TRIED] == 1

    # Catches the sync award reading another account's ticks: Will's first
    # play would be answered with a 10 drills he never did.
    def test_a_sync_awards_will_nothing_from_another_users_ticks(
        self, client, deck, all_badges, will, other, drill
    ):
        ticks(other, drill, 10)
        client.force_login(will)
        body = post(client, [api_play("toe-taps-30")]).json()
        assert "drills-10" not in body["badges"]
        assert "drills-10" not in codes_of(will)

    # Catches the staff refusal moving after the award now that the award
    # reads ticks: the coach account gets neither a read nor a kept badge.
    def test_staff_get_and_post_are_refused_and_award_nothing(
        self, client, deck, all_badges, will, drill
    ):
        ticks(will, drill, 10)
        coach = get_user_model().objects.create_user(
            username="coach", password="x", is_staff=True
        )
        client.force_login(coach)
        assert client.get(URL).status_code == 403
        assert post(client, [api_play("toe-taps-30")]).status_code == 403
        assert not EarnedBadge.objects.exists()


# --- 2. nothing he earned is lost -------------------------------------------


class TestKeptBadgesAreNeverLost:
    # Catches award() losing the savepoint around each create. A second path
    # awarding the same badge between the `already` read and the create is
    # simulated by making the read stale. Without the savepoint the
    # IntegrityError poisons the outer transaction - the one drill_complete
    # holds the tick in - and the next query raises.
    def test_a_raced_award_is_skipped_and_the_outer_transaction_survives(
        self, will, drill, monkeypatch
    ):
        raced = Badge.objects.create(
            code="test-raced", name="raced", description="", kind=Badge.TOTAL_DRILLS,
            threshold=1, order=1,
        )
        fresh = Badge.objects.create(
            code="test-fresh", name="fresh", description="", kind=Badge.TOTAL_DRILLS,
            threshold=1, order=2,
        )
        EarnedBadge.objects.create(athlete=will, badge=raced, earned_on=LONG_AGO)

        real = EarnedBadge.objects

        class StaleRead:
            class objects:
                @staticmethod
                def filter(**kwargs):
                    return real.none()

                create = real.create

        monkeypatch.setattr(progress, "EarnedBadge", StaleRead)
        with transaction.atomic():
            log = SessionLog.objects.create(athlete=will, drill=drill, date=LONG_AGO)
            newly = progress.award(will, {Badge.TOTAL_DRILLS: 1}, {Badge.TOTAL_DRILLS}, LONG_AGO)
            # A query after the race: raises if the transaction was poisoned.
            assert SessionLog.objects.filter(pk=log.pk).exists()
        assert newly == [fresh]
        assert EarnedBadge.objects.filter(athlete=will, badge=raced).count() == 1
        assert SessionLog.objects.filter(pk=log.pk).exists()

    # Catches award_deck_badges revoking a kept badge whose count has since
    # fallen (an untick, a threshold raised): already earned stays earned.
    def test_a_sync_never_deletes_a_kept_award_he_no_longer_reaches(
        self, client, deck, all_badges, will
    ):
        earned = earn(will, "drills-50", on=date(2026, 2, 1))
        client.force_login(will)
        post(client, [api_play("toe-taps-30")])
        deck_rules.award_deck_badges(will, timezone.localdate())
        earned.refresh_from_db()
        assert earned.earned_on == date(2026, 2, 1)


# --- 3. the counting rules ----------------------------------------------------


class TestKeptCountsFromPlays:
    """Read through deck_rows from real seeded cards, so a pack or per_foot
    dropped from the query breaks these too."""

    def counts(self, athlete):
        return deck_rules.kept_counts_from_plays(deck_rules.deck_rows(athlete))

    # Catches card-days being counted per play: ten goes on one card in an
    # evening would be ten drills.
    def test_three_plays_of_one_card_on_one_day_are_one_card_day(self, deck, will):
        for _ in range(3):
            make_play(will, "toe-taps-30", LONG_AGO)
        make_play(will, "toe-taps-30", LONG_AGO + timedelta(days=1))
        assert self.counts(will)[Badge.TOTAL_DRILLS] == 2

    # Catches free play being left out of the total, or counted as an eighth
    # pack, which would let All rounder be had a pack early.
    def test_free_play_is_a_go_but_not_a_pack(self, deck, will):
        make_play(will, "free-play", LONG_AGO, score=None)
        counts = self.counts(will)
        assert counts[Badge.TOTAL_DRILLS] == 1
        assert counts[Badge.SKILLS_TRIED] == 0

    # Catches the weak-foot rule: keepy-ups-weak counts by name, a per-foot
    # card counts by its flag, and keepy-ups-alternate (not per_foot, not
    # listed) does not count at all.
    def test_weak_foot_counts_weak_keepy_ups_and_per_foot_cards_only(self, deck, will):
        per_foot = Card.objects.filter(per_foot=True).first()
        assert not Card.objects.get(slug="keepy-ups-alternate").per_foot
        make_play(will, "keepy-ups-weak", LONG_AGO)
        make_play(will, per_foot.slug, LONG_AGO, score=10, weak_score=8)
        make_play(will, "keepy-ups-alternate", LONG_AGO)
        assert self.counts(will)[Badge.WEAK_FOOT] == 2

    # Catches the score leaking into juggling: 100 keepy-ups is one go, and a
    # go that scored nothing is still a go.
    def test_a_keepy_ups_score_never_counts_only_the_go(self, deck, will):
        make_play(will, "keepy-ups-best", LONG_AGO, score=100)
        make_play(will, "keepy-ups-thighs", LONG_AGO, score=0)
        assert self.counts(will)[Badge.JUGGLING] == 2

    # Catches deck_rows or the counts filtering on active cards: retiring a
    # card would take his goes on it off every kept badge.
    def test_plays_on_a_retired_card_still_count(self, deck, will):
        make_play(will, "keepy-ups-weak", LONG_AGO)
        before = self.counts(will)
        Card.objects.filter(slug="keepy-ups-weak").update(is_active=False)
        assert self.counts(will) == before
        assert before[Badge.TOTAL_DRILLS] == before[Badge.WEAK_FOOT] == 1


class TestKeptBadgeValues:
    # Catches All rounder adding skills and packs: two lists of one idea, so
    # three skills and two packs is three, never five - and the other way.
    def test_all_rounder_is_the_larger_of_skills_and_packs_never_the_sum(
        self, deck, will, drill
    ):
        for n in range(2):
            skill = Skill.objects.create(slug=f"test-skill-{n}", name=f"Skill {n}", order=10 + n)
            other_drill = Drill.objects.create(
                name=f"Drill {n}", slug=f"test-drill-{n}", skill=skill,
                instructions="Do it.", cue="Head up", duration_minutes=5,
            )
            ticks(will, other_drill, 1)
        ticks(will, drill, 1)
        make_play(will, "toe-taps-30", LONG_AGO)
        make_play(will, "keepy-ups-best", LONG_AGO)
        assert progress.kept_badge_values(will)[Badge.SKILLS_TRIED] == 3

        played = {Card.QUICK_FEET, Card.KEEPY_UPS}
        unplayed = [
            p for p, _ in Card.PACK_CHOICES if p not in played and p != Card.FREE_PLAY
        ]
        for pack in unplayed[:3]:
            make_play(will, Card.objects.filter(pack=pack).first().slug, LONG_AGO)
        assert progress.kept_badge_values(will)[Badge.SKILLS_TRIED] == 5

    # Catches the number of scored packs and All rounder's threshold coming
    # apart: an eighth pack is fine, but a pack taken away would leave the
    # badge unreachable from cards alone.
    def test_scored_packs_match_the_all_rounder_threshold(self):
        from training.management.commands.seed_drills import BADGES

        threshold = next(t for code, *_, t, _o in BADGES if code == "all-skills")
        scored = [p for p, _ in Card.PACK_CHOICES if p != Card.FREE_PLAY]
        assert len(scored) == threshold


class TestKeptBadgeAwardPaths:
    @pytest.fixture
    def seven_and_two(self, deck, all_badges, will, drill):
        """Seven old ticks and two card-days: nine, one short of 10 drills."""
        ticks(will, drill, 7)
        make_play(will, "toe-taps-30", LONG_AGO)
        make_play(will, "free-play", LONG_AGO, score=None)

    # Catches the sync path not awarding kept kinds, or not reading old
    # ticks: the third card-day is what tips seven ticks into ten.
    def test_ticks_and_card_days_together_earn_10_drills_at_sync(
        self, client, seven_and_two, will
    ):
        client.force_login(will)
        assert "drills-10" not in codes_of(will)
        body = post(client, [api_play("keepy-ups-best")]).json()
        assert "drills-10" in body["badges"]
        assert "drills-10" in codes_of(will)

    # Catches neither half alone reaching it: seven ticks, or three plays,
    # must not be ten.
    def test_neither_ticks_nor_card_days_alone_earn_10_drills(
        self, deck, all_badges, will, other, drill
    ):
        ticks(will, drill, 7)
        for slug in ("toe-taps-30", "free-play", "keepy-ups-best"):
            make_play(other, slug, LONG_AGO)
        assert "drills-10" not in {b.code for b in deck_rules.award_deck_badges(will, LONG_AGO)}
        assert "drills-10" not in {
            b.code for b in deck_rules.award_deck_badges(other, LONG_AGO)
        }

# --- 4. the deck's badge screen ----------------------------------------------


class TestDeckBadgeScreen:
    # Catches the screen dropping the kept badges or his old earned ones, or
    # promising an old badge the deck can never award ("Not yet" on Century).
    def test_the_screen_shows_kept_badges_and_his_streak_but_not_an_unearned_old_one(
        self, client, deck, all_badges, will
    ):
        earn(will, "streak-3")
        earn(will, "drills-10")
        client.force_login(will)
        rows = {r["code"]: r for r in deck_badges_in(client.get(reverse("training:deck")))}
        kept = set(
            Badge.objects.filter(kind__in=Badge.KEPT_KINDS).values_list("code", flat=True)
        )
        assert kept <= set(rows)
        assert rows["drills-10"]["earned"] and not rows["drills-50"]["earned"]
        assert rows["streak-3"]["earned"]
        assert "streak-100" not in rows
        assert "minutes-500" not in rows

    # Catches GET's earned list being cut back to deck kinds: a badge won on
    # Today would be news to the phone and celebrated twice.
    def test_get_earned_includes_his_kept_and_old_badges(
        self, client, deck, all_badges, will
    ):
        earn(will, "streak-3")
        earn(will, "drills-10")
        client.force_login(will)
        assert set(client.get(URL).json()["earned"]) == {"streak-3", "drills-10"}


# --- 5. the clear's dry run flags what the trial plays earned ----------------


