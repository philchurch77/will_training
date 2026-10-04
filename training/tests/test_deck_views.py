"""The deck page, /api/plays/, the service worker, and deck.js read as source.

/api/plays/ is the backup of everything he scores. The rules it keeps:
it answers a signed-out phone in JSON, never with the PIN pad; it shows and
accepts plays for the signed-in user only; a resend changes nothing; one bad
play is refused on its own while the rest of the batch saves; and nothing it
says can make the phone throw a play away.
"""

import json
import re
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from training.deck_data import seed_deck
from training.deck_views import MAX_BATCH, MAX_SCORE, OLDEST_PLAY_DAYS
from training.models import Badge, Card, EarnedBadge, Play

pytestmark = pytest.mark.django_db

URL = "/api/plays/"


@pytest.fixture
def deck(db):
    seed_deck()


@pytest.fixture
def other(db):
    """A second account, standing in for anyone who is not Will."""
    return get_user_model().objects.create_user(username="other", password="x")


def play(card="toe-taps-30", **over):
    return {
        "id": str(uuid.uuid4()),
        "card": card,
        "date": timezone.localdate().isoformat(),
        "played_at": timezone.now().isoformat(),
        "score": 40,
        "weak_score": None,
        **over,
    }


def post(client, plays):
    return client.post(URL, data=json.dumps({"plays": plays}), content_type="application/json")


# --- A. access and isolation -------------------------------------------------


