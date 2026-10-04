"""Leg 4: his cards on the coach page (/coach/), read-only.

The page sums and maxes what his phone stamped, so it must agree with the
phone (levelFor, bestsFor, counts and beats in deck.js), show only his plays,
and stay behind the coach sign-in. Access first, then the rules.
"""

import html
import json
import logging
import re
import uuid
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from training import deck_rules
from training.deck_data import seed_deck
from training.models import Card, Drill, Play, SessionLog
from training.templatetags.deck_format import medal, score

pytestmark = pytest.mark.django_db

URL = "/coach/"
TODAY = date(2026, 10, 7)  # a Wednesday
LONG_AGO = date(2026, 1, 5)


# --- fixtures and helpers ----------------------------------------------------


@pytest.fixture
def deck(db):
    seed_deck()


@pytest.fixture
def other(db):
    """A second non-staff account, made after Will, so get_athlete() is Will."""
    return get_user_model().objects.create_user(username="other", password="x")


@pytest.fixture
def coach(db):
    return get_user_model().objects.create_user(
        username="coach", password="x", is_staff=True
    )


@pytest.fixture
def thigh_drill(skill):
    """The old drill that HISTORY_CARDS maps to keepy-ups-thighs."""
    return Drill.objects.create(
        name="Thigh juggles", slug="thigh-juggles", skill=skill,
        instructions="Juggle with your thighs.", cue="Flat", target_reps=20,
    )


def make_play(athlete, slug, day=TODAY, score=10, weak_score=None, points=None,
              medal=None, played_at=None):
    return Play.objects.create(
        id=uuid.uuid4(), athlete=athlete, card=Card.objects.get(slug=slug),
        date=day, played_at=played_at or timezone.now(), score=score,
        weak_score=weak_score, points=points, medal=medal,
    )


def ticks(athlete, drill, count, reps=None):
    for n in range(count):
        SessionLog.objects.create(
            athlete=athlete, drill=drill, date=LONG_AGO + timedelta(days=n),
            actual_reps=reps,
        )


def _cells(table_html):
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", table_html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if cells:
            rows.append([
                " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                for c in cells
            ])
    return rows


def _sections(response):
    page = response.content.decode()
    head, _, plays = page.partition("His plays</h2>")
    assert plays, "the plays section heading has moved"
    _, _, bests = head.partition("Best on each card</h2>")
    return bests, plays


def best_rows(response):
    """Cell text of the Best on each card table: [card, best, medal, played]."""
    return _cells(_sections(response)[0])


def play_rows(response):
    """Cell text of the His plays table: [date, card, score, medal, points]."""
    return _cells(_sections(response)[1])


def best_for(response, name):
    rows = [row for row in best_rows(response) if row[0].startswith(name)]
    assert len(rows) == 1, f"{name} is not exactly once in the bests: {rows}"
    return rows[0]


def coach_get(client, coach, **params):
    client.force_login(coach)
    return client.get(URL, params)


# --- 1. another user's plays never reach his figures -------------------------


class TestCoachPageIsolation:
    # Catches coach_summary losing its athlete filter on the Sum, or
    # history_for counting someone else's ticks into his head start.
    def test_another_users_plays_and_ticks_do_not_change_his_summary(
        self, deck, will, other, rep_drill
    ):
        make_play(will, "toe-taps-30", score=40, points=25)
        ticks(will, rep_drill, 2)
        before = deck_rules.coach_summary(will, TODAY)

        for n in range(4):
            make_play(other, "toe-taps-30", day=TODAY - timedelta(days=n % 2),
                      score=90, points=500)
        make_play(other, "slalom-race", score=987, points=500)
        make_play(other, "foundations-30", score=5, points=500)
        ticks(other, rep_drill, 50)

        after = deck_rules.coach_summary(will, TODAY)
        assert after == before
        assert after["points"] == 25 + 10

    # Catches card_bests losing its athlete filter: another account's higher
    # score, or a card he never played, would show as Will's best.
    def test_another_users_plays_do_not_change_his_card_bests(self, deck, will, other):
        make_play(will, "toe-taps-30", score=40, medal=0)
        before = deck_rules.card_bests(will)

        make_play(other, "toe-taps-30", score=99, medal=3)
        make_play(other, "slalom-race", score=987, medal=3)

        after = deck_rules.card_bests(will)
        assert after == before
        assert [(row["slug"], row["best"], row["plays"]) for row in after] == [
            ("toe-taps-30", 40, 1)
        ]

    # Catches the view reading plays for request.user or for everyone rather
    # than for Will: the coach page must not show another account's card.
    def test_the_coach_page_does_not_show_another_users_card_or_score(
        self, client, deck, will, other, coach
    ):
        make_play(will, "toe-taps-30", score=40, points=25)
        make_play(other, "speed-dribble-race", score=987, points=999)

        response = coach_get(client, coach)
        page = response.content.decode()
        assert response.status_code == 200
        assert "Speed dribble race" not in page
        assert "98.7" not in page
        assert "999" not in page
        assert [row[1] for row in play_rows(response)] == ["Toe tap race Quick feet"]


