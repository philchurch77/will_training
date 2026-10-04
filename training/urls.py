from django.urls import path
from django.views.generic import RedirectView

from . import deck_views, views

app_name = "training"

urlpatterns = [
    # Child-facing. The deck is the app (leg 3c): `/` renders it, never
    # redirects - the home-screen icon opens `/`, and the service worker
    # refuses to keep a redirected page, so a redirect here would leave the
    # icon blank offline. Progress is a tab drawn by deck.js (`/#progress`).
    path("", deck_views.deck, name="deck"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("before/", views.before_cards, name="before_cards"),
    # Old addresses, for bookmarks and cached pages.
    path("deck/", RedirectView.as_view(url="/", permanent=False)),
    path("progress/", RedirectView.as_view(url="/#progress", permanent=False)),
    # The old fixed plan, off his tab bar until 3d retires it. The tick URLs
    # never move: ticks queued on his phone replay to the address they stored.
    path("today/", views.today, name="today"),
    path("library/", views.library, name="library"),
    path("library/<slug:slug>/", views.library, name="library_skill"),
    path("drill/<slug:slug>/", views.drill_detail, name="drill"),
    path("drill/<slug:slug>/done/", views.drill_complete, name="drill_complete"),
    path("drill/<slug:slug>/undo/", views.drill_uncomplete, name="drill_uncomplete"),
    path("session/time/", views.session_time, name="session_time"),
    path("offline/", views.offline, name="offline"),
    # What feeds the deck.
    path("api/plays/", deck_views.api_plays, name="api_plays"),
    # Coach (staff only)
    path("coach/", views.coach_plan, name="coach_plan"),
    path("coach/day/<int:weekday>/", views.coach_plan_day, name="coach_plan_day"),
    path("coach/drills/", views.coach_drills, name="coach_drills"),
    path("coach/drills/new/", views.coach_drill_edit, name="coach_drill_new"),
    path("coach/drills/<slug:slug>/", views.coach_drill_edit, name="coach_drill_edit"),
    path("coach/logs/", views.coach_logs, name="coach_logs"),
    path("coach/logs/<int:pk>/edit/", views.coach_log_edit, name="coach_log_edit"),
]
