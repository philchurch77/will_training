"""Leg 3c of docs/chart/deck.md: the switch-over.

The deck becomes the app at `/`, the old plan's history moves to a read-only
"Before the cards" page, the old addresses redirect, the service worker and
manifest follow, and the day-streak badges retire without leaving his record.

Access control first: /before/ shows the signed-in user's history and nobody
else's.
"""

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from training import progress
from training.models import Badge, EarnedBadge, SessionClock, SessionLog
from training.tests.conftest import MONDAY
from training.tests.test_deck_views import deck, deck_badges_in  # noqa: F401

pytestmark = pytest.mark.django_db

WILLS_RECORD = 987
RETIRED = {"streak-3", "streak-7", "streak-30", "streak-100", "perfect-week", "minutes-500"}


def _source(path):
    return Path(path).read_text(encoding="utf-8")


def _function_body(source, name):
    start = source.find(f"function {name}(")
    assert start != -1, f"no {name}() function"
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


@pytest.fixture
def wills_history(will, rep_drill):
    """One counted session on a rep drill, with a number nobody else has."""
    SessionLog.objects.create(
        athlete=will, date=MONDAY, drill=rep_drill, actual_reps=WILLS_RECORD
    )
    return rep_drill


# --- 1. access control on /before/ -------------------------------------------


class TestBeforeCardsIsolation:
    # Catches before_cards reading get_athlete() (or any fixed user) instead of
    # request.user: another account would be shown Will's whole record.
    def test_another_user_sees_none_of_wills_history(self, client, wills_history):
        other = get_user_model().objects.create_user(username="other", password="x")
        client.force_login(other)
        response = client.get(reverse("training:before_cards"))
        assert response.status_code == 200
        assert response.context["total_drills"] == 0
        assert response.context["best_rows"] == []
        assert str(WILLS_RECORD) not in response.content.decode()

    # Catches the same leak through the coach account, which shares Will's phone.
    def test_a_staff_user_sees_none_of_wills_history(self, client, wills_history):
        coach = get_user_model().objects.create_user(
            username="coach", password="x", is_staff=True
        )
        client.force_login(coach)
        response = client.get(reverse("training:before_cards"))
        assert response.status_code == 200
        assert response.context["total_drills"] == 0
        assert response.context["best_rows"] == []
        assert str(WILLS_RECORD) not in response.content.decode()

    # Catches the history page losing login_required: it is still his data.
    @pytest.mark.parametrize("path", ["/", "/before/"])
    def test_signed_out_is_sent_to_the_pin_pad(self, client, will, path):
        response = client.get(path)
        assert response.status_code == 302
        assert response["Location"].startswith(reverse("training:login"))

    # Catches the page showing nothing to Will himself - the other half of
    # filtering by request.user.
    def test_will_sees_his_own_record(self, client, will, wills_history):
        client.force_login(will)
        response = client.get(reverse("training:before_cards"))
        assert response.context["total_drills"] == 1
        assert str(WILLS_RECORD) in response.content.decode()


# --- 2. / is the deck, old addresses redirect -------------------------------


class TestDeckIsHome:
    # Catches `/` becoming a redirect: the home-screen icon opens `/`, and the
    # service worker will not keep a redirected page, so offline it goes blank.
    def test_home_renders_the_deck_with_no_redirect(self, client, deck, will):
        client.force_login(will)
        response = client.get("/")
        assert response.status_code == 200
        assert '<script id="deck-cards" type="application/json">' in response.content.decode()

    # Catches a bookmark or cached page at /deck/ or /progress/ hitting a 404.
    @pytest.mark.parametrize("old, new", [("/deck/", "/"), ("/progress/", "/#progress")])
    def test_old_addresses_redirect(self, client, will, old, new):
        client.force_login(will)
        response = client.get(old)
        assert response.status_code == 302
        assert response["Location"] == new

    # Catches the PIN pad dropping him on Today rather than the cards.
    def test_signing_in_lands_on_the_deck(self, client, will):
        response = client.post(reverse("training:login"), {"pin": "1234"})
        assert response["Location"] == "/"


# --- 3. service worker and manifest -----------------------------------------


class TestOfflineShellAfterSwitch:
    def sw(self, client):
        return client.get("/sw.js").content.decode()

    def precache(self, client):
        match = re.search(r"const PRECACHE = (\[.*?\]);", self.sw(client), re.S)
        assert match, "sw.js no longer has a PRECACHE list"
        return json.loads(match.group(1))

    # Catches the deck or the history page not opening offline.
    def test_home_and_before_are_precached(self, client, deck):
        urls = self.precache(client)
        assert "/" in urls
        assert "/before/" in urls

    # Catches the old plan's pages and scripts still being precached: drill
    # pages carry the tick forms, and the clock script runs only on Today.
    def test_the_old_plan_is_not_precached(self, client, seeded):
        urls = self.precache(client)
        assert not [u for u in urls if "/drill/" in u]
        assert not [u for u in urls if "session.js" in u or "drill.js" in u]
        assert "/today/" not in urls

    # Catches 3c's deck.js and base.html shipping under 3b's cache name:
    # phones would keep the old tab bar pointing at Today.
    def test_the_cache_was_bumped_for_the_switch(self, client, deck):
        body = self.sw(client)
        assert "const CACHE = 'will-training-v25';" in body
        assert "const CACHE = 'will-training-v24';" not in body

    # Catches the shortcuts still pointing at the retired screens, or the id
    # moving and orphaning the icon on his phone.
    def test_manifest_keeps_its_id_and_points_at_the_deck(self, client):
        data = client.get("/manifest.json").json()
        assert data["id"] == "/"
        assert data["start_url"] == "/"
        assert [s["url"] for s in data["shortcuts"]] == ["/", "/#progress"]