# --- 2. who can reach the page ----------------------------------------------


class TestCoachPageAccess:
    # Catches the staff route breaking: Dad reads the page signed in as the
    # coach, and it must show Will's plays, not the coach's (none).
    def test_a_staff_session_sees_wills_plays(self, client, deck, will, coach):
        make_play(will, "toe-taps-30", score=47, points=25)
        response = coach_get(client, coach)
        assert response.status_code == 200
        rows = play_rows(response)
        assert len(rows) == 1
        assert rows[0][1].startswith("Toe tap race")
        assert rows[0][2] == "47"

    # Catches the staff guard coming off /api/plays/: Dad's phone would file
    # plays under the coach, or on Will's record.
    def test_a_staff_session_cannot_write_a_play(self, client, deck, will, coach):
        client.force_login(coach)
        body = {"plays": [{
            "id": str(uuid.uuid4()), "card": "toe-taps-30",
            "date": timezone.localdate().isoformat(),
            "played_at": timezone.now().isoformat(), "score": 40, "weak_score": None,
        }]}
        response = client.post(
            reverse("training:api_plays"), data=json.dumps(body),
            content_type="application/json",
        )
        assert response.status_code == 403
        assert not Play.objects.exists()

    # Catches coach_required coming off: the page holds his whole record.
    # Catches the coach door leading to Will's PIN pad (the Lookout's High,
    # leg 4): a PIN session on Dad's phone could sync its plays onto Will.
    def test_signed_out_get_goes_to_the_staff_sign_in(self, client, deck, will):
        make_play(will, "toe-taps-30", score=47)
        response = client.get(URL)
        assert response.status_code == 302
        assert response["Location"].startswith("/admin/login/?next=")
        assert "47" not in response.content.decode()

    def test_signing_out_of_coach_goes_back_to_the_staff_sign_in(self, client, coach):
        client.force_login(coach)
        response = client.post(reverse("training:logout"), {"from": "coach"})
        assert response["Location"] == "/admin/login/?next=/coach/"
        assert client.get(URL)["Location"].startswith("/admin/login/")

    # Catches Will's own sign-out being sent to the staff sign-in instead.
    def test_signing_out_elsewhere_still_goes_to_the_pin_pad(self, client, will):
        client.force_login(will)
        response = client.post(reverse("training:logout"))
        assert response["Location"] == reverse(settings.LOGIN_URL)

    # Catches a staff phone being shown Will's tab bar or nudged to his deck,
    # where plays could only ever sync onto him later.
    def test_staff_get_no_tab_bar_and_no_way_to_the_deck(self, client, deck, coach):
        client.force_login(coach)
        body = client.get(URL).content.decode()
        assert 'class="tabbar"' not in body
        assert 'href="/admin/"' in body
        assert "Back to the cards" not in body

    # Catches require_GET coming off a page that must never write.
    def test_a_post_is_refused(self, client, deck, will, coach):
        client.force_login(coach)
        assert client.post(URL, {"page": "2"}).status_code == 405

    # Catches the paginator being swapped for .page(), which 404s or 500s on
    # a hand-edited URL.
    @pytest.mark.parametrize("value", ["abc", "-1", "0", "99999", ""])
    def test_a_garbage_page_number_still_renders(self, client, deck, will, coach, value):
        make_play(will, "toe-taps-30", score=47)
        assert coach_get(client, coach, page=value).status_code == 200


# --- 3. the figures agree with the phone ------------------------------------


