from django.urls import path

from . import views

urlpatterns = [
    path("shops/", views.ShopListCreateView.as_view(), name="shop-list"),
    path("shops/<uuid:shop_id>/", views.ShopDetailView.as_view(), name="shop-detail"),
    path("shops/<uuid:shop_id>/members/", views.ShopMemberCreateView.as_view(), name="shop-members"),
]
