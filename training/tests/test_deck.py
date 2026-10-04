"""The deck's cards, the seeder, the one command that deletes plays, and the admin.

The cards are the product, the way seed_drills.py is for the old plan, so the
coaching brief is asserted here against every card. A play is his record:
nothing that seeds, retires or administers cards may take one away, and a
card's meaning (how it is scored) never changes under the plays already made
against it.
"""

import re
import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone

from training import deck_data
from training.deck_data import CARDS, seed_deck
from training.deck_rules import award_deck_badges
from training.models import Badge, Card, EarnedBadge, Play


@pytest.fixture
def deck(db):
    seed_deck()
    return Card.objects.all()


@pytest.fixture
def coach(db):
    return get_user_model().objects.create_superuser(
        username="phil-admin", email="phil@example.com", password="not-a-pin"
    )


def make_play(athlete, slug="toe-taps-30", day=None, score=40, weak_score=None):
    return Play.objects.create(
        id=uuid.uuid4(),
        athlete=athlete,
        card=Card.objects.get(slug=slug),
        date=day or timezone.localdate(),
        played_at=timezone.now(),
        score=score,
        weak_score=weak_score,
    )


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


# --- a card's meaning is frozen ----------------------------------------------

# (scoring, per_foot, timer_seconds, out_of, move, level) for every card, as
# first shipped. The first four decide what a score against the card means;
# move and level decide which skill of the week doubles it and which level it
# unlocks. Changing one in place silently rewrites every play already made
# against it.
FROZEN_MEANINGS = {
    "toe-taps-30": ("count", False, 30, None, "", None),
    "foundations-30": ("count", False, 30, None, "", None),
    "inside-outside-30": ("count", True, 30, None, "", None),
    "pull-push-30": ("count", True, 30, None, "", None),
    "combo-step-over-cruyff": ("count", True, 30, None, "", None),
    "combo-rollover-chop": ("count", True, 30, None, "", None),
    "combo-double-scissor": ("count", True, 30, None, "", None),
    "combo-l-turn": ("count", True, 30, None, "", None),
    "combo-croqueta-chop": ("count", True, 30, None, "", None),
    "combo-tap-drag-turn": ("count", True, 30, None, "", None),
    "rebounder-two-touch": ("count", True, 60, None, "", None),
    "rebounder-one-touch": ("count", True, 60, None, "", None),
    "rebounder-turn": ("count", True, None, 10, "", None),
    "rebounder-into-space": ("count", True, None, 10, "", None),
    "rebounder-cushion": ("count", True, None, 10, "", None),
    "slalom-race": ("time", False, None, None, "", None),
    "speed-dribble-race": ("time", False, None, None, "", None),
    "slow-slow-fast": ("count", False, None, 8, "", None),
    "corners": ("count", True, None, 5, "", None),
    "laces-rolling": ("count", True, None, 5, "", None),
    "rebounder-finish": ("count", True, None, 5, "", None),
    "volley-finish": ("count", True, None, 5, "", None),
    "keepy-ups-best": ("count", False, None, None, "", None),
    "keepy-ups-weak": ("count", False, None, None, "", None),
    "keepy-ups-alternate": ("count", False, None, None, "", None),
    "keepy-ups-thighs": ("count", False, None, None, "", None),
    "free-play": ("none", False, None, None, "", None),
    "chop-1": ("count", True, 30, None, "chop", 1),
    "chop-2": ("time", False, None, None, "chop", 2),
    "chop-3": ("count", False, None, 8, "chop", 3),
    "drag-back-1": ("count", True, 30, None, "drag-back", 1),
    "drag-back-2": ("time", False, None, None, "drag-back", 2),
    "drag-back-3": ("count", False, None, 8, "drag-back", 3),
    "scissors-1": ("count", True, 30, None, "scissors", 1),
    "scissors-2": ("time", False, None, None, "scissors", 2),
    "scissors-3": ("count", False, None, 8, "scissors", 3),
    "matthews-1": ("count", True, 30, None, "matthews", 1),
    "matthews-2": ("time", False, None, None, "matthews", 2),
    "matthews-3": ("count", False, None, 8, "matthews", 3),
    "outside-hook-1": ("count", True, 30, None, "outside-hook", 1),
    "outside-hook-2": ("time", False, None, None, "outside-hook", 2),
    "outside-hook-3": ("count", False, None, 8, "outside-hook", 3),
    "cruyff-1": ("count", True, 30, None, "cruyff", 1),
    "cruyff-2": ("time", False, None, None, "cruyff", 2),
    "cruyff-3": ("count", False, None, 8, "cruyff", 3),
    "elastico-1": ("count", True, 30, None, "elastico", 1),
    "elastico-2": ("time", False, None, None, "elastico", 2),
    "elastico-3": ("count", False, None, 8, "elastico", 3),
    "body-feint-1": ("count", True, 30, None, "body-feint", 1),
    "body-feint-2": ("time", False, None, None, "body-feint", 2),
    "body-feint-3": ("count", False, None, 8, "body-feint", 3),
}