class TestCoachPoints:
    # Catches the total counting an unstamped play as anything, or leaving the
    # head start out: the phone shows stamps + history_for points.
    def test_points_are_the_stamps_plus_the_head_start(
        self, client, deck, will, coach, rep_drill
    ):
        make_play(will, "toe-taps-30", score=40, points=25, played_at=timezone.now())
        make_play(will, "foundations-30", score=30, points=15,
                  played_at=timezone.now() - timedelta(minutes=1))
        make_play(will, "pull-push-30", score=20, points=None,
                  played_at=timezone.now() - timedelta(minutes=2))
        ticks(will, rep_drill, 3)

        summary = deck_rules.coach_summary(will, TODAY)
        assert summary["head_start"] == deck_rules.history_for(will)["points"] == 15
        assert summary["points"] == 25 + 15 + 15

        response = coach_get(client, coach)
        page = response.content.decode()
        assert "55 points" in page
        # The unstamped play reads as a dash, not as 0 or None.
        assert [row[4] for row in play_rows(response)] == ["25", "15", "—"]

    @pytest.mark.parametrize("name,threshold", deck_rules.LEVELS[1:])
    # Catches player_level drifting from levelFor in deck.js at a boundary:
    # the level is reached at the threshold, not one point after it.
    def test_player_level_changes_exactly_at_each_threshold(self, name, threshold):
        names = [level for level, _ in deck_rules.LEVELS]
        below = names[names.index(name) - 1]
        assert deck_rules.player_level(threshold - 1) == below
        assert deck_rules.player_level(threshold) == name

    # Catches the bottom of the ladder: no points is the first level.
    def test_no_points_is_the_first_level(self):
        assert deck_rules.player_level(0) == deck_rules.LEVELS[0][0]


class TestCoachBests:
    # Catches a count best taken as anything but the highest, or a best of 0
    # dropped as falsy (the phone's counts() keeps a 0 on a count card).
    def test_a_count_best_is_the_highest_and_a_zero_best_shows_zero(
        self, client, deck, will, coach
    ):
        for value in (12, 30, 7):
            make_play(will, "toe-taps-30", score=value)
        make_play(will, "foundations-30", score=0)

        response = coach_get(client, coach)
        assert best_for(response, "Toe tap race")[1] == "30"
        assert best_for(response, "Foundations race")[1] == "0"

    # Catches a time best taken as the highest, or a 0 (stopwatch never
    # started) winning as the fastest: the phone ignores a time of 0.
    def test_a_time_best_is_the_fastest_above_zero_in_seconds(
        self, client, deck, will, coach
    ):
        for value in (0, 150, 123):
            make_play(will, "slalom-race", score=value)

        bests = {row["slug"]: row for row in deck_rules.card_bests(will)}
        assert bests["slalom-race"]["best"] == 123
        assert best_for(coach_get(client, coach), "Slalom race")[1] == "12.3 s"

    # Catches the two feet merged: on a per-foot card each foot's best is its
    # own, as bestsFor keeps them on the phone.
    def test_a_per_foot_card_shows_each_feet_best_separately(
        self, client, deck, will, coach
    ):
        make_play(will, "inside-outside-30", score=30, weak_score=12)
        make_play(will, "inside-outside-30", score=25, weak_score=18)

        cell = best_for(coach_get(client, coach), "One-foot inside, outside")[1]
        assert cell == "Weak 18 Strong 30"

    # Catches the old app's best being lost, or shown as beaten when he only
    # matched it: the phone's beats() needs strictly more.
    @pytest.mark.parametrize("played,shown,flagged", [
        (10, "15", True),   # unbeaten
        (15, "15", True),   # a tie is not a new best
        (16, "16", False),  # beaten: his card score replaces it
    ])
    def test_a_best_from_before_shows_flagged_until_a_play_beats_it(
        self, client, deck, will, coach, thigh_drill, played, shown, flagged
    ):
        SessionLog.objects.create(
            athlete=will, drill=thigh_drill, date=LONG_AGO, actual_reps=15
        )
        make_play(will, "keepy-ups-thighs", score=played)

        row = best_for(coach_get(client, coach), "Thigh keepy-ups")
        assert row[1].startswith(shown)
        assert ("(from before)" in row[1]) is flagged

    # Catches free play counted as a scored card (a best of "—"), or dropped
    # from his plays list: it is a session card all the same.
    def test_free_play_is_in_the_plays_list_but_not_the_bests(
        self, client, deck, will, coach
    ):
        make_play(will, "free-play", score=None)

        assert deck_rules.card_bests(will) == []
        response = coach_get(client, coach)
        assert best_rows(response) == []
        rows = play_rows(response)
        assert len(rows) == 1
        assert rows[0][1].startswith("I played football")
        assert rows[0][2] == "Played"

    # Catches card_bests filtering on active cards: retiring a card must not
    # take his best off the page (the trap progress.best_scores fell into).
    def test_a_retired_cards_best_still_shows(self, client, deck, will, coach):
        make_play(will, "slalom-race", score=140)
        Card.objects.filter(slug="slalom-race").update(is_active=False)

        assert best_for(coach_get(client, coach), "Slalom race")[1] == "14.0 s"


