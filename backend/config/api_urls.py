from django.urls import include, path

from apps.common.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.shops.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.sync.urls")),
]