class TestCardMeaningIsFrozen:
    # Catches a card's scoring, per-foot, timer, out-of, move or level being
    # edited in place, which makes every play already against it mean
    # something else.
    def test_no_shipped_card_changes_what_its_score_means(self):
        by_slug = {card["slug"]: card for card in CARDS}
        for slug, frozen in FROZEN_MEANINGS.items():
            assert slug in by_slug, (
                f"{slug} was taken out of CARDS. A card is never removed: "
                "leave it in CARDS and put its slug in RETIRED."
            )
            card = by_slug[slug]
            now = (
                card.get("scoring", Card.COUNT),
                card.get("per_foot", False),
                card.get("timer_seconds"),
                card.get("out_of"),
                card.get("move", ""),
                card.get("level"),
            )
            assert now == frozen, (
                f"{slug}: {frozen} -> {now}. a card's meaning changed: give it "
                "a new slug and put the old one in RETIRED (slug, move and level are "
                "frozen with the scoring)"
            )

    # Catches a new card shipping without being frozen, so the guard above
    # would never notice its meaning drift later.
    def test_every_card_is_in_the_frozen_list(self):
        missing = {card["slug"] for card in CARDS} - set(FROZEN_MEANINGS)
        assert not missing, f"new cards: add them to FROZEN_MEANINGS: {sorted(missing)}"


# --- seeding never loses a play ----------------------------------------------


@pytest.mark.django_db
class TestSeedDeckKeepsHistory:
    # Catches seed_deck deleting or recreating rows on a rerun, which runs on
    # every Render start.
    def test_running_the_seeder_twice_keeps_every_play_and_card_row(self, deck, will):
        plays = [make_play(will, slug) for slug in ("toe-taps-30", "chop-1", "free-play")]
        card_ids = set(Card.objects.values_list("pk", flat=True))
        seed_deck()
        seed_deck()
        assert set(Card.objects.values_list("pk", flat=True)) == card_ids
        assert Card.objects.count() == len(CARDS)
        for play in plays:
            stored = Play.objects.get(pk=play.pk)
            assert stored.score == play.score
            assert stored.card_id == play.card_id

    # Catches retirement deleting the card (and so failing, or with a looser
    # FK, cascading) instead of switching it off.
    def test_a_slug_in_retired_is_switched_off_and_its_plays_survive(
        self, deck, will, monkeypatch
    ):
        play = make_play(will, "toe-taps-30")
        monkeypatch.setattr(deck_data, "RETIRED", {"toe-taps-30"})
        seed_deck()
        card = Card.objects.get(slug="toe-taps-30")
        assert card.is_active is False
        assert Play.objects.filter(pk=play.pk, card=card).exists()
        assert Card.objects.active().filter(slug="chop-1").exists()

    # Catches a "deactivate anything not in CARDS" sweep, which would switch
    # off a card Dad added by hand on the next deploy.
    def test_a_card_added_by_hand_is_left_alone(self, deck):
        Card.objects.create(
            slug="test-hand-made", name="Hand made", pack=Card.QUICK_FEET,
            instructions="Do it. Then again.", cue="Go",
        )
        seed_deck()
        card = Card.objects.get(slug="test-hand-made")
        assert card.is_active is True
        assert card.name == "Hand made"

    # Catches Play.card being loosened from PROTECT: deleting a card would
    # take every score against it.
    def test_deleting_a_card_with_plays_is_refused(self, deck, will):
        play = make_play(will, "chop-1")
        with pytest.raises(ProtectedError):
            Card.objects.get(slug="chop-1").delete()
        assert Play.objects.filter(pk=play.pk).exists()

    # Catches Play.athlete being loosened from PROTECT: deleting the user
    # would take his whole deck record.
    def test_deleting_the_athlete_with_plays_is_refused(self, deck, will):
        play = make_play(will)
        with pytest.raises(ProtectedError):
            will.delete()
        assert Play.objects.filter(pk=play.pk).exists()


