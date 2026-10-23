from django.urls import path

from . import views

S = "shops/<uuid:shop_id>/group-orders/"
W = "wholesalers/<uuid:wholesaler_id>/group-orders/"

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
    path(f"{S}<uuid:group_id>/close/", views.GroupCloseView.as_view(), name="shop-group-close"),
    path(
        f"{S}<uuid:group_id>/cost-breakdown/",
        views.GroupCostBreakdownView.as_view(),
        name="shop-group-costs",
    ),
    # the supplying wholesaler
    path(W, views.WholesalerGroupListView.as_view(), name="wholesaler-groups"),
    path(f"{W}<uuid:group_id>/", views.WholesalerGroupDetailView.as_view(), name="wholesaler-group"),
    path(
        f"{W}<uuid:group_id>/cost-breakdown/",
        views.WholesalerGroupCostBreakdownView.as_view(),
        name="wholesaler-group-costs",
    ),
    path(
        f"{W}<uuid:group_id>/confirm/",
        views.WholesalerGroupConfirmView.as_view(),
        name="wholesaler-group-confirm",
    ),
    path(
        f"{W}<uuid:group_id>/decline/",
        views.WholesalerGroupDeclineView.as_view(),
        name="wholesaler-group-decline",
    ),
]
