"""Screens, PIN login and access to the coach area."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone
from django.urls import reverse

from training.models import Skill

pytestmark = pytest.mark.django_db

CHILD_URLS = ["training:before_cards", "training:deck"]
COACH_URLS = [
    "training:coach_cards",
    "training:coach_logs",
]


class TestLoginRequired:
    @pytest.mark.parametrize("name", CHILD_URLS)
    def test_anonymous_is_sent_to_login(self, client, name):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert reverse("training:login") in response["Location"]

    def test_the_login_page_itself_is_open(self, client, will):
        assert client.get(reverse("training:login")).status_code == 200


class TestPinLogin:
    """One profile, so the pad is the whole screen - there is no name to pick."""

    def test_the_login_page_needs_no_name(self, client, will):
        body = client.get(reverse("training:login")).content.decode()
        assert "Will" in body
        assert 'name="username"' not in body

    def test_the_right_pin_gets_in(self, client, will):
        response = client.post(reverse("training:login"), {"pin": "1234"})
        assert response.status_code == 302
        assert response["Location"] == reverse("training:deck")

    # The deck's "Sign in to back it up" brings him back to the cards.
    def test_the_right_pin_goes_back_to_a_page_on_this_site(self, client, will):
        response = client.post(reverse("training:login") + "?next=/before/", {"pin": "1234"})
        assert response["Location"] == "/before/"

    # Catches the pad becoming an open redirect.
    @pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/"])
    def test_the_right_pin_never_goes_off_site(self, client, will, target):
        response = client.post(reverse("training:login") + "?next=" + target, {"pin": "1234"})
        assert response["Location"] == reverse("training:deck")

    def test_the_wrong_pin_does_not(self, client, will):
        response = client.post(reverse("training:login"), {"pin": "0000"})
        assert response.status_code == 200
        assert "Wrong code" in response.content.decode()

    def test_it_copes_with_no_profile_at_all(self, client, db):
        response = client.post(reverse("training:login"), {"pin": "1234"})
        assert response.status_code == 200
        assert "seed_drills" in response.content.decode()

    def test_a_logged_in_user_skips_the_login_page(self, client, will):
        client.force_login(will)
        response = client.get(reverse("training:login"))
        assert response.status_code == 302

    def test_logout_returns_to_login(self, client, will):
        client.force_login(will)
        response = client.post(reverse("training:logout"))
        assert response["Location"] == reverse("training:login")

    def test_the_session_lasts_a_year(self, client, will, settings):
        client.post(reverse("training:login"), {"pin": "1234"})
        assert client.session.get_expiry_age() > 60 * 60 * 24 * 300


class TestCoachAccess:
    """The coach screens read Will's record (one profile) and are read by Dad
    signed in as staff; signed out, they lead to the staff sign-in."""

    @pytest.mark.parametrize("name", COACH_URLS)
    def test_anonymous_is_sent_to_the_staff_sign_in(self, client, name):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert response["Location"].startswith("/admin/login/?next=")

    @pytest.mark.parametrize("name", COACH_URLS)
    def test_a_signed_in_user_can_reach_them(self, client, will, seeded, name):
        client.force_login(will)
        assert client.get(reverse(name)).status_code == 200

    def test_the_coach_screens_are_not_in_the_tab_bar(self, client, will, seeded):
        """Will should not be invited onto Dad's screen from his tab bar."""
        client.force_login(will)
        body = client.get(reverse("training:deck")).content.decode()
        tabbar = body.split('class="tabbar"')[1].split("</nav>")[0]
        assert reverse("training:coach_cards") not in tabbar


class TestBeforeTheCards:
    def test_renders_with_no_data(self, client, will, seeded):
        client.force_login(will)
        assert client.get(reverse("training:before_cards")).status_code == 200

    def test_shows_the_totals_and_the_skill_bars(self, client, will, seeded):
        from training.models import Drill, SessionLog

        drill = Drill.objects.get(slug="toe-taps")
        SessionLog.objects.create(
            athlete=will, date=timezone.localdate(),
            drill=drill, actual_minutes=10,
        )
        client.force_login(will)
        response = client.get(reverse("training:before_cards"))
        assert response.context["total_minutes"] == 10
        assert response.context["longest"] == 1
        assert len(response.context["skill_rows"]) == 7

    # Catches a live streak coming back: it breaks the day he switches to
    # the cards, and on this page it would read as a telling-off.
    def test_there_is_no_live_streak(self, client, will, seeded):
        client.force_login(will)
        response = client.get(reverse("training:before_cards"))
        assert "streak" not in response.context
        assert b"flame" not in response.content