# --- the coaching brief, against every card ----------------------------------


@pytest.mark.django_db
class TestDeckContent:
    # Catches instructions too long for him to read alone, or a bare note.
    def test_every_card_is_two_or_three_sentences(self, deck):
        for card in deck:
            count = len(sentences(card.instructions))
            assert 2 <= count <= 3, f"{card.slug}: {count} sentences"

    # Catches a card he cannot do alone in the garden. No wall: the rebounder
    # does that job.
    def test_no_card_needs_a_wall_or_another_person(self, deck):
        for card in deck:
            text = f"{card.name} {card.instructions} {card.cue}".lower()
            for word in ("wall", "partner", "goalkeeper", "teammate"):
                assert word not in text, f"{card.slug} mentions {word}"

    # Catches the kit flag and the text disagreeing: a card that says
    # rebounder must say so on its kit line, and one that needs it must say
    # how to use it.
    def test_rebounder_in_the_text_and_the_kit_flag_agree(self, deck):
        for card in deck:
            says = "rebounder" in card.instructions.lower()
            assert says == card.needs_rebounder, card.slug

    # Catches cones in the instructions with no cones on the kit line, and
    # the reverse.
    def test_cones_in_the_text_and_the_kit_flag_agree(self, deck):
        for card in deck:
            says = "cone" in card.instructions.lower()
            assert says == card.needs_cones, card.slug

    # Catches a card that sends him at a goal without saying he needs one.
    # One direction only: laces-rolling needs a goal and says "on target".
    def test_a_card_that_says_goal_needs_a_goal(self, deck):
        for card in deck:
            if "goal" in card.instructions.lower():
                assert card.needs_goal, card.slug

    # Catches a timer on a card it makes no sense on, or a timer length the
    # bar was not designed for. A stopwatch card counting up must not also
    # have a bar filling.
    def test_timed_cards_are_count_cards_of_30_or_60_seconds(self, deck):
        for card in deck:
            if card.timer_seconds is not None:
                assert card.scoring == Card.COUNT, card.slug
                assert card.timer_seconds in (30, 60), card.slug
            if card.scoring == Card.TIME:
                assert card.timer_seconds is None, card.slug

    # Catches a second unscored card creeping in: every card but free play
    # has something to beat.
    def test_free_play_is_the_only_unscored_card(self, deck):
        unscored = list(deck.filter(scoring=Card.NONE))
        assert [card.slug for card in unscored] == ["free-play"]
        assert unscored[0].pack == Card.FREE_PLAY

    # Catches medals the wrong way round (gold easier than bronze), or a gold
    # he cannot score because it is above the card's maximum.
    def test_medals_are_ordered_and_reachable(self, deck):
        for card in deck.exclude(scoring=Card.NONE):
            medals = (card.bronze, card.silver, card.gold)
            assert None not in medals, card.slug
            if card.scoring == Card.TIME:
                assert card.bronze > card.silver > card.gold, card.slug
            else:
                assert card.bronze < card.silver < card.gold, card.slug
            if card.out_of is not None:
                assert card.out_of >= card.gold, card.slug

    # Catches a move losing a level or a level changing shape: on the spot
    # per foot in 30s, a timed cone run, then eight goes past a cone.
    def test_every_move_has_three_levels_of_the_right_shape(self, deck):
        moves = deck.filter(pack=Card.MOVES)
        names = set(moves.values_list("move", flat=True))
        assert len(names) == 8
        for move in names:
            levels = {card.level: card for card in moves.filter(move=move)}
            assert set(levels) == {1, 2, 3}, move
            assert levels[1].per_foot and levels[1].timer_seconds == 30, move
            assert levels[2].scoring == Card.TIME, move
            assert levels[3].out_of == 8, move

    # Catches a second word for an existing move: the inside cut in front is
    # the chop, behind the standing leg is the Cruyff.
    def test_no_inside_hook_or_ronaldo_anywhere(self, deck):
        for card in deck:
            text = f"{card.name} {card.instructions} {card.cue}".lower()
            assert "inside hook" not in text, card.slug
            assert "ronaldo" not in text, card.slug

    # Catches the move descriptions drifting from the drill library: scissor
    # exits with the same foot, chop cuts in front, Cruyff goes behind.
    def test_moves_are_described_the_way_the_library_describes_them(self, deck):
        assert "same foot" in Card.objects.get(slug="scissors-1").instructions
        assert "in front of you" in Card.objects.get(slug="chop-1").instructions
        assert "behind your standing leg" in Card.objects.get(slug="cruyff-1").instructions

    # Catches a retirement that leaves deck.js unable to deal a full hand:
    # five packs, always a Moves card and a Quick feet or Combos card.
    def test_a_full_hand_can_always_be_dealt(self, deck):
        active = Card.objects.active().exclude(pack=Card.FREE_PLAY)
        assert len(set(active.values_list("pack", flat=True))) >= 5
        assert active.filter(pack=Card.MOVES).exists()
        assert active.filter(pack__in=[Card.QUICK_FEET, Card.COMBOS]).exists()


