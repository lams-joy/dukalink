from django.urls import path

from . import views

S = "shops/<uuid:shop_id>/orders/"
W = "wholesalers/<uuid:wholesaler_id>/orders/"

urlpatterns = [
    # the ordering shop
    path(S, views.ShopOrderListCreateView.as_view(), name="shop-orders"),
    path(f"{S}<uuid:order_id>/", views.ShopOrderDetailView.as_view(), name="shop-order"),
    path(
        f"{S}<uuid:order_id>/cancel/", views.ShopOrderCancelView.as_view(), name="shop-order-cancel"
    ),
    path(
        f"{S}<uuid:order_id>/receive/",
        views.ShopOrderReceiveView.as_view(),
        name="shop-order-receive",
    ),
    # the supplying wholesaler
    path(W, views.WholesalerOrderListView.as_view(), name="wholesaler-orders"),
    path(
        f"{W}<uuid:order_id>/", views.WholesalerOrderDetailView.as_view(), name="wholesaler-order"
    ),
    path(
        f"{W}<uuid:order_id>/confirm/",
        views.WholesalerOrderConfirmView.as_view(),
        name="wholesaler-order-confirm",
    ),
    path(
        f"{W}<uuid:order_id>/reject/",
        views.WholesalerOrderRejectView.as_view(),
        name="wholesaler-order-reject",
    ),
    path(
        f"{W}<uuid:order_id>/dispatch/",
        views.WholesalerOrderDispatchView.as_view(),
        name="wholesaler-order-dispatch",
    ),
    path(
        f"{W}<uuid:order_id>/cancel/",
        views.WholesalerOrderCancelView.as_view(),
        name="wholesaler-order-cancel",
    ),
]