# --- 4-5. ticks queued before the switch -------------------------------------


class TestQueuedTicksStillLand:
    # Catches the offline replay reloading `/` (now the deck) with ?done=,
    # which the deck ignores, instead of Today.
    def test_app_js_replays_to_today(self):
        source = _source("training/static/training/js/app.js")
        assert "'/today/?done='" in source
        assert "'/?done='" not in source

    # Catches the tick URL moving: a tick queued on his phone before the
    # deploy replays to the address it stored, and must still be saved.
    # Queued two days ago (inside the 14-day replay window), sent after.
    def test_a_queued_tick_is_saved(self, client, will, rep_drill):
        queued_on = timezone.localdate() - timedelta(days=2)
        client.force_login(will)
        response = client.post(
            reverse("training:drill_complete", args=[rep_drill.slug]),
            {"date": queued_on.isoformat(), "session_seconds": "600"},
        )
        assert response.status_code in (200, 302)
        assert SessionLog.objects.filter(
            athlete=will, date=queued_on, drill=rep_drill, completed=True
        ).exists()
        assert SessionClock.objects.get(athlete=will, date=queued_on).seconds == 600


# --- 6-7. read-only history and the tab bar ----------------------------------


class TestReadOnlyAndTabBar:
    # Catches a tick or untick form - or a link to a drill page, which carries
    # them - reaching the read-only history.
    def test_before_cards_has_no_form_and_no_drill_link(self, client, will, wills_history):
        client.force_login(will)
        page = client.get(reverse("training:before_cards")).content.decode()
        assert "<form" not in page
        assert "/drill/" not in page

    # Catches the old tab bar coming back on the deck: the library tab, the
    # session clock chip, or the clock script that banks time to Today.
    def test_the_deck_tab_bar_is_cards_and_progress_only(self, client, will, seeded):
        client.force_login(will)
        page = client.get("/").content.decode()
        nav = re.search(r'<nav class="tabbar">(.*?)</nav>', page, re.S).group(1)
        hrefs = re.findall(r'href="([^"]+)"', nav)
        assert hrefs == ["/", "/#progress"]
        assert reverse("training:library") not in page
        assert 'id="clockchip"' not in page
        assert "session.js" not in page


# --- 8-9. retired badges and records -----------------------------------------


class TestRetiredBadgesAndRecords:
    # Catches the retired list drifting, or naming a code that does not exist
    # (a typo would retire nothing and leave a streak badge being awarded).
    def test_retired_badges_are_exactly_the_six_and_all_exist(self):
        from training.management.commands.seed_drills import BADGES, RETIRED_BADGES

        assert set(RETIRED_BADGES) == RETIRED
        assert len(RETIRED_BADGES) == len(RETIRED)
        assert RETIRED <= {row[0] for row in BADGES}

    # Catches a deploy (seed_drills on every start) deleting or re-dating a
    # badge he earned, or the deck hiding it once it is retired.
    def test_an_earned_retired_badge_survives_deploys_and_shows_as_legend(
        self, client, will, seeded
    ):
        badge = Badge.objects.get(code="streak-3")
        EarnedBadge.objects.create(athlete=will, badge=badge, earned_on=MONDAY)

        call_command("seed_drills", verbosity=0)
        call_command("seed_drills", verbosity=0)

        earned = EarnedBadge.objects.get(athlete=will, badge__code="streak-3")
        assert earned.earned_on == MONDAY
        assert not Badge.objects.get(code="streak-3").is_active

        client.force_login(will)
        rows = {b["code"]: b for b in deck_badges_in(client.get("/"))}
        assert rows["streak-3"]["legend"] is True
        assert rows["streak-3"]["earned"] is True
        # A retired badge he never earned is a promise nothing can keep.
        assert "streak-100" not in rows

    # Catches best_scores going back to Drill.objects.active(): retiring a rep
    # drill would take his record off the board while every row survives.
    def test_a_retired_rep_drills_record_stays_on_the_board(self, will, wills_history):
        wills_history.is_active = False
        wills_history.save()
        rows = progress.best_scores(will)
        assert [(r["drill"].slug, r["best"]) for r in rows] == [
            (wills_history.slug, WILLS_RECORD)
        ]


# --- 10. deck.js, read as source ---------------------------------------------


class TestProgressTabScript:
    def source(self):
        return _source("training/static/training/js/deck.js")

    # Catches the history page becoming unreachable: Progress is the only door
    # to /before/ now the old Progress screen is gone.
    def test_render_progress_links_to_before_the_cards(self):
        source = self.source()
        assert "root.getAttribute('data-before-url')" in source
        assert "href: BEFORE_URL" in _function_body(source, "renderProgress")

    # Catches the Progress tab (/#progress) or an old badges link (#badges)
    # falling through to the hand.
    def test_route_sends_progress_and_badges_to_render_progress(self):
        body = _function_body(self.source(), "route")
        assert re.search(
            r"\(hash === 'progress' \|\| hash === 'badges'\)[^{]*\{ renderProgress\(", body
        )
        assert "lightTab(" in body

    # Catches the lit tab never moving: both tabs are one page, so only the
    # script can say which one he is on, for sight and for a screen reader.
    def test_light_tab_sets_aria_current(self):
        body = _function_body(self.source(), "lightTab")
        assert "setAttribute('aria-current', 'page')" in body
        assert "removeAttribute('aria-current')" in body