# --- clear_trial_plays: the one thing that deletes a play --------------------


@pytest.mark.django_db
class TestClearTrialPlays:
    @pytest.fixture
    def plays(self, deck, will):
        today = timezone.localdate()
        trial = [make_play(will, day=today - timedelta(days=10)) for _ in range(3)]
        later = [make_play(will, day=today - timedelta(days=2)) for _ in range(2)]
        return today - timedelta(days=5), trial, later

    # Catches --through becoming optional, which would make a bare run clear
    # everything he has ever played.
    def test_through_is_required(self, plays):
        with pytest.raises(CommandError):
            call_command("clear_trial_plays", "--confirm", "--expect", "5")
        assert Play.objects.count() == 5

    # Catches the dry run deleting anything.
    def test_without_confirm_nothing_is_deleted(self, plays):
        through, _, _ = plays
        call_command("clear_trial_plays", "--through", through.isoformat())
        assert Play.objects.count() == 5

    # Catches --confirm going through without the dry-run count to check.
    def test_confirm_without_expect_deletes_nothing(self, plays):
        through, _, _ = plays
        with pytest.raises(CommandError):
            call_command("clear_trial_plays", "--through", through.isoformat(), "--confirm")
        assert Play.objects.count() == 5

    # Catches a stale count going through: he played a card since the dry run.
    def test_confirm_with_a_wrong_expect_deletes_nothing(self, plays):
        through, _, _ = plays
        with pytest.raises(CommandError):
            call_command(
                "clear_trial_plays", "--through", through.isoformat(),
                "--confirm", "--expect", "4",
            )
        assert Play.objects.count() == 5

    # Catches the date filter going wrong: only plays on or before --through
    # go, and every later play (his real ones) stays.
    def test_the_right_expect_deletes_only_plays_through_the_date(self, plays):
        through, trial, later = plays
        call_command(
            "clear_trial_plays", "--through", through.isoformat(),
            "--confirm", "--expect", "3",
        )
        assert not Play.objects.filter(pk__in=[p.pk for p in trial]).exists()
        assert set(Play.objects.values_list("pk", flat=True)) == {p.pk for p in later}