class TestPwaEndpoints:
    def test_the_service_worker_is_served_from_the_root(self, client, seeded):
        response = client.get("/sw.js")
        assert response.status_code == 200
        assert "javascript" in response["Content-Type"]
        assert response["Service-Worker-Allowed"] == "/"

    def test_the_manifest_is_json(self, client):
        response = client.get("/manifest.json")
        assert response.status_code == 200
        assert response.json()["display"] == "standalone"

    def test_the_manifest_has_a_stable_id_and_scope(self, client):
        # Changing these orphans the icon already on his home screen.
        data = client.get("/manifest.json").json()
        assert data["id"] == "/"
        assert data["start_url"] == "/"
        assert data["scope"] == "/"

    def test_the_manifest_offers_the_icon_sizes_android_installs_need(
        self, client
    ):
        icons = client.get("/manifest.json").json()["icons"]
        sizes = {i["sizes"] for i in icons if i["type"] == "image/png"}
        assert "192x192" in sizes and "512x512" in sizes
        # Cropped to a circle by some launchers, so it needs its own artwork.
        maskable = [i for i in icons if i["purpose"] == "maskable"]
        assert maskable and maskable[0]["sizes"] == "512x512"

    def test_every_manifest_icon_actually_exists(self, client):
        # A manifest naming a missing icon fails install silently.
        for icon in client.get("/manifest.json").json()["icons"]:
            assert finders.find(icon["src"].replace(settings.STATIC_URL, "")), (
                icon["src"]
            )

    def test_the_theme_colour_matches_the_page(self, client, will, seeded):
        # A manifest colour that differs from the meta tag paints a bar above
        # the app's own top bar in standalone mode.
        theme = client.get("/manifest.json").json()["theme_color"]
        client.force_login(will)
        body = client.get(reverse("training:deck")).content.decode()
        assert f'<meta name="theme-color" content="{theme}">' in body

    def test_ios_gets_its_own_icon_and_title(self, client, will, seeded):
        # iOS ignores the manifest entirely.
        client.force_login(will)
        body = client.get(reverse("training:deck")).content.decode()
        assert 'rel="apple-touch-icon"' in body
        assert 'name="apple-mobile-web-app-title"' in body
        assert finders.find("training/img/apple-touch-icon.png")

    def test_the_service_worker_precaches_the_manifest_and_icons(
        self, client, seeded
    ):
        # An installed app opened offline still asks for these.
        body = client.get("/sw.js").content.decode()
        assert "/manifest.json" in body
        assert "icon-192.png" in body
        assert "apple-touch-icon.png" in body

    def test_no_install_chip_in_the_top_bar(self, client, will, seeded):
        # Adding to the home screen is the browser's job (Safari's Share
        # sheet, Chrome's menu). The top bar stays for Will's app only.
        client.force_login(will)
        body = client.get(reverse("training:deck")).content.decode()
        assert "install-go" not in body
        # The Safari route still has to work, so the icon tag stays.
        assert "apple-touch-icon" in body

    def test_the_offline_page_renders(self, client, will):
        client.force_login(will)
        assert client.get(reverse("training:offline")).status_code == 200


class TestTemplateComments:
    """Django's {# #} comment is single-line only.

    Spread one over two lines and it stops being a comment: the text renders
    straight onto the page. It happened once, on Will's Today screen, and
    nothing in the suite noticed because the page still returned a 200.
    """

    @pytest.mark.parametrize("name", CHILD_URLS + COACH_URLS)
    def test_no_template_syntax_leaks_onto_the_page(
        self, client, will, seeded, name
    ):
        client.force_login(will)
        body = client.get(reverse(name)).content.decode()
        for marker in ("{#", "#}", "{%", "%}"):
            assert marker not in body, f"{marker} leaked into {name}"

    def test_the_multi_line_comment_trap_is_understood(self):
        # Belt and braces: catch it in the template source too, since a
        # comment can leak on a branch no test happens to render.
        from pathlib import Path

        templates = Path("training/templates").rglob("*.html")
        for path in templates:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "{#" in line:
                    assert "#}" in line, f"{path}:{number} opens {{# and never closes it"


class TestChrome:
    def test_the_coach_link_is_offered_on_will_screens(self, client, will, seeded):
        client.force_login(will)
        body = client.get(reverse("training:deck")).content.decode()
        assert reverse("training:coach_cards") in body

    def test_but_not_repeated_on_the_coach_screens_themselves(
        self, client, will, seeded
    ):
        client.force_login(will)
        body = client.get(reverse("training:coach_cards")).content.decode()
        header = body.split("</header>")[0]
        assert reverse("training:coach_cards") not in header


