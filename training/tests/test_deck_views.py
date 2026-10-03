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
from training.models import Card, Play

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
        assert client.get(URL).json() == {"plays": []}

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

    # Catches the script being renamed or moved without the page following.
    def test_the_deck_script_exists(self):
        assert finders.find("training/js/deck.js")

    # Catches the deck reaching Will's own screens before leg 3: it is
    # reached from the coach plan only.
    def test_the_deck_is_linked_from_coach_and_not_from_today(self, client, will, seeded):
        client.force_login(will)
        deck_url = reverse("training:deck")
        assert deck_url in client.get(reverse("training:coach_plan")).content.decode()
        assert deck_url not in client.get(reverse("training:today")).content.decode()


class TestDeckServiceWorker:
    def body(self, client):
        return client.get("/sw.js").content.decode()

    # Catches the deck not working with no signal: the page and its script
    # must be in the precache list.
    def test_the_deck_page_and_script_are_precached(self, client, deck):
        body = self.body(client)
        assert '"/deck/"' in body
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