@pytest.mark.django_db
class TestClearTrialPlaysBadges:
    """The deck's badges go with the trial plays and are awarded again from
    the plays left. Nothing else of his is touched."""

    @pytest.fixture
    def record(self, deck, will):
        today = timezone.localdate()

        def badge(code, kind, is_active=True):
            return Badge.objects.create(
                code=code, name=code, description="", emoji="*",
                kind=kind, threshold=1, is_active=is_active,
            )

        old_app = badge("test-old-app", Badge.TOTAL_DRILLS)
        legend = badge("test-legend", Badge.FREE_PLAYS, is_active=False)
        badge("test-free", Badge.FREE_PLAYS)       # earned only by a trial play
        badge("test-bests", Badge.PERSONAL_BESTS)  # earned by a later play too
        make_play(will, "free-play", day=today - timedelta(days=10), score=None)
        later = make_play(will, day=today - timedelta(days=2))
        Play.objects.filter(pk=later.pk).update(bests=1)
        EarnedBadge.objects.create(athlete=will, badge=old_app, earned_on=today)
        EarnedBadge.objects.create(athlete=will, badge=legend, earned_on=today)
        assert {b.code for b in award_deck_badges(will, today)} == {"test-free", "test-bests"}
        return today - timedelta(days=5)

    def codes(self):
        return set(EarnedBadge.objects.values_list("badge__code", flat=True))

    # Catches the clear deleting the old app's badges or a Legend (which
    # could never be awarded again), keeping a badge only the trial earned,
    # or not awarding back one his own later plays still earn.
    def test_confirm_clears_trial_badges_and_awards_back_the_rest(self, record):
        call_command(
            "clear_trial_plays", "--through", record.isoformat(), "--confirm", "--expect", "1",
        )
        assert self.codes() == {"test-old-app", "test-legend", "test-bests"}

    # Catches the re-award running outside the delete's transaction: a
    # failure there would leave the plays gone and the badges half done.
    def test_a_failing_re_award_rolls_the_play_delete_back(self, record, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("simulated")

        monkeypatch.setattr(
            "training.management.commands.clear_trial_plays.award_deck_badges", explode
        )
        before = self.codes()
        with pytest.raises(RuntimeError):
            call_command(
                "clear_trial_plays", "--through", record.isoformat(),
                "--confirm", "--expect", "1",
            )
        assert Play.objects.count() == 2
        assert self.codes() == before

    # Catches the dry run not saying how many badges would go, or counting a
    # Legend that is kept.
    def test_the_dry_run_prints_the_deck_badge_count(self, record):
        out = StringIO()
        call_command("clear_trial_plays", "--through", record.isoformat(), stdout=out)
        assert "2 deck badges would be cleared" in out.getvalue()
        assert Play.objects.count() == 2


# --- admin -------------------------------------------------------------------


@pytest.mark.django_db
class TestDeckAdmin:
    # Catches NoDeleteMixin being dropped from CardAdmin or PlayAdmin, which
    # would offer Delete on a card or a play from a superuser's screen.
    @pytest.mark.parametrize("model", [Card, Play])
    def test_card_and_play_admin_refuse_delete(self, rf, coach, model):
        request = rf.get("/admin/")
        request.user = coach
        admin = site._registry[model]
        assert admin.has_delete_permission(request) is False
        assert "delete_selected" not in admin.get_actions(request)

    # The same guard over HTTP: the play is still there after the POST.
    def test_posting_the_delete_url_does_not_delete_a_play(self, client, coach, deck, will):
        play = make_play(will)
        client.force_login(coach)
        url = reverse("admin:training_play_delete", args=[play.pk])
        assert client.post(url, {"post": "yes"}).status_code == 403
        assert Play.objects.filter(pk=play.pk).exists()

    # Catches the scores becoming editable in the admin: the phone never
    # takes the server's copy, so a correction here would silently disagree
    # with his bests.
    def test_play_change_form_has_no_score_inputs(self, client, coach, deck, will):
        play = make_play(will, "chop-1", score=12, weak_score=9)
        client.force_login(coach)
        response = client.get(reverse("admin:training_play_change", args=[play.pk]))
        assert response.status_code == 200
        body = response.content.decode()
        assert 'name="score"' not in body
        assert 'name="weak_score"' not in body
        # Nor the stamp: written once on the phone, read by a restored phone.
        for field in ("points", "medal", "bests"):
            assert f'name="{field}"' not in body

    # Catches the Add button coming back: every field is read-only and the
    # id is made on the phone, so saving the empty form was a 500.
    def test_play_admin_offers_no_add(self, rf, coach):
        request = rf.get("/admin/")
        request.user = coach
        assert site._registry[Play].has_add_permission(request) is False
