from django.urls import path

from . import views

urlpatterns = [
    path(
        "shops/<uuid:shop_id>/audit-events/",
        views.AuditEventListView.as_view(),
        name="audit-events",
    ),
]
