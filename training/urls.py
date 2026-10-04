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
    # The fixed plan, retired in leg 3d. Its screens go home; its tick URLs
    # are gone, so nothing outside the admin writes a SessionLog any more.
    path("today/", RedirectView.as_view(url="/", permanent=False)),
    path("library/", RedirectView.as_view(url="/", permanent=False)),
    path("offline/", views.offline, name="offline"),
    # What feeds the deck.
    path("api/plays/", deck_views.api_plays, name="api_plays"),
    # Coach: his cards (read-only), and his sessions before the cards, where
    # a count can still be corrected.
    path("coach/", views.coach_cards, name="coach_cards"),
    path("coach/before/", views.coach_logs, name="coach_logs"),
    path("coach/logs/", RedirectView.as_view(url="/coach/before/", permanent=False)),
    path("coach/logs/<int:pk>/edit/", views.coach_log_edit, name="coach_log_edit"),
]