class TestPlaysApiAccess:
    # Catches login_required on the API: fetch follows the redirect and the
    # phone reads a 200 of PIN-pad HTML as a sync that worked.
    def test_signed_out_get_is_a_401_json_not_a_redirect(self, client, deck):
        response = client.get(URL)
        assert response.status_code == 401
        assert response["Content-Type"].startswith("application/json")

    # And the POST: refused in JSON, and nothing written.
    def test_signed_out_post_is_a_401_and_writes_nothing(self, client, deck):
        response = post(client, [play()])
        assert response.status_code == 401
        assert response["Content-Type"].startswith("application/json")
        assert not Play.objects.exists()

    # Catches the GET losing its athlete filter.
    def test_a_user_cannot_read_another_users_plays(self, client, deck, will, other):
        client.force_login(will)
        mine = play()
        post(client, [mine])
        client.force_login(other)
        body = client.get(URL).json()
        assert body["plays"] == []
        assert body["earned"] == []

    # Catches a resend path that overwrites, or quietly claims, someone
    # else's play by guessing its id.
    def test_a_user_cannot_overwrite_another_users_play_by_its_id(
        self, client, deck, will, other
    ):
        client.force_login(will)
        mine = play(score=40)
        post(client, [mine])
        client.force_login(other)
        body = post(client, [{**mine, "score": 99}]).json()
        assert body["saved"] == []
        assert body["refused"] == [{"id": mine["id"], "reason": "id in use"}]
        stored = Play.objects.get(pk=mine["id"])
        assert stored.athlete == will
        assert stored.score == 40

    # Catches a staff session writing plays: the phone holds one list of plays
    # whoever is signed in, so the coach account must neither file plays under
    # itself nor answer a GET that makes every one of Will's look lost.
    def test_a_staff_account_can_neither_read_nor_write_plays(self, client, deck, will):
        coach = get_user_model().objects.create_user(
            username="coach", password="x", is_staff=True
        )
        client.force_login(will)
        post(client, [play()])
        client.force_login(coach)
        assert client.get(URL).status_code == 403
        assert post(client, [play()]).status_code == 403
        assert not Play.objects.filter(athlete=coach).exists()

    # Catches the API being made csrf_exempt.
    def test_a_post_without_a_csrf_token_is_refused(self, deck, will):
        client = Client(enforce_csrf_checks=True)
        client.force_login(will)
        assert post(client, [play()]).status_code == 403
        assert not Play.objects.exists()

    # Catches the token deck.js reads (the csrftoken cookie, via X-CSRFToken)
    # no longer being the one Django checks.
    def test_a_post_with_the_cookie_token_in_the_header_is_accepted(self, deck, will):
        client = Client(enforce_csrf_checks=True)
        client.force_login(will)
        client.get(reverse("training:deck"))
        token = client.cookies["csrftoken"].value
        p = play()
        response = client.post(
            URL, data=json.dumps({"plays": [p]}), content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert response.status_code == 200
        assert response.json()["saved"] == [p["id"]]

    # Catches CSRF_COOKIE_HTTPONLY being switched on: deck.js could no longer
    # read the token and every sync would 403 for good.
    def test_the_csrf_cookie_stays_readable_by_the_page(self, settings):
        assert settings.CSRF_COOKIE_HTTPONLY is False

    # Catches a browser or proxy keeping a copy of his plays.
    def test_get_and_post_answers_are_not_stored(self, client, deck, will):
        client.force_login(will)
        assert client.get(URL)["Cache-Control"] == "no-store"
        assert post(client, [play()])["Cache-Control"] == "no-store"


# --- B. nothing is lost, nothing is doubled ----------------------------------


class TestPlaysApiKeepsEveryPlay:
    # Catches a resend overwriting the first copy, or making a second row.
    def test_the_same_play_sent_twice_is_one_row_and_the_first_score_stands(
        self, client, deck, will
    ):
        client.force_login(will)
        p = play(score=40)
        assert post(client, [p]).json()["saved"] == [p["id"]]
        assert post(client, [{**p, "score": 7}]).json()["saved"] == [p["id"]]
        assert Play.objects.count() == 1
        assert Play.objects.get(pk=p["id"]).score == 40

    # Catches a duplicate inside one batch hitting the IntegrityError path,
    # or saving twice.
    def test_the_same_play_twice_in_one_batch_is_one_row(self, client, deck, will):
        client.force_login(will)
        p = play(score=40)
        body = post(client, [p, {**p, "score": 7}]).json()
        assert body["refused"] == []
        assert set(body["saved"]) == {p["id"]}
        assert Play.objects.count() == 1
        assert Play.objects.get(pk=p["id"]).score == 40

    # Catches the server refusing a play it has lost (a disk restored from
    # backup): restore() resends it, and it must go back in.
    def test_a_play_lost_on_the_server_is_saved_again_when_resent(
        self, client, deck, will
    ):
        client.force_login(will)
        p = play(score=40)
        post(client, [p])
        Play.objects.filter(pk=p["id"]).delete()
        assert post(client, [p]).json()["saved"] == [p["id"]]
        assert Play.objects.get(pk=p["id"]).score == 40

    # Catches the race branch answering "saved" for a play that is not in
    # the database: the phone would stop sending it, and it would be gone.
    def test_a_failed_insert_with_no_row_is_refused_not_saved(
        self, client, deck, will, monkeypatch
    ):
        def fail(self, *args, **kwargs):
            raise IntegrityError("simulated")

        monkeypatch.setattr(Play, "save", fail)
        client.force_login(will)
        p = play()
        body = post(client, [p]).json()
        assert p["id"] not in body["saved"]
        assert body["refused"] == [{"id": p["id"], "reason": "not saved"}]

    # Catches the card lookup filtering on is_active: a play made before a
    # retirement is still his and the phone has no other copy.
    def test_a_play_on_a_retired_card_is_accepted(self, client, deck, will):
        Card.objects.filter(slug="toe-taps-30").update(is_active=False)
        client.force_login(will)
        p = play("toe-taps-30")
        assert post(client, [p]).json()["saved"] == [p["id"]]
        assert Play.objects.filter(pk=p["id"]).exists()

    # Catches a per-foot play losing its weak-foot score on the way in.
    def test_both_feet_round_trip_through_the_api(self, client, deck, will):
        client.force_login(will)
        p = play("chop-1", score=12, weak_score=9)
        post(client, [p])
        [back] = client.get(URL).json()["plays"]
        assert (back["id"], back["card"], back["score"], back["weak_score"]) == (
            p["id"], "chop-1", 12, 9,
        )
        assert back["date"] == p["date"]


# --- C. refusals -------------------------------------------------------------


def _bad_plays():
    today = timezone.localdate()
    upper = str(uuid.uuid4()).upper()
    return [
        ("not-a-uuid", play(id="not-a-uuid"), "bad id"),
        ("uppercase-id", play(id=upper), "bad id"),
        ("braced-id", play(id="{" + str(uuid.uuid4()) + "}"), "bad id"),
        ("unknown-card", play("no-such-card"), "unknown card"),
        ("bad-date", play(date="2026-13-40"), "bad date"),
        ("bad-time", play(played_at="yesterday-ish"), "bad time"),
        ("year-one", play(played_at="0001-01-01T00:30:00+01:00"), "bad time"),
        ("year-9999", play(played_at="9999-12-31T23:59:59-01:00"), "bad time"),
        ("bool-score", play(score=True), "bad score"),
        ("string-score", play(score="40"), "bad score"),
        ("negative-score", play(score=-1), "score out of range"),
        ("huge-score", play(score=MAX_SCORE + 1), "score out of range"),
        ("bool-weak", play(weak_score=False), "bad weak_score"),
        ("future-date", play(date=(today + timedelta(days=2)).isoformat()), "date out of range"),
        (
            "ancient-date",
            play(date=(today - timedelta(days=OLDEST_PLAY_DAYS + 1)).isoformat()),
            "date out of range",
        ),
    ]


class TestPlaysApiRefusals:
    # Catches one bad play failing (or 500ing) the whole batch, which would
    # strand every good play behind it on the phone for good.
    @pytest.mark.parametrize(
        "bad, reason", [(b, r) for _, b, r in _bad_plays()], ids=[i for i, _, _ in _bad_plays()]
    )
    def test_a_bad_play_is_refused_alone_and_the_rest_saves(
        self, client, deck, will, bad, reason
    ):
        client.force_login(will)
        good = play()
        response = post(client, [good, bad])
        assert response.status_code == 200
        body = response.json()
        assert body["saved"] == [good["id"]]
        assert [r["reason"] for r in body["refused"]] == [reason]
        assert list(Play.objects.values_list("pk", flat=True)) == [uuid.UUID(good["id"])]

    # Catches the edges of the window being off by one the wrong way:
    # tomorrow (phone across midnight) and the oldest day are accepted.
    def test_the_edges_of_the_date_window_are_accepted(self, client, deck, will):
        client.force_login(will)
        today = timezone.localdate()
        edges = [
            play(date=(today + timedelta(days=1)).isoformat()),
            play(date=(today - timedelta(days=OLDEST_PLAY_DAYS)).isoformat()),
        ]
        assert post(client, edges).json()["refused"] == []

    # Catches a malformed body reaching the parser as a 500.
    @pytest.mark.parametrize(
        "body",
        ["not json", "[1, 2]", '"plays"', '{"plays": "x"}', '{"plays": {"a": 1}}'],
        ids=["not-json", "json-list", "json-string", "plays-string", "plays-object"],
    )
    def test_a_malformed_body_is_a_400(self, client, deck, will, body):
        client.force_login(will)
        response = client.post(URL, data=body, content_type="application/json")
        assert response.status_code == 400
        assert not Play.objects.exists()

    # Catches MAX_BATCH being lost: an unbounded batch is one request doing
    # unbounded work. The phone sends the rest next time.
    def test_an_oversized_batch_saves_exactly_max_batch(self, client, deck, will):
        client.force_login(will)
        batch = [play() for _ in range(600)]
        body = post(client, batch).json()
        assert len(body["saved"]) == MAX_BATCH
        assert Play.objects.count() == MAX_BATCH
        assert body["saved"] == [p["id"] for p in batch[:MAX_BATCH]]


# --- D. the stamp: points, medal, bests --------------------------------------

STAMP = {"points": 70, "medal": 2, "bests": 1}
NO_STAMP = {"points": None, "medal": None, "bests": None}


def stored_stamp(play_id):
    p = Play.objects.get(pk=play_id)
    return {"points": p.points, "medal": p.medal, "bests": p.bests}


class TestPlaysApiStamp:
    # Catches the stamp being dropped on the way in or on the way back: the
    # phone fills a lost copy from the server's, and totals add these up.
    def test_a_stamp_in_range_is_stored_and_returned_unchanged(self, client, deck, will):
        client.force_login(will)
        p = play("chop-1", score=12, weak_score=9, **STAMP)
        assert post(client, [p]).json()["saved"] == [p["id"]]
        assert stored_stamp(p["id"]) == STAMP
        [back] = client.get(URL).json()["plays"]
        assert {k: back[k] for k in STAMP} == STAMP

    # Catches a play from before the game layer (no stamp) being refused or
    # given a made-up value.
    def test_a_play_with_no_stamp_is_stored_with_nulls(self, client, deck, will):
        client.force_login(will)
        p = play()
        assert post(client, [p]).json()["saved"] == [p["id"]]
        assert stored_stamp(p["id"]) == NO_STAMP

    # Catches a bad stamp refusing the play, which would leave a real score
    # unsent on the phone for good, or a half-kept stamp.
    @pytest.mark.parametrize(
        "bad",
        [
            {"points": 5000}, {"points": 22.5}, {"points": -1}, {"medal": 4},
            {"medal": True}, {"bests": 3}, {"bests": "1"}, {"points": {}},
        ],
        ids=[
            "points-huge", "points-float", "points-negative", "medal-4",
            "medal-bool", "bests-3", "bests-string", "points-object",
        ],
    )
    def test_a_bad_stamp_drops_all_three_fields_and_keeps_the_play(
        self, client, deck, will, bad
    ):
        client.force_login(will)
        p = play(score=40, **{**STAMP, **bad})
        body = post(client, [p]).json()
        assert body["saved"] == [p["id"]]
        assert body["refused"] == []
        assert Play.objects.get(pk=p["id"]).score == 40
        assert stored_stamp(p["id"]) == NO_STAMP

    # Catches a medal claimed on a play with no score at all.
    def test_a_medal_with_no_score_drops_the_stamp_and_keeps_the_play(
        self, client, deck, will
    ):
        client.force_login(will)
        p = play(score=None, weak_score=None, points=10, medal=3, bests=0)
        assert post(client, [p]).json()["saved"] == [p["id"]]
        assert Play.objects.filter(pk=p["id"]).exists()
        assert stored_stamp(p["id"]) == NO_STAMP

    # Catches a resend rewriting the stamp: a stamp is written once, so a
    # later change to the points table never reaches an old play.
    def test_a_resend_with_a_different_stamp_changes_nothing(self, client, deck, will):
        client.force_login(will)
        p = play(**STAMP)
        post(client, [p])
        resend = {**p, "points": 110, "medal": 3, "bests": 2}
        assert post(client, [resend]).json()["saved"] == [p["id"]]
        assert stored_stamp(p["id"]) == STAMP

    # Catches another account restamping Will's play by guessing its id.
    def test_another_user_cannot_restamp_wills_play(self, client, deck, will, other):
        client.force_login(will)
        p = play(**STAMP)
        post(client, [p])
        client.force_login(other)
        body = post(client, [{**p, "points": 999, "medal": 3, "bests": 2}]).json()
        assert body["refused"] == [{"id": p["id"], "reason": "id in use"}]
        assert stored_stamp(p["id"]) == STAMP
        assert Play.objects.get(pk=p["id"]).athlete == will

    # Catches a stamp opening a way round the staff refusal.
    def test_a_staff_account_is_still_refused_with_a_stamp(self, client, deck):
        coach = get_user_model().objects.create_user(
            username="coach", password="x", is_staff=True
        )
        client.force_login(coach)
        assert post(client, [play(**STAMP)]).status_code == 403
        assert not Play.objects.exists()


# --- F. the page and the service worker --------------------------------------


class TestDeckPage:
    def cards_in(self, response):
        match = re.search(
            r'<script id="deck-cards" type="application/json">(.*?)</script>',
            response.content.decode(), re.S,
        )
        assert match, "the cards are no longer baked into the page as deck-cards"
        return json.loads(match.group(1))

    # Catches a retired card still being dealt, or the page building from
    # Card.objects.all().
    def test_the_page_bakes_in_only_active_cards(self, client, deck, will):
        Card.objects.filter(slug="chop-1").update(is_active=False)
        client.force_login(will)
        response = client.get(reverse("training:deck"))
        assert response.status_code == 200
        slugs = {card["slug"] for card in self.cards_in(response)}
        assert slugs == set(Card.objects.active().values_list("slug", flat=True))
        assert "chop-1" not in slugs
        assert "training/js/deck.js" in response.content.decode()

    # Catches the rules not reaching the phone: deck.js falls back to no game
    # at all (every stamp null) when deck-rules is missing or unreadable.
    def test_the_page_bakes_in_the_rules(self, client, deck, will):
        client.force_login(will)
        match = re.search(
            r'<script id="deck-rules" type="application/json">(.*?)</script>',
            client.get(reverse("training:deck")).content.decode(), re.S,
        )
        assert match, "the rules are no longer baked into the page as deck-rules"
        rules = json.loads(match.group(1))
        assert rules["levels"] and rules["calendar"]

    # Catches the script being renamed or moved without the page following.
    def test_the_deck_script_exists(self):
        assert finders.find("training/js/deck.js")

    # Catches the switch-over (leg 3c) being undone: the deck is the lit
    # Cards tab, and nothing links back to the retired Today.
    def test_the_deck_is_the_cards_tab(self, client, will, seeded):
        client.force_login(will)
        deck = client.get(reverse("training:deck")).content.decode()
        assert 'href="/" class="tab is-on" data-tab="cards"' in deck
        assert 'href="/today/"' not in deck


class TestDeckServiceWorker:
    def body(self, client):
        return client.get("/sw.js").content.decode()

    # Catches the deck not working with no signal: the page at / and its
    # script must be in the precache list.
    def test_the_deck_page_and_script_are_precached(self, client, deck):
        body = self.body(client)
        assert '"/"' in body
        assert "deck.js" in body

    # Catches the service worker answering /api/ from cache (an old list) or
    # with the offline page as a 200 that the phone reads as a sync.
    def test_the_service_worker_leaves_the_api_alone(self, client, deck):
        compact = re.sub(r"\s+", " ", self.body(client))
        assert re.search(
            r"""startsWith\(\s*['"]/api/['"]\s*\)\s*\)\s*\{\s*return;\s*\}""", compact
        ), "sw.js no longer returns early for /api/ requests"

    # Catches the cache name going, which is what makes a deploy replace
    # last week's deck.js.
    def test_the_cache_is_versioned(self, client, deck):
        assert re.search(r"const CACHE = '[^']+-v\d+';", self.body(client))

    # Catches leg 2's deck.js shipping under the old cache name: phones
    # would keep last deploy's script, which stamps nothing.
    def test_the_cache_was_bumped_for_the_game_layer(self, client, deck):
        assert "const CACHE = 'will-training-v21';" not in self.body(client)

    # Catches 2b's deck.js (badges, the week bar, the server cache) shipping
    # under 2a's cache name: phones would keep the script with none of it.
    def test_the_cache_was_bumped_for_goals_and_badges(self, client, deck):
        body = self.body(client)
        assert "const CACHE = 'will-training-v22';" not in body
        assert "const CACHE = 'will-training-v21';" not in body


# --- H. deck.js, read as source ----------------------------------------------


class TestDeckScript:
    """There is no JavaScript runner here (no node, no build step), so these
    read deck.js and assert the shape of each guard, the way
    TestSessionClockScript reads session.js. Whitespace is collapsed so a
    reformat does not fail them; removing the guard does."""

    def source(self):
        return Path("training/static/training/js/deck.js").read_text(encoding="utf-8")

    def compact(self):
        return re.sub(r"\s+", " ", self.source())

    def function_body(self, name):
        source = self.source()
        start = source.find(f"function {name}(")
        assert start != -1, f"deck.js no longer has a {name}() function"
        open_at = source.index("{", start)
        depth = 0
        for i in range(open_at, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    return re.sub(r"\s+", " ", source[open_at:i + 1])
        raise AssertionError(f"{name}() never closes")

    # Catches digits counting down at him on a timed card - the one thing the
    # timed-card exception does not allow.
    def test_the_timed_bar_writes_no_text_or_numbers(self):
        body = self.function_body("runTimedBar")
        for banned in (
            "textContent", "innerText", "innerHTML", "toFixed",
            "aria-valuenow", "aria-valuetext",
        ):
            assert banned not in body, f"runTimedBar uses {banned}"
        assert "Date.now() - startedAt" in body

    # Catches the stopwatch counting ticks, which drift and stall when the
    # screen sleeps, instead of reading the clock.
    def test_the_stopwatch_reads_the_clock(self):
        assert "Date.now() - startedAt" in self.function_body("stopwatch")

    # Catches a UTC date: a play at 00:30 in summer would land on yesterday.
    def test_the_date_is_never_cut_from_a_utc_string(self):
        compact = self.compact()
        assert not re.search(r"toISOString\(\)\s*\.\s*(slice|substring|substr)\(", compact)
        assert "getFullYear()" in self.function_body("localDate")

    # Catches savePlays losing the guard that makes the list only grow.
    def test_save_plays_refuses_a_shorter_or_incomplete_list(self):
        body = self.function_body("savePlays")
        assert re.search(r"next\.length < current\.length\s*\)\s*\{?\s*return false", body)
        assert re.search(r"if \(!ids\[current\[i\]\.id\]\)\s*\{?\s*return false", body)

    # Catches any code path that removes a key from storage outright.
    def test_nothing_removes_a_key_from_storage(self):
        assert "removeItem" not in self.source()

    # Catches the plays key changing, which orphans every play already on
    # the phone.
    def test_the_plays_key_is_unchanged(self):
        assert "var PLAYS_KEY = 'will-deck-plays-v1';" in self.compact()

    # Catches restore() trusting its own "synced" flag over the server's
    # list, so a play lost on the server would never be resent.
    def test_restore_marks_plays_the_server_lost_as_unsent(self):
        body = self.function_body("restore")
        assert re.search(
            r"if \(play\.synced && !theirs\[play\.id\]\) \{[^}]*play\.synced = false", body
        )

    # Catches the weak-foot score living only in memory until the strong
    # foot is done: a page thrown away mid-card would lose it.
    def test_the_weak_foot_score_goes_to_the_draft_key_straight_away(self):
        compact = self.compact()
        assert "var DRAFT_KEY = 'will-deck-draft-v1';" in compact
        assert re.search(
            r"if \(foot === 'weak'\) \{ setItem\(DRAFT_KEY, JSON\.stringify\(\{[^}]*weak: value",
            compact,
        )

    # Catches the token being read from the page, which goes stale at the
    # next sign-in on a cached copy.
    def test_the_csrf_token_is_read_from_the_cookie_at_send_time(self):
        body = self.function_body("csrfToken")
        assert "document.cookie" in body and "csrftoken" in body
        assert "'X-CSRFToken': csrfToken()" in self.compact()

    # Catches makePlay dropping the stamp: wire() and restore() both build
    # plays through it, so a missing field is lost on every sync.
    def test_make_play_copies_the_stamp(self):
        body = self.function_body("makePlay")
        for field in ("points", "medal", "bests"):
            assert f"{field}: nullable(fields.{field})" in body, field

    # Catches restore() overwriting a stamp the phone already has, or never
    # filling one it lost.
    def test_restore_fills_only_null_stamp_fields_from_the_server(self):
        body = self.function_body("restore")
        assert "['points', 'medal', 'bests']" in body
        assert re.search(
            r"if \(local\[field\] === null && s\[field\] !== null[^)]*\) \{ local\[field\] = s\[field\];",
            body,
        )

    # Catches a medal being worked out a second time somewhere else, against
    # today's targets rather than the ones the play was stamped with.
    def test_stamp_is_the_only_caller_of_medal_for(self):
        assert self.source().count("medalFor(") == 2
        assert "medalFor(card, score, weak)" in self.function_body("stamp")

    # Catches a locked level being dealt, or kept in a stored hand.
    def test_deal_and_the_stored_hand_skip_locked_cards(self):
        assert "isOpen(c, plays)" in self.function_body("deal")
        assert "isOpen(BY_SLUG[s], plays)" in self.function_body("currentHand")

    # Catches a game number copied into deck.js: there is no JS test runner,
    # so a copy could drift from deck_rules.py with nothing to notice.
    def test_no_game_number_is_written_into_the_script(self):
        # `seconds * 1000` is milliseconds in runTimedBar, not a level.
        source = re.sub(r"\*\s*1000\b", "* MS", self.source())
        for threshold in ("300", "1000", "2500", "5000"):
            assert not re.search(rf"\b{threshold}\b", source), threshold
        assert not re.search(r"\b(base|weak_foot|best|skill_multiplier)\s*:\s*\d", source)
        assert "RULES.points" in self.function_body("stamp")

    # Catches a first score of 0 counting as a best to beat, which turns any
    # next score into a bonus and a "New best!".
    def test_a_zero_best_is_no_best_in_stamp_and_verdict(self):
        assert "realBest(value) { return value === 0 ? null : value; }" in self.compact()
        assert "realBest(before.score) !== null" in self.function_body("stamp")
        assert "realBest(best) === null" in self.function_body("verdict")

    # Catches the weeks-in-a-row line vanishing every Monday: before the
    # phone syncs, the server's figure is for last week and must be rolled on
    # from his own plays, not dropped.
    def test_weeks_in_a_row_survives_a_monday_before_sync(self):
        body = self.function_body("weekStatus")
        assert "addDays(monday, -7)" in body
        assert "gw.before + 1" in body
        # And a moved weeks figure from the server redraws the hand.
        assert "return moved" in self.function_body("noteServer")

    # Catches free play saving silently again: a level-up it caused was
    # applied and never shown.
    def test_free_play_shows_what_it_earned(self):
        body = self.function_body("freePlayButton")
        assert "gameState(" in body
        assert "rewardLines(" in body
        assert "flashCard()" in self.function_body("renderHand")

    # Catches the game layer reaching into the timed bar: points or medals
    # on a timer are a number counting at him.
    def test_the_timed_bar_knows_nothing_of_the_game(self):
        body = self.function_body("runTimedBar")
        for banned in ("RULES", "points", "medal", "stamp", "level"):
            assert banned not in body, f"runTimedBar mentions {banned}"

    # --- leg 2b: goals and badges ---

    # Catches free play being left out of the day's count again: the server
    # counts it as one of the three (deck_rules.session_dates), so the hand
    # would say "2 of 3" on a day the server already calls a session.
    def test_the_hand_counts_free_play_as_a_card(self):
        body = self.function_body("renderHand")
        assert "!== FREE_PLAY" not in body
        assert "!= FREE_PLAY" not in body
        assert "Object.keys(done).length" in body

    # Catches the weekly bar carrying its own copy of the session or goal
    # numbers instead of reading deck_rules through RULES.
    def test_the_week_reads_session_and_goal_numbers_from_rules(self):
        # The session size is counted in sessionsBetween, the goal in weekStatus.
        body = self.function_body("weekStatus") + self.function_body("sessionsBetween")
        assert "RULES.session_cards" in body
        assert "RULES.goal_sessions" in body
        assert not re.search(r"(>=|>|===)\s*\d", body), "weekStatus compares against a literal"

    # Catches the server cache key changing, which would forget every badge
    # the phone has been told about and celebrate them all again.
    def test_the_server_key_is_unchanged(self):
        assert "var SERVER_KEY = 'will-deck-server-v1';" in self.compact()

    # Catches the phone's earned list shrinking: already earned stays earned,
    # whatever one sync's answer happens to say.
    def test_note_server_only_ever_adds_to_earned(self):
        body = self.function_body("noteServer")
        assert "s.earned.push(code)" in body
        assert "splice" not in body
        assert "filter" not in body
        assert not re.search(r"s\.earned\s*=[^=]", body), "noteServer reassigns s.earned"

    # Catches the badge flash clearing a badge an old cached page cannot
    # name: it would never be celebrated anywhere.
    def test_badge_flash_clears_only_badges_it_can_name(self):
        body = self.function_body("badgeFlash")
        assert re.search(
            r"s\.unseen = s\.unseen\.filter\(function \(code\) \{ return !badgeByCode\(code\); \}\)",
            body,
        )
        assert not re.search(r"s\.unseen\s*=\s*\[\]", body)


    # --- leg 3a: the head start ---

    # Catches bestsFor starting from nothing: his old best would never be
    # the score to beat and the first play would claim a "New best!".
    def test_bests_start_from_the_old_apps_best(self):
        body = self.function_body("bestsFor")
        assert "RULES.starting_bests[card.slug]" in body
        assert "score: start ? start.score : null" in body

    # Catches the "(from before)" label going, so a number on a card he has
    # never played looks like a mistake; or spreading to per-foot cards,
    # which carry no old best.
    def test_best_line_says_from_before_only_on_a_single_score_card(self):
        body = self.function_body("bestLine")
        assert "RULES.starting_bests[card.slug]" in body
        assert "best.score === start.score" in body
        assert "(fromBefore ? ' (from before)' : '')" in body
        assert body.index("if (!card.per_foot)") < body.index("(from before)")

    # Catches the head-start line showing "Includes 0 points" to an account
    # with no history, or vanishing for one with a head start.
    def test_the_game_strip_names_the_head_start_only_when_there_is_one(self):
        body = self.function_body("gameStrip")
        assert re.search(
            r"RULES\.starting_points > 0 \? el\(.*?from before the cards\.' \}\) : null,",
            body,
        )


# --- I. leg 2b: badges at sync, one user's own ---------------------------------


@pytest.fixture
def badges(db):
    """The deck's badges exactly as seed_drills ships them."""
    from training.management.commands.seed_drills import BADGES

    for code, name, description, emoji, kind, threshold, order in BADGES:
        if kind in Badge.DECK_KINDS:
            Badge.objects.create(
                code=code, name=name, description=description, emoji=emoji,
                kind=kind, threshold=threshold, order=order,
            )


def free_play(**over):
    return play("free-play", score=None, **over)


def deck_badges_in(response):
    match = re.search(
        r'<script id="deck-badges" type="application/json">(.*?)</script>',
        response.content.decode(), re.S,
    )
    assert match, "the badges are no longer baked into the page as deck-badges"
    return json.loads(match.group(1))


class TestDeckBadgeIsolation:
    # Catches the GET's earned list or goal weeks losing the athlete filter:
    # another account's Free player would show on Will's phone as his.
    def test_another_users_badge_is_not_in_wills_get(self, client, deck, badges, will, other):
        client.force_login(other)
        assert "free-player" in post(client, [free_play()]).json()["badges"]
        client.force_login(will)
        body = client.get(URL).json()
        assert body["earned"] == []
        assert body["goal_weeks"]["before"] == 0

    # Catches the award reading every user's plays: Will's first ordinary
    # play would be answered with the other account's badge.
    def test_another_users_plays_award_will_nothing(self, client, deck, badges, will, other):
        client.force_login(other)
        post(client, [free_play()])
        client.force_login(will)
        body = post(client, [play()]).json()
        assert body["badges"] == []
        assert body["goal_weeks"]["before"] == 0
        assert not EarnedBadge.objects.filter(athlete=will).exists()

    # Catches _deck_badges_json marking a badge earned because anyone earned
    # it, rather than the signed-in user.
    def test_the_page_marks_nothing_earned_from_another_users_award(
        self, client, deck, badges, will, other
    ):
        client.force_login(other)
        post(client, [free_play()])
        client.force_login(will)
        rows = deck_badges_in(client.get(reverse("training:deck")))
        assert rows, "no deck badges baked in at all"
        assert not any(row["earned"] for row in rows)

    # Catches the staff refusal moving after the award: the coach account
    # collects no deck badges, any more than plays.
    def test_a_staff_post_is_refused_and_awards_nothing(self, client, deck, badges):
        coach = get_user_model().objects.create_user(
            username="coach", password="x", is_staff=True
        )
        client.force_login(coach)
        assert post(client, [free_play()]).status_code == 403
        assert not EarnedBadge.objects.exists()

    # Catches a signed-out sync reaching the award.
    def test_a_signed_out_post_is_a_401_and_awards_nothing(self, client, deck, badges):
        assert post(client, [free_play()]).status_code == 401
        assert not EarnedBadge.objects.exists()


class TestDeckBadgeAwarding:
    # Catches the award not running at sync, or not answering the codes the
    # phone celebrates.
    def test_a_free_play_awards_free_player_dated_today(self, client, deck, badges, will):
        client.force_login(will)
        body = post(client, [free_play()]).json()
        assert body["badges"] == ["free-player"]
        earned = EarnedBadge.objects.get(athlete=will, badge__code="free-player")
        assert earned.earned_on == timezone.localdate()

    # Catches a resend awarding again: a second row, or a second celebration.
    def test_a_resend_awards_nothing_new_and_keeps_one_row(self, client, deck, badges, will):
        client.force_login(will)
        p = free_play()
        post(client, [p])
        body = post(client, [p]).json()
        assert body["saved"] == [p["id"]]
        assert body["badges"] == []
        assert EarnedBadge.objects.filter(athlete=will, badge__code="free-player").count() == 1

    # Catches awarding only when a play is newly inserted: a sync whose award
    # was lost must be put right by the resend alone.
    def test_a_resend_alone_awards_a_badge_that_was_lost(self, client, deck, badges, will):
        client.force_login(will)
        p = free_play()
        post(client, [p])
        EarnedBadge.objects.filter(athlete=will).delete()
        body = post(client, [p]).json()
        assert body["badges"] == ["free-player"]
        assert EarnedBadge.objects.filter(athlete=will, badge__code="free-player").exists()

    # Catches a badge failure taking the sync down: the play must be saved and
    # acknowledged, or the phone resends it forever.
    def test_an_award_that_raises_still_saves_the_play(
        self, client, deck, badges, will, monkeypatch
    ):
        def explode(*args, **kwargs):
            raise RuntimeError("simulated")

        monkeypatch.setattr("training.deck_views.award_deck_badges", explode)
        client.force_login(will)
        p = free_play()
        response = post(client, [p])
        assert response.status_code == 200
        assert response.json()["saved"] == [p["id"]]
        assert response.json()["badges"] == []
        assert Play.objects.filter(pk=p["id"]).exists()

    # Catches the award re-checking earned badges against today's threshold:
    # raising a threshold must never take a badge off him.
    def test_an_earned_badge_survives_its_threshold_being_raised(
        self, client, deck, badges, will
    ):
        client.force_login(will)
        post(client, [free_play()])
        Badge.objects.filter(code="free-player").update(threshold=50)
        post(client, [play()])
        assert EarnedBadge.objects.filter(athlete=will, badge__code="free-player").exists()
        assert "free-player" in client.get(URL).json()["earned"]

    # Catches award_deck_badges dropping its is_active filter: a retired badge
    # would be handed out new.
    def test_an_inactive_badge_is_never_awarded(self, client, deck, badges, will):
        Badge.objects.filter(code="free-player").update(is_active=False)
        client.force_login(will)
        assert post(client, [free_play()]).json()["badges"] == []
        assert not EarnedBadge.objects.filter(badge__code="free-player").exists()


class TestStampCrossChecks:
    """Gold medal and Record breaker trust the stamp, so a stamp the card
    could never have earned is dropped. The play itself is always kept."""

    # Catches each cross-check in _parse_stamp being loosened. Free play is
    # sent with a score so the medal-needs-a-score check cannot be what drops
    # it, and the one-foot card carries a weak score that must not count.
    @pytest.mark.parametrize(
        "card, scores, stamp",
        [
            ("free-play", {"score": 5}, {"points": 10, "medal": 1}),
            ("free-play", {"score": 5}, {"points": 10, "bests": 1}),
            ("toe-taps-30", {"score": 0}, {"points": 10, "medal": 3}),
            ("chop-1", {"score": 12, "weak_score": None}, {"points": 10, "medal": 3}),
            ("chop-1", {"score": 12, "weak_score": 0}, {"points": 10, "medal": 3}),
            ("toe-taps-30", {"score": 40, "weak_score": 30}, {"points": 10, "bests": 2}),
            ("chop-1", {"score": 12, "weak_score": None}, {"points": 10, "bests": 2}),
        ],
        ids=[
            "unscored-card-medal", "unscored-card-best", "medal-on-zero",
            "per-foot-medal-no-weak", "per-foot-medal-weak-zero",
            "two-bests-one-foot-card", "two-bests-one-foot-scored",
        ],
    )
    def test_an_impossible_stamp_is_dropped_and_the_play_kept(
        self, client, deck, will, card, scores, stamp
    ):
        client.force_login(will)
        p = play(card, **{"weak_score": None, **scores, **stamp})
        body = post(client, [p]).json()
        assert body["saved"] == [p["id"]]
        assert body["refused"] == []
        assert Play.objects.get(pk=p["id"]).score == scores["score"]
        assert stored_stamp(p["id"]) == NO_STAMP

    # Catches the cross-checks being so strict they drop a real gold with a
    # best on each foot.
    def test_a_per_foot_gold_with_two_bests_is_kept(self, client, deck, will):
        client.force_login(will)
        stamp = {"points": 110, "medal": 3, "bests": 2}
        p = play("chop-1", score=14, weak_score=12, **stamp)
        post(client, [p])
        assert stored_stamp(p["id"]) == stamp


# --- J. leg 3a: the head start, one user's own --------------------------------


def rules_in(response):
    match = re.search(
        r'<script id="deck-rules" type="application/json">(.*?)</script>',
        response.content.decode(), re.S,
    )
    assert match, "the rules are no longer baked into the page as deck-rules"
    return json.loads(match.group(1))


@pytest.fixture
def history_drills(db):
    """The three old drills that map onto cards, as rep drills."""
    from training.models import Drill, Skill

    skill = Skill.objects.get_or_create(
        slug="first-touch", defaults={"name": "First touch", "order": 2}
    )[0]
    return {
        slug: Drill.objects.create(
            name=slug, slug=slug, skill=skill, instructions="Juggle.",
            cue="Toes up", target_reps=30,
        )
        for slug in ("thigh-juggles", "weak-foot-juggles", "alternate-foot-juggles")
    }


def tick(athlete, drill, days, reps):
    from training.models import SessionLog

    start = timezone.localdate() - timedelta(days=400)
    for n in range(days):
        SessionLog.objects.create(
            athlete=athlete, drill=drill, date=start + timedelta(days=n), actual_reps=reps
        )


class TestDeckHeadStartIsolation:
    # Catches history_for reading every athlete's logs, or the view passing
    # anyone but request.user: each deck must carry its own head start.
    def test_each_deck_carries_only_its_own_users_head_start(
        self, client, deck, will, other, history_drills
    ):
        tick(will, history_drills["thigh-juggles"], 3, reps=12)
        tick(other, history_drills["weak-foot-juggles"], 7, reps=40)

        client.force_login(will)
        mine = rules_in(client.get(reverse("training:deck")))
        assert mine["starting_points"] == 15
        assert mine["starting_bests"] == {"keepy-ups-thighs": {"score": 12, "weak": None}}

        client.force_login(other)
        theirs = rules_in(client.get(reverse("training:deck")))
        assert theirs["starting_points"] == 35
        assert theirs["starting_bests"] == {"keepy-ups-weak": {"score": 40, "weak": None}}

    # Catches the coach account being handed Will's history (get_athlete()
    # in place of request.user, say).
    def test_a_staff_account_gets_no_head_start_from_wills_logs(
        self, client, deck, will, history_drills
    ):
        tick(will, history_drills["thigh-juggles"], 3, reps=12)
        staff = get_user_model().objects.create_user(
            username="phil", password="x", is_staff=True
        )
        client.force_login(staff)
        rules = rules_in(client.get(reverse("training:deck")))
        assert rules["starting_points"] == 0
        assert rules["starting_bests"] == {}

    # Catches a fresh account with no logs being handed someone else's
    # head start, or a key going missing when there is nothing to give.
    def test_an_account_with_no_logs_starts_from_nothing(
        self, client, deck, will, other, history_drills
    ):
        tick(will, history_drills["alternate-foot-juggles"], 2, reps=9)
        client.force_login(other)
        rules = rules_in(client.get(reverse("training:deck")))
        assert rules["starting_points"] == 0
        assert rules["starting_bests"] == {}


class TestDeckServiceWorkerHeadStart:
    # Catches leg 3a's deck.js shipping under 2b's cache name: phones would
    # keep the script that ignores the head start.
    def test_the_cache_was_bumped_for_the_head_start(self, client, deck):
        body = client.get("/sw.js").content.decode()
        for old in ("v21", "v22", "v23"):
            assert f"const CACHE = 'will-training-{old}';" not in body
