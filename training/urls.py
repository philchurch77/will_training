from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    # Child-facing
    path("", views.today, name="today"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("progress/", views.progress_view, name="progress"),
    path("library/", views.library, name="library"),
    path("library/<slug:slug>/", views.library, name="library_skill"),
    path("drill/<slug:slug>/", views.drill_detail, name="drill"),
    path("drill/<slug:slug>/done/", views.drill_complete, name="drill_complete"),
    path("drill/<slug:slug>/undo/", views.drill_uncomplete, name="drill_uncomplete"),
    path("session/time/", views.session_time, name="session_time"),
    path("offline/", views.offline, name="offline"),
    # Coach (staff only)
    path("coach/", views.coach_plan, name="coach_plan"),
    path("coach/day/<int:weekday>/", views.coach_plan_day, name="coach_plan_day"),
    path("coach/drills/", views.coach_drills, name="coach_drills"),
    path("coach/drills/new/", views.coach_drill_edit, name="coach_drill_new"),
    path("coach/drills/<slug:slug>/", views.coach_drill_edit, name="coach_drill_edit"),
    path("coach/logs/", views.coach_logs, name="coach_logs"),
    path("coach/logs/<int:pk>/edit/", views.coach_log_edit, name="coach_log_edit"),
]