class TestDeckFormatFilters:
    # Catches the medal filter crashing on, or inventing a word for, a value
    # outside the choices - a bad stamp must never 500 the coach page.
    @pytest.mark.parametrize("value,expected", [
        (None, ""), (0, ""), (1, "Bronze ★"), (3, "Gold ★★★"), (9, ""),
    ])
    def test_medal_reads_as_word_and_stars_or_nothing(self, value, expected):
        assert medal(value) == expected

    # Catches a time read as a count, or a missing score read as "None".
    def test_score_reads_tenths_as_seconds_and_none_as_a_dash(self):
        assert score(123, Card.TIME) == "12.3 s"
        assert score(0, Card.COUNT) == "0"
        assert score(None, Card.COUNT) == "—"


# --- 4. paging and query count ----------------------------------------------


class TestCoachPagePaging:
    # Catches the page size or the paginator going: 51 plays is two pages,
    # and nothing past the first fifty is lost.
    def test_fifty_one_plays_put_one_on_page_two(self, client, deck, will, coach):
        now = timezone.now()
        for n in range(51):
            make_play(will, "toe-taps-30", day=TODAY - timedelta(days=n),
                      score=n, played_at=now - timedelta(days=n))

        first = coach_get(client, coach)
        assert len(play_rows(first)) == 50
        second = client.get(URL, {"page": "2"})
        rows = play_rows(second)
        assert len(rows) == 1
        assert rows[0][2] == "50"  # the oldest play

    # Catches a query per play: a missing select_related on card, or a lookup
    # inside the bests loop, would grow with his record.
    def test_queries_do_not_grow_with_the_number_of_plays(
        self, client, deck, will, coach
    ):
        client.force_login(coach)
        slugs = list(
            Card.objects.exclude(scoring=Card.NONE).values_list("slug", flat=True)[:30]
        )
        make_play(will, slugs[0], score=5)
        client.get(URL)  # warm the session and any first-request lookups
        with CaptureQueriesContext(connection) as one:
            assert client.get(URL).status_code == 200

        for n, slug in enumerate(slugs[1:], start=1):
            make_play(will, slug, day=TODAY - timedelta(days=n), score=5)
        with CaptureQueriesContext(connection) as thirty:
            assert client.get(URL).status_code == 200

        assert Play.objects.filter(athlete=will).count() == 30
        assert len(thirty) == len(one)


# --- 5. the log and the service worker --------------------------------------


class TestRefusalLogAndServiceWorker:
    # Catches the refusal log written with %s: an id carrying a newline from
    # a tampered request would forge a second log line.
    def test_a_refused_play_is_logged_with_its_id_escaped(
        self, client, deck, will, caplog
    ):
        client.force_login(will)
        bad = {"id": "abc\nplay refused: forged", "card": "toe-taps-30",
               "date": timezone.localdate().isoformat(),
               "played_at": timezone.now().isoformat(), "score": 4, "weak_score": None}
        with caplog.at_level(logging.WARNING, logger="training.deck_views"):
            response = client.post(
                reverse("training:api_plays"), data=json.dumps({"plays": [bad]}),
                content_type="application/json",
            )
        assert response.status_code == 200
        assert response.json()["refused"]
        messages = [r.getMessage() for r in caplog.records if "play refused" in r.getMessage()]
        assert len(messages) == 1
        assert "\n" not in messages[0]
        assert repr(bad["id"]) in messages[0]
        assert not Play.objects.exists()

    # Catches the service worker caching Dad's screens: a kept copy of the
    # coach page would show Will's plays on the phone after signing out.
    def test_the_service_worker_never_handles_coach_or_admin(self, client):
        source = client.get("/sw.js").content.decode()
        for prefix in ("/coach/", "/admin/"):
            lines = [
                line for line in source.splitlines()
                if f"url.pathname.startsWith('{prefix}')" in line
            ]
            assert lines, f"sw.js no longer skips {prefix}"
            assert all(re.search(r"\{\s*return;\s*\}", line) for line in lines)
        # And before anything is cached.
        skip = source.index("startsWith('/coach/')")
        assert skip < source.index("const isStatic")


class TestLookoutFixes:
    # Catches the coach page and the phone disagreeing: an old best on a card
    # he has not played on the deck yet is shown to beat on his phone.
    def test_an_old_best_on_an_unplayed_card_is_listed(self, client, deck, will, coach, thigh_drill):
        ticks(will, thigh_drill, 1, reps=14)
        rows = {r["slug"]: r for r in deck_rules.card_bests(will, deck_rules.history_for(will)["bests"])}
        row = rows["keepy-ups-thighs"]
        assert (row["best"], row["from_before"], row["plays"]) == (14, True, 0)

    # Catches a 0 on a time card reading as a real time.
    def test_a_zero_time_reads_as_no_time(self):
        assert score(0, Card.TIME) == "—"
        assert score(0, Card.COUNT) == "0"
