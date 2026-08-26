"""Screens, PIN login and access to the coach area."""

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone
from django.urls import reverse

from training.models import Skill

pytestmark = pytest.mark.django_db

CHILD_URLS = ["training:today", "training:progress", "training:library"]
COACH_URLS = [
    "training:coach_plan",
    "training:coach_drills",
    "training:coach_drill_new",
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
        assert response["Location"] == reverse("training:today")

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
    """One profile means the coach screens sit behind the same code. They are
    kept off Will's tab bar rather than behind a second account."""

    @pytest.mark.parametrize("name", COACH_URLS)
    def test_anonymous_is_sent_to_login(self, client, name):
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert reverse("training:login") in response["Location"]

    @pytest.mark.parametrize("name", COACH_URLS)
    def test_a_signed_in_user_can_reach_them(self, client, will, seeded, name):
        client.force_login(will)
        assert client.get(reverse(name)).status_code == 200

    def test_the_coach_screens_are_not_in_the_tab_bar(self, client, will, seeded):
        """Will should not be invited to rewrite his own training plan."""
        client.force_login(will)
        body = client.get(reverse("training:today")).content.decode()
        tabbar = body.split('class="tabbar"')[1].split("</nav>")[0]
        assert reverse("training:coach_plan") not in tabbar


class TestTodayScreen:
    def test_shows_the_drills_for_the_right_weekday(self, client, will, seeded):
        from django.utils import timezone

        from training.models import TrainingPlan

        client.force_login(will)
        response = client.get(reverse("training:today"))
        assert response.status_code == 200

        plan = TrainingPlan.get_active()
        today = plan.days.get(weekday=timezone.localdate().weekday())
        body = response.content.decode()
        for item in today.items.all():
            assert item.drill.name in body

    def test_today_carries_the_session_clock(self, client, will, plan):
        client.force_login(will)
        body = client.get(reverse("training:today")).content.decode()
        assert 'id="session"' in body
        assert 'id="clockstart"' in body

    def test_a_drill_can_be_ticked_off_without_opening_it(self, client, will, plan, drill):
        # The tick is the whole job on a normal day; the drill page is for
        # reading the instructions. One tap, no page to come back from.
        from training.models import SessionLog

        client.force_login(will)
        body = client.get(reverse("training:today")).content.decode()
        assert reverse("training:drill_complete", args=[drill.slug]) in body

        client.post(
            reverse("training:drill_complete", args=[drill.slug]),
            {"session_seconds": "600"},
        )
        assert SessionLog.objects.filter(athlete=will, drill=drill).exists()

    def test_a_rest_day_says_so(self, client, will, plan):
        """Force the plan so every day is a rest day, then check the wording."""
        from training.models import PlanDay

        PlanDay.objects.update(is_rest=True)
        client.force_login(will)
        response = client.get(reverse("training:today"))
        assert "Rest day" in response.content.decode()

    def test_an_optional_day_is_marked_as_a_bonus(self, client, will, plan):
        from training.models import PlanDay

        PlanDay.objects.update(is_rest=False, is_optional=True)
        client.force_login(will)
        body = client.get(reverse("training:today")).content.decode()
        assert "Bonus session" in body

    def test_a_completed_drill_shows_as_done(self, client, will, plan, drill):
        """Force every day to a plain session carrying the drill, the same way
        the two tests above force rest and bonus. Without it this depends on
        the day the suite happens to run: the fixture's Sunday is a rest day
        with no drills on it, so it passed six days a week and failed on the
        seventh."""
        from training.models import PlanDay, PlanDrill

        PlanDay.objects.update(is_rest=False, is_optional=False)
        for day in PlanDay.objects.all():
            PlanDrill.objects.get_or_create(
                plan_day=day, drill=drill, defaults={"order": 1}
            )

        client.force_login(will)
        client.post(reverse("training:drill_complete", args=[drill.slug]))
        body = client.get(reverse("training:today")).content.decode()
        assert "is-done" in body


class TestDrillAndLibrary:
    def test_a_drill_page_shows_its_cue_and_instructions(self, client, will, drill):
        client.force_login(will)
        body = client.get(reverse("training:drill", args=[drill.slug])).content.decode()
        assert drill.cue in body
        assert "Tap the ball." in body

    def test_a_timed_drill_has_no_countdown(self, client, will, drill):
        """The clock moved up to the session. A drill he is enjoying should not
        have a number ticking down at him telling him to stop."""
        client.force_login(will)
        body = client.get(reverse("training:drill", args=[drill.slug])).content.decode()
        assert 'id="clock"' not in body
        assert "no timer on this one" in body

    def test_the_session_clock_is_reachable_from_inside_a_drill(
        self, client, will, drill
    ):
        # The chip in the top bar is the only clock he can see once he has
        # tapped into a drill, and it is on every screen for that reason.
        client.force_login(will)
        body = client.get(reverse("training:drill", args=[drill.slug])).content.decode()
        assert 'id="clockchip"' in body

    def test_a_rep_drill_gets_a_counter(self, client, will, rep_drill):
        client.force_login(will)
        body = client.get(
            reverse("training:drill", args=[rep_drill.slug])
        ).content.decode()
        assert 'id="count"' in body

    def test_the_library_can_be_filtered_by_skill(self, client, will, seeded):
        client.force_login(will)
        response = client.get(reverse("training:library_skill", args=["shooting"]))
        assert response.status_code == 200
        names = {d.name for d in response.context["drills"]}
        assert "Pick your corner" in names
        assert "Toe taps" not in names  # that one is ball mastery

    def test_the_unfiltered_library_groups_drills_under_skill_headings(
        self, client, will, seeded
    ):
        # The headings are what make the filter strip optional: every skill is
        # reachable by scrolling, so nothing is lost if he never swipes it.
        client.force_login(will)
        body = client.get(reverse("training:library")).content.decode()
        for skill in Skill.objects.all():
            assert skill.name in body
        assert body.count('class="drill-group"') == Skill.objects.count()

    def test_a_filtered_library_drops_the_headings(self, client, will, seeded):
        # The lit chip already names the skill; a heading would repeat it.
        client.force_login(will)
        body = client.get(
            reverse("training:library_skill", args=["shooting"])
        ).content.decode()
        assert 'class="drill-group"' not in body

    def test_a_missing_drill_is_a_404(self, client, will):
        client.force_login(will)
        assert client.get(reverse("training:drill", args=["nope"])).status_code == 404


class TestProgressScreen:
    def test_renders_with_no_data(self, client, will, seeded):
        client.force_login(will)
        assert client.get(reverse("training:progress")).status_code == 200

    def test_shows_the_streak_and_the_skill_bars(self, client, will, seeded):
        from training.models import Drill, SessionLog

        drill = Drill.objects.get(slug="toe-taps")
        SessionLog.objects.create(
            athlete=will, date=timezone.localdate(),
            drill=drill, actual_minutes=10,
        )
        client.force_login(will)
        response = client.get(reverse("training:progress"))
        assert response.context["streak"] == 1
        assert response.context["total_minutes"] == 10
        assert len(response.context["skill_rows"]) == 7
        # The flame is lit only when there is a streak burning.
        assert b"flame is-out" not in response.content

    def test_the_flame_is_out_with_no_streak(self, client, will, seeded):
        client.force_login(will)
        response = client.get(reverse("training:progress"))
        assert response.context["streak"] == 0
        assert b"flame is-out" in response.content


class TestCoachEditing:
    """Dad edits the plan through the same signed-in session."""

    def test_the_coach_can_reorder_a_day(self, client, will, seeded):
        from training.models import PlanDay

        client.force_login(will)
        day = PlanDay.objects.get(weekday=0)
        items = list(day.items.order_by("order"))
        second = items[1]

        client.post(
            reverse("training:coach_plan_day", args=[0]),
            {"action": "up", "item": second.pk},
        )
        assert list(day.items.order_by("order"))[0].pk == second.pk

    def test_the_coach_can_remove_a_drill_from_a_day(self, client, will, seeded):
        from training.models import PlanDay

        client.force_login(will)
        day = PlanDay.objects.get(weekday=0)
        before = day.items.count()
        client.post(
            reverse("training:coach_plan_day", args=[0]),
            {"action": "remove", "item": day.items.first().pk},
        )
        assert day.items.count() == before - 1

    def test_the_coach_can_add_a_drill_to_a_day(self, client, will, seeded):
        from training.models import Drill, PlanDay

        client.force_login(will)
        day = PlanDay.objects.get(weekday=0)
        before = day.items.count()
        extra = Drill.objects.get(slug="cone-slalom")
        client.post(
            reverse("training:coach_plan_day", args=[0]),
            {"action": "add", "drill": extra.pk},
        )
        assert day.items.count() == before + 1

    def test_the_coach_can_turn_a_day_into_a_rest_day(self, client, will, seeded):
        from training.models import PlanDay

        client.force_login(will)
        client.post(
            reverse("training:coach_plan_day", args=[0]),
            {
                "action": "settings",
                "label": "Rest",
                "target_minutes": "0",
                "is_rest": "on",
            },
        )
        assert PlanDay.objects.get(weekday=0).is_rest

    def test_a_drill_needs_minutes_or_reps_but_not_both(self, client, will, seeded):
        client.force_login(will)
        response = client.post(
            reverse("training:coach_drill_new"),
            {
                "name": "Bad drill",
                "slug": "bad-drill",
                "skill": Skill.objects.first().pk,
                "instructions": "Do a thing.",
                "cue": "Cue",
                "duration_minutes": "5",
                "target_reps": "20",
                "difficulty": "1",
            },
        )
        assert response.status_code == 200
        assert "one or the other" in response.content.decode()


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
        body = client.get(reverse("training:today")).content.decode()
        assert f'<meta name="theme-color" content="{theme}">' in body

    def test_ios_gets_its_own_icon_and_title(self, client, will, seeded):
        # iOS ignores the manifest entirely.
        client.force_login(will)
        body = client.get(reverse("training:today")).content.decode()
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
        body = client.get(reverse("training:today")).content.decode()
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
        body = client.get(reverse("training:today")).content.decode()
        assert reverse("training:coach_plan") in body

    def test_but_not_repeated_on_the_coach_screens_themselves(
        self, client, will, seeded
    ):
        client.force_login(will)
        body = client.get(reverse("training:coach_plan")).content.decode()
        header = body.split("</header>")[0]
        assert reverse("training:coach_plan") not in header
