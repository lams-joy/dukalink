from django.urls import path

from .views import SyncView

urlpatterns = [
    path("shops/<uuid:shop_id>/sync/", SyncView.as_view(), name="shop-sync"),
]
