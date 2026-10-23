from django.urls import path

from . import views

S = "shops/<uuid:shop_id>/group-orders/"

urlpatterns = [
    path(S, views.GroupListCreateView.as_view(), name="shop-groups"),
    path(f"{S}<uuid:group_id>/", views.GroupDetailView.as_view(), name="shop-group"),
    path(f"{S}<uuid:group_id>/join/", views.GroupJoinView.as_view(), name="shop-group-join"),
    path(
        f"{S}<uuid:group_id>/my-commitment/",
        views.GroupMyCommitmentView.as_view(),
        name="shop-group-commitment",
    ),
    path(
        f"{S}<uuid:group_id>/withdraw/", views.GroupWithdrawView.as_view(), name="shop-group-withdraw"
    ),
    path(f"{S}<uuid:group_id>/cancel/", views.GroupCancelView.as_view(), name="shop-group-cancel"),
]
