from django.contrib import admin
from django.urls import include, path

from training import views as training_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # The service worker must be served from the site root, otherwise its
    # scope is limited to /static/ and it cannot control the app's pages.
    path("sw.js", training_views.service_worker, name="service_worker"),
    path("manifest.json", training_views.manifest, name="manifest"),
    path("", include("training.urls")),
]
