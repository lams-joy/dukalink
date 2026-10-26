from django.urls import path

from . import admin_views, views

urlpatterns = [
    path("catalog/products/", views.ProductListView.as_view(), name="catalog-products"),
    path("admin/catalog/products/", admin_views.AdminProductListCreateView.as_view(), name="admin-catalog-products"),
    path("admin/catalog/products/<uuid:product_id>/", admin_views.AdminProductDetailView.as_view(), name="admin-catalog-product"),
    path("admin/catalog/products/<uuid:product_id>/units/", admin_views.AdminUnitCreateView.as_view(), name="admin-catalog-units"),
    path("admin/catalog/products/<uuid:product_id>/units/<uuid:unit_id>/", admin_views.AdminUnitDetailView.as_view(), name="admin-catalog-unit"),
]
